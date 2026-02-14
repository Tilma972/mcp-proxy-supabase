"""
Schema definitions for WORKFLOW tools (multi-worker orchestration)

These tools orchestrate multiple worker calls to complete complex operations.
"""

from typing import Dict, Any
from schemas import ToolSchema


# ============================================================================
# EMAIL WORKFLOWS
# ============================================================================

SEND_FACTURE_EMAIL_SCHEMA = ToolSchema(
    name="send_facture_email",
    description="Workflow complet : Génère PDF de facture → Upload → Envoie email au client. Retourne URL du PDF et statut d'envoi.",
    input_schema={
        "type": "object",
        "properties": {
            "facture_id": {
                "type": "string",
                "description": "UUID de la facture à envoyer (requis)"
            },
            "recipient_email": {
                "type": "string",
                "description": "Email du destinataire (optionnel, utilise email entreprise si absent)"
            },
            "message": {
                "type": "string",
                "description": "Message personnalisé à inclure dans l'email (optionnel)"
            }
        },
        "required": ["facture_id"]
    },
    category="workflow"
)

CREATE_AND_SEND_FACTURE_SCHEMA = ToolSchema(
    name="create_and_send_facture",
    description="Workflow complet : Crée facture → Génère PDF → Upload → Envoie email. Simplifie création + envoi en une seule opération.",
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
                "description": "Description des services facturés"
            },
            "recipient_email": {
                "type": "string",
                "description": "Email du destinataire (optionnel, utilise email entreprise si absent)"
            },
            "date_echeance": {
                "type": "string",
                "description": "Date d'échéance (format ISO 8601: YYYY-MM-DD)"
            },
            "message": {
                "type": "string",
                "description": "Message personnalisé dans l'email (optionnel)"
            }
        },
        "required": ["qualification_id", "montant"]
    },
    category="workflow"
)

# ============================================================================
# REPORTING WORKFLOWS
# ============================================================================

GENERATE_MONTHLY_REPORT_SCHEMA = ToolSchema(
    name="generate_monthly_report",
    description="Génère rapport mensuel : Fetch stats revenus + factures impayées → Génère PDF → Upload. Retourne URL du rapport PDF.",
    input_schema={
        "type": "object",
        "properties": {
            "year": {
                "type": "integer",
                "description": "Année du rapport (ex: 2025)"
            },
            "month": {
                "type": "integer",
                "description": "Mois du rapport (1-12)"
            },
            "send_email": {
                "type": "boolean",
                "description": "Envoyer le rapport par email après génération (défaut: false)",
                "default": False
            },
            "recipient_email": {
                "type": "string",
                "description": "Email destinataire si send_email=true"
            }
        },
        "required": ["year", "month"]
    },
    category="workflow"
)

# ============================================================================
# REGISTRY
# ============================================================================

WORKFLOW_TOOL_SCHEMAS = {
    "send_facture_email": SEND_FACTURE_EMAIL_SCHEMA,
    "create_and_send_facture": CREATE_AND_SEND_FACTURE_SCHEMA,
    "generate_monthly_report": GENERATE_MONTHLY_REPORT_SCHEMA,
}
