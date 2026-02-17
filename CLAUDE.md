# FlowChat MCP Unified Proxy - Project Documentation

## Project Overview

This is a **unified MCP (Model Context Protocol) proxy** that centralizes access to FlowChat CRM tools for the Claude API. It solves a critical token budget problem by reducing tool definitions from 51,000 tokens to ~2,000 tokens.

**Purpose**: Enable a Telegram bot (FlowChat CRM for firefighters) to use Claude API effectively by exposing 21 tools through a single MCP server instead of defining them directly in each API call.

**Status**: Modular architecture (Phase 6), ready for runtime testing with workers.

---

## Architecture

### High-Level Design

```
Claude API (Bot)
    ↓ (MCP SSE connection)
Supabase MCP Proxy (this project)
    ↓ (REST calls)
FlowChat Workers (4 services)
    ↓ (Database operations)
Supabase Database
```

### Core Components

1. **Supabase Proxy** (existing functionality - UNCHANGED)
   - Route: `/mcp/{path:path}`
   - Proxies SSE and REST requests to Supabase MCP
   - Authentication: `X-Proxy-Key`

2. **FlowChat MCP Tools** (modular domain architecture)
   - Routes: `/mcp/tools/list`, `/mcp/tools/{name}/schema`, `/mcp/tools/call`
   - Exposes 21 tools (11 READ, 6 WRITE, 4 WORKFLOW) across 5 domains
   - Authentication: `FLOWCHAT_MCP_KEY`

3. **Worker Integration**
   - Database Worker (validation + persistence)
   - Document Worker (PDF generation)
   - Storage Worker (file upload)
   - Email Worker (email sending)

---

## Project Structure

```
supabase-mcp-proxy/
├── main.py                    # FastAPI app, routes, lifecycle
├── config.py                  # Settings (Pydantic BaseSettings)
├── auth.py                    # Authentication (verify_proxy_key, verify_flowchat_mcp_key)
├── middleware.py              # RequestIDMiddleware (ContextVar tracking)
├── tools_registry.py          # Tool registration & dispatch system
│
├── tools/                     # Modular domain-based tools (schemas + handlers)
│   ├── __init__.py           # Registration hub, ALL_TOOL_SCHEMAS export
│   ├── base.py               # ToolSchema class + worker call helpers
│   ├── entreprises.py        # Gestion clients (5 tools)
│   ├── qualifications.py     # Gestion commerciale (3 tools)
│   ├── factures.py           # Facturation (7 tools)
│   ├── paiements.py          # Tresorerie (3 tools)
│   ├── communications.py     # Emails & notifications (3 tools)
│   └── analytics.py          # Reporting (placeholder futur)
│
├── utils/                     # Shared utilities
│   ├── __init__.py
│   ├── http_client.py        # Shared AsyncClient (connection pooling)
│   └── retry.py              # Exponential backoff decorator
│
├── test_implementation.py     # Verification tests (6 tests)
├── requirements.txt           # Dependencies
├── .env.example              # Configuration template
├── Dockerfile                # Container build
├── IMPLEMENTATION.md         # Detailed implementation docs
├── COMPLETION_SUMMARY.md     # Status & metrics
└── CLAUDE.md                 # This file
```

---

## Key Concepts

### 1. Tool Registration Pattern (Modular)

Each domain file contains both schemas AND handlers:

```python
# tools/entreprises.py
from tools.base import ToolSchema, register_tool, ToolCategory, call_supabase_rpc

# Schema
SEARCH_ENTREPRISE_SCHEMA = ToolSchema(
    name="search_entreprise_with_stats",
    description="Recherche entreprise par nom avec statistiques...",
    input_schema={...},
    category="read"
)

# Handler
@register_tool(
    name="search_entreprise_with_stats",
    category=ToolCategory.READ,
    description_short="Recherche entreprise par nom avec statistiques"
)
async def search_entreprise_with_stats_handler(params: Dict[str, Any]):
    return await call_supabase_rpc("search_entreprise_with_stats", {
        "p_search_term": params["search_term"],
        "p_limit": params.get("limit", 10)
    })

# Domain schema registry
ENTREPRISE_SCHEMAS = {
    "search_entreprise_with_stats": SEARCH_ENTREPRISE_SCHEMA,
    ...
}
```

