"""
Workflows - Orchestration Multi-Domaine

Workflows complexes orchestrant plusieurs domaines métier :
- generate_facture_pdf (factures → document → storage)
- create_and_send_facture (factures → communication)
- send_facture_email (factures → document → storage → email)
- generate_monthly_report (factures + analytics → document → storage → email)

PRINCIPE : Ce domaine IMPORTE des autres domaines (unidirectionnel).
Les domaines métier (entreprises, factures, etc.) ne doivent JAMAIS importer workflows.
"""

import asyncio
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
    call_email_worker,
)
from middleware import request_id_ctx

# CROSS-DOMAIN IMPORTS (top-level, explicit)
# These imports are SAFE because workflows is imported LAST in tools/__init__.py
from tools.factures import create_facture_handler

logger = structlog.get_logger()


# ============================================================================
# SCHEMAS
# ============================================================================

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

SEND_FACTURE_EMAIL_SCHEMA = ToolSchema(
    name="send_facture_email",
    description="Workflow complet : Genere PDF de facture -> Upload -> Envoie email au client. Retourne URL du PDF et statut d'envoi.",
    input_schema={
        "type": "object",
        "properties": {
            "facture_id": {
                "type": "string",
                "description": "UUID de la facture a envoyer (requis)"
            },
            "recipient_email": {
                "type": "string",
                "description": "Email du destinataire (optionnel, utilise email entreprise si absent)"
            },
            "message": {
                "type": "string",
                "description": "Message personnalise a inclure dans l'email (optionnel)"
            }
        },
        "required": ["facture_id"]
    },
    category="workflow"
)

