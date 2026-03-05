import re

with open('tools/workflows.py', 'r', encoding='utf-8') as f:
    content = f.read()

SCHEMA_ADD = """
SEND_BON_COMMANDE_EMAIL_SCHEMA = ToolSchema(
    name="send_bon_commande_email",
    description="Workflow complet : Genere le bon de commande PDF -> Upload sur Storage -> Envoie email au client. Met a jour la qualification avec l'url et le statut 'BC envoyé'.",
    input_schema={
        "type": "object",
        "properties": {
            "qualification_id": {
                "type": "string",
                "description": "UUID de la qualification (requis)"
            },
            "recipient_email": {
                "type": "string",
                "description": "Email du destinataire (requis de preference pour garantir l'envoi)"
            },
            "message": {
                "type": "string",
                "description": "Message personnalise dans l'email (optionnel)"
            }
        },
        "required": ["qualification_id", "recipient_email"]
    },
    category="workflow"
)
"""

HANDLER_ADD = """
@register_tool(
    name="send_bon_commande_email",
    category=ToolCategory.WORKFLOW,
    description_short="Genere, upload et envoie le bon de commande par email"
)
async def send_bon_commande_email_handler(params: Dict[str, Any]):
    qualification_id = params["qualification_id"]
    recipient_email = params.get("recipient_email")
    message = params.get("message", "")

    logger.info("workflow_send_bon_commande_email_start", qualification_id=qualification_id)

    try:
        # Step 1: Re-generate or generate PDF via document-worker (it re-uses bc_numero from DB)
        pdf_result = await call_document_worker(
            "/generate/bon-commande",
            {
                "request_id": request_id_ctx.get() or str(uuid.uuid4()),
                "qualification_id": qualification_id,
            }
        )
        
        pdf_base64 = pdf_result.get("pdf_base64")
        if not pdf_base64:
            raise HTTPException(status_code=500, detail="Document worker did not return pdf_base64")
            
        metadata = pdf_result.get("metadata", {})
        bc_numero = pdf_result.get("bc_numero") or metadata.get("bc_numero") or "BC-INCONNU"
        entreprise_nom = metadata.get("annonceur_nom", "Client")
        
        if not recipient_email:
            raise HTTPException(status_code=400, detail="recipient_email is required to send the email.")

        # Step 2: Upload to storage
        year = datetime.now().year
        month = datetime.now().strftime('%m')
        storage_path = f"bon_commandes/{year}/{month}/{bc_numero}.pdf"
        
        upload_result = await call_storage_worker(
            "/upload/base64",
            {
                "request_id": request_id_ctx.get() or str(uuid.uuid4()),
                "bucket": "documents",
                "filename": f"{bc_numero}.pdf",
                "path": storage_path,
                "content": pdf_base64,
                "content_type": "application/pdf",
                "upsert": "true"
            },
            use_form_data=True
        )
        
        pdf_url = upload_result.get("public_url")
        if not pdf_url:
            raise HTTPException(status_code=500, detail="Storage worker did not return public_url")
            
        # Step 3: Send email via email-worker
        await call_email_worker(
            "/send/bon-commande",
            {
                "to": recipient_email,
                "bc_numero": bc_numero,
                "entreprise_nom": entreprise_nom,
                "montant_total": float(metadata.get("prix_total", 0.0)),
                "date_emission": metadata.get("date_generation", datetime.now().strftime("%Y-%m-%d")),
                "date_livraison": metadata.get("mois_parution", ""),
                "pdf_base64": pdf_base64,
                "pdf_filename": f"{bc_numero}.pdf",
                "message": message
            }
        )

        # Step 4: Update database worker
        db_result = await call_database_worker(
            "/qualification/upsert",
            {
                "id": qualification_id,
                "bc_url": pdf_url,
                "bc_numero": bc_numero,
                "statut": "BC envoyé"
            },
            require_validation=False
        )
        
        logger.info("workflow_send_bon_commande_email_complete", qualification_id=qualification_id, url=pdf_url)
        return {
            "success": True,
            "qualification_id": qualification_id,
            "bc_numero": bc_numero,
            "bc_url": pdf_url,
            "recipient_email": recipient_email,
            "message": f"Bon de commande {bc_numero} generé, email envoyé à {recipient_email} et qualif mise à jour."
        }
    except Exception as e:
        logger.error("workflow_send_bon_commande_email_error", error=str(e), qualification_id=qualification_id)
        raise
"""

content = content.replace("GENERATE_BON_COMMANDE_SCHEMA = ToolSchema(", SCHEMA_ADD + "\nGENERATE_BON_COMMANDE_SCHEMA = ToolSchema(")
content = content.replace('@register_tool(\n    name="generate_bon_commande",', HANDLER_ADD + '\n@register_tool(\n    name="generate_bon_commande",')
content = content.replace('    "generate_bon_commande": GENERATE_BON_COMMANDE_SCHEMA,', '    "send_bon_commande_email": SEND_BON_COMMANDE_EMAIL_SCHEMA,\n    "generate_bon_commande": GENERATE_BON_COMMANDE_SCHEMA,')

with open('tools/workflows.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Code patched successfully')
