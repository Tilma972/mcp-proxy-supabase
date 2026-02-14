"""
Handlers for WRITE tools (database-worker calls)

All handlers call the database-worker service to modify data.
CRITICAL: All write operations enforce validation via validated flag.
"""

from typing import Dict, Any, Optional
from fastapi import HTTPException
import httpx
import structlog

from config import settings
from tools_registry import register_tool, ToolCategory
from utils.http_client import get_shared_client
from utils.retry import retry_with_backoff
from middleware import request_id_ctx

logger = structlog.get_logger()


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
# ENTREPRISE WRITE HANDLERS
# ============================================================================

@register_tool(
    name="upsert_entreprise",
    category=ToolCategory.WRITE,
    description_short="Crée ou met à jour une entreprise"
)
async def upsert_entreprise_handler(params: Dict[str, Any]):
    """Create or update a company"""
    return await call_database_worker(
        endpoint="/entreprise/upsert",
        payload={
            "nom": params["nom"],
            "email": params.get("email"),
            "telephone": params.get("telephone"),
            "adresse": params.get("adresse"),
            "notes": params.get("notes")
        },
        method="POST",
        require_validation=True
    )


# ============================================================================
# QUALIFICATION WRITE HANDLERS
# ============================================================================

@register_tool(
    name="upsert_qualification",
    category=ToolCategory.WRITE,
    description_short="Crée ou met à jour une qualification"
)
async def upsert_qualification_handler(params: Dict[str, Any]):
    """Create or update a qualification"""
    return await call_database_worker(
        endpoint="/qualification/upsert",
        payload={
            "entreprise_id": params["entreprise_id"],
            "statut": params["statut"],
            "montant_estime": params.get("montant_estime"),
            "description": params.get("description"),
            "date_prevue": params.get("date_prevue")
        },
        method="POST",
        require_validation=True
    )


# ============================================================================
# FACTURE WRITE HANDLERS
# ============================================================================

@register_tool(
    name="create_facture",
    category=ToolCategory.WRITE,
    description_short="Crée une nouvelle facture"
)
async def create_facture_handler(params: Dict[str, Any]):
    """Create a new invoice"""
    return await call_database_worker(
        endpoint="/facture/create",
        payload={
            "qualification_id": params["qualification_id"],
            "montant": params["montant"],
            "description": params.get("description"),
            "date_emission": params.get("date_emission"),
            "date_echeance": params.get("date_echeance")
        },
        method="POST",
        require_validation=True
    )


@register_tool(
    name="update_facture",
    category=ToolCategory.WRITE,
    description_short="Met à jour une facture"
)
async def update_facture_handler(params: Dict[str, Any]):
    """Update an existing invoice"""
    facture_id = params["facture_id"]

    return await call_database_worker(
        endpoint=f"/facture/{facture_id}",
        payload={
            "montant": params.get("montant"),
            "description": params.get("description"),
            "date_echeance": params.get("date_echeance")
        },
        method="PUT",
        require_validation=True
    )


@register_tool(
    name="mark_facture_paid",
    category=ToolCategory.WRITE,
    description_short="Marque une facture comme payée"
)
async def mark_facture_paid_handler(params: Dict[str, Any]):
    """Mark an invoice as paid"""
    facture_id = params["facture_id"]

    return await call_database_worker(
        endpoint=f"/facture/{facture_id}",
        payload={
            "payment_status": "paid",
            "payment_date": params.get("payment_date"),
            "payment_method": params.get("payment_method")
        },
        method="PUT",
        require_validation=True
    )


@register_tool(
    name="delete_facture",
    category=ToolCategory.WRITE,
    description_short="Supprime une facture (soft delete)"
)
async def delete_facture_handler(params: Dict[str, Any]):
    """Delete an invoice (soft delete)"""
    facture_id = params["facture_id"]

    return await call_database_worker(
        endpoint=f"/facture/{facture_id}",
        payload={},
        method="DELETE",
        require_validation=False  # Soft delete doesn't need validation
    )
