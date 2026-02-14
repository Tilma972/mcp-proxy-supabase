"""
Schema definitions for READ tools (Supabase RPC calls)

These tools fetch data from Supabase via RPC functions.
All are read-only and do not modify data.
"""

from typing import Dict, Any
from schemas import ToolSchema


# ============================================================================
# ENTREPRISE TOOLS
# ============================================================================

SEARCH_ENTREPRISE_SCHEMA = ToolSchema(
    name="search_entreprise_with_stats",
    description="Recherche entreprise par nom avec statistiques (CA, dernière qualification). Retourne nom, email, CA total, nombre de qualifications.",
    input_schema={
        "type": "object",
        "properties": {
            "search_term": {
                "type": "string",
                "description": "Nom ou partie du nom de l'entreprise à rechercher"
            },
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de résultats (défaut: 10)",
                "default": 10
            }
        },
        "required": ["search_term"]
    },
    category="read"
)

GET_ENTREPRISE_BY_ID_SCHEMA = ToolSchema(
    name="get_entreprise_by_id",
    description="Récupère les détails complets d'une entreprise par son ID (nom, email, téléphone, adresse, CA total, stats qualifications).",
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
                "description": "Nombre maximum de résultats (défaut: 50)",
                "default": 50
            },
            "offset": {
                "type": "integer",
                "description": "Décalage pour pagination (défaut: 0)",
                "default": 0
            }
        },
        "required": []
    },
    category="read"
)

# ============================================================================
# QUALIFICATION TOOLS
# ============================================================================

GET_ENTREPRISE_QUALIFICATIONS_SCHEMA = ToolSchema(
    name="get_entreprise_qualifications",
    description="Récupère toutes les qualifications d'une entreprise spécifique (date, statut, montant, description).",
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
    description="Recherche qualifications par statut, période ou entreprise. Utile pour filtrer les qualifications actives, gagnées ou perdues.",
    input_schema={
        "type": "object",
        "properties": {
            "statut": {
                "type": "string",
                "description": "Statut de la qualification (en_cours, gagne, perdu, annule)",
                "enum": ["en_cours", "gagne", "perdu", "annule"]
            },
            "start_date": {
                "type": "string",
                "description": "Date de début (format ISO 8601: YYYY-MM-DD)"
            },
            "end_date": {
                "type": "string",
                "description": "Date de fin (format ISO 8601: YYYY-MM-DD)"
            },
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de résultats (défaut: 50)",
                "default": 50
            }
        },
        "required": []
    },
    category="read"
)

# ============================================================================
# FACTURE TOOLS
# ============================================================================

SEARCH_FACTURES_SCHEMA = ToolSchema(
    name="search_factures",
    description="Recherche factures par entreprise, période ou statut de paiement. Retourne numéro, montant, statut, entreprise.",
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
                "description": "Date de début (format ISO 8601: YYYY-MM-DD)"
            },
            "end_date": {
                "type": "string",
                "description": "Date de fin (format ISO 8601: YYYY-MM-DD)"
            },
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de résultats (défaut: 50)",
                "default": 50
            }
        },
        "required": []
    },
    category="read"
)

GET_FACTURE_BY_ID_SCHEMA = ToolSchema(
    name="get_facture_by_id",
    description="Récupère les détails complets d'une facture par son ID (numéro, montant, entreprise, qualification, statut paiement, PDF URL).",
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

GET_UNPAID_FACTURES_SCHEMA = ToolSchema(
    name="get_unpaid_factures",
    description="Récupère toutes les factures impayées. Utile pour relances et suivi de paiements.",
    input_schema={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de résultats (défaut: 100)",
                "default": 100
            }
        },
        "required": []
    },
    category="read"
)

# ============================================================================
# STATS & REPORTING TOOLS
# ============================================================================

GET_REVENUE_STATS_SCHEMA = ToolSchema(
    name="get_revenue_stats",
    description="Calcule statistiques de revenus pour une période (CA total, nombre factures, montant moyen, taux paiement).",
    input_schema={
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "Date de début (format ISO 8601: YYYY-MM-DD)"
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

LIST_RECENT_INTERACTIONS_SCHEMA = ToolSchema(
    name="list_recent_interactions",
    description="Liste les interactions récentes (messages Telegram) pour une entreprise ou globalement. Utile pour contexte conversation.",
    input_schema={
        "type": "object",
        "properties": {
            "entreprise_id": {
                "type": "string",
                "description": "UUID de l'entreprise (optionnel, si absent retourne toutes interactions)"
            },
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de résultats (défaut: 20)",
                "default": 20
            }
        },
        "required": []
    },
    category="read"
)

# ============================================================================
# REGISTRY
# ============================================================================

READ_TOOL_SCHEMAS = {
    "search_entreprise_with_stats": SEARCH_ENTREPRISE_SCHEMA,
    "get_entreprise_by_id": GET_ENTREPRISE_BY_ID_SCHEMA,
    "list_entreprises": LIST_ENTREPRISES_SCHEMA,
    "get_entreprise_qualifications": GET_ENTREPRISE_QUALIFICATIONS_SCHEMA,
    "search_qualifications": SEARCH_QUALIFICATIONS_SCHEMA,
    "search_factures": SEARCH_FACTURES_SCHEMA,
    "get_facture_by_id": GET_FACTURE_BY_ID_SCHEMA,
    "get_unpaid_factures": GET_UNPAID_FACTURES_SCHEMA,
    "get_revenue_stats": GET_REVENUE_STATS_SCHEMA,
    "list_recent_interactions": LIST_RECENT_INTERACTIONS_SCHEMA,
}
