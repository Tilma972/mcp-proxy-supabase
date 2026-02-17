"""
FlowChat MCP Tools - Registration Hub

Imports all domain modules to trigger @register_tool decorators
and aggregates all tool schemas for the MCP protocol.

Domain modules:
- entreprises: Gestion clients (5 tools)
- qualifications: Gestion commerciale (3 tools)
- factures: Facturation (5 tools) [workflows moved out]
- paiements: Tresorerie (3 tools)
- communications: Emails & notifications (1 tool) [workflows moved out]
- workflows: Orchestration multi-domain (4 tools)
- analytics: Reporting (placeholder)

Total: 21 tools (11 READ + 6 WRITE + 4 WORKFLOW)
"""

# Import domain modules to trigger handler registration
from tools.entreprises import ENTREPRISE_SCHEMAS
from tools.qualifications import QUALIFICATION_SCHEMAS
from tools.factures import FACTURE_SCHEMAS
from tools.paiements import PAIEMENT_SCHEMAS
from tools.communications import COMMUNICATION_SCHEMAS
# Import workflows LAST to avoid circular dependencies
from tools.workflows import WORKFLOW_SCHEMAS

# Aggregated schema registry for all tools
ALL_TOOL_SCHEMAS = {
    **ENTREPRISE_SCHEMAS,
    **QUALIFICATION_SCHEMAS,
    **FACTURE_SCHEMAS,
    **PAIEMENT_SCHEMAS,
    **COMMUNICATION_SCHEMAS,
    **WORKFLOW_SCHEMAS,  # Added last
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
    "workflows": {
        "description": "Orchestration multi-domain (cross-domain workflows)",
        "tools": list(WORKFLOW_SCHEMAS.keys()),
        "schemas": WORKFLOW_SCHEMAS,
    },
}
