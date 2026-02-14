"""
Handlers for READ tools (Supabase RPC calls)

All handlers call Supabase RPC functions to fetch data.
No data modification occurs.
"""

from typing import Dict, Any
import httpx
import structlog

from config import settings
from tools_registry import register_tool, ToolCategory
from utils.http_client import get_shared_client
from utils.retry import retry_with_backoff
from middleware import request_id_ctx

logger = structlog.get_logger()


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
# ENTREPRISE READ HANDLERS
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
    description_short="Récupère détails complets d'une entreprise"
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


# ============================================================================
# QUALIFICATION READ HANDLERS
# ============================================================================

@register_tool(
    name="get_entreprise_qualifications",
    category=ToolCategory.READ,
    description_short="Récupère qualifications d'une entreprise"
)
async def get_entreprise_qualifications_handler(params: Dict[str, Any]):
    """Get all qualifications for a company"""
    return await call_supabase_rpc("get_entreprise_qualifications", {
        "p_entreprise_id": params["entreprise_id"]
    })


@register_tool(
    name="search_qualifications",
    category=ToolCategory.READ,
    description_short="Recherche qualifications par critères"
)
async def search_qualifications_handler(params: Dict[str, Any]):
    """Search qualifications by status, date range"""
    return await call_supabase_rpc("search_qualifications", {
        "p_statut": params.get("statut"),
        "p_start_date": params.get("start_date"),
        "p_end_date": params.get("end_date"),
        "p_limit": params.get("limit", 50)
    })


# ============================================================================
# FACTURE READ HANDLERS
# ============================================================================

@register_tool(
    name="search_factures",
    category=ToolCategory.READ,
    description_short="Recherche factures par critères"
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
    description_short="Récupère détails complets d'une facture"
)
async def get_facture_by_id_handler(params: Dict[str, Any]):
    """Get invoice details by ID"""
    return await call_supabase_rpc("get_facture_by_id", {
        "p_id": params["facture_id"]
    })


@register_tool(
    name="get_unpaid_factures",
    category=ToolCategory.READ,
    description_short="Récupère factures impayées"
)
async def get_unpaid_factures_handler(params: Dict[str, Any]):
    """Get all unpaid invoices"""
    return await call_supabase_rpc("get_unpaid_factures", {
        "p_limit": params.get("limit", 100)
    })


# ============================================================================
# STATS READ HANDLERS
# ============================================================================

@register_tool(
    name="get_revenue_stats",
    category=ToolCategory.READ,
    description_short="Calcule statistiques revenus pour période"
)
async def get_revenue_stats_handler(params: Dict[str, Any]):
    """Get revenue statistics for a period"""
    return await call_supabase_rpc("get_revenue_stats", {
        "p_start_date": params["start_date"],
        "p_end_date": params["end_date"]
    })


@register_tool(
    name="list_recent_interactions",
    category=ToolCategory.READ,
    description_short="Liste interactions récentes"
)
async def list_recent_interactions_handler(params: Dict[str, Any]):
    """List recent interactions (Telegram messages)"""
    return await call_supabase_rpc("list_recent_interactions", {
        "p_entreprise_id": params.get("entreprise_id"),
        "p_limit": params.get("limit", 20)
    })