**How it works**:
- Each domain file groups schemas + handlers for a business domain
- `tools/__init__.py` imports all domains, triggering `@register_tool` decorators
- `ALL_TOOL_SCHEMAS` aggregates all domain schemas for the MCP protocol
- `dispatch_tool()` routes tool calls via the global `TOOL_REGISTRY`

### 2. Request ID Propagation

Every request gets a unique UUID tracked via `ContextVar`:

```python
from middleware import request_id_ctx

# In handler
request_id = request_id_ctx.get()  # Auto-set by middleware

# Propagate to workers
headers = {"X-Request-ID": request_id}
```

**Why**: Enables tracing a request across multiple layers (proxy → handler → worker → database)

### 3. Validation Enforcement (WRITE tools)

**CRITICAL**: All WRITE operations MUST check the `validated` flag:

```python
async def call_database_worker(endpoint, payload, require_validation=True):
    resp = await client.post(url, json=payload)
    data = resp.json()

    # CRITICAL: Enforce validation
    if require_validation and not data.get("validated", False):
        raise HTTPException(422, detail=f"Validation failed: {data.get('discrepancies')}")

    return data
```

**Why**: Prevents silent data corruption. Database-worker validates data before persistence.

### 4. Retry Logic

Network calls use exponential backoff:

```python
from utils.retry import retry_with_backoff

@retry_with_backoff(max_attempts=3, base_delay=1.0, max_delay=10.0)
async def call_worker():
    return await client.post(...)
```

**Retries on**:
- `httpx.TimeoutException`
- `httpx.NetworkError`
- `httpx.HTTPStatusError` (5xx only, NOT 4xx)

### 5. Shared HTTP Client

One `httpx.AsyncClient` instance for all requests:

```python
from utils.http_client import get_shared_client

async def some_handler():
    client = await get_shared_client()
    resp = await client.post(url, json=data)
```

**Benefits**:
- Connection pooling (reuses TCP connections)
- Reduced latency (no handshake overhead)
- Max 100 connections, 20 keepalive

---

## Tool Domains (21 tools)

### entreprises.py - Gestion clients (5 tools)

| Tool | Type | Description |
|------|------|-------------|
| `search_entreprise_with_stats` | READ | Recherche entreprise par nom avec stats |
| `get_entreprise_by_id` | READ | Details complets d'une entreprise |
| `list_entreprises` | READ | Liste entreprises avec pagination |
| `get_stats_entreprises` | READ | Statistiques globales CRM |
| `upsert_entreprise` | WRITE | Cree ou met a jour une entreprise |

### qualifications.py - Gestion commerciale (3 tools)

| Tool | Type | Description |
|------|------|-------------|
| `get_entreprise_qualifications` | READ | Qualifications d'une entreprise |
| `search_qualifications` | READ | Recherche par statut/periode |
| `upsert_qualification` | WRITE | Cree ou met a jour une qualification |

### factures.py - Facturation (7 tools)

| Tool | Type | Description |
|------|------|-------------|
| `search_factures` | READ | Recherche factures par criteres |
| `get_facture_by_id` | READ | Details complets d'une facture |
| `create_facture` | WRITE | Cree une nouvelle facture |
| `update_facture` | WRITE | Met a jour une facture |
| `delete_facture` | WRITE | Soft delete d'une facture |
| `generate_facture_pdf` | WORKFLOW | Genere PDF et upload (sans email) |
| `create_and_send_facture` | WORKFLOW | Cree + genere PDF + envoie email |

### paiements.py - Tresorerie (3 tools)

| Tool | Type | Description |
|------|------|-------------|
| `get_unpaid_factures` | READ | Factures impayees |
| `get_revenue_stats` | READ | Statistiques revenus par periode |
| `mark_facture_paid` | WRITE | Marque facture comme payee |

### communications.py - Emails & notifications (3 tools)

