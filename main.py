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
from utils.validation import validate_params

# Import tools module to register all domain handlers and load schemas
from tools import ALL_TOOL_SCHEMAS, TOOL_DOMAINS

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


@app.get("/health/workers")
async def health_workers():
    """
    Check worker availability and which tool categories are operational.

    Tests connectivity to each worker URL with a short timeout.
    No auth required (same as /health).

    USAGE RECOMMENDATIONS:
    - Call this ONCE at bot startup to identify available services
    - Do NOT call before each tool request (adds unnecessary latency)
    - The proxy now returns user-friendly 503 errors when workers are down
    - Claude can interpret these 503 messages and inform the user directly

    Example bot startup flow:
        1. GET /health/workers → Check what's available
        2. Store available categories in bot state
        3. On tool errors, let proxy error messages guide Claude's response
    """
    from utils.http_client import get_shared_client

    worker_configs = {
        "database_worker": {
            "url": settings.database_worker_url,
            "required_for": ["write"],
        },
        "document_worker": {
            "url": settings.document_worker_url,
            "required_for": ["workflow"],
        },
        "storage_worker": {
            "url": settings.storage_worker_url,
            "required_for": ["workflow"],
        },
        "email_worker": {
            "url": settings.email_worker_url,
            "required_for": ["workflow"],
        },
    }

    results = {}
    try:
        client = await get_shared_client()
    except RuntimeError:
        # Client not initialized yet
        for name in worker_configs:
            results[name] = {"status": "unknown", "error": "HTTP client not initialized"}
        return {
            "workers": results,
            "categories": {"read": True, "write": False, "workflow": False},
        }

    for name, config in worker_configs.items():
        if not config["url"]:
            results[name] = {"status": "not_configured", "url": None}
            continue

        health_url = f"{config['url'].rstrip('/')}/health"
        try:
            resp = await client.get(health_url, timeout=5.0)
            results[name] = {
                "status": "healthy" if resp.status_code == 200 else "unhealthy",
                "status_code": resp.status_code,
                "url": config["url"],
            }
        except Exception as e:
            results[name] = {
                "status": "unreachable",
                "url": config["url"],
                "error": str(e),
            }

    # Determine which categories are operational
    categories = {
        "read": True,  # READ tools only need Supabase (always available)
        "write": results.get("database_worker", {}).get("status") == "healthy",
        "workflow": all(
            results.get(w, {}).get("status") == "healthy"
            for w in ["document_worker", "storage_worker", "email_worker"]
        ) and results.get("database_worker", {}).get("status") == "healthy",
    }

    return {
        "workers": results,
        "categories": categories,
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


@app.get("/mcp/tools/domains")
@limiter.limit(settings.rate_limit)
async def mcp_list_domains(
    request: Request,
    authenticated: bool = Depends(verify_flowchat_mcp_key)
):
    """
    List tools organized by business domain

    Returns:
        Domain map with description, tool count, and tool names per domain
    """
    logger.info("mcp_tools_domains_request", client_ip=request.client.host)

    domains = {}
    for domain_name, domain_info in TOOL_DOMAINS.items():
        tool_names = domain_info["tools"]
        # Enrich with category from registry
        tools_with_category = []
        for tool_name in tool_names:
            tool_meta = get_tool_info(tool_name)
            tools_with_category.append({
                "name": tool_name,
                "category": tool_meta["category"] if tool_meta else "unknown",
                "description": tool_meta["description"] if tool_meta else "",
            })

        domains[domain_name] = {
            "description": domain_info["description"],
            "tool_count": len(tool_names),
            "tools": tools_with_category,
        }

    return {
        "domains": domains,
        "total_domains": len(domains),
        "total_tools": sum(d["tool_count"] for d in domains.values()),
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

    schema = ALL_TOOL_SCHEMAS.get(tool_name)

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

    # Validate params against tool schema before dispatch
    schema = ALL_TOOL_SCHEMAS.get(tool_name)
    if schema:
        validation_errors = validate_params(params, schema.input_schema)
        if validation_errors:
            logger.warning(
                "mcp_tool_call_validation_failed",
                tool_name=tool_name,
                errors=validation_errors,
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Parameter validation failed",
                    "errors": validation_errors,
                    "tool_name": tool_name,
                }
            )

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
# HITL (Human In The Loop) WEBHOOK
# ============================================================================

@app.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = None
):
    """
    Telegram webhook endpoint for HITL validation responses

    Receives callback queries from Telegram inline buttons:
    - /approve - Approve pending request
    - /reject - Reject pending request
    - /modify - Modify parameters (requires follow-up message)

    Security: Verifies secret token set during webhook configuration

    Returns:
        Success/error status for Telegram webhook
    """
    from utils.hitl import process_validation_response
    from telegram import Update, Bot
    import json

    # Verify webhook secret token
    if not settings.telegram_webhook_secret:
        logger.warning("telegram_webhook_no_secret_configured")
        # Continue processing even without secret for development
    elif x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        logger.warning(
            "telegram_webhook_invalid_secret",
            provided=x_telegram_bot_api_secret_token[:10] + "..." if x_telegram_bot_api_secret_token else None
        )
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    try:
        # Parse Telegram update
        body = await request.json()
        update = Update.de_json(body, Bot(settings.telegram_token))

        # Handle callback query (inline button click)
        if update.callback_query:
            callback_data = update.callback_query.data
            user_id = str(update.callback_query.from_user.id)
            username = update.callback_query.from_user.username or "unknown"

            logger.info(
                "telegram_webhook_callback",
                callback_data=callback_data,
                user_id=user_id,
                username=username
            )

            # Parse callback data: "hitl_action:request_id"
            if callback_data.startswith("hitl_"):
                parts = callback_data.split(":", 1)
                if len(parts) != 2:
                    await update.callback_query.answer("Invalid callback data")
                    return {"ok": True}

                action_full = parts[0]  # "hitl_approve", "hitl_reject", "hitl_modify"
                request_id = parts[1]
                action = action_full.replace("hitl_", "")  # "approve", "reject", "modify"

                # Handle modify action (requires follow-up input)
                if action == "modify":
                    await update.callback_query.answer(
                        "⚠️ Modification manuelle non implémentée. Utilisez Approuver ou Rejeter.",
                        show_alert=True
                    )
                    return {"ok": True}

                # Process validation
                try:
                    result = await process_validation_response(
                        request_id=request_id,
                        action=action,
                        validator_id=f"{user_id}@{username}"
                    )

                    # Send confirmation
                    status_emoji = "✅" if action == "approve" else "❌"
                    confirmation_text = (
                        f"{status_emoji} **Validation {action.upper()}**\n\n"
                        f"Request ID: `{request_id}`\n"
                        f"Status: {result['status']}\n"
                    )

                    if result.get("success") and result.get("workflow_result"):
                        workflow_result = result["workflow_result"]
                        confirmation_text += f"\n**Résultat du workflow:**\n```json\n{json.dumps(workflow_result, indent=2, ensure_ascii=False)[:500]}```"

                    # Update message
                    await update.callback_query.edit_message_text(
                        text=confirmation_text,
                        parse_mode="Markdown"
                    )

                    await update.callback_query.answer(f"{status_emoji} Validation {action} effectuée")

                    logger.info(
                        "telegram_webhook_processed",
                        request_id=request_id,
                        action=action,
                        success=result.get("success")
                    )

                except HTTPException as e:
                    await update.callback_query.answer(f"❌ Erreur: {e.detail}", show_alert=True)
                    logger.error("telegram_webhook_processing_error", error=e.detail)

                except Exception as e:
                    await update.callback_query.answer(f"❌ Erreur interne: {str(e)}", show_alert=True)
                    logger.error("telegram_webhook_unexpected_error", error=str(e))

            else:
                await update.callback_query.answer("Action inconnue")

        return {"ok": True}

    except json.JSONDecodeError:
        logger.error("telegram_webhook_invalid_json")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    except Exception as e:
        logger.error("telegram_webhook_error", error=str(e))
        return {"ok": False, "error": str(e)}

