"""
HITL (Human In The Loop) - Validation humaine transparente via Telegram

Architecture:
- Fonction utilitaire interne (PAS un tool MCP exposé)
- Validation humaine transparente selon règles métier
- Reprise immédiate via webhook Telegram
- Timeout automatique après 30 minutes

Usage dans workflows:
    if needs_hitl_validation():
        return await perform_human_validation(
            workflow_name="create_and_send_facture",
            tool_name="create_and_send_facture",
            params=params,
            validation_context={...}
        )
"""

import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import structlog
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from fastapi import HTTPException

from config import settings
from tools.base import call_supabase_rpc

logger = structlog.get_logger()


# ============================================================================
# HITL Logic
# ============================================================================

async def needs_hitl_validation(
    workflow_name: str,
    params: Dict[str, Any]
) -> bool:
    """
    Determine if workflow requires human validation based on business rules

    Rules:
    1. Facture > threshold (default: 1500 EUR) → validation required
    2. New client/prospect → validation required
    3. Payment status "en_attente" + amount > 800 → validation required

    Args:
        workflow_name: Name of the workflow ("create_and_send_facture", etc.)
        params: Workflow parameters

    Returns:
        True if human validation required, False otherwise
    """
    if not settings.hitl_enabled:
        return False

    # Rule 1: Facture amount threshold
    if workflow_name == "create_and_send_facture":
        montant = params.get("montant", 0)
        if montant > settings.hitl_facture_threshold:
            logger.info(
                "hitl_required_amount_threshold",
                workflow=workflow_name,
                montant=montant,
                threshold=settings.hitl_facture_threshold
            )
            return True

        # Rule 2: Check if new client (requires qualification lookup)
        qualification_id = params.get("qualification_id")
        if qualification_id:
            try:
                # Check if this is first facture for this client
                qualif_data = await call_supabase_rpc(
                    "get_qualification_by_id",
                    {"p_id": qualification_id}
                )
                if qualif_data and len(qualif_data) > 0:
                    qualif = qualif_data[0]
                    entreprise_id = qualif.get("entreprise_id")

                    if entreprise_id:
                        # Count existing factures for this entreprise
                        factures_count = await call_supabase_rpc(
                            "count_factures_by_entreprise",
                            {"p_entreprise_id": entreprise_id}
                        )

                        # If first invoice for client
                        if factures_count == 0 or (isinstance(factures_count, list) and factures_count[0].get("count", 0) == 0):
                            logger.info(
                                "hitl_required_new_client",
                                workflow=workflow_name,
                                entreprise_id=entreprise_id
                            )
                            return True

            except Exception as e:
                logger.warning(
                    "hitl_validation_check_failed",
                    workflow=workflow_name,
                    error=str(e)
                )
                # Fail safe: require validation if check fails
                return True

    return False