| Tool | Type | Description |
|------|------|-------------|
| `list_recent_interactions` | READ | Interactions recentes (Telegram) |
| `send_facture_email` | WORKFLOW | Genere PDF + upload + envoie email |
| `generate_monthly_report` | WORKFLOW | Rapport mensuel PDF avec stats |

### analytics.py - Reporting (placeholder futur)

Prevu : `dashboard_stats`, `export_campaign_report`, `forecast_revenue`

---

## Tool Types

### READ (11 tools)

**Pattern**: `call_supabase_rpc()` | **Latency**: 50-200ms | **Worker**: None (Supabase only)

```python
async def handler(params):
    return await call_supabase_rpc("rpc_function_name", {
        "p_param": params["param"]
    })
```

### WRITE (6 tools)

**Pattern**: `call_database_worker()` | **Latency**: 100-500ms | **Worker**: database-worker

```python
async def handler(params):
    return await call_database_worker(
        endpoint="/facture/create",
        payload={"montant": params["montant"]},
        require_validation=True  # CRITICAL
    )
```

### WORKFLOW (4 tools)

**Pattern**: Multi-worker orchestration | **Latency**: 1-5s | **Workers**: All 4

```python
async def workflow_handler(params):
    facture = await call_supabase_rpc("get_facture_by_id", ...)
    pdf = await call_document_worker("/generate/facture", ...)
    upload = await call_storage_worker("/upload", ...)
    email = await call_email_worker("/send", ...)
    await call_database_worker("/facture/update", ...)
    return {"success": True, "pdf_url": upload["public_url"]}
```

---

## Configuration

### Environment Variables

```bash
# Supabase (required for all tools)
SUPABASE_PROJECT_REF=your_project_ref
SUPABASE_PAT=your_pat_token              # For MCP proxy
SUPABASE_URL=https://xyz.supabase.co
SUPABASE_API_KEY=your_service_role_key   # For RPC calls

# Authentication (required)
X_PROXY_KEY=secure_key_1                 # Supabase proxy auth
FLOWCHAT_MCP_KEY=secure_key_2            # FlowChat tools auth

# FlowChat Workers (optional - needed for WRITE/WORKFLOW tools)
DATABASE_WORKER_URL=http://localhost:8001
DOCUMENT_WORKER_URL=http://localhost:8002
STORAGE_WORKER_URL=http://localhost:8003
EMAIL_WORKER_URL=http://localhost:8004
WORKER_AUTH_KEY=shared_worker_secret

# Application
ENVIRONMENT=production                    # production | development
LOG_LEVEL=INFO                           # DEBUG | INFO | WARNING | ERROR
```

### Settings Loading

Settings are loaded via `pydantic_settings.BaseSettings`:

```python
from config import settings

# Safe access (returns None if not configured)
if settings:
    print(settings.database_worker_url)
```

**Note**: Settings can be `None` during testing if `.env` is missing.

---

## API Endpoints

### Health Check

```
GET /health
```

**Auth**: None
**Response**:
```json
{
  "status": "ok",
  "environment": "production",
  "version": "2.0.0",
  "features": ["supabase_proxy", "flowchat_tools"]
}
```

### Supabase Proxy (existing - UNCHANGED)

```
GET/POST/PUT/DELETE /mcp/{path:path}
```

**Auth**: `X-Proxy-Key` header or `?key=` query param
**Purpose**: Proxy requests to Supabase MCP (SSE + REST)
**Examples**:
- `/mcp/sse` - SSE streaming
- `/mcp/rest/v1/rpc/function_name` - REST API

### List Tools

```
GET /mcp/tools/list
```

**Auth**: `X-Proxy-Key: FLOWCHAT_MCP_KEY`
**Response**:
```json
{
  "tools": [
    {
      "name": "search_entreprise_with_stats",
      "category": "read",
      "description": "Recherche entreprise par nom avec stats"
    }
  ],
  "total": 21
}
```

### Get Tool Schema

```
GET /mcp/tools/{tool_name}/schema
```

