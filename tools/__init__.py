"""
FlowChat MCP Tools - Registration Hub

Imports all domain modules to trigger @register_tool decorators
and aggregates all tool schemas for the MCP protocol.

Domain modules:
- entreprises: Gestion clients (5 tools)
- qualifications: Gestion commerciale (3 tools)
- factures: Facturation (7 tools)
- paiements: Tresorerie (3 tools)
- communications: Emails & notifications (3 tools)
- analytics: Reporting (placeholder)
"""

# Import domain modules to trigger handler registration
from tools.entreprises import ENTREPRISE_SCHEMAS
from tools.qualifications import QUALIFICATION_SCHEMAS
from tools.factures import FACTURE_SCHEMAS
from tools.paiements import PAIEMENT_SCHEMAS
from tools.communications import COMMUNICATION_SCHEMAS

# Aggregated schema registry for all tools
ALL_TOOL_SCHEMAS = {
    **ENTREPRISE_SCHEMAS,
    **QUALIFICATION_SCHEMAS,
    **FACTURE_SCHEMAS,
    **PAIEMENT_SCHEMAS,
    **COMMUNICATION_SCHEMAS,
}

# Domain registry: maps domain name -> {description, tool_names, schemas}
TOOL_DOMAINS = {
    "entreprises": {
        "description": "Gestion clients",
        "tools": list(ENTREPRISE_SCHEMAS.keys()),
        "schemas": ENTREPRISE_SCHEMAS,
    },
    "qualifications": {
        "description": "Gestion commerciale",
        "tools": list(QUALIFICATION_SCHEMAS.keys()),
        "schemas": QUALIFICATION_SCHEMAS,
    },
    "factures": {
        "description": "Facturation",
        "tools": list(FACTURE_SCHEMAS.keys()),
        "schemas": FACTURE_SCHEMAS,
    },
    "paiements": {
        "description": "Tresorerie",
        "tools": list(PAIEMENT_SCHEMAS.keys()),
        "schemas": PAIEMENT_SCHEMAS,
    },
    "communications": {
        "description": "Emails & notifications",
        "tools": list(COMMUNICATION_SCHEMAS.keys()),
        "schemas": COMMUNICATION_SCHEMAS,
    },
}
