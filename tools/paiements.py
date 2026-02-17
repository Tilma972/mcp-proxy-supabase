"""
Tresorerie - Paiements

Schemas et handlers pour la gestion des paiements :
- get_unpaid_factures (READ)
- get_revenue_stats (READ)
- mark_facture_paid (WRITE)
"""

from typing import Dict, Any

from tools.base import (
    ToolSchema,
    register_tool,
    ToolCategory,
    call_supabase_rpc,
    call_database_worker,
)


# ============================================================================
# SCHEMAS
# ============================================================================

GET_UNPAID_FACTURES_SCHEMA = ToolSchema(
    name="get_unpaid_factures",
    description="Recupere toutes les factures impayees. Utile pour relances et suivi de paiements.",
    input_schema={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de resultats (defaut: 100)",
                "default": 100
            }
        },
        "required": []
    },
    category="read"
)

GET_REVENUE_STATS_SCHEMA = ToolSchema(
    name="get_revenue_stats",
    description="Calcule statistiques de revenus pour une periode (CA total, nombre factures, montant moyen, taux paiement).",
    input_schema={
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "Date de debut (format ISO 8601: YYYY-MM-DD)"
            },
            "end_date": {
                "type": "string",
                "description": "Date de fin (format ISO 8601: YYYY-MM-DD)"
            }
        },
        "required": ["start_date", "end_date"]
    },
    category="read"
)

MARK_FACTURE_PAID_SCHEMA = ToolSchema(
    name="mark_facture_paid",
    description="Marque une facture comme payee. Met a jour payment_status='paid' et enregistre la date de paiement.",
    input_schema={
        "type": "object",
        "properties": {
            "facture_id": {
                "type": "string",
                "description": "UUID de la facture (requis)"
            },
            "payment_date": {
                "type": "string",
                "description": "Date de paiement (format ISO 8601: YYYY-MM-DD, defaut: aujourd'hui)"
            },
            "payment_method": {
                "type": "string",
                "description": "Methode de paiement (virement, cheque, carte, especes)"
            }
        },
        "required": ["facture_id"]
    },
    category="write"
)


# ============================================================================
# HANDLERS
# ============================================================================

@register_tool(
    name="get_unpaid_factures",
    category=ToolCategory.READ,
    description_short="Recupere factures impayees"
)
async def get_unpaid_factures_handler(params: Dict[str, Any]):
    """Get all unpaid invoices"""
    return await call_supabase_rpc("get_unpaid_factures", {
        "p_limit": params.get("limit", 100)
    })


@register_tool(
    name="get_revenue_stats",
    category=ToolCategory.READ,
    description_short="Calcule statistiques revenus pour periode"
)
async def get_revenue_stats_handler(params: Dict[str, Any]):
    """Get revenue statistics for a period"""
    return await call_supabase_rpc("get_revenue_stats", {
        "p_start_date": params["start_date"],
        "p_end_date": params["end_date"]
    })


@register_tool(
    name="mark_facture_paid",
    category=ToolCategory.WRITE,
    description_short="Marque une facture comme payee"
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


# ============================================================================
# SCHEMA REGISTRY
# ============================================================================

PAIEMENT_SCHEMAS = {
    "get_unpaid_factures": GET_UNPAID_FACTURES_SCHEMA,
    "get_revenue_stats": GET_REVENUE_STATS_SCHEMA,
    "mark_facture_paid": MARK_FACTURE_PAID_SCHEMA,
}
