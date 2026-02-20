"""
Facturation - Factures

Schemas et handlers pour la facturation :
- search_factures (READ)
- get_facture_by_id (READ)
- create_facture (WRITE)
- update_facture (WRITE)
- delete_facture (WRITE)

WORKFLOWS moved to tools/workflows.py:
- generate_facture_pdf (WORKFLOW)
- create_and_send_facture (WORKFLOW)
"""

import uuid
from typing import Dict, Any
from datetime import datetime
from fastapi import HTTPException
import structlog

from tools.base import (
    ToolSchema,
    register_tool,
    ToolCategory,
    call_supabase_rpc,
    call_database_worker,
    call_document_worker,
    call_storage_worker,
)
from middleware import request_id_ctx


logger = structlog.get_logger()


# ============================================================================
# SCHEMAS
# ============================================================================

SEARCH_FACTURES_SCHEMA = ToolSchema(
    name="search_factures",
    description="Recherche factures par entreprise, periode ou statut de paiement. Retourne numero, montant, statut, entreprise.",
    input_schema={
        "type": "object",
        "properties": {
            "entreprise_id": {
                "type": "string",
                "description": "UUID de l'entreprise (optionnel)"
            },
            "payment_status": {
                "type": "string",
                "description": "Statut de paiement (paid, unpaid, pending)",
                "enum": ["paid", "unpaid", "pending"]
            },
            "start_date": {
                "type": "string",
                "description": "Date de debut (format ISO 8601: YYYY-MM-DD)"
            },
            "end_date": {
                "type": "string",
                "description": "Date de fin (format ISO 8601: YYYY-MM-DD)"
            },
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de resultats (defaut: 50)",
                "default": 50
            }
        },
        "required": []
    },
    category="read"
)

GET_FACTURE_BY_ID_SCHEMA = ToolSchema(
    name="get_facture_by_id",
    description="Recupere les details complets d'une facture par son ID (numero, montant, entreprise, qualification, statut paiement, PDF URL).",
    input_schema={
        "type": "object",
        "properties": {
            "facture_id": {
                "type": "string",
                "description": "UUID de la facture"
            }
        },
        "required": ["facture_id"]
    },
    category="read"
)

CREATE_FACTURE_SCHEMA = ToolSchema(
    name="create_facture",
    description="Cree une nouvelle facture pour une qualification. Genere automatiquement le numero de facture. Valide qualification_id et montant.",
    input_schema={
        "type": "object",
        "properties": {
            "qualification_id": {
                "type": "string",
                "description": "UUID de la qualification (requis)"
            },
            "montant": {
                "type": "number",
                "description": "Montant de la facture en euros (requis)"
            },
            "description": {
                "type": "string",
                "description": "Description des services factures"
            },
            "date_emission": {
                "type": "string",
                "description": "Date d'emission (format ISO 8601: YYYY-MM-DD, defaut: aujourd'hui)"
            },
            "date_echeance": {
                "type": "string",
                "description": "Date d'echeance (format ISO 8601: YYYY-MM-DD)"
            }
        },
        "required": ["qualification_id", "montant"]
    },
    category="write"
)

UPDATE_FACTURE_SCHEMA = ToolSchema(
    name="update_facture",
    description="Met a jour une facture existante (montant, description, dates). Ne modifie PAS le statut de paiement (utiliser mark_facture_paid).",
    input_schema={
        "type": "object",
        "properties": {
            "facture_id": {
                "type": "string",
                "description": "UUID de la facture (requis)"
            },
            "montant": {
                "type": "number",
                "description": "Nouveau montant en euros"
            },
            "description": {
                "type": "string",
                "description": "Nouvelle description"
            },
            "date_echeance": {
                "type": "string",
                "description": "Nouvelle date d'echeance (format ISO 8601: YYYY-MM-DD)"
            }
        },
        "required": ["facture_id"]
    },
    category="write"
)

DELETE_FACTURE_SCHEMA = ToolSchema(
    name="delete_facture",
    description="Supprime une facture (soft delete). Ne supprime PAS definitivement, marque comme deleted=true. Requiert confirmation.",
    input_schema={
        "type": "object",
        "properties": {
            "facture_id": {
                "type": "string",
                "description": "UUID de la facture (requis)"
            }
        },
        "required": ["facture_id"]
    },
    category="write"
)


# ============================================================================
# READ HANDLERS
# ============================================================================

@register_tool(
    name="search_factures",
    category=ToolCategory.READ,
    description_short="Recherche factures par criteres"
)
async def search_factures_handler(params: Dict[str, Any]):
    """Search invoices by company, date range, payment status"""
    return await call_supabase_rpc("search_factures", {
        "p_entreprise_id": params.get("entreprise_id"),
        "p_payment_status": params.get("payment_status"),
        "p_start_date": params.get("start_date"),
        "p_end_date": params.get("end_date"),
        "p_limit": params.get("limit", 50)
    })


@register_tool(
    name="get_facture_by_id",
    category=ToolCategory.READ,
    description_short="Recupere details complets d'une facture"
)
async def get_facture_by_id_handler(params: Dict[str, Any]):
    """Get invoice details by ID"""
    return await call_supabase_rpc("get_facture_by_id", {
        "p_id": params["facture_id"]
    })


# ============================================================================
# WRITE HANDLERS
# ============================================================================

@register_tool(
    name="create_facture",
    category=ToolCategory.WRITE,
    description_short="Cree une nouvelle facture"
)
async def create_facture_handler(params: Dict[str, Any]):
    """Create a new invoice"""
    logger = structlog.get_logger()

    data = await call_database_worker(
        endpoint="/facture/create",
        payload={
            "qualification_id": params["qualification_id"],
            "montant_ht": params["montant"],   # le worker attend "montant_ht"
            "description": params.get("description"),
            "date_echeance": params.get("date_echeance")
        },
        method="POST",
        require_validation=False
    )

    if data.get("id") is None:
        logger.error("database_worker_validation_failed", endpoint="/facture/create", response=data)
        raise HTTPException(status_code=422, detail="Validation failed: response missing 'id'")

    return {**data, "validated": True}


@register_tool(
    name="update_facture",
    category=ToolCategory.WRITE,
    description_short="Met a jour une facture"
)
async def update_facture_handler(params: Dict[str, Any]):
    """Update an existing invoice"""
    logger = structlog.get_logger()
    facture_id = params["facture_id"]

    data = await call_database_worker(
        endpoint=f"/facture/{facture_id}",
        payload={
            "montant": params.get("montant"),
            "description": params.get("description"),
            "date_echeance": params.get("date_echeance")
        },
        method="PUT",
        require_validation=False
    )

    if str(data.get("id", "")) != facture_id:
        logger.error("database_worker_validation_failed", endpoint=f"/facture/{facture_id}", response=data)
        raise HTTPException(status_code=422, detail=f"Validation failed: response id '{data.get('id')}' != '{facture_id}'")

    return {**data, "validated": True}


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


# ============================================================================
# SCHEMA REGISTRY
# ============================================================================

FACTURE_SCHEMAS = {
    "search_factures": SEARCH_FACTURES_SCHEMA,
    "get_facture_by_id": GET_FACTURE_BY_ID_SCHEMA,
    "create_facture": CREATE_FACTURE_SCHEMA,
    "update_facture": UPDATE_FACTURE_SCHEMA,
    "delete_facture": DELETE_FACTURE_SCHEMA,
    # Workflows moved to tools/workflows.py
}
