# MCP Gateway

[![PyPI version](https://badge.fury.io/py/mcp-gway.svg)](https://pypi.org/project/mcp-gway/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-gway)](https://pypi.org/project/mcp-gway/)
[![License](https://img.shields.io/pypi/l/mcp-gway)](https://github.com/deuriib/mcp-gateway/blob/main/LICENSE)

A standalone CLI gateway that aggregates multiple MCP (Model Context Protocol) servers behind a single HTTP/SSE endpoint with **Code Mode** — reducing LLM input token usage by up to 92% when using multiple MCP servers. **v1.4.1 GA** adds a local-first **Dashboard** (Python `htpy` + `python-htmx` + Tailwind vendoreado, sin Node).

## Features

- **Multi-Server Aggregation** — Connect to multiple MCP servers (HTTP, SSE, Stdio, Streamable HTTP) and expose them through a single endpoint
- **Code Mode** — 4 meta-tools that let LLMs discover and use tools dynamically without loading all schemas upfront
- **Dashboard (v1.4.1)** — Local-first UI en `http://127.0.0.1:8080` para listar/agregar/inspeccionar/enable-disable/remover/refrescar servers. SSR con `htpy`, mutaciones `htmx`, Tailwind vendoreado (<100KB), sin `package.json` ni build Node. Registry única fuente, masking `***` obligatorio.
- **OAuth 2.0 Support** — Built-in OAuth flow with dynamic client registration (RFC 7591) and token storage
- **Hermetic Sandbox** — Starlark-based sandbox for safe code execution
- **MCP Protocol Compliant** — Works with Claude Desktop, Cursor, and any MCP-compatible client

## Installation

```bash
pip install mcp-gway
```

Or with [mise](https://mise.jdx.dev/):

```bash
mise install
uv sync --all-groups  # installs dev group with pre-commit
```

## Quick Start

### OpenCode Format (Primary)

OpenCode schema — `remote` / `local` with transport auto-detection. This is the recommended path.

```bash
# Remote — auto-detects transport (streamable-http → sse → http)
mcp-gway add youtube --type remote --url http://localhost:3001/mcp

# Remote with headers
mcp-gway add supabase --type remote --url https://mcp.supabase.com/mcp --header "Authorization=Bearer TOKEN"

# Remote with pre-registered OAuth
mcp-gway add supabase --type remote --url https://mcp.supabase.com/mcp --oauth-client-id ID --oauth-client-secret SECRET --oauth-scope "openid profile"

# Remote with timeout and enable toggle
mcp-gway add api --type remote --url https://api.example.com/mcp --timeout 10000 --enabled
mcp-gway add api --type remote --url https://api.example.com/mcp --timeout 10000 --no-enabled

# Local
mcp-gway add filesystem --type local --command "npx -y @anthropic/mcp-filesystem"
mcp-gway add tools --type local --command "python -m my_mcp_server" --env MY_VAR=value --cwd /path/to/workdir
mcp-gway add tools --type local --command "npx -y my-mcp" --env KEY=VALUE --env OTHER=123 --cwd /tmp/workdir

# List and serve (local-first)
mcp-gway list
mcp-gway serve --port 8080              # bindea 127.0.0.1 por defecto
mcp-gway serve --host 127.0.0.1 --port 8080
open http://127.0.0.1:8080/dashboard
```

### Deprecated Format (still works)

Old `--type http|stdio|sse|streamable-http` syntax is kept for backward compat and internally mapped to `remote`/`local`. Prefer `remote`/`local` for new configs.

```bash
# Equivalent old syntax — prefer remote/local above
mcp-gway add youtube --type http --url http://localhost:3001/mcp
mcp-gway add filesystem --type stdio --command npx --args '["-y", "@anthropic/mcp-filesystem"]'
mcp-gway add supabase --type streamable-http --url https://mcp.supabase.com/mcp
mcp-gway add legacy --type sse --url https://example.com/sse
```

## Dashboard — Local-First SSR (htpy)

> **Stack:** `htpy` + `python-htmx` + TailwindCSS vendoreado en `src/mcp_gway/dashboard/static/` (<100KB + <20KB). **Sin Node**, sin `package.json`, sin build. Todo HTML tipado en Python; Registry es única fuente (dashboard nunca toca FS directo).

Un solo proceso `Gateway(registry, host)` monta dashboard embebido: `GET /dashboard` (SSR) + `GET /api/servers` (JSON) sobre el mismo `Starlette` que sirve `/mcp` y `/health`.

### Routes

| Method | Path | Response | Nota |
|--------|------|----------|------|
| `GET` | `/dashboard` | HTML `htpy.layout` (`max-w-6xl mx-auto` + Tailwind + `htmx.min.js`) | banner ámbar si host != loopback |
| `GET` | `/dashboard/servers` | Fragmento `<tbody id="server-table-body">` | `hx-get` polling |
| `GET` | `/dashboard/servers/{name}` | Drawer `server_drawer` con firmas `tools` (truncado >50KB) | |
| `GET` | `/dashboard/close` | Vacía drawer | |
| `GET` | `/static/tailwind.css` | CSS vendoreado | sin CDN |
| `GET` | `/static/htmx.min.js` | htmx vendoreado | |
| `GET` | `/api/servers` | `200 [{name,type,enabled,tool_count,url\|command,timeout}]` | secrets `***` |
| `GET` | `/api/servers/{name}` | `200 {config,pyi_content,truncated}` | secrets `***` |
| `POST` | `/api/servers` | `201` + `tools/list` discovery (timeout + `streamable-http→sse→http`); `409` si existe | `tools=[]` + toast si falla |
| `PATCH` | `/api/servers/{name}` | `{"enabled":bool}` → badge `disabled`/`healthy`/`unreachable` | vía `Registry.patch_enabled` |
| `DELETE` | `/api/servers/{name}` | `204` (idempotente, borra `*.json`+`*.pyi`+`tokens/`) | |
| `POST` | `/api/servers/{name}/refresh` | `202 {status:"refreshing"}` background no bloqueante | `409` si disabled |
| `POST` | `/api/servers/{name}/reveal` | `200 {headers\|oauth\|environment}` | solo `127.0.0.1` POST, rate-limit 5/min, `403` si no loopback |

Content negotiation: `HX-Request: true` → `text/html` fragment (swap); sin header → `application/json`. CSP `default-src 'self'` en todas las respuestas.

### curl Examples

```bash
# Serve local-first
mcp-gway serve --port 8080 &
curl -s http://127.0.0.1:8080/dashboard | head -n 20        # 200 HTML htpy
curl -s http://127.0.0.1:8080/api/servers | jq                # secrets masked ***

# Add remote (JSON)
curl -X POST http://127.0.0.1:8080/api/servers \
  -H 'Content-Type: application/json' \
  -d '{"name":"gh","type":"remote","url":"https://example.com/mcp"}'  # 201 {name,tool_count}

# Add local (form, htmx)
curl -X POST http://127.0.0.1:8080/api/servers \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'name=echo_srv&type=local&command=echo+hi&cwd=/tmp'

# Fragment htmx (polling tabla)
curl -H "HX-Request: true" http://127.0.0.1:8080/dashboard/servers          # <tbody>

# Inspect + reveal
curl -s http://127.0.0.1:8080/api/servers/gh | jq               # masked
curl -X POST http://127.0.0.1:8080/api/servers/gh/reveal \
  -H 'Content-Type: application/json' -d '{"field":"headers"}' | jq  # solo loopback POST

# Toggle / refresh / delete
curl -X PATCH http://127.0.0.1:8080/api/servers/gh \
  -H 'Content-Type: application/json' -d '{"enabled":false}' | jq
curl -X POST http://127.0.0.1:8080/api/servers/gh/refresh | jq   # 202 background, health <50ms
curl -X DELETE http://127.0.0.1:8080/api/servers/gh              # 204
```

### HTMX Examples

```html
<!-- Add: form SSR + hx-post swap tabla -->
<form hx-post="/api/servers" hx-target="#server-table-body" hx-swap="outerHTML" hx-indicator="#add-spinner">
  <input name="name" required /><select name="type"><option>remote</option><option>local</option></select>
  <input name="url" /><input name="command" /><button>Add</button>
</form>

<!-- Inspect: click fila abre drawer -->
<tr hx-get="/dashboard/servers/gh" hx-target="#drawer" hx-swap="innerHTML"><td>gh</td></tr>

<!-- Toggle / Refresh / Delete con confirm -->
<button hx-patch="/api/servers/gh" hx-vals='{"enabled":false}' hx-target="#drawer">Disable</button>
<button hx-post="/api/servers/gh/refresh" hx-target="#toast">Refresh</button>
<button hx-delete="/api/servers/gh" hx-confirm="Delete gh?" hx-target="#server-table-body" hx-swap="outerHTML">Delete</button>
```

### Local-First Security

```bash
# Default seguro — solo loopback
mcp-gway serve --port 8080            # bindea 127.0.0.1

# Exponer en 0.0.0.0 requiere opt-in explícito
MCP_GWAY_ALLOW_REMOTE=1 mcp-gway serve --host 0.0.0.0 --port 8080
# └─ log warning "dashboard exposed on non-loopback"
# └─ header X-Warning: exposed + banner ámbar en UI + botón Reveal deshabilitado

# Sin opt-in → error controlado
mcp-gway serve --host 0.0.0.0
# Error: binding to non-loopback host '0.0.0.0' requires MCP_GWAY_ALLOW_REMOTE=1
# exit 2
```

- Masking `***` obligatorio: `GET /api/servers`, `GET /api/servers/{name}`, `GET /dashboard` nunca exponen `headers`/`oauth.clientSecret`/`environment` reales.
- Reveal solo `POST /api/servers/{name}/reveal` desde `127.0.0.1`, rate-limit 5/min, audit log sin valor, `403` si no loopback, `405` si GET.

## Observability — Logs + Metrics + Health (Approach C, v1.4.1)

> **Zero vendor lock-in:** stdlib `json` logs (no `structlog`), vendored `MetricsRegistry` (no `prometheus_client`), correlation via `X-Request-ID` + `contextvars`, health probes `/health|/ready|/live` + Prometheus text `/metrics`. Local-first + masking `***` preserved; `/metrics` gated like `reveal`.

**Health & Metrics:**

```bash
curl -s http://127.0.0.1:8080/health | jq
# {"status":"ok","version":"1.4.1","checks":{"registry":"ok","dashboard":"ok"},"uptime_seconds":42}
curl -s http://127.0.0.1:8080/ready | jq   # 200 ready / 503 not_ready (registry/routes/event_loop checks)
curl -s http://127.0.0.1:8080/live | jq    # 200 alive — no FS I/O, <5ms
curl -s http://127.0.0.1:8080/metrics | head -n 20
# # HELP mcp_gway_http_requests_total Total HTTP requests
# # TYPE mcp_gway_http_requests_total counter
# mcp_gway_http_requests_total{method="GET",path="/health",status="200"} 7
curl -s http://127.0.0.1:8080/api/health | jq  # dashboard-friendly JSON + metrics_summary
```

**Correlation & JSON logs:**

```bash
curl -s -H "X-Request-ID: demo123" http://127.0.0.1:8080/health -D - | grep -i X-Request-ID
# X-Request-ID: demo123  ← echo on every response; json log line also has "request_id":"demo123"
uv run mcp-gway serve --port 8080 2>&1 | head   # each line valid JSON: timestamp, level, logger, message, request_id, method, path, status, duration_ms
```

- `X-Request-ID` or `X-Correlation-ID` accepted, sanitized to `^[A-Za-z0-9_-]{1,64}$`, truncated; auto `uuid4` if absent.
- Labels bounded: `path` templated to `/api/servers/{name}` (not concrete), server sanitized `[^A-Za-z0-9_]`→`_` 32 chars.
- Metrics catalog: `http_requests_total`, `http_request_duration_seconds` (buckets 0.005..5), `mcp_tool_calls_total{server,tool,status}`, `discovery_duration_seconds`, `sandbox_execute_total{status}`, `registry_operations_total{op}`, `gateway_sessions_active`.

**Dashboard ops card:**

- `GET /dashboard` renders `id="ops-card"` (htpy) with badge `healthy`/`degraded`/`not_ready`, uptime, p95, checks; polls `GET /api/health` (`hx-get every 15s`). `HX-Request:true` → fragment, else JSON. No secrets, CSP intact.

**Local-first gating:** `/metrics` never leaks secrets; if somehow bound non-loopback without `MCP_GWAY_ALLOW_REMOTE=1`, `serve` exits 2; if bypassed, `/metrics` returns `403` + `X-Warning: exposed`.

## Connect from Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gateway": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

## Commands

| Command | Description |
|---------|-------------|
| `mcp-gway add --type remote\|local` | Add an MCP server and generate `.pyi` stub (OpenCode format, primary) |
| `mcp-gway remove` | Remove an MCP server |
| `mcp-gway update` | Update tools for a server |
| `mcp-gway list` | List all connected servers |
| `mcp-gway inspect` | Show tool signatures for a server |
| `mcp-gway refresh [<name>] [--auth] [--oauth-port <port>]` | Refresh connection and re-discover tools |
| `mcp-gway serve [--host 127.0.0.1] [--port <port>]` | Start gateway (MCP + Dashboard). Default `127.0.0.1`; `0.0.0.0` necesita `MCP_GWAY_ALLOW_REMOTE=1` |

> **Backward compat:** `mcp-gway add --type http|stdio|sse|streamable-http` still works (deprecated). `http`/`sse`/`streamable-http` → `remote` (with `resolved_transport` cached), `stdio` → `local`. Use `remote`/`local` going forward.

Options for `add` (OpenCode) — 12+ flags grouped by scope:

| Option | Description |
|--------|-------------|
| `--type remote\|local` | Server type (primary) |
| `--url <url>` | URL for `remote` |
| `--header "KEY=VALUE"` | HTTP header for `remote` (repeatable) |
| `--command "<cmd>"` | Command for `local` (e.g. `"npx -y my-mcp"`) |
| `--env KEY=VALUE` | Environment variable for `local` (repeatable) |
| `--cwd <path>` | Working directory for `local` |
| `--oauth-client-id ID` | Pre-registered OAuth client ID |
| `--oauth-client-secret SECRET` | Pre-registered OAuth client secret |
| `--oauth-scope SCOPE` | OAuth scope |
| `--oauth-port <port>` | Local port for OAuth callback (default 8989) |
| `--timeout <ms>` | Connection timeout in ms (default 5000) |
| `--enabled / --no-enabled` | Enable/disable without removal (default enabled) |
| `--tools <list>` | Comma-separated tool filter (default `*` = all) |
| `--args <json>` | JSON array of extra args — deprecated compat, used with `stdio`/`local` |
| `--docs-url <url>` | Deprecated — accepted for compat but not persisted (legacy) |

## Code Mode

When connected, the gateway exposes 4 meta-tools:

| Tool | Description |
|------|-------------|
| `listToolFiles` | List all available `.pyi` stub files |
| `readToolFile` | Read function signatures from a stub |
| `getToolDocs` | Get detailed documentation for a tool |
| `executeToolCode` | Execute code in a sandboxed Starlark interpreter |

## OAuth Authentication

For servers requiring OAuth (e.g., Supabase):

```bash
# Trigger OAuth flow
mcp-gway refresh supabase --auth

# Or store token manually
mkdir -p ~/.config/mcp-gway/tokens
echo '{"access_token": "YOUR_TOKEN"}' > ~/.config/mcp-gway/tokens/supabase.json
```

## Development

```bash
# Install dependencies
uv sync --all-groups  # installs dev group with pre-commit
uv run pre-commit install  # once per clone — hooks already configured in .pre-commit-config.yaml

# Run checks
uv run pre-commit run --all-files  # ruff + ruff-format + hygiene (trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files)
uv run pytest -v  # 254 tests v1.4.1 — incluye test_dashboard_* + test_catalog_* + test_observability_*
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Verification Dashboard (sin Node, sin build)
uv run pytest tests/test_dashboard_views.py tests/test_dashboard_api.py -v  # masking, HX-Request, reveal, refresh, local gating
curl -s http://127.0.0.1:8080/dashboard | grep -q '<table' && echo "dashboard ok"
curl -s http://127.0.0.1:8080/api/servers | jq 'map(select(.headers))'       # *** masked
curl -H "HX-Request: true" http://127.0.0.1:8080/dashboard/servers | head   # fragment tbody

# Local-first check
mcp-gway serve --host 0.0.0.0 2>&1 | grep -q "requires MCP_GWAY_ALLOW_REMOTE" && echo "gate ok"
MCP_GWAY_ALLOW_REMOTE=1 mcp-gway serve --host 0.0.0.0 --port 8081 & curl -s -D - http://127.0.0.1:8081/dashboard | grep -qi X-Warning
```

Pre-commit is already in place (`.pre-commit-config.yaml` — `ruff` v0.16.4, `ruff-format`, `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`).

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        MCP Gateway v1.4.1 GA                         │
├──────────────────────────────────────────────────────────────────────┤
│  CLI (click)              │  Gateway (Starlette + uvicorn, CSP)      │
│  - add remote/local       │  - POST /mcp (JSON-RPC)                  │
│  - remove/inspect/list    │  - GET  /mcp (SSE endpoint event)        │
│  - refresh --auth         │  - POST /mcp/messages?session_id=...     │
│  - serve --host 127.0.0.1 │  - GET  /health                          │
│  (local-first default)    │                                          │
├───────────────────────────┼──────────────────────────────────────────┤
│  Dashboard (htpy+htmx, vendoreado)                                    │
│  SSR: GET /dashboard, /dashboard/servers, /dashboard/servers/{name}   │
│  API: GET/POST /api/servers, PATCH/DELETE /api/servers/{name},        │
│       POST /api/servers/{name}/refresh (202 background), /reveal      │
│  Static: /static/tailwind.css (<100KB) + /static/htmx.min.js (<20KB) │
│  Content-negotiation HX-Request + masking *** + rate-limit reveal      │
├──────────────────────────────────────────────────────────────────────┤
│  Code Mode (4 meta-tools)      │  Starlark Sandbox                    │
│  - listToolFiles               │  - Hermetic execution                │
│  - readToolFile                │  - Server injection                  │
│  - getToolDocs                 │                                      │
│  - executeToolCode             │                                      │
├──────────────────────────────────────────────────────────────────────┤
│  Registry (única fuente)       │  OAuth2 (RFC 7591, reutilizado)      │
│  - servers/*.pyi = signatures  │  - Dynamic registration              │
│  - servers/*.json = config     │  - PKCE + FileTokenStorage           │
│  - last-write-wins, atómico    │  - tokens/ no expuesto vía API       │
└──────────────────────────────────────────────────────────────────────┘
         │                │                │
    ┌────┴────┐      ┌────┴────┐      ┌────┴────┐
    │ Server1 │      │ Server2 │      │ Server3 │
    │ (remote)│      │ (local) │      │ (remote)│
    └─────────┘      └─────────┘      └─────────┘
```

- **Sin Node** en runtime ni CI: Tailwind + htmx vendoreados commit, `ruff` único linter, `uv_build` backend.
- **Release híbrido** (ADR-007): `push tags v*` → `uv build` + `pypi-publish` (GA `v1.4.1` tag manual) + `workflow_run Tests completed` → `python-semantic-release@v9` para `fix/perf` patches auto. `concurrency: release`, `fetch-depth:0`, `[tool.semantic_release]` sync `pyproject.toml` + `__init__.py` (`1.4.1` exacta).

## License

MIT
