# Plan de Refactorisation : Extraction des Workflows Cross-Domaine

## 🎯 Objectif

Isoler tous les workflows complexes (multi-domaine) dans `tools/workflows.py` pour :
- ✅ Éliminer dépendances circulaires
- ✅ Clarifier ownership des tools
- ✅ Faciliter maintenance et évolution
- ✅ Éviter bugs subtils de routing

---

## 📊 État Actuel

### Workflows identifiés (4 tools WORKFLOW)

| Tool | Localisation Actuelle | Domaines Touchés | Problème |
|------|----------------------|------------------|----------|
| **generate_facture_pdf** | `tools/factures.py` | factures (document, storage) | ⚠️ Appelle workers externes |
| **create_and_send_facture** | `tools/factures.py` | **factures + communications** | 🔴 Cross-domain import |
| **send_facture_email** | `tools/communications.py` | factures + communications | ⚠️ Dépend facture data |
| **generate_monthly_report** | `tools/communications.py` | factures + analytics | ⚠️ Cross-domain stats |

### Dépendances Inter-Domaines Actuelles

```python
# tools/factures.py (ligne 515)
from tools.communications import send_facture_email_handler  # 🔴 PROBLÈME

# tools/communications.py (ligne 180)
# Implicitement dépend de facture_id (données factures)
```

---

## 🚨 Problèmes Identifiés

### 1. Cross-Domain Import Dynamique
```python
# tools/factures.py - create_and_send_facture_handler()
from tools.communications import send_facture_email_handler  # Inside function!
```

**Risques** :
- Import circulaire potentiel
- Cache d'imports Python peut causer bugs subtils
- Tests difficiles (mocker 2 domaines)

### 2. Ambiguïté d'Ownership

```
Question : "create_and_send_facture appartient à quel domaine ?"
- factures.py ? (car il crée une facture)
- communications.py ? (car il envoie un email)
- Les deux ? ❌ Confusion
```

### 3. Couplage Fort

```python
# Si communications.send_facture_email change sa signature
# → factures.create_and_send_facture break
```

### 4. Découverte Bot Limitée

```
Bot voit : "create_and_send_facture" dans domaine "factures"
Bot ne sait pas : "Ça appelle aussi communications"
```

---

## ✅ Solution : Domaine `workflows.py`

### Architecture Proposée

```
tools/
├── entreprises.py       ✅ Pure CRUD entreprises
├── qualifications.py    ✅ Pure CRUD qualifications
├── factures.py          ✅ Pure CRUD factures (SANS workflows)
├── paiements.py         ✅ Pure payment tools
├── communications.py    ✅ Pure email/notif (SANS workflows)
├── analytics.py         ✅ Pure analytics
└── workflows.py         🆕 ORCHESTRATION CROSS-DOMAINE
    ├── generate_facture_pdf
    ├── create_and_send_facture
    ├── send_facture_email
    └── generate_monthly_report
```

**Principes** :
- ✅ Domaines métier = tools ATOMIQUES (1 domaine = 1 responsabilité)
- ✅ `workflows.py` = ORCHESTRATION (multi-domaine autorisé)
- ✅ Imports unidirectionnels : `workflows.py` → autres (jamais inverse)

---

## 📋 Plan d'Action Détaillé

### Phase 1 : Créer `tools/workflows.py` (nouveau fichier)

**Contenu** :

