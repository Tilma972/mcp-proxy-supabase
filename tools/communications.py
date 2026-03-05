"""
Emails & notifications - Communications

Schemas et handlers pour les communications :
- list_recent_interactions (READ)
- send_custom_email (WORKFLOW)
- prepare_email_draft (WORKFLOW)
- execute_email_draft (WORKFLOW)

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
from utils.draft_store import store_draft, get_draft


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

SEND_CUSTOM_EMAIL_SCHEMA = ToolSchema(
    name="send_custom_email",
    description="Envoie un email personnalisé directement (sans validation de l'utilisateur). À utiliser uniquement si l'utilisateur a explicitement demandé d'envoyer l'email sans relire, ou pour des envois internes.",
    input_schema={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Adresse email du destinataire"},
            "subject": {"type": "string", "description": "Sujet de l'email"},
            "message": {
                "type": "string", 
                "description": "Contenu HTML de l'email. Vous pouvez utiliser du formattage professionel."
            },
            "title": {"type": "string", "description": "Titre principal h1 affiché dans le template (optionnel)"},
            "use_template": {"type": "boolean", "description": "Utilise le template professionnel (défaut true)", "default": True}
        },
        "required": ["to", "subject", "message"]
    },
    category="workflow"
)

PREPARE_EMAIL_DRAFT_SCHEMA = ToolSchema(
    name="prepare_email_draft",
    description="Prépare un email et le met en attente (brouillon). L'IA DOIT TOUJOURS UTILISER CET OUTIL pour l'envoi de mails non-transactionnels plutôt que d'envoyer directement. L'outil retourne un ID. L'IA doit afficher à la fin de son message textuel exactement: [DRAFT_READY: uuid_retourne]. NE JAMAIS appeler send_custom_email directement unless explicitly requested.",
    input_schema={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Adresse email du destinataire"},
            "subject": {"type": "string", "description": "Sujet de l'email"},
            "message": {
                "type": "string", 
                "description": "Contenu HTML de l'email. Formatez élégamment."
            },
            "title": {"type": "string", "description": "Titre principal h1 dans le template (optionnel)"},
            "use_template": {"type": "boolean", "description": "Utilise le template pro (défaut true)", "default": True}
        },
        "required": ["to", "subject", "message"]
    },
    category="workflow"
)

EXECUTE_EMAIL_DRAFT_SCHEMA = ToolSchema(
    name="execute_email_draft",
    description="Execute l'envoi d'un brouillon d'email précédemment préparé. Normalement appelé par le système quand l'utilisateur clique sur Envoyer, mais l'IA peut l'utiliser si l'utilisateur l'y autorise explicitement.",
    input_schema={
        "type": "object",
        "properties": {
            "draft_id": {"type": "string", "description": "UUID du brouillon d'email"}
        },
        "required": ["draft_id"]
    },
    category="workflow"
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
# WORKFLOW HANDLERS
# ============================================================================

@register_tool(
    name="send_custom_email",
    category=ToolCategory.WORKFLOW,
    description_short="Envoie email personnalisé"
)
async def send_custom_email_handler(params: Dict[str, Any]):
    """Send a custom formatted email via email-worker"""
    payload = {
        "to": params["to"],
        "subject": params["subject"],
        "message": params["message"],
        "title": params.get("title", params["subject"]),
        "use_template": params.get("use_template", True)
    }
    
    response = await call_email_worker("/send/notification", payload)
    
    if not response.get("success"):
        raise HTTPException(status_code=500, detail=f"Failed to send email: {response.get('error')}")
        
    return {
        "success": True,
        "message_id": response.get("message_id"),
        "sent_at": response.get("sent_at")
    }

@register_tool(
    name="prepare_email_draft",
    category=ToolCategory.WORKFLOW,
    description_short="Prépare un brouillon d'email pour validation"
)
async def prepare_email_draft_handler(params: Dict[str, Any]):
    """Stocke les infos de l'email en mémoire et retourne un draft_id"""
    payload = {
        "to": params["to"],
        "subject": params["subject"],
        "message": params["message"],
        "title": params.get("title", params["subject"]),
        "use_template": params.get("use_template", True)
    }
    draft_id = await store_draft(payload)
    return {
        "success": True,
        "draft_id": draft_id,
        "message": f"Brouillon prêt. L'IA doit afficher [DRAFT_READY: {draft_id}] au Telegram pour générer le bouton UI."
    }

@register_tool(
    name="execute_email_draft",
    category=ToolCategory.WORKFLOW,
    description_short="Exécute l'envoi d'un brouillon d'email"
)
async def execute_email_draft_handler(params: Dict[str, Any]):
    draft_id = params["draft_id"]
    try:
        payload = await get_draft(draft_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    response = await call_email_worker("/send/notification", payload)
    
    if not response.get("success"):
        raise HTTPException(status_code=500, detail=f"Failed to send email: {response.get('error')}")
        
    return {
        "success": True,
        "message_id": response.get("message_id"),
        "sent_at": response.get("sent_at"),
        "to": payload["to"]
    }

# ============================================================================  
# SCHEMA REGISTRY
# ============================================================================  

COMMUNICATION_SCHEMAS = {
    "list_recent_interactions": LIST_RECENT_INTERACTIONS_SCHEMA,
    "send_custom_email": SEND_CUSTOM_EMAIL_SCHEMA,
    "prepare_email_draft": PREPARE_EMAIL_DRAFT_SCHEMA,
    "execute_email_draft": EXECUTE_EMAIL_DRAFT_SCHEMA,
}
