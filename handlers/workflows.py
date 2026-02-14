"""
Handlers for WORKFLOW tools (multi-worker orchestration)

Workflows orchestrate multiple worker calls to complete complex operations.
Examples: Generate PDF + Upload + Send Email
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import HTTPException
import structlog

from config import settings
from tools_registry import register_tool, ToolCategory
from utils.http_client import get_shared_client
from utils.retry import retry_with_backoff
from middleware import request_id_ctx

# Import handlers for reuse
from handlers.supabase_read import call_supabase_rpc
from handlers.database_write import call_database_worker

logger = structlog.get_logger()


# ============================================================================
# WORKER CALL HELPERS
# ============================================================================

@retry_with_backoff(max_attempts=3, base_delay=1.0)
async def call_document_worker(endpoint: str, payload: dict) -> dict:
    """Call the document-worker service (PDF generation)"""
    if not settings.document_worker_url:
        raise RuntimeError("DOCUMENT_WORKER_URL not configured")

    client = await get_shared_client()
    url = f"{settings.document_worker_url.rstrip('/')}{endpoint}"

    headers = {
        "Content-Type": "application/json",
        "X-FlowChat-Worker-Auth": settings.worker_auth_key or "",
        "X-Request-ID": request_id_ctx.get()
    }

    logger.debug("document_worker_call", endpoint=endpoint)

    resp = await client.post(url, headers=headers, json=payload, timeout=60.0)
    resp.raise_for_status()

    return resp.json()


@retry_with_backoff(max_attempts=3, base_delay=1.0)
async def call_storage_worker(endpoint: str, payload: dict) -> dict:
    """Call the storage-worker service (file upload)"""
    if not settings.storage_worker_url:
        raise RuntimeError("STORAGE_WORKER_URL not configured")

    client = await get_shared_client()
    url = f"{settings.storage_worker_url.rstrip('/')}{endpoint}"

    headers = {
        "Content-Type": "application/json",
        "X-FlowChat-Worker-Auth": settings.worker_auth_key or "",
        "X-Request-ID": request_id_ctx.get()
    }

    logger.debug("storage_worker_call", endpoint=endpoint)

    resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
    resp.raise_for_status()

    return resp.json()


@retry_with_backoff(max_attempts=3, base_delay=1.0)
async def call_email_worker(endpoint: str, payload: dict) -> dict:
    """Call the email-worker service (email sending)"""
    if not settings.email_worker_url:
        raise RuntimeError("EMAIL_WORKER_URL not configured")

    client = await get_shared_client()
    url = f"{settings.email_worker_url.rstrip('/')}{endpoint}"

    headers = {
        "Content-Type": "application/json",
        "X-FlowChat-Worker-Auth": settings.worker_auth_key or "",
        "X-Request-ID": request_id_ctx.get()
    }

    logger.debug("email_worker_call", endpoint=endpoint)

    resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
    resp.raise_for_status()

    return resp.json()


# ============================================================================
# FACTURE PDF WORKFLOW HANDLERS
# ============================================================================

@register_tool(
    name="generate_facture_pdf",
    category=ToolCategory.WORKFLOW,
    description_short="Génère PDF facture et upload (sans email)"
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

    Returns:
        {
            "success": True,
            "facture_id": "...",
            "pdf_url": "https://...",
            "pdf_status": "generated"
        }
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

        # Step 3: Generate PDF (document-worker with integrated upload)
        logger.debug("workflow_step_3_generate_pdf", facture_id=facture_id)
        
        # Call document-worker with upload=true to get direct URL
        pdf_result = await call_document_worker(
            "/generate/facture",
            {
                "facture_id": facture_id,
                "upload": True,  # Document worker uploads to Supabase directly
                "bucket": "factures"
            }
        )

        pdf_url = pdf_result.get("pdf_url") or pdf_result.get("public_url")

        if not pdf_url:
            raise HTTPException(
                status_code=500,
                detail="PDF generated but no URL returned from document-worker"
            )

        # Step 4: Update invoice status in DB
        logger.debug("workflow_step_4_update_status", facture_id=facture_id, pdf_url=pdf_url)
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
            "numero_facture": facture.get("numero_facture")
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


# ============================================================================
# EMAIL WORKFLOW HANDLERS
# ============================================================================

@register_tool(
    name="send_facture_email",
    category=ToolCategory.WORKFLOW,
    description_short="Génère PDF facture, upload et envoie email"
)
async def send_facture_email_handler(params: Dict[str, Any]):
    """
    Complete workflow: Fetch invoice → Generate PDF → Upload → Send email → Update status

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

        # Step 3: Generate PDF
        logger.debug("workflow_step_3_generate_pdf", facture_id=facture_id)
        pdf_result = await call_document_worker(
            "/generate/facture",
            {"facture_id": facture_id}
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
    name="create_and_send_facture",
    category=ToolCategory.WORKFLOW,
    description_short="Crée facture puis génère et envoie PDF"
)
async def create_and_send_facture_handler(params: Dict[str, Any]):
    """
    Complete workflow: Create invoice → Generate PDF → Upload → Send email

    Combines create_facture + send_facture_email into one operation
    """
    logger.info("workflow_create_and_send_facture_start")

    try:
        # Step 1: Create invoice (import handler to avoid circular dependency)
        from handlers.database_write import create_facture_handler

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

        # Step 2: Send (reuse workflow)
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
# REPORTING WORKFLOW HANDLERS
# ============================================================================

@register_tool(
    name="generate_monthly_report",
    category=ToolCategory.WORKFLOW,
    description_short="Génère rapport mensuel PDF avec stats"
)
async def generate_monthly_report_handler(params: Dict[str, Any]):
    """
    Generate monthly report: Fetch stats → Generate PDF → Upload → Optionally email

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