```python
"""
Workflows - Orchestration Multi-Domaine

Workflows complexes orchestrant plusieurs domaines :
- generate_facture_pdf (factures → document → storage)
- create_and_send_facture (factures → workflows)
- send_facture_email (factures → document → storage → email)
- generate_monthly_report (factures + analytics → document → storage → email)

Principe : Ce domaine IMPORTE des autres, jamais l'inverse.
"""

from typing import Dict, Any
import asyncio
import structlog

from tools.base import (
    ToolSchema,
    register_tool,
    ToolCategory,
    call_supabase_rpc,
    call_document_worker,
    call_storage_worker,
    call_email_worker,
)
from fastapi import HTTPException

# IMPORTS CROSS-DOMAINE (explicites, au top du fichier)
from tools.factures import create_facture_handler, get_facture_by_id_handler

logger = structlog.get_logger()


# ============================================================================
# SCHEMAS
# ============================================================================

GENERATE_FACTURE_PDF_SCHEMA = ToolSchema(
    name="generate_facture_pdf",
    description="...",
    input_schema={...},
    category="workflow"
)

CREATE_AND_SEND_FACTURE_SCHEMA = ToolSchema(...)
SEND_FACTURE_EMAIL_SCHEMA = ToolSchema(...)
GENERATE_MONTHLY_REPORT_SCHEMA = ToolSchema(...)

WORKFLOW_SCHEMAS = {
    "generate_facture_pdf": GENERATE_FACTURE_PDF_SCHEMA,
    "create_and_send_facture": CREATE_AND_SEND_FACTURE_SCHEMA,
    "send_facture_email": SEND_FACTURE_EMAIL_SCHEMA,
    "generate_monthly_report": GENERATE_MONTHLY_REPORT_SCHEMA,
}


# ============================================================================
# HANDLERS
# ============================================================================

@register_tool(
    name="generate_facture_pdf",
    category=ToolCategory.WORKFLOW,
    description_short="Genere PDF facture et upload"
)
async def generate_facture_pdf_handler(params: Dict[str, Any]):
    """Generate PDF for existing invoice"""
    # [Code migré depuis factures.py]
    ...


@register_tool(
    name="create_and_send_facture",
    category=ToolCategory.WORKFLOW,
    description_short="Cree + genere + envoie facture"
)
async def create_and_send_facture_handler(params: Dict[str, Any]):
    """Orchestrate: create facture → generate PDF → send email"""
    
    # Step 1: Create (appel direct, import top-level)
    facture_result = await create_facture_handler(params)
    facture_id = facture_result["facture_id"]
    
    # Step 2: Send (appel LOCAL - même fichier)
    send_result = await send_facture_email_handler({
        "facture_id": facture_id,
        "recipient_email": params.get("recipient_email")
    })
    
    return {**send_result, "facture_id": facture_id, "created": True}


@register_tool(
    name="send_facture_email",
    category=ToolCategory.WORKFLOW,
    description_short="Genere PDF + envoie email facture"
)
async def send_facture_email_handler(params: Dict[str, Any]):
    """Orchestrate: generate PDF → upload → send email"""
    # [Code migré depuis communications.py]
    ...


@register_tool(
    name="generate_monthly_report",
    category=ToolCategory.WORKFLOW,
    description_short="Genere rapport mensuel stats"
)
async def generate_monthly_report_handler(params: Dict[str, Any]):
    """Orchestrate: fetch stats → generate PDF → upload → email (opt)"""
    # [Code migré depuis communications.py]
    ...


__all__ = ["WORKFLOW_SCHEMAS"]
```

---

### Phase 2 : Supprimer Workflows des Domaines Métier

#### 2.1 Modifier `tools/factures.py`

**Supprimer** :
- ❌ `GENERATE_FACTURE_PDF_SCHEMA`
- ❌ `CREATE_AND_SEND_FACTURE_SCHEMA`
- ❌ `generate_facture_pdf_handler()`
- ❌ `create_and_send_facture_handler()`
- ❌ Import dynamique `from tools.communications import ...`

**Garder** :
- ✅ `create_facture_handler()` (handler métier pur)
- ✅ `get_facture_by_id_handler()`
- ✅ Tous les READ/WRITE factures

