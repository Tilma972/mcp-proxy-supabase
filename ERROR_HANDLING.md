# Error Handling Strategy

## Problème identifié

Avant cette implémentation, les erreurs de workers étaient opaques pour Claude :
- `RuntimeError: DATABASE_WORKER_URL not configured` → 500 générique
- `httpx.ConnectError` → 500 générique
- Messages cryptiques impossibles à interpréter par Claude Haiku

## Solution implémentée

### 1. Gestion d'erreur intelligente dans `dispatch_tool()`

Le dispatch intercepte maintenant les erreurs techniques et les transforme en messages métier clairs :

#### Worker non configuré → 503 Service Unavailable

```python
RuntimeError("DATABASE_WORKER_URL not configured")
↓
HTTPException(
    status_code=503,
    detail={
        "error": "service_unavailable",
        "message": "Le service d'écriture en base de données est temporairement indisponible. Seules les opérations de lecture sont disponibles.",
        "tool": tool_name,
        "category": "write"
    }
)
```

**Mapping des workers :**
- `DATABASE_WORKER_URL` → "Le service d'écriture en base de données..."
- `DOCUMENT_WORKER_URL` → "Le service de génération de documents PDF..."
- `STORAGE_WORKER_URL` → "Le service de stockage de fichiers..."
- `EMAIL_WORKER_URL` → "Le service d'envoi d'emails..."

#### Erreur de connexion → 503 Service Unavailable

```python
httpx.ConnectError / httpx.ConnectTimeout
↓
HTTPException(
    status_code=503,
    detail={
        "error": "service_unavailable",
        "message": "Un service externe requis pour cette opération est temporairement inaccessible. Veuillez réessayer dans quelques instants.",
        "tool": tool_name,
        "category": tool.category.value
    }
)
```

#### Timeout → 504 Gateway Timeout

```python
httpx.TimeoutException
↓
HTTPException(
    status_code=504,
    detail={
        "error": "gateway_timeout",
        "message": "L'opération a pris trop de temps à s'exécuter. Le service est peut-être surchargé. Veuillez réessayer.",
        "tool": tool_name,
        "category": tool.category.value
    }
)
```

#### Erreurs HTTP des workers → Code d'origine préservé

```python
httpx.HTTPStatusError (4xx/5xx)
↓
HTTPException(
    status_code=<original>,
    detail={
        "error": "worker_error",
        "message": "Le service a retourné une erreur : <détail>",
        "tool": tool_name,
        "category": tool.category.value,
        "worker_detail": <response_json>
    }
)
```

### 2. Erreurs préservées telles quelles

- **422 Validation Error** : Paramètres invalides → reste 422
- **404 Not Found** : Ressource introuvable → reste 404
- **HTTPException** : Toutes les HTTPException explicites sont re-raised

## Workflow recommandé pour le bot Telegram

### Au démarrage du bot (une seule fois)

```python
# Check worker availability at startup
response = requests.get("https://mcp-proxy/health/workers")
available_services = response.json()

# Store in bot state
bot.state.categories = available_services["categories"]
# Example: {"read": True, "write": False, "workflow": False}
```

### Pendant l'exécution (pas de health check)

```python
# Call tool directly - let error messages guide Claude
try:
    response = requests.post(
        "https://mcp-proxy/mcp/tools/call",
        json={"name": "create_facture", "arguments": {...}}
    )
except requests.HTTPError as e:
    if e.response.status_code == 503:
        # Claude receives user-friendly message in e.response.json()["detail"]["message"]
        # Example: "Le service d'écriture en base de données est temporairement indisponible."
        # Claude can relay this to user naturally
        pass
```

## Bénéfices

✅ **Claude comprend les erreurs** : Messages en français, orientés métier  
✅ **Pas d'overhead** : Pas de `/health/workers` avant chaque requête  
✅ **Expérience utilisateur fluide** : Claude peut dire "Le service PDF est indisponible, mais je peux créer la facture en base"  
✅ **Debugging amélioré** : Logs structurés avec `worker_not_configured`, `worker_connection_error`, etc.  

## Exemple de réponse Claude au user Telegram

**Avant** (500 générique) :
```
❌ Une erreur est survenue. Veuillez réessayer plus tard.
```

**Après** (503 avec message clair) :
```
Le service de génération de PDF est temporairement indisponible. 
Je peux créer la facture en base de données, mais la génération 
et l'envoi par email devront attendre que le service soit rétabli.
Voulez-vous créer la facture maintenant ?
```

## Endpoints concernés

- ✅ `POST /mcp/tools/call` : Dispatch avec gestion d'erreur intelligente
- ℹ️ `GET /health/workers` : Usage recommandé uniquement au démarrage

## Implémentation technique

### Fichier : `tools_registry.py`

```python
async def dispatch_tool(tool_name: str, params: Dict[str, Any]) -> Any:
    try:
        result = await tool.handler(params)
        return result
    
    except HTTPException:
        raise  # 422, 404 → préservés
    
    except RuntimeError as e:
        # Map worker config errors → 503 with user message
        
    except (httpx.ConnectError, httpx.ConnectTimeout):
        # Connection errors → 503
        
    except httpx.TimeoutException:
        # Timeouts → 504
        
    except httpx.HTTPStatusError as e:
        # Worker HTTP errors → original code + details
```

### Fichier : `main.py`

```python
@app.get("/health/workers")
async def health_workers():
    """
    USAGE RECOMMENDATIONS:
    - Call this ONCE at bot startup to identify available services
    - Do NOT call before each tool request (adds unnecessary latency)
    - The proxy now returns user-friendly 503 errors when workers are down
    """
```

## Rollback

Si besoin de revenir à l'ancien comportement (erreurs opaques) :

```python
# Dans tools_registry.py, remplacer le try/except par :
try:
    result = await tool.handler(params)
    return result
except Exception as e:
    logger.error("tool_dispatch_error", tool_name=tool_name, error=str(e))
    raise  # Re-raise as-is
```

## Tests

Tous les tests passent (8/8) avec la nouvelle gestion d'erreur :
```bash
python test_implementation.py
# [PASS] All tests passed! Modular architecture is ready.
```