# ============================================================================
# LIFECYCLE
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup"""
    # Initialize shared HTTP client
    await init_shared_client()

    # Configure Telegram webhook for HITL (if enabled)
    if settings.hitl_enabled and settings.telegram_token and settings.telegram_webhook_url:
        try:
            from telegram import Bot
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from utils.hitl import timeout_expired_requests

            bot = Bot(token=settings.telegram_token)

            # Set webhook
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url != settings.telegram_webhook_url:
                await bot.set_webhook(
                    url=settings.telegram_webhook_url,
                    secret_token=settings.telegram_webhook_secret,
                    drop_pending_updates=True  # Clear old updates
                )
                logger.info(
                    "telegram_webhook_configured",
                    url=settings.telegram_webhook_url
                )
            else:
                logger.info("telegram_webhook_already_configured", url=webhook_info.url)

            # Schedule timeout cleanup job (every 5 minutes)
            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                timeout_expired_requests,
                "interval",
                minutes=5,
                id="hitl_timeout_cleanup"
            )
            scheduler.start()

            logger.info("hitl_system_initialized", scheduler="active")

        except Exception as e:
            logger.error("telegram_webhook_setup_failed", error=str(e))
            # Don't fail startup if webhook setup fails
    elif settings.hitl_enabled:
        logger.warning(
            "hitl_enabled_but_not_configured",
            missing="telegram_token or telegram_webhook_url"
        )

    logger.info(
        "proxy_starting",
        environment=settings.environment,
        project_ref=settings.supabase_project_ref[:8] + "...",
        rate_limit=settings.rate_limit,
        auth_enabled=True,
        hitl_enabled=settings.hitl_enabled
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources on shutdown"""
    # Close shared HTTP client
    await close_shared_client()

    logger.info("proxy_shutdown")


# ============================================================================
# WEBHOOK — Nouveau Client (Supabase DB Hook → envoi plaquette automatique)
# ============================================================================

