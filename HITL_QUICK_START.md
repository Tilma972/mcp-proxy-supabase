# 🚀 HITL Quick Start Guide

## Installation Rapide (5 minutes)

### 1. Installation des Dépendances

```bash
cd supabase-mcp-proxy
pip install -r requirements.txt
```

### 2. Configuration Automatique

```bash
python setup_webhook.py
```

Le script interactif va :
- ✅ Vérifier votre bot token Telegram
- ✅ Générer un webhook secret sécurisé
- ✅ Configurer le webhook automatiquement
- ✅ Mettre à jour votre fichier .env

**Si vous n'avez pas encore de bot** :
1. Ouvrez Telegram
2. Recherchez `@BotFather`
3. Envoyez `/newbot`
4. Suivez les instructions
5. Copiez le token fourni

### 3. Base de Données

Appliquez le schéma Supabase :

**Option A : SQL Editor**
```sql
-- Ouvrez Supabase Dashboard → SQL Editor
-- Copiez/collez le contenu de : schemas/hitl_requests_schema.sql
-- Exécutez
```

**Option B : CLI**
```bash
supabase db push
```

### 4. Démarrage

```bash
python main.py
```

Vérifiez les logs :
```
✅ telegram_webhook_configured url=https://supabase.dsolution-ia.fr/webhook/telegram
✅ hitl_system_initialized scheduler=active
✅ proxy_starting hitl_enabled=True
```

## Test Rapide

### 1. Via Claude Bot

```
User: Crée une facture de 2500€ pour la qualification abc-123
      Description: Prestation importante

Claude: → Appelle create_and_send_facture
        → HITL détecte montant > 1500€
        → Retourne "Validation en attente"

User reçoit: "⏳ Validation humaine requise. En attente d'approbation"
```

### 2. Sur Telegram

Vous recevez :
```
🔔 **Validation HITL Requise**

**Workflow**: `create_and_send_facture`
Montant: **2500 €**
...

[✅ Approuver] [❌ Rejeter]
```

Cliquez **✅ Approuver**

### 3. Résultat

```
✅ **Validation APPROVE**

**Résultat du workflow:**
{
  "success": true,
  "facture_id": "...",
  "pdf_url": "https://...",
  "email_sent": true
}
```

## Variables d'Environnement Essentielles

Copiez dans votre `.env` :

```bash
# HITL System
TELEGRAM_TOKEN=<votre_token_de_BotFather>
TELEGRAM_WEBHOOK_SECRET=<généré_par_setup_webhook.py>
TELEGRAM_ADMIN_ID=<votre_user_id_telegram>
TELEGRAM_WEBHOOK_URL=https://supabase.dsolution-ia.fr/webhook/telegram

HITL_ENABLED=true
HITL_TIMEOUT_MINUTES=30
HITL_FACTURE_THRESHOLD=1500.0
```

## Obtenir Votre Chat ID

**Méthode simple** :
1. Envoyez `/start` à votre bot
2. Visitez : `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Cherchez `"chat":{"id": 123456789}`
4. C'est votre `TELEGRAM_ADMIN_ID`

## Règles de Validation HITL

Par défaut, validation déclenchée si :

| Règle | Condition | Configurable |
|-------|-----------|--------------|
| **Montant élevé** | Facture > 1500 EUR | ✅ `HITL_FACTURE_THRESHOLD` |
| **Nouveau client** | Première facture entreprise | ❌ (logique code) |
| **Custom** | Ajoutez vos règles | ✅ `utils/hitl.py` |

## Modification des Règles

Éditez `utils/hitl.py`, fonction `needs_hitl_validation()` :

```python
async def needs_hitl_validation(workflow_name: str, params: Dict[str, Any]) -> bool:
    if not settings.hitl_enabled:
        return False

    # Règle 1: Montant
    if params.get("montant", 0) > settings.hitl_facture_threshold:
        return True

    # Règle 2: Nouveau client
    # ... (voir code)

    # ➕ VOTRE RÈGLE ICI
    if params.get("custom_field") == "custom_value":
        logger.info("hitl_required_custom_rule")
        return True

    return False
```

## Troubleshooting

### ❌ "Telegram not configured"

```bash
# Vérifiez .env
grep TELEGRAM .env

# Assurez-vous que :
TELEGRAM_TOKEN=... (non vide)
TELEGRAM_ADMIN_ID=... (non vide)
HITL_ENABLED=true
```

### ❌ Webhook ne reçoit pas les callbacks

```bash
# Vérifiez webhook configuré
curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo

# Doit retourner :
{
  "url": "https://supabase.dsolution-ia.fr/webhook/telegram",
  "pending_update_count": 0
}

# Reconfigurer si nécessaire
python setup_webhook.py
```

### ❌ Notifications non reçues

```bash
# 1. Testez bot actif
curl https://api.telegram.org/bot<TOKEN>/getMe

# 2. Vérifiez chat ID correct
curl https://api.telegram.org/bot<TOKEN>/getUpdates

# 3. Envoyez message test
curl -X POST https://api.telegram.org/bot<TOKEN>/sendMessage \
  -d chat_id=<CHAT_ID> \
  -d text="Test HITL"
```

### ❌ Requêtes timeout immédiatement

```bash
# Vérifiez scheduler actif dans logs
docker logs supabase-mcp-proxy | grep scheduler

# Doit afficher :
hitl_system_initialized scheduler=active

# Tester manuellement timeout
SELECT timeout_expired_hitl_requests();
```

## Monitoring

### Dashboard SQL (Supabase)

```sql
-- Requêtes actives
SELECT * FROM hitl_requests WHERE status = 'pending' ORDER BY created_at DESC;

-- Stats dernières 24h
SELECT 
    status,
    COUNT(*) as count
FROM hitl_requests 
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY status;

-- Temps de réponse moyen
SELECT 
    AVG(EXTRACT(EPOCH FROM (validated_at - created_at))/60) as avg_minutes
FROM hitl_requests
WHERE validated_at IS NOT NULL;
```

### Logs Temps Réel

```bash
# Production (Docker)
docker logs -f supabase-mcp-proxy | grep hitl

# Développement
tail -f logs/proxy.log | grep hitl
```

## Désactiver HITL Temporairement

```bash
# Dans .env
HITL_ENABLED=false

# Redémarrer
python main.py
```

Tous les workflows s'exécutent normalement sans validation.

## Architecture Files

```
supabase-mcp-proxy/
├── schemas/hitl_requests_schema.sql   # DB schema
├── utils/hitl.py                      # Core HITL logic
├── tools/workflows.py                 # Integration + handlers
├── main.py                            # Webhook endpoint
├── config.py                          # Settings
├── setup_webhook.py                   # Setup wizard
├── HITL_IMPLEMENTATION.md             # Full docs
└── HITL_QUICK_START.md               # This file
```

## Support

- 📖 Documentation complète : `HITL_IMPLEMENTATION.md`
- 🐛 Issues : Vérifiez logs avec `grep hitl`
- 📊 Monitoring : SQL queries dans section ci-dessus
- 🔧 Configuration : `setup_webhook.py` pour reconfigurer

---

**Ready to go!** 🚀

Si tout est configuré correctement, créez une facture > 1500 EUR et vous devriez recevoir une notification Telegram immédiatement.