**Auth**: `X-Proxy-Key: FLOWCHAT_MCP_KEY`
**Response**:
```json
{
  "name": "search_entreprise_with_stats",
  "description": "Recherche entreprise...",
  "input_schema": {
    "type": "object",
    "properties": {
      "search_term": {"type": "string", "description": "..."},
      "limit": {"type": "integer", "default": 10}
    },
    "required": ["search_term"]
  }
}
```

### Call Tool

```
POST /mcp/tools/call
```

**Auth**: `X-Proxy-Key: FLOWCHAT_MCP_KEY`
**Body**:
```json
{
  "tool_name": "search_entreprise_with_stats",
  "params": {
    "search_term": "ACME",
    "limit": 5
  }
}
```

**Response**:
```json
{
  "success": true,
  "tool_name": "search_entreprise_with_stats",
  "result": [
    {"id": "uuid", "nom": "ACME Corp", "ca_total": 150000}
  ]
}
```

**Error Response** (validation failure):
```json
{
  "detail": "Validation failed: discrepancies..."
}
```
Status: 422

---

## Development Guidelines

### Adding a New Tool

1. **Choose the domain file** (`tools/entreprises.py`, `tools/factures.py`, etc.)
   - Or create a new domain file if needed

2. **Add schema + handler** in the same file:
```python
# In tools/entreprises.py (or appropriate domain file)
from tools.base import ToolSchema, register_tool, ToolCategory, call_supabase_rpc

# 1. Define schema
NEW_TOOL_SCHEMA = ToolSchema(
    name="new_tool",
    description="...",
    input_schema={...},
    category="read"  # or "write", "workflow"
)

# 2. Create handler
@register_tool(name="new_tool", category=ToolCategory.READ, description_short="...")
async def new_tool_handler(params: Dict[str, Any]):
    return await call_supabase_rpc("rpc_function_name", {
        "p_param": params["param"]
    })

# 3. Add to domain schema registry
ENTREPRISE_SCHEMAS["new_tool"] = NEW_TOOL_SCHEMA
```

3. **For WRITE tools**: Use `call_database_worker()` with `require_validation=True`
4. **For WORKFLOW tools**: Orchestrate multiple workers, handle errors gracefully
5. **If new domain file**: Import it in `tools/__init__.py`

6. **Test**:
```bash
python test_implementation.py  # Verify registration
curl -X POST http://localhost:8000/mcp/tools/call \
  -H "X-Proxy-Key: $KEY" \
  -d '{"tool_name": "new_tool", "params": {...}}'
```

### Code Style

- **Async all the way**: All handlers are `async def`
- **Type hints**: Use `Dict[str, Any]` for params
- **Logging**: Use `structlog` with context
- **Errors**: Raise `HTTPException` with appropriate status codes
- **Validation**: Always check `validated` flag for WRITE operations

---

## Testing

### Unit Testing (manual)

```bash
# Verify all modules compile and tools are correctly distributed
python test_implementation.py

# Expected output:
# Tests passed: 6/6
# [PASS] All tests passed! Modular architecture is ready.
```

### Integration Testing (requires workers)

```bash
# Start server
uvicorn main:app --reload

# Test READ tool
curl -X POST http://localhost:8000/mcp/tools/call \
  -H "X-Proxy-Key: $FLOWCHAT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "search_entreprise_with_stats", "params": {"search_term": "ACME"}}'

# Test WRITE tool (requires database-worker)
curl -X POST http://localhost:8000/mcp/tools/call \
  -H "X-Proxy-Key: $FLOWCHAT_KEY" \
  -d '{"tool_name": "upsert_entreprise", "params": {"nom": "Test"}}'

# Test WORKFLOW tool (requires all workers)
curl -X POST http://localhost:8000/mcp/tools/call \
  -H "X-Proxy-Key: $FLOWCHAT_KEY" \
  -d '{"tool_name": "send_facture_email", "params": {"facture_id": "uuid"}}'
```

### Debugging

**View logs with request tracking**:
```bash
# If using JSON logging
tail -f logs.json | jq

# Filter by request ID
tail -f logs.json | jq 'select(.request_id == "550e8400-...")'

# Filter by tool name
tail -f logs.json | jq 'select(.tool_name == "search_entreprise_with_stats")'

# Filter validation failures
tail -f logs.json | jq 'select(.event == "database_worker_validation_failed")'
```

