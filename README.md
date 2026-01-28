# Supabase MCP Proxy 🔧

Secure SSE-compatible proxy for Supabase MCP, optimized for FlowChat MVP on Coolify VPS.

## Features

- ✅ **SSE Streaming Support** - No response caching for real-time streams
- 🔐 **X-Proxy-Key Authentication** - Custom header-based authentication
- 🚀 **Automatic Project Ref Injection** - Seamless Supabase integration
- 📊 **Structured Logging** - JSON logging in production, console in development
- ⏱️ **Rate Limiting** - 200 req/min by default (adjustable)
- 🌍 **CORS Support** - Configurable cross-origin requests

## Installation

### 1. Clone/Setup Project
```bash
cd c:\Users\calen\supabase-mcp-proxy
```

### 2. Create Virtual Environment
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
cp .env.example .env
```

Then edit `.env` with your values:
```env
SUPABASE_PROJECT_REF=your_project_ref
SUPABASE_PAT=your_pat_token
X_PROXY_KEY=your_secure_key_here
```

## Running the Proxy

### Development
```bash
python main.py
```

### Production (with Uvicorn)
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Endpoints

### Health Check (No Auth Required)
```bash
GET /health
```

### MCP Proxy (Requires X-Proxy-Key)
```bash
GET|POST|PUT|DELETE /mcp/{path}
```

**Required Header:**
```
X-Proxy-Key: your_secure_proxy_key
```

### Example Requests

**SSE Stream:**
```bash
curl -H "X-Proxy-Key: your_key" \
     -H "Accept: text/event-stream" \
     http://localhost:8000/mcp/chat
```

**Regular Request:**
```bash
curl -X POST http://localhost:8000/mcp/models \
     -H "X-Proxy-Key: your_key" \
     -H "Content-Type: application/json" \
     -d '{"model": "gpt-4"}'
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SUPABASE_PROJECT_REF` | ✅ | - | Your Supabase project reference |
| `SUPABASE_PAT` | ✅ | - | Supabase Personal Access Token |
| `X_PROXY_KEY` | ✅ | - | Secret key for proxy authentication |
| `ENVIRONMENT` | ❌ | `production` | `production` or `development` |
| `LOG_LEVEL` | ❌ | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `ALLOWED_ORIGINS` | ❌ | `*` | CORS allowed origins (comma-separated) |
| `RATE_LIMIT` | ❌ | `200/minute` | Rate limiting rule |

## Docker Deployment

### Build Image
```bash
docker build -t supabase-mcp-proxy .
```

### Run Container
```bash
docker run -d \
  -p 8000:8000 \
  -e SUPABASE_PROJECT_REF=your_ref \
  -e SUPABASE_PAT=your_pat \
  -e X_PROXY_KEY=your_key \
  supabase-mcp-proxy
```

## Monitoring

### Request Logs
All requests are logged with:
- `path` - Request path
- `method` - HTTP method
- `client_ip` - Client IP address
- `status_code` - Response status
- `duration_ms` - Request duration

### SSE Streams
Special logging for SSE connections with:
- Stream start/end events
- Client IP tracking
- Duration monitoring

## Security Notes

⚠️ **Important:**
1. Never commit `.env` to version control
2. Use strong random `X_PROXY_KEY` (32+ characters recommended)
3. Rotate `SUPABASE_PAT` regularly
4. Use HTTPS in production
5. Monitor rate limits for DDoS protection

## Coolify Deployment

Set environment variables in Coolify:
```
SUPABASE_PROJECT_REF=xxxx...
SUPABASE_PAT=xxxx...
X_PROXY_KEY=xxxx...
ENVIRONMENT=production
```

## Troubleshooting

### 503 Gateway Timeout
- Increase `timeout` in httpx.AsyncClient for long-running operations
- Check Supabase MCP service availability

### 403 Authentication Failed
- Verify `X-Proxy-Key` header is sent correctly
- Check `.env` configuration

### CORS Issues
- Update `ALLOWED_ORIGINS` in `.env`
- Ensure client sends proper headers

## License

MIT
