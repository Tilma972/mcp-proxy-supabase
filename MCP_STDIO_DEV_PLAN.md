# Plan : Serveur MCP STDIO pour Claude Desktop

## 📋 Problématique

### Situation actuelle
```
Architecture Production:
FlowChat Bot (Telegram)
    ↓ HTTPS
MCP Proxy HTTP-REST (VPS Docker)
    - Authentication: X_PROXY_KEY + FLOWCHAT_MCP_KEY
    - Routes: /mcp/tools/list, /mcp/tools/{name}/schema, /mcp/tools/call
    ↓ HTTPS
Workers (Database, Document, Storage, Email)
```

### Besoin de développement
- **Claude Desktop doit** :
  - 🔍 Voir le code complet du projet
  - 🧪 Lancer des tests de bout en bout (E2E)
  - 🔌 Se connecter au proxy pour tester les tools
  - 📝 Utiliser STDIO (native MCP protocol)

### Limitation actuelle
- ❌ Proxy HTTP-REST n'expose **pas** STDIO
- ❌ Claude Desktop ne peut **pas** utiliser le proxy en dev local
- ❌ Tests E2E manuels, pas automatisés via Claude

---

## ✅ Solution Proposée

### Approche : Serveur MCP STDIO dédié (Développement)

**Principe clé** : Ne **jamais** modifier le proxy HTTP en production

```
DÉVELOPPEMENT (Local):
Claude Desktop (STDIO)
    ↓ MCP Protocol (JSON-RPC over STDIO)
mcp_dev_server.py (nouveau)
    ├── Implémente protocole MCP natif ✅
    ├── Réutilise schemas existants ✅
    ├── Réutilise handlers existants ✅
    └── Se connecte au proxy HTTP local (8000)
        ↓ HTTP localhost
    Votre proxy en localhost:8000

PRODUCTION (Docker/VPS):
FlowChat Bot
    ↓ HTTPS
Proxy HTTP-REST (INCHANGÉ)
    ↓ HTTPS
Workers
```

---

## 🎯 Avantages

| Aspect | Avant | Après |
|--------|-------|-------|
| **Protocole dev** | Aucun (manuel) | MCP STDIO natif ✅ |
| **Accès au code** | ❌ Non | ✅ Claude voit tout |
| **Tests E2E** | Script manuel | ✅ Claude peut orchestrer |
| **Impact production** | - | ✅ Zéro modification |
| **Réutilisation code** | - | ✅ Schemas + handlers |
| **Complexité** | - | ✅ Faible (wrapper) |

---

## 📂 Structure après implémentation

```
supabase-mcp-proxy/
├── main.py                           # Proxy HTTP (INCHANGÉ)
├── mcp_dev_server.py                 # 🆕 Serveur STDIO pour Claude Desktop
├── mcp_dev_client.py                 # 🆕 Client HTTP → Proxy local
├── schemas/                          # Réutilisé
│   ├── __init__.py
│   ├── read_tools.py                 
│   ├── write_tools.py
│   └── workflow_tools.py
├── handlers/                         # Réutilisé
│   ├── supabase_read.py
│   ├── database_write.py
│   └── workflows.py
├── .env.example                      # Inchangé
├── requirements.txt                  # MCP dépendance à ajouter
├── claude-desktop-config.json        # 🆕 Config Claude Desktop (symlink)
└── MCP_STDIO_DEV_PLAN.md            # Ce fichier
```

---

## 🔧 Implémentation détaillée

### Fichier 1: `mcp_dev_server.py` (serveur STDIO)

```python
"""
MCP STDIO Server for Claude Desktop
Wraps HTTP proxy handlers + exposes MCP protocol

Usage:
    python mcp_dev_server.py
    
Connects to: http://localhost:8000 (proxy)
Protocol: JSON-RPC over STDIO
"""

import asyncio
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Réutiliser schemas + handlers
from schemas.read_tools import READ_TOOL_SCHEMAS
from schemas.write_tools import WRITE_TOOL_SCHEMAS
from schemas.workflow_tools import WORKFLOW_TOOL_SCHEMAS
from mcp_dev_client import call_local_proxy

# Initialize MCP server
server = Server("flowchat-dev-mcp")

@server.list_tools()
async def list_tools():
    """List all available FlowChat tools"""
    all_schemas = {
        **READ_TOOL_SCHEMAS,
        **WRITE_TOOL_SCHEMAS,
        **WORKFLOW_TOOL_SCHEMAS
    }
    
    tools: list[Tool] = []
    for name, schema in all_schemas.items():
        tools.append(Tool(
            name=name,
            description=schema.description,
            inputSchema=schema.input_schema
        ))
    
    return tools

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a tool via local HTTP proxy"""
    try:
        result = await call_local_proxy(name, arguments)
        return [TextContent(
            type="text",
            text=str(result)
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error calling {name}: {str(e)}"
        )]

async def main():
    """Run STDIO server"""
    async with stdio_server(server):
        # Keep server running
        await asyncio.sleep(float('inf'))

if __name__ == "__main__":
    asyncio.run(main())
```

