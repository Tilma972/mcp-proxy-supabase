"""
Supabase MCP Unified Proxy - SSE Optimized with FlowChat Tools
Deployed on Coolify VPS for FlowChat MVP
"""

import time
from typing import Optional

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import httpx
import structlog
import uvicorn

# Import from new modules
from config import settings
from auth import verify_proxy_key, verify_flowchat_mcp_key
from middleware import RequestIDMiddleware
from utils.http_client import init_shared_client, close_shared_client
from tools_registry import dispatch_tool, list_tools, get_tool_info
from schemas.read_tools import READ_TOOL_SCHEMAS
from schemas.write_tools import WRITE_TOOL_SCHEMAS
from schemas.workflow_tools import WORKFLOW_TOOL_SCHEMAS

# Import handlers to register tools
import handlers.supabase_read
import handlers.database_write
import handlers.workflows

# ============================================================================
# LOGGING
# ============================================================================

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.processors.JSONRenderer() if settings.environment == "production" 
        else structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger()

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
}


def filter_response_headers(headers: httpx.Headers) -> dict:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}

# ============================================================================
# APP SETUP
# ============================================================================

app = FastAPI(
    title="Supabase MCP Proxy",
    version="1.0.0",
    description="Secure SSE-compatible proxy for Supabase MCP"
)

# CORS
origins = settings.allowed_origins.split(",") if settings.allowed_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID tracking
app.add_middleware(RequestIDMiddleware)

# Rate Limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ============================================================================
# AUTH
# ============================================================================
# Auth functions imported from auth.py module

