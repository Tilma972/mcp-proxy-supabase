"""
Emails & notifications - Communications

Schemas et handlers pour les communications :
- list_recent_interactions (READ)

WORKFLOWS moved to tools/workflows.py:
- send_facture_email (WORKFLOW)
- generate_monthly_report (WORKFLOW)
"""

import asyncio
from typing import Dict, Any
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
    call_email_worker,
)


logger = structlog.get_logger()


# ============================================================================
# SCHEMAS
# ============================================================================

LIST_RECENT_INTERACTIONS_SCHEMA = ToolSchema(
    name="list_recent_interactions",
    description="Liste les interactions recentes (messages Telegram) pour une entreprise ou globalement. Utile pour contexte conversation.",
    input_schema={
        "type": "object",
        "properties": {
            "entreprise_id": {
                "type": "string",
                "description": "UUID de l'entreprise (optionnel, si absent retourne toutes interactions)"
            },
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de resultats (defaut: 20)",
                "default": 20
            }
        },
        "required": []
    },
    category="read"
)


# ============================================================================
# READ HANDLERS
# ============================================================================

@register_tool(
    name="list_recent_interactions",
    category=ToolCategory.READ,
    description_short="Liste interactions recentes"
)
async def list_recent_interactions_handler(params: Dict[str, Any]):
    """List recent interactions (Telegram messages)"""
    return await call_supabase_rpc("list_recent_interactions", {
        "p_entreprise_id": params.get("entreprise_id"),
        "p_limit": params.get("limit", 20)
    })


# ============================================================================
# SCHEMA REGISTRY
# ============================================================================

COMMUNICATION_SCHEMAS = {
    "list_recent_interactions": LIST_RECENT_INTERACTIONS_SCHEMA,
    # Workflows moved to tools/workflows.py
}