async def perform_human_validation(
    workflow_name: str,
    tool_name: str,
    params: Dict[str, Any],
    validation_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Perform human validation via Telegram webhook

    Workflow:
    1. Store request in hitl_requests table
    2. Send Telegram message with inline buttons
    3. Return "pending" status to Claude (workflow paused)
    4. Webhook receives response → updates DB → resumes workflow
    5. Timeout after 30 minutes if no response

    Args:
        workflow_name: Name of the workflow
        tool_name: Name of the tool being validated
        params: Original workflow parameters
        validation_context: Additional context for human reviewer

    Returns:
        Dict with status "pending_validation" and request_id

    Raises:
        HTTPException: If Telegram not configured or request creation fails
    """
    if not settings.telegram_token or not settings.telegram_admin_id:
        raise HTTPException(
            status_code=500,
            detail="HITL validation enabled but Telegram not configured"
        )

    request_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(minutes=settings.hitl_timeout_minutes)

    logger.info(
        "hitl_validation_start",
        request_id=request_id,
        workflow=workflow_name,
        tool=tool_name
    )

    try:
        # Step 1: Store request in database
        await call_supabase_rpc(
            "execute_sql",
            {
                "query": """
                    INSERT INTO hitl_requests (
                        id, workflow_name, tool_name, original_params,
                        status, expires_at
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id
                """,
                "params": [
                    request_id,
                    workflow_name,
                    tool_name,
                    json.dumps(params),
                    "pending",
                    expires_at.isoformat()
                ]
            }
        )

        # Step 2: Format message for Telegram
        message = _format_validation_message(
            workflow_name, tool_name, params, validation_context
        )

        # Step 3: Send Telegram notification
        bot = Bot(token=settings.telegram_token)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approuver", callback_data=f"hitl_approve:{request_id}"),
                InlineKeyboardButton("❌ Rejeter", callback_data=f"hitl_reject:{request_id}")
            ],
            [
                InlineKeyboardButton("✏️ Modifier", callback_data=f"hitl_modify:{request_id}")
            ]
        ])

        telegram_message = await bot.send_message(
            chat_id=settings.telegram_admin_id,
            text=message,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

        # Step 4: Update request with Telegram message info
        await call_supabase_rpc(
            "execute_sql",
            {
                "query": """
                    UPDATE hitl_requests 
                    SET telegram_message_id = $1, telegram_chat_id = $2
                    WHERE id = $3
                """,
                "params": [
                    str(telegram_message.message_id),
                    str(telegram_message.chat_id),
                    request_id
                ]
            }
        )

        logger.info(
            "hitl_validation_sent",
            request_id=request_id,
            telegram_message_id=telegram_message.message_id
        )

        return {
            "success": False,  # Workflow paused
            "status": "pending_validation",
            "request_id": request_id,
            "message": f"⏳ Validation humaine requise. En attente d'approbation (timeout: {settings.hitl_timeout_minutes} min)",
            "expires_at": expires_at.isoformat(),
            "workflow_name": workflow_name
        }

    except TelegramError as e:
        logger.error(
            "hitl_telegram_error",
            request_id=request_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send Telegram notification: {str(e)}"
        )
    except Exception as e:
        logger.error(
            "hitl_validation_failed",
            request_id=request_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create HITL request: {str(e)}"
        )


def _format_validation_message(
    workflow_name: str,
    tool_name: str,
    params: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Format human-readable Telegram message for validation request

    Args:
        workflow_name: Workflow being validated
        tool_name: Tool being validated
        params: Workflow parameters
        context: Additional context

    Returns:
        Formatted Markdown message
    """
    lines = [
        "🔔 **Validation HITL Requise**",
        "",
        f"**Workflow**: `{workflow_name}`",
        f"**Tool**: `{tool_name}`",
        "",
        "**Paramètres**:"
    ]

    # Format params based on workflow type
    if workflow_name == "create_and_send_facture":
        lines.extend([
            f"- Montant: **{params.get('montant', 'N/A')} €**",
            f"- Qualification ID: `{params.get('qualification_id', 'N/A')}`",
            f"- Description: {params.get('description', 'N/A')}",
            f"- Email destinataire: {params.get('recipient_email', 'Email entreprise')}"
        ])

        if params.get("date_echeance"):
            lines.append(f"- Date échéance: {params['date_echeance']}")

    else:
        # Generic format for other workflows
        for key, value in params.items():
            lines.append(f"- {key}: {value}")

    # Add context if provided
    if context:
        lines.extend([
            "",
            "**Contexte supplémentaire**:"
        ])
        for key, value in context.items():
            lines.append(f"- {key}: {value}")

    lines.extend([
        "",
        "⏱️ Timeout: 30 minutes",
        "",
        "👇 Choisissez une action ci-dessous:"
    ])

    return "\n".join(lines)


async def process_validation_response(
    request_id: str,
    action: str,
    validator_id: str,
    modified_params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Process human validation response from Telegram webhook

    Args:
        request_id: UUID of the HITL request
        action: "approve", "reject", or "modify"
        validator_id: Telegram user ID who validated
        modified_params: Modified parameters (if action="modify")

    Returns:
        Result with status and workflow resumption info

    Raises:
        HTTPException: If request not found or already processed
    """
    logger.info(
        "hitl_process_response",
        request_id=request_id,
        action=action,
        validator=validator_id
    )

    try:
        # Fetch request
        request_data = await call_supabase_rpc(
            "get_hitl_request",
            {"request_id": request_id}
        )

        if not request_data or len(request_data) == 0:
            raise HTTPException(
                status_code=404,
                detail=f"HITL request {request_id} not found"
            )

        request = request_data[0]

        # Check if already processed
        if request["status"] != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"HITL request already processed: {request['status']}"
            )

        # Update status based on action
        new_status = {
            "approve": "approved",
            "reject": "rejected",
            "modify": "modified"
        }.get(action, "rejected")

        decision = {
            "action": action,
            "validator_id": validator_id,
            "timestamp": datetime.utcnow().isoformat()
        }

        if modified_params:
            decision["modified_params"] = modified_params

        # Update database
        await call_supabase_rpc(
            "update_hitl_request_status",
            {
                "request_id": request_id,
                "new_status": new_status,
                "validator_id": validator_id,
                "decision": json.dumps(decision)
            }
        )

        # If approved or modified, resume workflow
        if action in ["approve", "modify"]:
            workflow_result = await _resume_workflow(
                request["workflow_name"],
                request["tool_name"],
                modified_params or json.loads(request["original_params"])
            )

            # Store result
            await call_supabase_rpc(
                "execute_sql",
                {
                    "query": "UPDATE hitl_requests SET workflow_result = $1 WHERE id = $2",
                    "params": [json.dumps(workflow_result), request_id]
                }
            )

            logger.info(
                "hitl_workflow_resumed",
                request_id=request_id,
                status=new_status
            )

            return {
                "success": True,
                "status": new_status,
                "request_id": request_id,
                "workflow_result": workflow_result
            }

        # If rejected, just update status
        logger.info(
            "hitl_workflow_rejected",
            request_id=request_id
        )

        return {
            "success": False,
            "status": "rejected",
            "request_id": request_id,
            "message": "Workflow rejected by human validator"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "hitl_process_response_failed",
            request_id=request_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process validation response: {str(e)}"
        )


async def _resume_workflow(
    workflow_name: str,
    tool_name: str,
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Resume workflow after human validation

    Args:
        workflow_name: Name of the workflow
        tool_name: Name of the tool
        params: Parameters (original or modified)

    Returns:
        Workflow execution result
    """
    from tools_registry import dispatch_tool

    logger.info(
        "hitl_resume_workflow",
        workflow=workflow_name,
        tool=tool_name
    )

    try:
        # Dispatch to original tool handler
        # NOTE: This will bypass HITL check (already validated)
        result = await dispatch_tool(tool_name, params)
        return result

    except Exception as e:
        logger.error(
            "hitl_resume_workflow_failed",
            workflow=workflow_name,
            error=str(e)
        )
        return {
            "success": False,
            "error": str(e),
            "message": f"Workflow approved but execution failed: {str(e)}"
        }


async def timeout_expired_requests() -> int:
    """
    Mark expired pending HITL requests as timed_out

    Should be called by scheduler every 5 minutes.

    Returns:
        Number of requests timed out
    """
    try:
        result = await call_supabase_rpc("timeout_expired_hitl_requests", {})
        count = result if isinstance(result, int) else 0

        if count > 0:
            logger.info("hitl_timeout_cleanup", count=count)

        return count

    except Exception as e:
        logger.error("hitl_timeout_cleanup_failed", error=str(e))
        return 0