# ============================================================================
# ROUTES
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint (no auth required)"""
    return {
        "status": "ok",
        "environment": settings.environment,
        "version": "2.0.0",
        "features": ["supabase_proxy", "flowchat_tools"]
    }


# ============================================================================
# FLOWCHAT MCP TOOL ROUTES
# ============================================================================

@app.get("/mcp/tools/list")
@limiter.limit(settings.rate_limit)
async def mcp_list_tools(
    request: Request,
    authenticated: bool = Depends(verify_flowchat_mcp_key)
):
    """
    List all available FlowChat MCP tools

    Returns:
        List of tools with name, category, and description
    """
    logger.info("mcp_tools_list_request", client_ip=request.client.host)

    tools = list_tools()

    logger.info("mcp_tools_list_response", tool_count=len(tools))

    return {
        "tools": tools,
        "total": len(tools)
    }


@app.get("/mcp/tools/{tool_name}/schema")
@limiter.limit(settings.rate_limit)
async def mcp_get_tool_schema(
    tool_name: str,
    request: Request,
    authenticated: bool = Depends(verify_flowchat_mcp_key)
):
    """
    Get the schema for a specific tool

    Args:
        tool_name: Name of the tool

    Returns:
        Tool schema in MCP format
    """
    logger.info("mcp_tool_schema_request", tool_name=tool_name, client_ip=request.client.host)

    # Check all schema registries
    all_schemas = {
        **READ_TOOL_SCHEMAS,
        **WRITE_TOOL_SCHEMAS,
        **WORKFLOW_TOOL_SCHEMAS
    }

    schema = all_schemas.get(tool_name)

    if not schema:
        logger.warning("mcp_tool_schema_not_found", tool_name=tool_name)
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    logger.info("mcp_tool_schema_response", tool_name=tool_name)

    return schema.to_dict()


@app.post("/mcp/tools/call")
@limiter.limit(settings.rate_limit)
async def mcp_call_tool(
    request: Request,
    authenticated: bool = Depends(verify_flowchat_mcp_key)
):
    """
    Execute a tool call

    Request body:
        {
            "tool_name": "search_entreprise_with_stats",
            "params": {"search_term": "ACME", "limit": 10}
        }

    Returns:
        Tool execution result
    """
    body = await request.json()
    tool_name = body.get("tool_name")
    params = body.get("params", {})

    logger.info(
        "mcp_tool_call_request",
        tool_name=tool_name,
        params_keys=list(params.keys()),
        client_ip=request.client.host
    )

    if not tool_name:
        raise HTTPException(status_code=400, detail="Missing 'tool_name' in request body")

    try:
        result = await dispatch_tool(tool_name, params)

        logger.info("mcp_tool_call_response", tool_name=tool_name)

        return {
            "success": True,
            "tool_name": tool_name,
            "result": result
        }

    except ValueError as e:
        logger.error("mcp_tool_call_not_found", tool_name=tool_name, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))

    except HTTPException:
        # Re-raise HTTPExceptions from handlers (e.g., validation errors)
        raise

    except Exception as e:
        logger.error(
            "mcp_tool_call_error",
            tool_name=tool_name,
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=500,
            detail=f"Tool execution failed: {str(e)}"
        )

@app.api_route("/mcp/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@limiter.limit(settings.rate_limit)
async def proxy_mcp(
    path: str, 
    request: Request,
    authenticated: bool = Depends(verify_proxy_key)
):
    """
    Proxy all MCP requests to Supabase
    
    Features:
    - SSE streaming support (no caching)
    - X-Proxy-Key authentication
    - Automatic project_ref injection
    - Request/response logging
    """
    start_time = time.time()
    client_ip = request.client.host
    method = request.method
    
    logger.info(
        "mcp_request_received",
        path=path,
        method=method,
        client_ip=client_ip,
        content_type=request.headers.get("content-type")
    )
    
    rest_prefixes = ("rest/", "auth/", "storage/", "functions/", "realtime/")
    is_rest = path.startswith(rest_prefixes)

    # Build upstream request
    if is_rest:
        if not settings.supabase_api_key:
            logger.warning("supabase_api_key_missing", path=path)
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Missing SUPABASE_API_KEY for REST requests",
                    "hint": "Set SUPABASE_API_KEY (anon or service role) and optionally SUPABASE_URL"
                }
            )
        base_url = settings.supabase_url or f"https://{settings.supabase_project_ref}.supabase.co"
        supabase_url = f"{base_url.rstrip('/')}/{path}"
        headers = {
            "Authorization": f"Bearer {settings.supabase_api_key}",
            "apikey": settings.supabase_api_key,
            "Content-Type": "application/json",
            **{k: v for k, v in request.headers.items() 
               if k.lower() not in ["host", "authorization", "x-proxy-key", "apikey"]}
        }
    else:
        supabase_url = f"{settings.supabase_mcp_base_url.rstrip('/')}/mcp/{path}"
        headers = {
            "Authorization": f"Bearer {settings.supabase_pat}",
            "Content-Type": "application/json",
            **{k: v for k, v in request.headers.items() 
               if k.lower() not in ["host", "authorization", "x-proxy-key"]}
        }
    
    # Inject project_ref if missing (MCP only)
    params = dict(request.query_params)
    if not is_rest and "project_ref" not in path and "project_ref" not in params:
        params["project_ref"] = settings.supabase_project_ref
    
    # Check if SSE request
    accept_header = request.headers.get("accept", "")
    is_sse = "text/event-stream" in accept_header
    
    try:
        content = await request.body()
        
        # SSE: Stream response
        if is_sse:
            logger.info("mcp_sse_stream_start", path=path, client_ip=client_ip)
            
            async def stream_sse():
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        method,
                        supabase_url,
                        headers=headers,
                        params=params,
                        content=content
                    ) as resp:
                        async for chunk in resp.aiter_bytes():
                            yield chunk
            
            return StreamingResponse(
                stream_sse(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"  # Nginx compatibility
                }
            )
        
        # Non-SSE: Regular request
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.request(
                method,
                supabase_url,
                headers=headers,
                params=params,
                content=content
            )
        
        duration = time.time() - start_time

        # 🆕 AJOUT : Log du contenu de la réponse pour debugging
        try:
            response_data = resp.json() if resp.content else None
            response_preview = str(response_data)[:500] if response_data else "empty"
            result_count = len(response_data) if isinstance(response_data, list) else 1
        except:
            response_preview = resp.content[:500].decode('utf-8', errors='ignore')
            result_count = "unknown"

        logger.info(
            "mcp_request_completed",
            path=path,
            method=method,
            status_code=resp.status_code,
            duration_ms=int(duration * 1000),
            client_ip=client_ip,
            result_count=result_count,              # 🆕 Nombre de résultats
            response_preview=response_preview       # 🆕 Aperçu de la réponse
        )
        
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=filter_response_headers(resp.headers)
        )
    
    except httpx.TimeoutException:
        logger.error("mcp_timeout", path=path, client_ip=client_ip)
        return JSONResponse(
            status_code=504,
            content={"error": "Supabase MCP timeout", "path": path}
        )
    
    except httpx.HTTPError as e:
        logger.error("mcp_http_error", path=path, error=str(e), client_ip=client_ip)
        return JSONResponse(
            status_code=502,
            content={"error": "Supabase MCP unreachable", "details": str(e)}
        )
    
    except Exception as e:
        logger.error("mcp_unexpected_error", path=path, error=str(e), client_ip=client_ip)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal proxy error"}
        )

# ============================================================================
# LIFECYCLE
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup"""
    # Initialize shared HTTP client
    await init_shared_client()

    logger.info(
        "proxy_starting",
        environment=settings.environment,
        project_ref=settings.supabase_project_ref[:8] + "...",
        rate_limit=settings.rate_limit,
        auth_enabled=True
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources on shutdown"""
    # Close shared HTTP client
    await close_shared_client()

    logger.info("proxy_shutdown")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=settings.log_level.lower()
    )
