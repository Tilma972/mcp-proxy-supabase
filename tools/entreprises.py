"""
Gestion clients - Entreprises

Schemas et handlers pour la gestion des entreprises :
- search_entreprise_with_stats (READ)
- get_entreprise_by_id (READ)
- list_entreprises (READ)
- get_stats_entreprises (READ)
- upsert_entreprise (WRITE)
"""

from typing import Dict, Any

import structlog
from fastapi import HTTPException

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

SEARCH_ENTREPRISE_SCHEMA = ToolSchema(
    name="search_entreprise_with_stats",
    description="Recherche entreprise par nom avec statistiques (CA, derniere qualification). Retourne nom, email, CA total, nombre de qualifications.",
    input_schema={
        "type": "object",
        "properties": {
            "search_term": {
                "type": "string",
                "description": "Nom ou partie du nom de l'entreprise a rechercher"
            },
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de resultats (defaut: 10)",
                "default": 10
            }
        },
        "required": ["search_term"]
    },
    category="read"
)

GET_ENTREPRISE_BY_ID_SCHEMA = ToolSchema(
    name="get_entreprise_by_id",
    description="Recupere les details complets d'une entreprise par son ID (nom, email, telephone, adresse, CA total, stats qualifications).",
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

LIST_ENTREPRISES_SCHEMA = ToolSchema(
    name="list_entreprises",
    description="Liste toutes les entreprises avec pagination. Retourne nom, email, CA total pour chaque entreprise.",
    input_schema={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de resultats (defaut: 50)",
                "default": 50
            },
            "offset": {
                "type": "integer",
                "description": "Decalage pour pagination (defaut: 0)",
                "default": 0
            }
        },
        "required": []
    },
    category="read"
)

GET_STATS_ENTREPRISES_SCHEMA = ToolSchema(
    name="get_stats_entreprises",
    description="Recupere les statistiques globales sur toutes les entreprises (nombre total, revenus totaux des encarts). Utile pour obtenir une vue d'ensemble du CRM.",
    input_schema={
        "type": "object",
        "properties": {},
        "required": []
    },
    category="read"
)

UPSERT_ENTREPRISE_SCHEMA = ToolSchema(
    name="upsert_entreprise",
    description="Cree ou met a jour une entreprise. Si nom existe, met a jour. Sinon cree nouvelle entreprise. Valide les donnees avant insertion.",
    input_schema={
        "type": "object",
        "properties": {
            "nom": {
                "type": "string",
                "description": "Nom de l'entreprise (requis)"
            },
            "email": {
                "type": "string",
                "description": "Email de contact"
            },
            "telephone": {
                "type": "string",
                "description": "Numero de telephone"
            },
            "adresse": {
                "type": "string",
                "description": "Adresse complete"
            },
            "notes": {
                "type": "string",
                "description": "Notes internes"
            }
        },
        "required": ["nom"]
    },
    category="write"
)


# ============================================================================
# HANDLERS
# ============================================================================

@register_tool(
    name="search_entreprise_with_stats",
    category=ToolCategory.READ,
    description_short="Recherche entreprise par nom avec statistiques"
)
async def search_entreprise_with_stats_handler(params: Dict[str, Any]):
    """Search companies by name with statistics"""
    return await call_supabase_rpc("search_entreprise_with_stats", {
        "p_search_term": params["search_term"],
        "p_limit": params.get("limit", 10)
    })


@register_tool(
    name="get_entreprise_by_id",
    category=ToolCategory.READ,
    description_short="Recupere details complets d'une entreprise"
)
async def get_entreprise_by_id_handler(params: Dict[str, Any]):
    """Get company details by ID"""
    return await call_supabase_rpc("get_entreprise_by_id", {
        "p_id": params["entreprise_id"]
    })


@register_tool(
    name="list_entreprises",
    category=ToolCategory.READ,
    description_short="Liste toutes les entreprises avec pagination"
)
async def list_entreprises_handler(params: Dict[str, Any]):
    """List all companies with pagination"""
    return await call_supabase_rpc("list_entreprises", {
        "p_limit": params.get("limit", 50),
        "p_offset": params.get("offset", 0)
    })


@register_tool(
    name="get_stats_entreprises",
    category=ToolCategory.READ,
    description_short="Statistiques globales sur les entreprises et revenus"
)
async def get_stats_entreprises_handler(params: Dict[str, Any]):
    """Get global statistics about companies and revenue"""
    return await call_supabase_rpc("get_stats_entreprises", {})


@register_tool(
    name="upsert_entreprise",
    category=ToolCategory.WRITE,
    description_short="Cree ou met a jour une entreprise"
)
async def upsert_entreprise_handler(params: Dict[str, Any]):
    """Create or update a company"""
    logger = structlog.get_logger()

    data = await call_database_worker(
        endpoint="/entreprise/upsert",
        payload={
            "nom": params["nom"],
            "email": params.get("email"),
            "telephone": params.get("telephone"),
            "adresse": params.get("adresse"),
            "notes": params.get("notes")
        },
        method="POST",
        require_validation=False
    )

    if data.get("id") is None:
        logger.error("database_worker_validation_failed", endpoint="/entreprise/upsert", response=data)
        raise HTTPException(status_code=422, detail="Validation failed: response missing 'id'")

    return {**data, "validated": True}


# ============================================================================
# SCHEMA REGISTRY
# ============================================================================

ENTREPRISE_SCHEMAS = {
    "search_entreprise_with_stats": SEARCH_ENTREPRISE_SCHEMA,
    "get_entreprise_by_id": GET_ENTREPRISE_BY_ID_SCHEMA,
    "list_entreprises": LIST_ENTREPRISES_SCHEMA,
    "get_stats_entreprises": GET_STATS_ENTREPRISES_SCHEMA,
    "upsert_entreprise": UPSERT_ENTREPRISE_SCHEMA,
}
