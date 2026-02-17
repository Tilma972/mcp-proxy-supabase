# Architecture des Tools - Guide pour futurs domaines

## 🏗️ Vue d'ensemble

La nouvelle architecture **co-localise schemas et handlers** par domaine métier dans le dossier `tools/`.

```
tools/
├── __init__.py                (Hub d'agrégation + registration)
├── base.py                    (Classe base + helpers partagés)
├── entreprises.py             (5 tools: search, get, upsert, etc.)
├── qualifications.py          (3 tools: search, create, update)
├── factures.py                (7 tools: search, create, PDF, email)
├── paiements.py               (3 tools: payment tools)
├── communications.py          (3 tools: workflows email)
└── analytics.py               (Placeholder pour futurs tools)
```

---

## 📋 Pattern : Ajouter un nouveau domaine

### Étape 1 : Créer `tools/mon_domaine.py`

```python
"""
Mon Domaine - Description courte

Schemas et handlers pour:
- outil_1 (READ/WRITE/WORKFLOW)
- outil_2
- outil_3
"""

from typing import Dict, Any
from tools.base import (
    ToolSchema,
    register_tool,
    ToolCategory,
    call_supabase_rpc,
    call_database_worker,
    # Import helpers selon vos besoins
)
import structlog

logger = structlog.get_logger()


# ============================================================================
# SCHEMAS
# ============================================================================

OUTIL_1_SCHEMA = ToolSchema(
    name="outil_1",
    description="Description claire de ce que fait l'outil. Quand l'utiliser.",
    input_schema={
        "type": "object",
        "properties": {
            "param_1": {
                "type": "string",
                "description": "Description du paramètre"
            },
            # ... autres paramètres
        },
        "required": ["param_1"]  # Si requis
    },
    category="read"  # ou "write", "workflow"
)

OUTIL_2_SCHEMA = ToolSchema(
    name="outil_2",
    description="...",
    input_schema={...},
    category="write"
)

# Exporter tous les schemas du domaine sous MON_DOMAINE_SCHEMAS
MON_DOMAINE_SCHEMAS = {
    "outil_1": OUTIL_1_SCHEMA,
    "outil_2": OUTIL_2_SCHEMA,
}


# ============================================================================
# HANDLERS
# ============================================================================

@register_tool(
    name="outil_1",
    category=ToolCategory.READ,
    description_short="Description courte pour tool list"
)
async def outil_1_handler(params: Dict[str, Any]):
    """Handler pour outil_1"""
    try:
        # Appeler Supabase RPC
        result = await call_supabase_rpc("rpc_function_name", {
            "param_1": params["param_1"]
        })
        
        logger.info("outil_1_success", param=params["param_1"])
        return result
    
    except Exception as e:
        logger.error("outil_1_error", error=str(e))
        raise


@register_tool(
    name="outil_2",
    category=ToolCategory.WRITE,
    description_short="Description courte pour tool list"
)
async def outil_2_handler(params: Dict[str, Any]):
    """Handler pour outil_2"""
    try:
        # Appeler Database Worker
        result = await call_database_worker(
            endpoint="/mon_domaine/outil_2",
            payload=params,
            method="POST"
        )
        
        logger.info("outil_2_success")
        return result
    
    except Exception as e:
        logger.error("outil_2_error", error=str(e))
        raise


__all__ = ["MON_DOMAINE_SCHEMAS"]
```

### Étape 2 : Enregistrer dans `tools/__init__.py`

Ajouter l'import :

```python
# Dans tools/__init__.py, ajouter:
from tools.mon_domaine import MON_DOMAINE_SCHEMAS

# Mettre à jour ALL_TOOL_SCHEMAS
ALL_TOOL_SCHEMAS = {
    # ... schemas existants ...
    **MON_DOMAINE_SCHEMAS,  # 🆕 Nouveau domaine
}

# Mettre à jour TOOL_DOMAINS (pour discovery/documentation)
TOOL_DOMAINS = {
    # ... domaines existants ...
    "mon_domaine": {
        "description": "Description du domaine",
        "tools": list(MON_DOMAINE_SCHEMAS.keys()),
        "schemas": MON_DOMAINE_SCHEMAS,
    },
}
```

### Étape 3 : Importer dans `mcp_dev_server.py`

```python
# Ajouter import dans mcp_dev_server.py (ligne: import tools.mon_domaine)
import tools.mon_domaine  # noqa: F401
```

### Étape 4 : Tester

```bash
# Lancer les tests
python test_implementation.py

# Vérifier que votre domaine est présent:
# - test_imports() doit passer
# - test_tool_registry() doit compter le nouveau tool
# - test_schemas() doit voir MON_DOMAINE_SCHEMAS
```

---

## 🎯 Conventions à respecter

### Naming