**Impact** :
```python
# AVANT
FACTURE_SCHEMAS = {
    "search_factures": ...,
    "create_facture": ...,
    "generate_facture_pdf": ...,        # ❌ À supprimer
    "create_and_send_facture": ...,     # ❌ À supprimer
}

# APRÈS
FACTURE_SCHEMAS = {
    "search_factures": ...,
    "create_facture": ...,
    # Workflows moved to workflows.py
}
```

#### 2.2 Modifier `tools/communications.py`

**Supprimer** :
- ❌ `SEND_FACTURE_EMAIL_SCHEMA`
- ❌ `GENERATE_MONTHLY_REPORT_SCHEMA`
- ❌ `send_facture_email_handler()`
- ❌ `generate_monthly_report_handler()`

**Garder** :
- ✅ `list_recent_interactions_handler()` (READ pur)

**Impact** :
```python
# AVANT
COMMUNICATION_SCHEMAS = {
    "list_recent_interactions": ...,
    "send_facture_email": ...,          # ❌ À supprimer
    "generate_monthly_report": ...,     # ❌ À supprimer
}

# APRÈS
COMMUNICATION_SCHEMAS = {
    "list_recent_interactions": ...,
    # Workflows moved to workflows.py
}
```

---

### Phase 3 : Mettre à Jour Aggregation (`tools/__init__.py`)

**Ajouter** :

```python
# Import workflow domain
from tools.workflows import WORKFLOW_SCHEMAS

# Update aggregation
ALL_TOOL_SCHEMAS = {
    **ENTREPRISE_SCHEMAS,
    **QUALIFICATION_SCHEMAS,
    **FACTURE_SCHEMAS,
    **PAIEMENT_SCHEMAS,
    **COMMUNICATION_SCHEMAS,
    **WORKFLOW_SCHEMAS,  # 🆕
}

# Update domain registry
TOOL_DOMAINS = {
    "entreprises": {...},
    "qualifications": {...},
    "factures": {...},
    "paiements": {...},
    "communications": {...},
    "workflows": {  # 🆕
        "description": "Orchestration multi-domaine",
        "tools": list(WORKFLOW_SCHEMAS.keys()),
        "schemas": WORKFLOW_SCHEMAS,
    },
}
```

---

### Phase 4 : Mettre à Jour `mcp_dev_server.py`

**Ajouter** :

```python
# Import tool domains to trigger @register_tool decorators
import tools.entreprises  # noqa: F401
import tools.qualifications  # noqa: F401
import tools.factures  # noqa: F401
import tools.paiements  # noqa: F401
import tools.communications  # noqa: F401
import tools.workflows  # noqa: F401  # 🆕
import tools.analytics  # noqa: F401
```

---

### Phase 5 : Mettre à Jour Tests

**Modifier `test_implementation.py`** :

```python
def test_schemas():
    """Test schemas per domain"""
    from tools.entreprises import ENTREPRISE_SCHEMAS
    from tools.qualifications import QUALIFICATION_SCHEMAS
    from tools.factures import FACTURE_SCHEMAS
    from tools.paiements import PAIEMENT_SCHEMAS
    from tools.communications import COMMUNICATION_SCHEMAS
    from tools.workflows import WORKFLOW_SCHEMAS  # 🆕
    from tools import ALL_TOOL_SCHEMAS

    print(f"   Entreprises schemas: {len(ENTREPRISE_SCHEMAS)}/5")
    print(f"   Qualifications schemas: {len(QUALIFICATION_SCHEMAS)}/3")
    print(f"   Factures schemas: {len(FACTURE_SCHEMAS)}/5")  # 🔄 Was 7, now 5
    print(f"   Paiements schemas: {len(PAIEMENT_SCHEMAS)}/3")
    print(f"   Communications schemas: {len(COMMUNICATION_SCHEMAS)}/1")  # 🔄 Was 3, now 1
    print(f"   Workflows schemas: {len(WORKFLOW_SCHEMAS)}/4")  # 🆕
    print(f"   TOTAL: {len(ALL_TOOL_SCHEMAS)}/21")  # Still 21!

def test_domain_distribution():
    """Test domain distribution"""
    from tools import TOOL_DOMAINS

    expected = {
        "entreprises": 5,
        "qualifications": 3,
        "factures": 5,  # 🔄 Changed from 7
        "paiements": 3,
        "communications": 1,  # 🔄 Changed from 3
        "workflows": 4,  # 🆕 New
    }
    
    for domain, count in expected.items():
        actual = len(TOOL_DOMAINS[domain]["tools"])
        assert actual == count, f"{domain}: expected {count}, got {actual}"
```