### Fichier 2: `mcp_dev_client.py` (client HTTP)

```python
"""
HTTP Client to local proxy
Handles authentication + request/response
"""

import httpx
import os
from typing import Any, Dict

PROXY_URL = os.getenv("DEV_PROXY_URL", "http://localhost:8000")
FLOWCHAT_MCP_KEY = os.getenv("FLOWCHAT_MCP_KEY", "dev-key")

async def call_local_proxy(tool_name: str, params: Dict[str, Any]) -> Any:
    """
    Call tool via local HTTP proxy
    
    Args:
        tool_name: Name of tool to call
        params: Tool parameters
    
    Returns:
        Tool result
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PROXY_URL}/mcp/tools/call",
            json={
                "tool_name": tool_name,
                "params": params
            },
            headers={
                "Authorization": f"Bearer {FLOWCHAT_MCP_KEY}"
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Proxy error: {response.text}")
        
        data = response.json()
        return data.get("result")
```

### Fichier 3: `claude-desktop-config.json`

```json
{
  "mcpServers": {
    "flowchat-dev": {
      "command": "python",
      "args": ["path/to/mcp_dev_server.py"],
      "env": {
        "DEV_PROXY_URL": "http://localhost:8000",
        "FLOWCHAT_MCP_KEY": "dev-key",
        "PYTHONPATH": "."
      }
    }
  }
}
```

**Note** : À ajouter dans `~/.config/Claude/claude_desktop_config.json` (macOS/Linux) ou `%APPDATA%\Claude\claude_desktop_config.json` (Windows)

---

## 🚀 Workflow de développement

### 1️⃣ Setup initial

```bash
# Installer dépendance MCP
pip install mcp

# Copy config
cp claude-desktop-config.json ~/.config/Claude/claude_desktop_config.json

# Démarrer proxy dev
python main.py  # Sur port 8000
```

### 2️⃣ Claude Desktop

```
- Ouvrir Claude Desktop
- Se connecter à "flowchat-dev"
- Voir tous les tools (19)
- Utiliser les outils via STDIO
```

### 3️⃣ Tests E2E

Claude peut maintenant :

```
"Teste la création d'une facture et vérifie..."
Claude Desktop → mcp_dev_server.py (STDIO) → 
    → call_local_proxy → Proxy HTTP (8000) → 
    → handlers → Worker
```

---

## 📊 Phase d'implémentation

| Phase | Fichier | Effort | Notes |
|-------|---------|--------|-------|
| 1 | `mcp_dev_server.py` | 🟢 Faible | ~80 lignes |
| 2 | `mcp_dev_client.py` | 🟢 Faible | ~50 lignes |
| 3 | `claude-desktop-config.json` | 🟢 Minimal | ~15 lignes |
| 4 | `requirements.txt` | 🟢 Minimal | Ajouter `mcp` |
| 5 | Tests E2E | 🟡 Moyen | Création de scénarios |

**Total** : ~2 heures (incluant testing)

---

## ⚠️ Points importants

### ✅ À conserver
- Proxy HTTP en production (INCHANGÉ)
- Schemas + Handlers existants (RÉUTILISÉS)
- Authentication (ajustée pour dev)

### ❌ À éviter
- Modifier `main.py` en production
- Distribuer `mcp_dev_server.py` en prod
- Exposer FLOWCHAT_MCP_KEY dev en prod

### 🔐 Sécurité dev
- `FLOWCHAT_MCP_KEY` peut être générique en dev ("dev-key")
- Proxy local ne nécessite pas HTTPS
- Authentification simplifiée pour localhost

---

## 🎯 Résultat final

**Claude Desktop pourra** :
- ✅ Accéder à tous les 21 tools
- ✅ Lancer des tests E2E orchestrés
- ✅ Voir le code complet du projet
- ✅ Communiquer via MCP STDIO natif
- ✅ Proposer des améliorations basées sur l'architecture

**Sans** :
- ❌ Modifier le proxy production
- ❌ Ajouter de la complexité
- ❌ Risquer la stabilité

---

## ❓ Questions avant implémentation

1. Voulez-vous que je **crée** tous les fichiers (`mcp_dev_server.py`, `mcp_dev_client.py`) ?
2. Quelle **clé dev** préférez-vous pour `FLOWCHAT_MCP_KEY` ?
3. Voulez-vous des **tests E2E** comme modèles pour Claude Desktop ?
4. Faut-il ajouter un **README** pour la setup Claude Desktop ?
