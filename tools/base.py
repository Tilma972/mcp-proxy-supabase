"""
Shared base classes and worker call helpers for FlowChat MCP tools.

This module centralizes:
- ToolSchema: base class for MCP tool schema definitions
- Worker call helpers: call_supabase_rpc, call_database_worker,
  call_document_worker, call_storage_worker, call_email_worker
- Re-exports: register_tool, ToolCategory from tools_registry
"""

from typing import Dict, Any, Optional
from fastapi import HTTPException
import structlog

from config import settings
from tools_registry import register_tool, ToolCategory  # noqa: F401 (re-export)
from utils.http_client import get_shared_client
from utils.retry import retry_with_backoff
from middleware import request_id_ctx


logger = structlog.get_logger()


# ============================================================================
# TOOL SCHEMA BASE CLASS
# ============================================================================

class ToolSchema:
    """Base class for tool schemas (MCP format)"""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        category: str = "read"
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.category = category

    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP tool format"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema
        }


# ============================================================================
# SUPABASE RPC HELPER
# ============================================================================

@retry_with_backoff(max_attempts=3, base_delay=1.0)
async def call_supabase_rpc(function_name: str, params: dict) -> Any:
    """
    Call a Supabase RPC function

    Args:
        function_name: Name of the RPC function
        params: Function parameters

    Returns:
        RPC function result

    Raises:
        httpx.HTTPStatusError: If request fails
    """
    client = await get_shared_client()

    url = f"{settings.supabase_url}/rest/v1/rpc/{function_name}"

    headers = {
        "Authorization": f"Bearer {settings.supabase_api_key}",
        "apikey": settings.supabase_api_key,
        "Content-Type": "application/json",
        "X-Request-ID": request_id_ctx.get()
    }

    logger.debug(
        "supabase_rpc_call",
        function=function_name,
        params_keys=list(params.keys())
    )

    resp = await client.post(url, headers=headers, json=params, timeout=30.0)
    resp.raise_for_status()

    return resp.json()


# ============================================================================
# DATABASE WORKER HELPER
# ============================================================================

@retry_with_backoff(max_attempts=3, base_delay=1.0)
async def call_database_worker(
    endpoint: str,
    payload: dict,
    method: str = "POST",
    require_validation: bool = True
) -> dict:
    """
    Call the database-worker service

    Args:
        endpoint: API endpoint (e.g., "/entreprise/upsert")
        payload: Request payload
        method: HTTP method (POST, PUT, DELETE)
        require_validation: If True, enforce validation check

    Returns:
        Worker response

    Raises:
        HTTPException: If validation fails or request fails
        RuntimeError: If DATABASE_WORKER_URL not configured
    """
    if not settings.database_worker_url:
        logger.error("database_worker_url_not_configured")
        raise RuntimeError("DATABASE_WORKER_URL not configured")

    client = await get_shared_client()

    url = f"{settings.database_worker_url.rstrip('/')}{endpoint}"

    headers = {
        "Content-Type": "application/json",
        "X-FlowChat-Worker-Auth": settings.worker_auth_key or "",
        "X-Request-ID": request_id_ctx.get()
    }

    logger.debug(
        "database_worker_call",
        endpoint=endpoint,
        method=method,
        payload_keys=list(payload.keys())
    )

    # Make request based on method
    if method == "POST":
        resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
    elif method == "PUT":
        resp = await client.put(url, headers=headers, json=payload, timeout=30.0)
    elif method == "DELETE":
        resp = await client.delete(url, headers=headers, json=payload, timeout=30.0)
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")

    resp.raise_for_status()
    data = resp.json()

    # CRITICAL: Enforce validation check
    if require_validation and not data.get("validated", False):
        logger.error(
            "database_worker_validation_failed",
            endpoint=endpoint,
            response=data,
            discrepancies=data.get("discrepancies")
        )
        raise HTTPException(
            status_code=422,
            detail=f"Validation failed: {data.get('discrepancies', 'Unknown error')}"
        )

    logger.info(
        "database_worker_success",
        endpoint=endpoint,
        validated=data.get("validated", False)
    )

    return data


# ============================================================================
# DOCUMENT WORKER HELPER
# ============================================================================

@retry_with_backoff(max_attempts=3, base_delay=1.0)
async def call_document_worker(endpoint: str, payload: dict) -> dict:
    """Call the document-worker service (PDF generation)"""
    if not settings.document_worker_url:
        raise RuntimeError("DOCUMENT_WORKER_URL not configured")

    client = await get_shared_client()
    url = f"{settings.document_worker_url.rstrip('/')}{endpoint}"

    headers = {
        "Content-Type": "application/json",
        "X-FlowChat-Worker-Auth": settings.worker_auth_key or "",
        "X-Request-ID": request_id_ctx.get()
    }

    logger.debug("document_worker_call", endpoint=endpoint)

    resp = await client.post(url, headers=headers, json=payload, timeout=60.0)
    resp.raise_for_status()

    return resp.json()


# ============================================================================
# STORAGE WORKER HELPER
# ============================================================================

@retry_with_backoff(max_attempts=3, base_delay=1.0)
async def call_storage_worker(endpoint: str, payload: dict, use_form_data: bool = False) -> dict:
    """Call the storage-worker service (file upload)"""
    if not settings.storage_worker_url:
        raise RuntimeError("STORAGE_WORKER_URL not configured")

    client = await get_shared_client()
    url = f"{settings.storage_worker_url.rstrip('/')}{endpoint}"

    headers = {
        "X-FlowChat-Worker-Auth": settings.worker_auth_key or "",
        "X-Request-ID": request_id_ctx.get()
    }

    if not use_form_data:
        headers["Content-Type"] = "application/json"

    logger.debug("storage_worker_call", endpoint=endpoint)

    if use_form_data:
        resp = await client.post(url, headers=headers, data=payload, timeout=30.0)
    else:
        resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
    resp.raise_for_status()

    return resp.json()


# ============================================================================
# EMAIL WORKER HELPER
# ============================================================================

@retry_with_backoff(max_attempts=3, base_delay=1.0)
async def call_email_worker(endpoint: str, payload: dict) -> dict:
    """Call the email-worker service (email sending)"""
    if not settings.email_worker_url:
        raise RuntimeError("EMAIL_WORKER_URL not configured")

    client = await get_shared_client()
    url = f"{settings.email_worker_url.rstrip('/')}{endpoint}"

    headers = {
        "Content-Type": "application/json",
        "X-FlowChat-Worker-Auth": settings.worker_auth_key or "",
        "X-Request-ID": request_id_ctx.get()
    }

    logger.debug("email_worker_call", endpoint=endpoint)

    resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
    resp.raise_for_status()

    return resp.json()
