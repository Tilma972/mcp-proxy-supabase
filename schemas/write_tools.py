"""
Schema definitions for WRITE tools (database-worker calls)

These tools modify data via the database-worker service.
All include validation enforcement to ensure data integrity.
"""

from typing import Dict, Any
from schemas import ToolSchema


# ============================================================================
# ENTREPRISE WRITE TOOLS
# ============================================================================

UPSERT_ENTREPRISE_SCHEMA = ToolSchema(
    name="upsert_entreprise",
    description="Crée ou met à jour une entreprise. Si nom existe, met à jour. Sinon crée nouvelle entreprise. Valide les données avant insertion.",
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
                "description": "Numéro de téléphone"
            },
            "adresse": {
                "type": "string",
                "description": "Adresse complète"
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
# QUALIFICATION WRITE TOOLS
# ============================================================================

UPSERT_QUALIFICATION_SCHEMA = ToolSchema(
    name="upsert_qualification",
    description="Crée ou met à jour une qualification pour une entreprise. Valide entreprise_id et statut avant insertion.",
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
                "enum": ["en_cours", "gagne", "perdu", "annule"]
            },
            "montant_estime": {
                "type": "number",
                "description": "Montant estimé en euros"
            },
            "description": {
                "type": "string",
                "description": "Description de la qualification"
            },
            "date_prevue": {
                "type": "string",
                "description": "Date prévisionnelle (format ISO 8601: YYYY-MM-DD)"
            }
        },
        "required": ["entreprise_id", "statut"]
    },
    category="write"
)

# ============================================================================
# FACTURE WRITE TOOLS
# ============================================================================

CREATE_FACTURE_SCHEMA = ToolSchema(
    name="create_facture",
    description="Crée une nouvelle facture pour une qualification. Génère automatiquement le numéro de facture. Valide qualification_id et montant.",
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
            "date_emission": {
                "type": "string",
                "description": "Date d'émission (format ISO 8601: YYYY-MM-DD, défaut: aujourd'hui)"
            },
            "date_echeance": {
                "type": "string",
                "description": "Date d'échéance (format ISO 8601: YYYY-MM-DD)"
            }
        },
        "required": ["qualification_id", "montant"]
    },
    category="write"
)

UPDATE_FACTURE_SCHEMA = ToolSchema(
    name="update_facture",
    description="Met à jour une facture existante (montant, description, dates). Ne modifie PAS le statut de paiement (utiliser mark_facture_paid).",
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
                "description": "Nouvelle date d'échéance (format ISO 8601: YYYY-MM-DD)"
            }
        },
        "required": ["facture_id"]
    },
    category="write"
)

MARK_FACTURE_PAID_SCHEMA = ToolSchema(
    name="mark_facture_paid",
    description="Marque une facture comme payée. Met à jour payment_status='paid' et enregistre la date de paiement.",
    input_schema={
        "type": "object",
        "properties": {
            "facture_id": {
                "type": "string",
                "description": "UUID de la facture (requis)"
            },
            "payment_date": {
                "type": "string",
                "description": "Date de paiement (format ISO 8601: YYYY-MM-DD, défaut: aujourd'hui)"
            },
            "payment_method": {
                "type": "string",
                "description": "Méthode de paiement (virement, chèque, carte, espèces)"
            }
        },
        "required": ["facture_id"]
    },
    category="write"
)

DELETE_FACTURE_SCHEMA = ToolSchema(
    name="delete_facture",
    description="Supprime une facture (soft delete). Ne supprime PAS définitivement, marque comme deleted=true. Requiert confirmation.",
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
# REGISTRY
# ============================================================================

WRITE_TOOL_SCHEMAS = {
    "upsert_entreprise": UPSERT_ENTREPRISE_SCHEMA,
    "upsert_qualification": UPSERT_QUALIFICATION_SCHEMA,
    "create_facture": CREATE_FACTURE_SCHEMA,
    "update_facture": UPDATE_FACTURE_SCHEMA,
    "mark_facture_paid": MARK_FACTURE_PAID_SCHEMA,
    "delete_facture": DELETE_FACTURE_SCHEMA,
}
