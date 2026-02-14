"""
Authentication utilities for Supabase MCP Unified Proxy
"""

from typing import Optional
from fastapi import Header, HTTPException
import structlog

from config import settings

logger = structlog.get_logger()


def verify_proxy_key(
    x_proxy_key: Optional[str] = Header(None),
    key: Optional[str] = None  # Permet de passer la clé via ?key=...
):
    """
    Verify X-Proxy-Key header or query parameter for Supabase proxy access

    This is the original authentication for the Supabase MCP proxy endpoint.
    """
    provided_key = x_proxy_key or key
    if provided_key != settings.x_proxy_key:
        logger.warning("auth_failed", provided_key=provided_key[:8] if provided_key else None)
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing Proxy Key"
        )
    return True


def verify_flowchat_mcp_key(
    x_proxy_key: Optional[str] = Header(None)
):
    """
    Verify X-Proxy-Key header for FlowChat MCP tools access

    This authentication is used for the new FlowChat-specific MCP endpoints
    (/mcp/tools/list, /mcp/tools/call, etc.)
    """
    if not settings.flowchat_mcp_key:
        logger.error("flowchat_mcp_key_not_configured")
        raise HTTPException(
            status_code=500,
            detail="FlowChat MCP authentication not configured"
        )

    if x_proxy_key != settings.flowchat_mcp_key:
        logger.warning(
            "flowchat_auth_failed",
            provided_key=x_proxy_key[:8] if x_proxy_key else None
        )
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing FlowChat MCP Key"
        )
    return True