---

## 📊 Tableau de Migration

### Avant → Après

| Tool | Avant | Après | Lignes Code |
|------|-------|-------|-------------|
| **generate_facture_pdf** | `factures.py` | `workflows.py` | ~80 lignes |
| **create_and_send_facture** | `factures.py` | `workflows.py` | ~60 lignes |
| **send_facture_email** | `communications.py` | `workflows.py` | ~120 lignes |
| **generate_monthly_report** | `communications.py` | `workflows.py` | ~150 lignes |

**Total migré** : ~410 lignes de code

---

## 🔍 Impacts

### Fichiers Modifiés

| Fichier | Changements | Risque |
|---------|------------|--------|
| `tools/workflows.py` | 🆕 Créé (~450 lignes) | 🟢 Faible |
| `tools/factures.py` | ✂️ Supprimer 2 workflows (~140 lignes) | 🟡 Moyen |
| `tools/communications.py` | ✂️ Supprimer 2 workflows (~270 lignes) | 🟡 Moyen |
| `tools/__init__.py` | ➕ Import WORKFLOW_SCHEMAS (~5 lignes) | 🟢 Faible |
| `mcp_dev_server.py` | ➕ Import tools.workflows (~1 ligne) | 🟢 Faible |
| `test_implementation.py` | 🔄 Mise à jour expected counts (~10 lignes) | 🟢 Faible |

### Breaking Changes

**Aucun** ❌ :
- Tool names : Identiques
- Tool signatures : Identiques
- API HTTP : Inchangée
- MCP protocol : Inchangé

**Changement invisible** pour :
- ✅ Claude Bot (production)
- ✅ Claude Desktop (dev)
- ✅ Utilisateurs finaux

**Changement visible** pour :
- 🔍 Développeurs (code mieux organisé)
- 📊 Tool discovery `/mcp/tools/list` (domaine "workflows" ajouté)

---

## 🧪 Plan de Test

### 1. Tests Unitaires

```bash
# Valider que tout compile
python test_implementation.py

# Vérifier counts
✅ READ tools: 11/11
✅ WRITE tools: 6/6
✅ WORKFLOW tools: 4/4
✅ TOTAL: 21/21

# Vérifier domaines
✅ factures: 5 tools (was 7)
✅ communications: 1 tool (was 3)
✅ workflows: 4 tools (new)
```

### 2. Tests MCP STDIO

```bash
# Démarrer serveur dev
python mcp_dev_server.py

# Vérifier que les 4 workflows sont listés
# - generate_facture_pdf
# - create_and_send_facture
# - send_facture_email
# - generate_monthly_report
```

### 3. Tests Production HTTP

```bash
# Démarrer proxy
python main.py

# Test GET /mcp/tools/list
curl http://localhost:8000/mcp/tools/list \
  -H "Authorization: Bearer $FLOWCHAT_MCP_KEY"

# Vérifier que workflows sont présents avec category="workflow"
```

### 4. Tests E2E

```bash
# Test create_and_send_facture
curl -X POST http://localhost:8000/mcp/tools/call \
  -H "Authorization: Bearer $FLOWCHAT_MCP_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "create_and_send_facture",
    "params": {
      "qualification_id": "...",
      "montant": 1500
    }
  }'

# Vérifier résultat inclut:
# - facture_id
# - pdf_url
# - email_sent
# - created: true
```

