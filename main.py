"""
Supabase MCP Proxy - SSE Optimized with Custom Auth
Deployed on Coolify VPS for FlowChat MVP
"""

import os
import time
from typing import Optional

from fastapi import FastAPI, Request, Response, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic_settings import BaseSettings
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import httpx
import structlog
import uvicorn

# ============================================================================
# CONFIGURATION
# ============================================================================

class Settings(BaseSettings):
    """Application settings with validation"""
    supabase_project_ref: str
    supabase_pat: str
    
    # Auth
    x_proxy_key: str  # Secret key pour authentifier les clients
    
    # App
    environment: str = "production"
    log_level: str = "INFO"
    
    # CORS
    allowed_origins: str = "*"
    
    # Rate limiting
    rate_limit: str = "200/minute"  # Plus haut pour SSE
    
    class Config:
        env_file = ".env"
        case_sensitive = False

try:
    settings = Settings()
except Exception as e:
    print(f"❌ Configuration error: {e}")
    print("Required: SUPABASE_PROJECT_REF, SUPABASE_PAT, X_PROXY_KEY")
    exit(1)

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

# Rate Limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ============================================================================
# AUTH MIDDLEWARE
# ============================================================================

def verify_proxy_key(
    x_proxy_key: Optional[str] = Header(None),
    key: Optional[str] = None  # Permet de passer la clé via ?key=...
):
    """Verify X-Proxy-Key header or query parameter"""
    provided_key = x_proxy_key or key
    if provided_key != settings.x_proxy_key:
        logger.warning("auth_failed", provided_key=provided_key[:8] if provided_key else None)
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing Proxy Key"
        )
    return True

# ============================================================================
# ROUTES
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint (no auth required)"""
    return {
        "status": "ok",
        "environment": settings.environment,
        "version": "1.0.0"
    }

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
    
    # Build upstream request
    headers = {
        "Authorization": f"Bearer {settings.supabase_pat}",
        "Content-Type": "application/json",
        **{k: v for k, v in request.headers.items() 
           if k.lower() not in ["host", "authorization", "x-proxy-key"]}
    }
    
    supabase_url = f"https://mcp.supabase.com/mcp/{path}"
    
    # Inject project_ref if missing
    params = dict(request.query_params)
    if "project_ref" not in path and "project_ref" not in params:
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
        
        logger.info(
            "mcp_request_completed",
            path=path,
            method=method,
            status_code=resp.status_code,
            duration_ms=int(duration * 1000),
            client_ip=client_ip
        )
        
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers)
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
# STARTUP
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Log startup info"""
    logger.info(
        "proxy_starting",
        environment=settings.environment,
        project_ref=settings.supabase_project_ref[:8] + "...",
        rate_limit=settings.rate_limit,
        auth_enabled=True
    )

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=settings.log_level.lower()
    )