GENERATE_MONTHLY_REPORT_SCHEMA = ToolSchema(
    name="generate_monthly_report",
    description="Genere rapport mensuel : Fetch stats revenus + factures impayees -> Genere PDF -> Upload. Retourne URL du rapport PDF.",
    input_schema={
        "type": "object",
        "properties": {
            "year": {
                "type": "integer",
                "description": "Annee du rapport (ex: 2025)"
            },
            "month": {
                "type": "integer",
                "description": "Mois du rapport (1-12)"
            },
            "send_email": {
                "type": "boolean",
                "description": "Envoyer le rapport par email apres generation (defaut: false)",
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
# HANDLERS
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
    3. Generate PDF (document-worker) - API: base64 format
    4. Upload PDF (storage-worker) - API: base64 upload
    5. Update invoice pdf_status and pdf_url (database-worker)
    
    NOTE: This workflow uses document-worker API returning pdf_base64.
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

        # Call document-worker with current API schema (base64 API)
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

        # Step 4: Upload PDF to storage-worker (base64 upload API)
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

    Combines create_facture + send_facture_email into one operation.
    Orchestrates cross-domain handlers (factures + communication).

    HITL Integration:
    - Validates if human approval required (amount > threshold, new client)
    - If required, pauses workflow and sends Telegram notification
    - Resumes automatically after webhook response
    """
    logger.info("workflow_create_and_send_facture_start")

    try:
        # HITL: Check if validation required
        from utils.hitl import needs_hitl_validation, perform_human_validation

        if await needs_hitl_validation("create_and_send_facture", params):
            logger.info("workflow_hitl_validation_required")

            # Prepare validation context
            validation_context = {
                "montant": f"{params.get('montant', 0)} EUR",
                "qualification_id": params.get("qualification_id"),
                "description": params.get("description", "N/A")
            }

            # Pause workflow and request human validation
            return await perform_human_validation(
                workflow_name="create_and_send_facture",
                tool_name="create_and_send_facture",
                params=params,
                validation_context=validation_context
            )

        # Continue normal workflow if no validation required
        # Step 1: Create invoice (import from factures domain - top-level import)
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

        # Step 2: Send (call local workflow handler - same file)
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


@register_tool(
    name="send_facture_email",
    category=ToolCategory.WORKFLOW,
    description_short="Genere PDF facture, upload et envoie email"
)
async def send_facture_email_handler(params: Dict[str, Any]):
    """
    Complete workflow: Fetch invoice -> Generate PDF -> Upload -> Send email -> Update status

    Steps:
    1. Fetch invoice data (Supabase RPC)
    2. Fetch company email if not provided (Supabase RPC)
    3. Generate PDF (document-worker) - API: file_path format
    4. Upload PDF (storage-worker) - API: file_path upload
    5. Send email (email-worker)
    6. Update invoice pdf_status (database-worker)
    
    NOTE: This workflow uses document-worker API returning file_path (different from generate_facture_pdf).
    """
    facture_id = params["facture_id"]
    recipient_email = params.get("recipient_email")
    message = params.get("message", "")

    logger.info("workflow_send_facture_email_start", facture_id=facture_id)

    try:
        # Step 1: Fetch invoice
        logger.debug("workflow_step_1_fetch_facture", facture_id=facture_id)
        facture = await call_supabase_rpc("get_facture_by_id", {"p_id": facture_id})

        if not facture:
            raise HTTPException(status_code=404, detail=f"Facture {facture_id} not found")

        # Step 2: Fetch email if not provided
        if not recipient_email:
            logger.debug("workflow_step_2_fetch_email", entreprise_id=facture.get("entreprise_id"))
            entreprise = await call_supabase_rpc(
                "get_entreprise_by_id",
                {"p_id": facture["entreprise_id"]}
            )
            recipient_email = entreprise.get("email")

            if not recipient_email:
                raise HTTPException(
                    status_code=400,
                    detail="No email address found for this company"
                )

        # Step 3: Determine template based on payment status
        payment_status = facture.get("payment_status", "unpaid")
        template = "facture_acquittee" if payment_status == "paid" else "facture_emise"

        logger.debug(
            "workflow_step_3_generate_pdf",
            facture_id=facture_id,
            payment_status=payment_status,
            template=template
        )

        # Call document-worker with current API schema (file_path API - different from generate_facture_pdf)
        pdf_result = await call_document_worker(
            "/generate/facture",
            {
                "facture_id": facture_id,
                "template": template  # facture_emise or facture_acquittee
            }
        )

        # Step 4: Upload PDF (file_path upload API - different from generate_facture_pdf)
        logger.debug("workflow_step_4_upload_pdf", file_path=pdf_result.get("file_path"))
        upload_result = await call_storage_worker(
            "/upload",
            {
                "bucket": "factures",
                "file_path": pdf_result["file_path"],
                "destination": f"factures/{facture.get('numero', facture_id)}.pdf"
            }
        )

        # Step 5: Send email
        logger.debug("workflow_step_5_send_email", recipient=recipient_email)
        email_result = await call_email_worker(
            "/send",
            {
                "to": recipient_email,
                "subject": f"Facture {facture.get('numero', facture_id)}",
                "template": "facture",
                "message": message,
                "attachments": [upload_result["public_url"]]
            }
        )

        # Step 6: Update invoice status
        logger.debug("workflow_step_6_update_status", facture_id=facture_id)
        await call_database_worker(
            f"/facture/{facture_id}",
            {
                "pdf_status": "sent",
                "pdf_url": upload_result["public_url"]
            },
            method="PUT",
            require_validation=False
        )

        logger.info(
            "workflow_send_facture_email_complete",
            facture_id=facture_id,
            email_sent=email_result.get("success")
        )

        return {
            "success": True,
            "pdf_url": upload_result["public_url"],
            "email_sent": email_result.get("success", False),
            "recipient": recipient_email
        }

    except Exception as e:
        logger.error(
            "workflow_send_facture_email_error",
            facture_id=facture_id,
            error=str(e),
            error_type=type(e).__name__
        )
        raise


@register_tool(
    name="generate_monthly_report",
    category=ToolCategory.WORKFLOW,
    description_short="Genere rapport mensuel PDF avec stats"
)
async def generate_monthly_report_handler(params: Dict[str, Any]):
    """
    Generate monthly report: Fetch stats -> Generate PDF -> Upload -> Optionally email

    Steps:
    1. Calculate date range for month
    2. Fetch revenue stats and unpaid invoices (parallel)
    3. Generate PDF report (document-worker)
    4. Upload PDF (storage-worker)
    5. Optionally send email
    """
    year = params["year"]
    month = params["month"]
    send_email = params.get("send_email", False)
    recipient_email = params.get("recipient_email")

    logger.info("workflow_generate_monthly_report_start", year=year, month=month)

    try:
        # Step 1: Calculate date range
        from datetime import date
        import calendar

        start_date = date(year, month, 1).isoformat()
        last_day = calendar.monthrange(year, month)[1]
        end_date = date(year, month, last_day).isoformat()

        logger.debug("workflow_step_1_date_range", start_date=start_date, end_date=end_date)

        # Step 2: Fetch stats and unpaid invoices in parallel
        logger.debug("workflow_step_2_fetch_stats")
        stats, unpaid = await asyncio.gather(
            call_supabase_rpc("get_revenue_stats", {
                "p_start_date": start_date,
                "p_end_date": end_date
            }),
            call_supabase_rpc("get_unpaid_factures", {"p_limit": 100})
        )

        # Step 3: Generate PDF
        logger.debug("workflow_step_3_generate_pdf")
        pdf_result = await call_document_worker(
            "/generate/report",
            {
                "year": year,
                "month": month,
                "stats": stats,
                "unpaid": unpaid
            }
        )

        # Step 4: Upload PDF
        logger.debug("workflow_step_4_upload_pdf")
        upload_result = await call_storage_worker(
            "/upload",
            {
                "bucket": "reports",
                "file_path": pdf_result["file_path"],
                "destination": f"reports/monthly_{year}_{month:02d}.pdf"
            }
        )

        result = {
            "success": True,
            "pdf_url": upload_result["public_url"],
            "year": year,
            "month": month,
            "stats": stats
        }

        # Step 5: Optionally send email
        if send_email:
            if not recipient_email:
                raise HTTPException(
                    status_code=400,
                    detail="recipient_email required when send_email=true"
                )

            logger.debug("workflow_step_5_send_email", recipient=recipient_email)
            email_result = await call_email_worker(
                "/send",
                {
                    "to": recipient_email,
                    "subject": f"Rapport mensuel {month}/{year}",
                    "template": "monthly_report",
                    "attachments": [upload_result["public_url"]]
                }
            )

            result["email_sent"] = email_result.get("success", False)
            result["recipient"] = recipient_email

        logger.info("workflow_generate_monthly_report_complete", year=year, month=month)

        return result

    except Exception as e:
        logger.error(
            "workflow_generate_monthly_report_error",
            year=year,
            month=month,
            error=str(e),
            error_type=type(e).__name__
        )
        raise


# ============================================================================
# SCHEMA REGISTRY
# ============================================================================

WORKFLOW_SCHEMAS = {
    "generate_facture_pdf": GENERATE_FACTURE_PDF_SCHEMA,
    "create_and_send_facture": CREATE_AND_SEND_FACTURE_SCHEMA,
    "send_facture_email": SEND_FACTURE_EMAIL_SCHEMA,
    "generate_monthly_report": GENERATE_MONTHLY_REPORT_SCHEMA,
}


__all__ = ["WORKFLOW_SCHEMAS"]