---

## ✅ Checklist d'Exécution

### Préparation
- [ ] Backup du code actuel (`git stash` ou `git branch refactor-workflows`)
- [ ] Lire ce plan en entier
- [ ] Comprendre les dépendances

### Phase 1 : Création
- [ ] Créer `tools/workflows.py` avec structure complète
- [ ] Copier les 4 schemas depuis factures.py et communications.py
- [ ] Copier les 4 handlers avec toute la logique
- [ ] Mettre à jour imports (top-level, pas dynamiques)
- [ ] Exporter `WORKFLOW_SCHEMAS` dict

### Phase 2 : Nettoyage Domaines
- [ ] Supprimer workflows de `tools/factures.py`
- [ ] Supprimer workflows de `tools/communications.py`
- [ ] Vérifier que handlers métier restent intacts
- [ ] Vérifier pas d'imports cassés

### Phase 3 : Aggregation
- [ ] Ajouter import dans `tools/__init__.py`
- [ ] Mettre à jour `ALL_TOOL_SCHEMAS`
- [ ] Ajouter entry `TOOL_DOMAINS["workflows"]`

### Phase 4 : MCP STDIO
- [ ] Ajouter import dans `mcp_dev_server.py`

### Phase 5 : Tests
- [ ] Mettre à jour `test_implementation.py` expected counts
- [ ] Lancer `python test_implementation.py` ✅
- [ ] Vérifier tous les tests passent (8/8)

### Phase 6 : Validation
- [ ] Démarrer `mcp_dev_server.py` sans erreurs
- [ ] Démarrer `main.py` sans erreurs
- [ ] Test GET `/mcp/tools/list` retourne 21 tools
- [ ] Test POST `/mcp/tools/call` avec create_and_send_facture

---

## 🎯 Résultat Final

### Structure Finale

```
tools/
├── __init__.py              (registre centralisé)
├── base.py                  (helpers partagés)
├── entreprises.py           (5 tools - pure CRUD)
├── qualifications.py        (3 tools - pure CRUD)
├── factures.py              (5 tools - pure CRUD) ✅ Nettoyé
├── paiements.py             (3 tools - payment)
├── communications.py        (1 tool - notifications) ✅ Nettoyé
├── workflows.py             (4 tools - orchestration) 🆕 Créé
└── analytics.py             (0 tools - placeholder)
```

### Bénéfices

| Bénéfice | Avant | Après |
|----------|-------|-------|
| **Clarté** | Workflows mélangés dans métiers | ✅ Workflows isolés |
| **Dépendances** | Import dynamiques cachés | ✅ Imports explicites top-level |
| **Ownership** | Ambiguï (factures vs communications) | ✅ Clair : workflows.py |
| **Risque circulaire** | 🔴 Possible | ✅ Impossible (imports unidirectionnels) |
| **Maintenabilité** | Modifier workflow = chercher 2 fichiers | ✅ Modifier workflow = 1 fichier |
| **Tests** | Mocker 2 domaines | ✅ Mocker domaines atomiques |
| **Documentation** | Implicite | ✅ Explicite dans workflows.py |

---

## 🚀 Lancer la Migration

**Prêt à exécuter ?**

Options :
1. **Automatique** : "Lance la migration complète"
2. **Étape par étape** : "Commence par Phase 1"
3. **Review** : "Montre-moi d'abord le code de workflows.py"

---

## ⚠️ Rollback Plan

Si problème détecté :

```bash
# Option 1 : Git reset
git reset --hard HEAD

# Option 2 : Git stash pop
git stash pop

# Option 3 : Restaurer backup manuel
```

**Tests critiques avant commit** :
- ✅ `python test_implementation.py` passe
- ✅ `python mcp_dev_server.py` démarre sans erreur
- ✅ `python main.py` démarre sans erreur
- ✅ GET /mcp/tools/list retourne 21 tools
