"""
Emails & notifications - Communications

Schemas et handlers pour les communications :
- list_recent_interactions (READ)
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
    3. Generate PDF (document-worker)
    4. Upload PDF (storage-worker)
    5. Send email (email-worker)
    6. Update invoice pdf_status (database-worker)
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

        pdf_result = await call_document_worker(
            "/generate/facture",
            {
                "facture_id": facture_id,
                "template": template  # facture_emise or facture_acquittee
            }
        )

        # Step 4: Upload PDF
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

COMMUNICATION_SCHEMAS = {
    "list_recent_interactions": LIST_RECENT_INTERACTIONS_SCHEMA,
    "send_facture_email": SEND_FACTURE_EMAIL_SCHEMA,
    "generate_monthly_report": GENERATE_MONTHLY_REPORT_SCHEMA,
}
