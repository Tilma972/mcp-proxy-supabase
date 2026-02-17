"""
Facturation - Factures

Schemas et handlers pour la facturation :
- search_factures (READ)
- get_facture_by_id (READ)
- create_facture (WRITE)
- update_facture (WRITE)
- delete_facture (WRITE)
- generate_facture_pdf (WORKFLOW)
- create_and_send_facture (WORKFLOW)
"""

import uuid
from typing import Dict, Any
from datetime import datetime
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
)
from middleware import request_id_ctx


logger = structlog.get_logger()


# ============================================================================
# SCHEMAS
# ============================================================================

SEARCH_FACTURES_SCHEMA = ToolSchema(
    name="search_factures",
    description="Recherche factures par entreprise, periode ou statut de paiement. Retourne numero, montant, statut, entreprise.",
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

GET_FACTURE_BY_ID_SCHEMA = ToolSchema(
    name="get_facture_by_id",
    description="Recupere les details complets d'une facture par son ID (numero, montant, entreprise, qualification, statut paiement, PDF URL).",
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

CREATE_FACTURE_SCHEMA = ToolSchema(
    name="create_facture",
    description="Cree une nouvelle facture pour une qualification. Genere automatiquement le numero de facture. Valide qualification_id et montant.",
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
                "description": "Description des services factures"
            },
            "date_emission": {
                "type": "string",
                "description": "Date d'emission (format ISO 8601: YYYY-MM-DD, defaut: aujourd'hui)"
            },
            "date_echeance": {
                "type": "string",
                "description": "Date d'echeance (format ISO 8601: YYYY-MM-DD)"
            }
        },
        "required": ["qualification_id", "montant"]
    },
    category="write"
)

UPDATE_FACTURE_SCHEMA = ToolSchema(
    name="update_facture",
    description="Met a jour une facture existante (montant, description, dates). Ne modifie PAS le statut de paiement (utiliser mark_facture_paid).",
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
                "description": "Nouvelle date d'echeance (format ISO 8601: YYYY-MM-DD)"
            }
        },
        "required": ["facture_id"]
    },
    category="write"
)

DELETE_FACTURE_SCHEMA = ToolSchema(
    name="delete_facture",
    description="Supprime une facture (soft delete). Ne supprime PAS definitivement, marque comme deleted=true. Requiert confirmation.",
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

GENERATE_FACTURE_PDF_SCHEMA = ToolSchema(
    name="generate_facture_pdf",
    description="Genere le PDF d'une facture existante et l'upload sur Supabase Storage. Retourne l'URL du PDF. N'envoie PAS d'email.",
    input_schema={
        "type": "object",
        "properties": {
            "facture_id": {
                "type": "string",
                "description": "UUID de la facture (requis)"
            },
            "force_regenerate": {
                "type": "boolean",
                "description": "Forcer la regeneration meme si PDF existe deja (defaut: false)",
                "default": False
            }
        },
        "required": ["facture_id"]
    },
    category="workflow"
)

CREATE_AND_SEND_FACTURE_SCHEMA = ToolSchema(
    name="create_and_send_facture",
    description="Workflow complet : Cree facture -> Genere PDF -> Upload -> Envoie email. Simplifie creation + envoi en une seule operation.",
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
                "description": "Description des services factures"
            },
            "recipient_email": {
                "type": "string",
                "description": "Email du destinataire (optionnel, utilise email entreprise si absent)"
            },
            "date_echeance": {
                "type": "string",
                "description": "Date d'echeance (format ISO 8601: YYYY-MM-DD)"
            },
            "message": {
                "type": "string",
                "description": "Message personnalise dans l'email (optionnel)"
            }
        },
        "required": ["qualification_id", "montant"]
    },
    category="workflow"
)


# ============================================================================
# READ HANDLERS
# ============================================================================

@register_tool(
    name="search_factures",
    category=ToolCategory.READ,
    description_short="Recherche factures par criteres"
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
    description_short="Recupere details complets d'une facture"
)
async def get_facture_by_id_handler(params: Dict[str, Any]):
    """Get invoice details by ID"""
    return await call_supabase_rpc("get_facture_by_id", {
        "p_id": params["facture_id"]
    })


# ============================================================================
# WRITE HANDLERS
# ============================================================================

