"""
Gestion commerciale - Qualifications

Schemas et handlers pour la gestion des qualifications :
- get_entreprise_qualifications (READ)
- search_qualifications (READ)
- upsert_qualification (WRITE)
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

GET_ENTREPRISE_QUALIFICATIONS_SCHEMA = ToolSchema(
    name="get_entreprise_qualifications",
    description="Recupere toutes les qualifications d'une entreprise specifique (date, statut, montant, description).",
    input_schema={
        "type": "object",
        "properties": {
            "entreprise_id": {
                "type": "string",
                "description": "UUID de l'entreprise"
            }
        },
        "required": ["entreprise_id"]
    },
    category="read"
)

SEARCH_QUALIFICATIONS_SCHEMA = ToolSchema(
    name="search_qualifications",
    description="Recherche qualifications par statut, periode ou entreprise. Utile pour filtrer les qualifications actives, gagnees ou perdues.",
    input_schema={
        "type": "object",
        "properties": {
            "statut": {
                "type": "string",
                "description": "Statut de la qualification (Nouveau, Qualifié, BC envoyé, Payé, Terminé, Annulé)",
                "enum": ["Nouveau", "Qualifié", "BC envoyé", "Payé", "Terminé", "Annulé"]
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

UPSERT_QUALIFICATION_SCHEMA = ToolSchema(
    name="upsert_qualification",
    description="Cree ou met a jour une qualification pour une entreprise. Valide entreprise_id et statut avant insertion.",
    input_schema={
        "type": "object",
        "properties": {
            "entreprise_id": {
                "type": "string",
                "description": "UUID de l'entreprise (requis)"
            },
            "statut": {
                "type": "string",
                "description": "Statut de la qualification (requis)",
                "enum": ["Nouveau", "Qualifié", "BC envoyé", "Payé", "Terminé", "Annulé"]
            },
            "montant_estime": {
                "type": "number",
                "description": "Montant estime en euros"
            },
            "description": {
                "type": "string",
                "description": "Description de la qualification"
            },
            "date_prevue": {
                "type": "string",
                "description": "Date previsionnelle (format ISO 8601: YYYY-MM-DD)"
            }
        },
        "required": ["entreprise_id", "statut"]
    },
    category="write"
)


# ============================================================================
# HANDLERS
# ============================================================================

@register_tool(
    name="get_entreprise_qualifications",
    category=ToolCategory.READ,
    description_short="Recupere qualifications d'une entreprise"
)
async def get_entreprise_qualifications_handler(params: Dict[str, Any]):
    """Get all qualifications for a company"""
    return await call_supabase_rpc("get_entreprise_qualifications", {
        "p_entreprise_id": params["entreprise_id"]
    })


@register_tool(
    name="search_qualifications",
    category=ToolCategory.READ,
    description_short="Recherche qualifications par criteres"
)
async def search_qualifications_handler(params: Dict[str, Any]):
    """Search qualifications by status, date range"""
    return await call_supabase_rpc("search_qualifications", {
        "p_statut": params.get("statut"),
        "p_start_date": params.get("start_date"),
        "p_end_date": params.get("end_date"),
        "p_limit": params.get("limit", 50)
    })


@register_tool(
    name="upsert_qualification",
    category=ToolCategory.WRITE,
    description_short="Cree ou met a jour une qualification"
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
# SCHEMA REGISTRY
# ============================================================================

QUALIFICATION_SCHEMAS = {
    "get_entreprise_qualifications": GET_ENTREPRISE_QUALIFICATIONS_SCHEMA,
    "search_qualifications": SEARCH_QUALIFICATIONS_SCHEMA,
    "upsert_qualification": UPSERT_QUALIFICATION_SCHEMA,
}
