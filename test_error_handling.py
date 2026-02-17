"""
Error Handling Examples - What Claude Receives

This file demonstrates the user-friendly error messages that Claude receives
when workers are unavailable. These examples show the actual JSON response
format returned by the proxy.

To test in real conditions:
    1. Start the proxy: uvicorn main:app --reload
    2. Leave a worker URL unconfigured in .env
    3. Call a tool that needs that worker
    4. Observe the 503 response with clear message

For automated testing, use: python test_implementation.py
"""

# Example 1: Database Worker Not Configured
# ==========================================
# Request: POST /mcp/tools/call
# Body: {"name": "create_facture", "arguments": {"entreprise_id": "...", "montant_ht": 1000}}
#
# Response: HTTP 503 Service Unavailable
EXAMPLE_DATABASE_WORKER_ERROR = {
    "detail": {
        "error": "service_unavailable",
        "message": "Le service d'écriture en base de données est temporairement indisponible. Seules les opérations de lecture sont disponibles.",
        "tool": "create_facture",
        "category": "write"
    }
}

# Claude interpretation:
# "Le système de facturation ne peut pas créer de nouvelles factures pour 
#  le moment car le service d'écriture est indisponible. Je peux cependant 
#  consulter les factures existantes. Voulez-vous que je vous affiche les 
#  dernières factures ?"


# Example 2: Document Worker Not Configured
# ==========================================
# Request: POST /mcp/tools/call
# Body: {"name": "generate_facture_pdf", "arguments": {"facture_id": "..."}}
#
# Response: HTTP 503 Service Unavailable
EXAMPLE_DOCUMENT_WORKER_ERROR = {
    "detail": {
        "error": "service_unavailable",
        "message": "Le service de génération de documents PDF est temporairement indisponible. Les opérations de lecture et d'écriture en base restent disponibles.",
        "tool": "generate_facture_pdf",
        "category": "workflow"
    }
}

# Claude interpretation:
# "Je ne peux pas générer le PDF pour le moment car le service de documents 
#  est indisponible. Cependant, je peux créer la facture en base de données. 
#  Voulez-vous que je la crée maintenant, et nous générerons le PDF plus tard ?"


# Example 3: Storage Worker Not Configured
# =========================================
# Request: POST /mcp/tools/call
# Body: {"name": "send_facture_email", "arguments": {"facture_id": "..."}}
#
# Response: HTTP 503 Service Unavailable
EXAMPLE_STORAGE_WORKER_ERROR = {
    "detail": {
        "error": "service_unavailable",
        "message": "Le service de stockage de fichiers est temporairement indisponible. Les opérations de lecture et d'écriture en base restent disponibles.",
        "tool": "send_facture_email",
        "category": "workflow"
    }
}

# Claude interpretation:
# "Le service de stockage est indisponible, je ne peux donc pas uploader 
#  la facture pour l'envoyer par email. Les autres opérations fonctionnent 
#  normalement. Voulez-vous réessayer plus tard ?"


# Example 4: Email Worker Not Configured
# =======================================
# Request: POST /mcp/tools/call
# Body: {"name": "send_facture_email", "arguments": {"facture_id": "..."}}
#
# Response: HTTP 503 Service Unavailable
EXAMPLE_EMAIL_WORKER_ERROR = {
    "detail": {
        "error": "service_unavailable",
        "message": "Le service d'envoi d'emails est temporairement indisponible. Les opérations de lecture et d'écriture en base restent disponibles.",
        "tool": "send_facture_email",
        "category": "workflow"
    }
}

# Claude interpretation:
# "Le service d'envoi d'emails est indisponible pour le moment. Je peux 
#  générer la facture PDF et la sauvegarder, mais l'envoi par email devra 
#  attendre. Voulez-vous continuer quand même ?"


# Example 5: Worker Connection Error (Network Issue)
# ===================================================
# Worker is configured but unreachable (down, network issue, etc.)
#
# Response: HTTP 503 Service Unavailable
EXAMPLE_CONNECTION_ERROR = {
    "detail": {
        "error": "service_unavailable",
        "message": "Un service externe requis pour cette opération est temporairement inaccessible. Veuillez réessayer dans quelques instants.",
        "tool": "create_facture",
        "category": "write"
    }
}

# Claude interpretation:
# "Un service externe est temporairement inaccessible. Pouvez-vous réessayer 
#  dans quelques instants ? Si le problème persiste, je vous suggère de 
#  contacter le support technique."


# Example 6: Worker Timeout
# ==========================
# Worker responds too slowly
#
# Response: HTTP 504 Gateway Timeout
EXAMPLE_TIMEOUT_ERROR = {
    "detail": {
        "error": "gateway_timeout",
        "message": "L'opération a pris trop de temps à s'exécuter. Le service est peut-être surchargé. Veuillez réessayer.",
        "tool": "generate_monthly_report",
        "category": "workflow"
    }
}

# Claude interpretation:
# "La génération du rapport prend trop de temps, le service est peut-être 
#  surchargé. Voulez-vous réessayer ? Si le problème persiste, essayons 
#  de limiter la période du rapport."


# Example 7: Validation Error (User Input)
# =========================================
# User provides invalid parameters
#
# Response: HTTP 422 Unprocessable Entity
EXAMPLE_VALIDATION_ERROR = {
    "detail": [
        {
            "type": "missing",
            "loc": ["body", "montant_ht"],
            "msg": "Field required",
            "input": {"entreprise_id": "..."}
        }
    ]
}

# Claude interpretation:
# "Il me manque le montant HT pour créer la facture. Pouvez-vous me 
#  préciser le montant ?"


# ============================================================================
# COMPARISON: Before vs After Error Handling
# ============================================================================

print("\n" + "=" * 70)
print("ERROR HANDLING - Before vs After")
print("=" * 70)

print("\n📛 BEFORE (Opaque Errors):")
print("   HTTP 500: Internal Server Error")
print("   Body: RuntimeError: DATABASE_WORKER_URL not configured")
print("\n   Claude tells user:")
print("   ❌ 'Une erreur est survenue. Veuillez réessayer plus tard.'")

print("\n✅ AFTER (User-Friendly Errors):")
print("   HTTP 503: Service Unavailable")
print(f"   Body: {EXAMPLE_DATABASE_WORKER_ERROR}")
print("\n   Claude tells user:")
print("   ✅ 'Le service d'écriture en base de données est temporairement")
print("       indisponible. Je peux consulter les factures existantes mais")
print("       pas en créer de nouvelles pour le moment. Que souhaitez-vous faire?'")

print("\n" + "=" * 70)
print("BENEFITS")
print("=" * 70)
print("""
✅ Claude understands what's broken and what still works
✅ Claude can suggest alternatives to the user
✅ User gets actionable information instead of generic errors
✅ Reduces support requests (users know it's temporary)
✅ Improves user experience and trust in the system
""")

print("=" * 70)
print("USAGE RECOMMENDATION")
print("=" * 70)
print("""
1. Bot startup: Call GET /health/workers ONCE to check availability
2. During operation: Let proxy errors guide Claude's responses
3. No health check before each tool call (unnecessary latency)

The proxy now transforms all worker errors into clear 503 messages
that Claude can interpret and relay to users naturally.
""")