@register_tool(
    name="create_facture",
    category=ToolCategory.WRITE,
    description_short="Cree une nouvelle facture"
)
async def create_facture_handler(params: Dict[str, Any]):
    """Create a new invoice"""
    return await call_database_worker(
        endpoint="/facture/create",
        payload={
            "qualification_id": params["qualification_id"],
            "montant": params["montant"],
            "description": params.get("description"),
            "date_emission": params.get("date_emission"),
            "date_echeance": params.get("date_echeance")
        },
        method="POST",
        require_validation=True
    )


@register_tool(
    name="update_facture",
    category=ToolCategory.WRITE,
    description_short="Met a jour une facture"
)
async def update_facture_handler(params: Dict[str, Any]):
    """Update an existing invoice"""
    facture_id = params["facture_id"]

    return await call_database_worker(
        endpoint=f"/facture/{facture_id}",
        payload={
            "montant": params.get("montant"),
            "description": params.get("description"),
            "date_echeance": params.get("date_echeance")
        },
        method="PUT",
        require_validation=True
    )


@register_tool(
    name="delete_facture",
    category=ToolCategory.WRITE,
    description_short="Supprime une facture (soft delete)"
)
async def delete_facture_handler(params: Dict[str, Any]):
    """Delete an invoice (soft delete)"""
    facture_id = params["facture_id"]

    return await call_database_worker(
        endpoint=f"/facture/{facture_id}",
        payload={},
        method="DELETE",
        require_validation=False  # Soft delete doesn't need validation
    )


# ============================================================================
# WORKFLOW HANDLERS
# ============================================================================

@register_tool(
    name="generate_facture_pdf",
    category=ToolCategory.WORKFLOW,
    description_short="Genere PDF facture et upload (sans email)"
)
async def generate_facture_pdf_handler(params: Dict[str, Any]):
    """
    Generate invoice PDF and upload to storage (no email)

    Steps:
    1. Fetch invoice data (Supabase RPC)
    2. Check if PDF already exists (unless force_regenerate)
    3. Generate PDF (document-worker)
    4. Upload PDF (storage-worker or document-worker integrated upload)
    5. Update invoice pdf_status and pdf_url (database-worker)
    """
    facture_id = params["facture_id"]
    force_regenerate = params.get("force_regenerate", False)

    logger.info("workflow_generate_facture_pdf_start", facture_id=facture_id, force=force_regenerate)

    try:
        # Step 1: Fetch invoice
        logger.debug("workflow_step_1_fetch_facture", facture_id=facture_id)
        facture_data = await call_supabase_rpc("get_facture_by_id", {"p_id": facture_id})

        if not facture_data or len(facture_data) == 0:
            raise HTTPException(status_code=404, detail=f"Facture {facture_id} not found")

        facture = facture_data[0] if isinstance(facture_data, list) else facture_data

        # Step 2: Check if PDF already exists
        if not force_regenerate and facture.get("pdf_url") and facture.get("pdf_status") == "generated":
            logger.info("workflow_pdf_already_exists", pdf_url=facture["pdf_url"])
            return {
                "success": True,
                "facture_id": facture_id,
                "pdf_url": facture["pdf_url"],
                "pdf_status": "generated",
                "message": "PDF already exists (use force_regenerate=true to regenerate)"
            }

        # Step 3: Determine payment flag for document-worker
        payment_status = facture.get("payment_status", "unpaid")
        is_paid = payment_status == "paid"
        qualification_id = facture.get("qualification_id")

        if not qualification_id:
            raise HTTPException(
                status_code=400,
                detail=f"Facture {facture_id} has no qualification_id"
            )

        logger.debug(
            "workflow_step_3_generate_pdf",
            facture_id=facture_id,
            payment_status=payment_status,
            qualification_id=qualification_id,
            is_paid=is_paid
        )

        # Call document-worker with current API schema
        pdf_result = await call_document_worker(
            "/generate/facture",
            {
                "request_id": request_id_ctx.get() or str(uuid.uuid4()),
                "qualification_id": qualification_id,
                "is_paid": is_paid,
                "send_email": False
            }
        )

        pdf_base64 = pdf_result.get("pdf_base64")
        # Use .strip() to handle empty strings ("" is truthy but useless)
        numero_facture = (
            (facture.get("numero_facture") or "").strip()
            or pdf_result.get("facture_numero")
            or str(facture_id)
        )
        created_at = facture.get("created_at") or ""
        year = str(created_at)[:4] if created_at else str(datetime.utcnow().year)

        if not pdf_base64:
            raise HTTPException(
                status_code=500,
                detail="PDF generated but no pdf_base64 returned from document-worker"
            )

        # Step 4: Upload PDF to storage-worker
        filename = f"{numero_facture}.pdf"
        # Combine year folder + filename into a single path
        storage_path = f"{year}/{filename}"
        upload_result = await call_storage_worker(
            "/upload/base64",
            {
                "bucket": "factures",
                "filename": filename,
                "content": pdf_base64,
                "content_type": "application/pdf",
                "path": storage_path,
                "upsert": "true",
                "request_id": request_id_ctx.get() or str(uuid.uuid4())
            },
            use_form_data=True
        )

        pdf_url = upload_result.get("public_url") or upload_result.get("url") or upload_result.get("signed_url")

        if not pdf_url:
            raise HTTPException(
                status_code=500,
                detail="PDF uploaded but no URL returned from storage-worker"
            )

        # Step 5: Update invoice status in DB
        logger.debug("workflow_step_5_update_status", facture_id=facture_id, pdf_url=pdf_url)
        await call_database_worker(
            f"/facture/{facture_id}",
            {
                "pdf_status": "generated",
                "pdf_url": pdf_url
            },
            method="PUT",
            require_validation=False
        )

        logger.info(
            "workflow_generate_facture_pdf_complete",
            facture_id=facture_id,
            pdf_url=pdf_url
        )

        return {
            "success": True,
            "facture_id": facture_id,
            "pdf_url": pdf_url,
            "pdf_status": "generated",
            "numero_facture": numero_facture
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "workflow_generate_facture_pdf_failed",
            facture_id=facture_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate facture PDF: {str(e)}"
        )


