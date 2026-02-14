# FlowChat MCP Unified Proxy - Project Documentation

## Project Overview

This is a **unified MCP (Model Context Protocol) proxy** that centralizes access to FlowChat CRM tools for the Claude API. It solves a critical token budget problem by reducing tool definitions from 51,000 tokens to ~2,000 tokens.

**Purpose**: Enable a Telegram bot (FlowChat CRM for firefighters) to use Claude API effectively by exposing 19 tools through a single MCP server instead of defining them directly in each API call.

**Status**: Implementation complete (Phases 1-5), ready for runtime testing with workers.

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

2. **FlowChat MCP Tools** (new functionality)
   - Routes: `/mcp/tools/list`, `/mcp/tools/{name}/schema`, `/mcp/tools/call`
   - Exposes 19 tools (10 READ, 6 WRITE, 3 WORKFLOW)
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
├── schemas/                   # Tool schemas (MCP format)
│   ├── __init__.py           # ToolSchema base class
│   ├── read_tools.py         # 10 READ tool schemas (Supabase RPC)
│   ├── write_tools.py        # 6 WRITE tool schemas (database-worker)
│   └── workflow_tools.py     # 3 WORKFLOW tool schemas (multi-worker)
│
├── handlers/                  # Tool handlers (async functions)
│   ├── __init__.py
│   ├── supabase_read.py      # 10 READ handlers (call_supabase_rpc)
│   ├── database_write.py     # 6 WRITE handlers (call_database_worker)
│   └── workflows.py          # 3 WORKFLOW handlers (orchestration)
│
├── utils/                     # Shared utilities
│   ├── __init__.py
│   ├── http_client.py        # Shared AsyncClient (connection pooling)
│   └── retry.py              # Exponential backoff decorator
│
├── test_implementation.py     # Verification tests
├── requirements.txt           # Dependencies
├── .env.example              # Configuration template
├── Dockerfile                # Container build
├── IMPLEMENTATION.md         # Detailed implementation docs
├── COMPLETION_SUMMARY.md     # Status & metrics
└── CLAUDE.md                 # This file
```

---

## Key Concepts

### 1. Tool Registration Pattern

Tools are registered using a decorator pattern:

```python
from tools_registry import register_tool, ToolCategory

@register_tool(
    name="search_entreprise_with_stats",
    category=ToolCategory.READ,
    description_short="Recherche entreprise par nom avec stats"
)
async def search_entreprise_with_stats_handler(params: Dict[str, Any]):
    return await call_supabase_rpc("search_entreprise_with_stats", {
        "p_search_term": params["search_term"],
        "p_limit": params.get("limit", 10)
    })
```

**How it works**:
- Decorator adds handler to `TOOL_REGISTRY` dict
- `/mcp/tools/call` uses `dispatch_tool()` to route to handler
- Schema is stored separately in `schemas/` folder

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

## Tool Categories

### READ Tools (10)

**Purpose**: Fetch data from Supabase via RPC functions
**Authentication**: Supabase API key
**Worker dependency**: None (Supabase only)
**Latency**: 50-200ms

**Examples**:
- `search_entreprise_with_stats` - Search companies with revenue stats
- `get_facture_by_id` - Get invoice details
- `list_recent_interactions` - Get recent Telegram messages

**Pattern**:
```python
async def handler(params):
    return await call_supabase_rpc("rpc_function_name", {
        "p_param": params["param"]
    })
```

### WRITE Tools (6)

**Purpose**: Modify data via database-worker
**Authentication**: Worker auth key + validation
**Worker dependency**: database-worker
**Latency**: 100-500ms

**Examples**:
- `upsert_entreprise` - Create/update company
- `create_facture` - Create invoice
- `mark_facture_paid` - Update payment status

**Pattern**:
```python
async def handler(params):
    return await call_database_worker(
        endpoint="/facture/create",
        payload={"montant": params["montant"]},
        require_validation=True  # CRITICAL
    )
```

### WORKFLOW Tools (3)

**Purpose**: Orchestrate multiple workers for complex operations
**Authentication**: Worker auth key
**Worker dependency**: All 4 workers
**Latency**: 1-5s

**Examples**:
- `send_facture_email` - Generate PDF → Upload → Email → Update status
- `create_and_send_facture` - Create + send in one operation
- `generate_monthly_report` - Fetch stats → Generate PDF → Upload

**Pattern**:
```python
async def workflow_handler(params):
    # Step 1: Fetch data
    facture = await call_supabase_rpc("get_facture_by_id", ...)

    # Step 2: Generate PDF
    pdf = await call_document_worker("/generate/facture", ...)

    # Step 3: Upload
    upload = await call_storage_worker("/upload", ...)

    # Step 4: Send email
    email = await call_email_worker("/send", ...)

    # Step 5: Update status
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
  "total": 19
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

### Adding a New READ Tool

1. **Define schema** in `schemas/read_tools.py`:
```python
NEW_TOOL_SCHEMA = ToolSchema(
    name="new_tool",
    description="...",
    input_schema={...},
    category="read"
)

READ_TOOL_SCHEMAS["new_tool"] = NEW_TOOL_SCHEMA
```

2. **Create handler** in `handlers/supabase_read.py`:
```python
@register_tool(name="new_tool", category=ToolCategory.READ, description_short="...")
async def new_tool_handler(params: Dict[str, Any]):
    return await call_supabase_rpc("rpc_function_name", {
        "p_param": params["param"]
    })
```

3. **Test**:
```bash
curl -X POST http://localhost:8000/mcp/tools/call \
  -H "X-Proxy-Key: $KEY" \
  -d '{"tool_name": "new_tool", "params": {...}}'
```

### Adding a New WRITE Tool

Same as READ, but:
- Schema in `schemas/write_tools.py`
- Handler in `handlers/database_write.py`
- **MUST** use `call_database_worker()` with `require_validation=True`

### Adding a New WORKFLOW Tool

Same as READ, but:
- Schema in `schemas/workflow_tools.py`
- Handler in `handlers/workflows.py`
- Orchestrate multiple workers
- Handle errors gracefully (no automatic rollback)

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
# Verify all modules compile
python test_implementation.py

# Expected output:
# Tests passed: 5/5
# [PASS] All tests passed!
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
**Status**: ✅ Implementation complete (Phases 1-5)
**Next**: Runtime testing with workers

For detailed implementation info, see:
- `IMPLEMENTATION.md` - Full technical details
- `COMPLETION_SUMMARY.md` - Status and metrics
- `test_implementation.py` - Verification tests