@app.post("/webhook/new-client")
async def webhook_new_client(request: Request):
    """
    Reçoit un webhook Supabase Database Hook sur INSERT dans la table entreprise.
    Si l'entreprise a un email → envoie automatiquement la plaquette 2027.
    Si pas d'email → notifie Telegram pour traitement manuel.

    Configuration Supabase :
      Table: entreprise | Event: INSERT
      URL: https://<domain>/webhook/new-client
      Header: x-webhook-secret: <telegram_webhook_secret>
    """
    # Vérification du secret webhook
    webhook_secret = settings.telegram_webhook_secret
    if webhook_secret:
        sig = request.headers.get("x-webhook-secret", "")
        if sig != webhook_secret:
            logger.warning("webhook_new_client_unauthorized")
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Supabase DB Hook: {"type": "INSERT", "record": {...}}
    record        = body.get("record") or body
    entreprise_id = record.get("id")
    email         = record.get("email")
    nom           = record.get("nom", "Nouveau client")

    logger.info("webhook_new_client_received", entreprise_id=entreprise_id, nom=nom, has_email=bool(email))

    if not entreprise_id:
        return {"status": "ignored", "reason": "no entreprise_id in payload"}

    async def _notify_telegram(text: str):
        if not settings.telegram_token or not settings.telegram_admin_id:
            return
        from telegram import Bot
        bot = Bot(token=settings.telegram_token)
        try:
            await bot.send_message(chat_id=settings.telegram_admin_id, text=text, parse_mode="Markdown")
        except Exception as tg_err:
            logger.warning("webhook_telegram_notify_failed", error=str(tg_err))
        finally:
            await bot.close()

    if not email:
        await _notify_telegram(
            f"⚠️ *Nouveau client sans email*\n\n"
            f"🏢 *{nom}*\n🆔 `{entreprise_id}`\n\n"
            f"Plaquette non envoyée. Complétez l'email puis utilisez `send_plaquette_to_entreprise`."
        )
        return {"status": "skipped", "reason": "no_email", "entreprise_id": entreprise_id}

    # Fire-and-forget : répond 200 immédiatement
    import asyncio

    async def _send():
        try:
            from tools.workflows import send_plaquette_to_entreprise_handler
            result = await asyncio.wait_for(
                send_plaquette_to_entreprise_handler({"entreprise_id": entreprise_id}),
                timeout=30
            )
            await _notify_telegram(
                f"📨 *Plaquette 2027 envoyée*\n\n🏢 *{nom}*\n📧 {email}\n🆔 `{entreprise_id}`"
            )
            logger.info("webhook_plaquette_sent", entreprise_id=entreprise_id, email=email)
        except asyncio.TimeoutError:
            logger.error("webhook_plaquette_timeout", entreprise_id=entreprise_id)
            await _notify_telegram(
                f"⏱ *Timeout envoi plaquette*\n\n🏢 *{nom}* ({email})\n🆔 `{entreprise_id}`\n\n"
                f"L'envoi a dépassé 30s. Utilise `send_plaquette_to_entreprise` ID `{entreprise_id}`."
            )
        except Exception as e:
            logger.error("webhook_plaquette_failed", entreprise_id=entreprise_id, error=str(e))
            await _notify_telegram(
                f"❌ *Erreur envoi plaquette*\n\n🏢 *{nom}* ({email})\n"
                f"`{str(e)[:200]}`\n\nUtilise `send_plaquette_to_entreprise` ID `{entreprise_id}`."
            )

    asyncio.create_task(_send())
    return {"status": "accepted", "entreprise_id": entreprise_id, "email": email}


@app.post("/internal/send-plaquette")
async def internal_send_plaquette(request: Request):
    """
    Endpoint interne appelé par le FlowChat FSM (/plaquette command).
    Authentifié par X-FlowChat-Worker-Auth.
    Appel synchrone — retourne le résultat complet (pas fire-and-forget).

    Body: {
        "entreprise_id": "...",
        "prospecteur_nom":       (optionnel),
        "prospecteur_telephone": (optionnel),
        "prospecteur_email":     (optionnel),
        "message":               (optionnel)
    }
    """
    auth_key = request.headers.get("X-FlowChat-Worker-Auth", "")
    if settings.worker_auth_key and auth_key != settings.worker_auth_key:
        logger.warning("internal_send_plaquette_unauthorized")
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    entreprise_id = body.get("entreprise_id")
    if not entreprise_id:
        raise HTTPException(status_code=422, detail="entreprise_id required")

    logger.info("internal_send_plaquette_called", entreprise_id=entreprise_id)

    try:
        from tools.workflows import send_plaquette_to_entreprise_handler
        params = {
            "entreprise_id": entreprise_id,
            **{k: v for k, v in body.items() if k != "entreprise_id" and v is not None},
        }
        result = await send_plaquette_to_entreprise_handler(params)
        return {"status": "ok", **result}
    except Exception as e:
        logger.error("internal_send_plaquette_failed", entreprise_id=entreprise_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=settings.log_level.lower()
    )