@register_tool(
    name="create_and_send_facture",
    category=ToolCategory.WORKFLOW,
    description_short="Cree facture puis genere et envoie PDF"
)
async def create_and_send_facture_handler(params: Dict[str, Any]):
    """
    Complete workflow: Create invoice -> Generate PDF -> Upload -> Send email

    Combines create_facture + send_facture_email into one operation
    """
    logger.info("workflow_create_and_send_facture_start")

    try:
        # Step 1: Create invoice (local handler)
        logger.debug("workflow_step_1_create_facture")
        facture_result = await create_facture_handler({
            "qualification_id": params["qualification_id"],
            "montant": params["montant"],
            "description": params.get("description"),
            "date_emission": params.get("date_emission"),
            "date_echeance": params.get("date_echeance")
        })

        facture_id = facture_result.get("facture_id")

        if not facture_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to create invoice: no facture_id returned"
            )

        # Step 2: Send (cross-domain import from communications)
        from tools.communications import send_facture_email_handler

        logger.debug("workflow_step_2_send_facture", facture_id=facture_id)
        send_result = await send_facture_email_handler({
            "facture_id": facture_id,
            "recipient_email": params.get("recipient_email"),
            "message": params.get("message")
        })

        logger.info("workflow_create_and_send_facture_complete", facture_id=facture_id)

        return {
            **send_result,
            "facture_id": facture_id,
            "created": True
        }

    except Exception as e:
        logger.error(
            "workflow_create_and_send_facture_error",
            error=str(e),
            error_type=type(e).__name__
        )
        raise


# ============================================================================
# SCHEMA REGISTRY
# ============================================================================

FACTURE_SCHEMAS = {
    "search_factures": SEARCH_FACTURES_SCHEMA,
    "get_facture_by_id": GET_FACTURE_BY_ID_SCHEMA,
    "create_facture": CREATE_FACTURE_SCHEMA,
    "update_facture": UPDATE_FACTURE_SCHEMA,
    "delete_facture": DELETE_FACTURE_SCHEMA,
    "generate_facture_pdf": GENERATE_FACTURE_PDF_SCHEMA,
    "create_and_send_facture": CREATE_AND_SEND_FACTURE_SCHEMA,
}