---

## Deployment

### Local Development

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker

```bash
docker build -t flowchat-mcp-proxy .
docker run -p 8000:8000 --env-file .env flowchat-mcp-proxy
```

### Production (Coolify VPS)

The project is deployed on Coolify. See existing Dockerfile.

**Important**: Ensure all worker URLs are accessible from the proxy container.

---

## Security Considerations

1. **Dual Authentication**:
   - `X_PROXY_KEY` for Supabase proxy (existing clients)
   - `FLOWCHAT_MCP_KEY` for FlowChat tools (new clients)

2. **Worker Authentication**:
   - All worker calls include `X-FlowChat-Worker-Auth` header
   - Workers should validate this header

3. **Validation Enforcement**:
   - WRITE operations MUST check `validated` flag
   - Prevents silent data corruption

4. **Rate Limiting**:
   - 200 requests/minute per client IP
   - Configurable via `RATE_LIMIT` env var

5. **Secrets Management**:
   - Never commit `.env` to git
   - Use environment variables in production
   - Rotate keys periodically

---

## Performance Metrics

**Expected Latency**:
- READ tools: 50-200ms (Supabase RPC)
- WRITE tools: 100-500ms (database-worker + validation)
- WORKFLOW tools: 1-5s (multi-worker orchestration)

**Optimizations**:
- ✅ Shared HTTP client (connection pooling)
- ✅ Exponential backoff retry (max 3 attempts)
- ✅ Parallel operations in workflows (`asyncio.gather`)
- ✅ Request ID tracking for debugging

**Token Budget**:
- Before: 51,000 tokens (20+ tools defined directly)
- After: ~2,000 tokens (1 MCP server)
- **Reduction**: 96%

---

## Troubleshooting

### "Configuration error" on startup

**Cause**: Missing required env vars
**Fix**: Ensure `.env` has `SUPABASE_PROJECT_REF`, `SUPABASE_PAT`, `X_PROXY_KEY`

### "Shared HTTP client not initialized"

**Cause**: `init_shared_client()` not called
**Fix**: Ensure startup hook is registered in `main.py`

### "Validation failed" (422 error)

**Cause**: Database-worker rejected data
**Fix**: Check logs for `discrepancies`, fix data format

### Worker connection errors

**Cause**: Worker URL incorrect or worker not running
**Fix**:
- Verify `DATABASE_WORKER_URL` etc. in `.env`
- Test: `curl http://localhost:8001/health`

### Request ID not in logs

**Cause**: `RequestIDMiddleware` not registered
**Fix**: Ensure middleware added to FastAPI app

---

## Future Enhancements

### Phase 6: Integration Testing
- [ ] End-to-end workflow tests
- [ ] Bot integration testing
- [ ] Load testing (concurrent requests)

### Phase 7: Optional Features
- [ ] CoT (Chain-of-Thought) prompt enhancement
- [ ] `/mcp/enhance_prompt` endpoint
- [ ] Performance monitoring (latency per tool)
- [ ] Error aggregation and alerting
- [ ] Worker health checks

### Long-term
- [ ] Automated unit tests (pytest)
- [ ] CI/CD pipeline
- [ ] API versioning
- [ ] Rate limiting per tool category
- [ ] Audit logging to database
- [ ] Rollback mechanism for workflows

---

## References

- **MCP Protocol**: https://modelcontextprotocol.io/
- **FastAPI**: https://fastapi.tiangolo.com/
- **Pydantic Settings**: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- **httpx**: https://www.python-httpx.org/
- **structlog**: https://www.structlog.org/

---

## Contact & Support

**Project**: FlowChat MCP Unified Proxy
**Status**: Modular architecture complete (Phase 6)
**Next**: Runtime testing with workers

For detailed implementation info, see:
- `IMPLEMENTATION.md` - Full technical details
- `COMPLETION_SUMMARY.md` - Status and metrics
- `test_implementation.py` - Verification tests (6 tests, 21 tools)