| Élément | Convention | Exemple |
|---------|-----------|---------|
| **Fichier** | `tools/domaine_pluriel.py` | `tools/entreprises.py` |
| **Schema dict** | `{DOMAINE}_SCHEMAS` | `ENTREPRISE_SCHEMAS` |
| **Tool name** | `snake_case` | `search_entreprise` |
| **Handler** | `{tool_name}_handler` | `search_entreprise_handler` |
| **Export** | `__all__ = ["{DOMAINE}_SCHEMAS"]` | - |

### Structure fichier

```python
"""Module docstring avec:
- Domaine
- Description
- List des tools du domaine
"""

# Imports (tools.base, structlog, etc.)
# Logger

# ============================================================================
# SCHEMAS
# ============================================================================
# Définir tous les TOOL_SCHEMA

# Exporter: MON_DOMAINE_SCHEMAS = {...}

# ============================================================================
# HANDLERS
# ============================================================================
# Définir tous les @register_tool handlers

# __all__ = ["MON_DOMAINE_SCHEMAS"]
```

---

## 📁 Exemple complet : `tools/mon_domaine.py`

**Fichier mini** (~80 lignes) :

```python
"""
Trésorerie - Gestion des paiements

Tools:
- register_payment (WRITE)
- get_payment_status (READ)
"""

from typing import Dict, Any
from tools.base import (
    ToolSchema,
    register_tool,
    ToolCategory,
    call_database_worker,
)
import structlog

logger = structlog.get_logger()


# SCHEMAS
REGISTER_PAYMENT_SCHEMA = ToolSchema(
    name="register_payment",
    description="Enregistre un paiement pour une facture",
    input_schema={
        "type": "object",
        "properties": {
            "facture_id": {"type": "string"},
            "amount": {"type": "number"},
            "date": {"type": "string"}
        },
        "required": ["facture_id", "amount"]
    },
    category="write"
)

TRÉSORERIE_SCHEMAS = {"register_payment": REGISTER_PAYMENT_SCHEMA}


# HANDLERS
@register_tool(
    name="register_payment",
    category=ToolCategory.WRITE,
    description_short="Enregistrer un paiement"
)
async def register_payment_handler(params: Dict[str, Any]):
    result = await call_database_worker(
        endpoint="/payment/register",
        payload=params,
        method="POST"
    )
    logger.info("payment_registered", facture_id=params["facture_id"])
    return result


__all__ = ["TRÉSORERIE_SCHEMAS"]
```

---

## 🔍 Vérifier l'intégration

Après ajouter un nouveau domaine, **vérifier** :

```bash
# 1. Les tests passent
$ python test_implementation.py
[PASS] All modules import successfully
[PASS] All 21 tools registered successfully (updated count)
[PASS] All schemas defined successfully (updated count)

# 2. Claude Desktop voit les nouveaux tools
$ python mcp_dev_server.py
# Devrait lister le nouveau tool

# 3. Production fonctionne
$ python main.py
# GET /mcp/tools/list doit inclure les nouveaux tools
```

---

## 🆚 Avant vs Après

### ❌ AVANT (Ancien pattern)

1. Créer schema dans `schemas/read_tools.py` (ou write_tools.py)
2. Créer handler dans `handlers/supabase_read.py` (ou database_write.py)
3. Mettre à jour `tools_registry.py` pour l'import
4. 3 fichiers à modifier ❌

### ✅ APRÈS (Nouveau pattern)

1. Créer `tools/mon_domaine.py` avec schemas + handlers
2. Ajouter import dans `tools/__init__.py`
3. Ajouter import dans `mcp_dev_server.py` (optionnel, pour MCP)
4. 1-2 fichiers à modifier ✅

---

## 📊 Checklist ajouter un nouveau domaine

- [ ] Créer `tools/mon_domaine.py` avec schemas + handlers
- [ ] Exporter `MON_DOMAINE_SCHEMAS` dict
- [ ] Importer dans `tools/__init__.py` → `ALL_TOOL_SCHEMAS`
- [ ] Ajouter entry dans `tools/__init__.py` → `TOOL_DOMAINS`
- [ ] (Optionnel) Importer dans `mcp_dev_server.py`
- [ ] Lancer `python test_implementation.py` ✅
- [ ] Vérifier count tools augmente
- [ ] Tester via `mcp_dev_server.py` ou API

---

## ❓ Questions courantes

**Q: Où mets-je la logique de validation ?**  
A: Voir `utils/validation.py` - centraliser par domaine.

**Q: Comment faire un workflow (multi-step) ?**  
A: Voir `tools/communications.py` - exemple : `send_facture_email` combine plusieurs steps.

**Q: Comment appeler un autre handler ?**  
A: Import direct et appel async.
```python
from tools.factures import create_facture_handler
result = await create_facture_handler({...})
```

**Q: Quand ajouter helpers dans base.py vs tools/mon_domaine.py ?**  
A:
- `base.py` : Helpers **génériques** (call_supabase_rpc, retry, etc.)
- `tools/mon_domaine.py` : Logique **spécifique au domaine**
