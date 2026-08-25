# AGENTS.md

## Project Overview

**MCP Gateway** — A standalone Python CLI that aggregates multiple MCP servers behind a single HTTP/SSE endpoint with Code Mode and a local-first Dashboard (v0.7.0 GA).

## Tech Stack

- **Language**: Python 3.12+
- **Package Manager**: uv (with mise for tool versions)
- **CLI Framework**: click
- **HTTP Server**: Starlette + uvicorn
- **MCP SDK**: mcp v2.0.0
- **Dashboard**: htpy + python-htmx + TailwindCSS vendoreado (sin Node, sin build)
- **Sandbox**: starlark-pyo3
- **Testing**: pytest + pytest-asyncio (181 tests v0.7.0)
- **Linting**: ruff

## Project Structure

```
src/mcp_gway/
├── __init__.py          # Package version (0.7.0)
├── models.py            # Pydantic models (MCPServerConfig OpenCode + MCPClientConfig deprecated compat, ToolInfo, ConnectionType)
├── registry.py          # .pyi file CRUD (servers/ directory) — única fuente de verdad
├── sandbox.py           # Starlark sandbox (hermetic execution)
├── server_proxy.py      # MCP server wrapper for sandbox
├── code_mode.py         # 4 meta-tools orchestrator
├── gateway.py           # HTTP/SSE server (JSON-RPC 2.0) + monta Dashboard, local-first 127.0.0.1 + CSP
├── dashboard/           # Bounded context UI — sin Node, sin DB
│   ├── routes.py        # SSR + API + static mounts
│   ├── views.py         # htpy components (layout, table, drawer, badges)
│   ├── api.py           # handlers Registry + masking + htmx negotiation
│   └── static/
│       ├── tailwind.css # vendoreado <100KB (commit, sin build)
│       └── htmx.min.js  # vendoreado <20KB
├── cli.py               # CLI commands (add/remove/update/list/inspect/refresh/serve --host 127.0.0.1)
└── oauth.py             # OAuth2 support (dynamic registration, token storage)

tests/
├── test_models.py       # Model validation tests
├── test_registry.py     # Registry CRUD tests
├── test_sandbox.py      # Sandbox execution tests
├── test_server_proxy.py # Server proxy tests
├── test_code_mode.py    # Code mode tests
├── test_gateway.py      # HTTP/SSE server tests
├── test_dashboard_api.py   # Dashboard API (CRUD, masking, reveal, refresh, local gating)
├── test_dashboard_views.py # htpy SSR snapshots (<table>, badges, empty state)
├── test_cli.py          # CLI command tests
└── test_integration.py  # End-to-end flow tests

docs/specs/
├── SPEC-UI-001.md       # Dashboard spec v0.7.0 GA (vinculante)
├── SCENARIOS-UI-001.md  # Given/When/Then 28 scenarios
└── ACCEPTANCE-UI-001.md # 9 AC ejecutables (TestClient)
```

## Commands

```bash
# Development
uv sync --all-groups                     # Install dependencies (dev group includes pre-commit)
uv run pre-commit install                # Install git hooks (once per clone)
uv run pre-commit run --all-files        # Run hooks on all files
uv run pytest -v                         # Run tests (181 tests v0.7.0)
uv run ruff check src/ tests/            # Lint (CI parity)
uv run ruff format --check src/ tests/   # Format check (CI parity)

# Verification Dashboard (local-first)
uv run pytest tests/test_dashboard_views.py tests/test_dashboard_api.py -v
curl -s http://127.0.0.1:8080/dashboard | head -n 20          # 200 HTML htpy + Tailwind
curl -s http://127.0.0.1:8080/api/servers | jq                  # JSON masked ***
curl -H "HX-Request: true" http://127.0.0.1:8080/dashboard/servers  # fragment <tbody>

# CLI — OpenCode format (primary)
mcp-gway add <name> --type remote --url <url> [--header "KEY=VALUE"] [--oauth-client-id ID] [--oauth-client-secret SECRET] [--oauth-scope SCOPE] [--timeout 5000] [--enabled] [--oauth-port 8989]
mcp-gway add <name> --type local --command "npx -y my-mcp" [--env KEY=VALUE] [--cwd /path] [--args '["..."]' (deprecated compat)] [--tools "*"]
# Full options: see README.md Options table (12+ flags: --type/--url/--command/--header/--env/--cwd/--oauth-* /--timeout/--enabled/--tools/--args/--docs-url)
# Deprecated (still works, use remote/local instead):
# mcp-gway add <name> --type <http|stdio|sse|streamable-http> [...]
mcp-gway remove <name>
mcp-gway list
mcp-gway inspect <name>
mcp-gway refresh [<name>] [--auth] [--oauth-port <port>]
mcp-gway serve [--host 127.0.0.1] [--port 8080]   # default local-first; 0.0.0.0 requiere MCP_GWAY_ALLOW_REMOTE=1
```

> **Local-first warning:** `serve` bindea `127.0.0.1` por defecto. `--host 0.0.0.0` sin `MCP_GWAY_ALLOW_REMOTE=1` → `exit 2` + `Error: binding to non-loopback ...`. Con `MCP_GWAY_ALLOW_REMOTE=1` → `WARNING: dashboard exposed on non-loopback` en log + header `X-Warning: exposed` + banner UI ámbar.

## Code Conventions

- Type hints on all public functions
- `from __future__ import annotations` in all modules
- Docstrings on classes and public methods
- ruff for linting and formatting
- No comments unless explicitly requested
- Dashboard: solo `htpy` + `python-htmx`, prohibido `Jinja2/React/Vue/Node`. Tailwind vendoreado, sin `package.json`.

## Testing

- Tests in `tests/` mirror `src/mcp_gway/` structure
- Use `tmp_path` fixture for file system tests
- Use `monkeypatch` for mocking
- Async tests with `@pytest.mark.asyncio`
- Mock MCP clients for unit tests
- Dashboard tests: `TestClient` / `httpx.ASGITransport(gateway.app)` — asserts `str(view())` contiene `<table`, masking `***`, `HX-Request` negotiation

## Deployment

- **PyPI**: Hybrid workflow `.github/workflows/release.yml` — `on: push tags v*` **+** `on: workflow_run Tests completed` (ver ADR-007)
  - `push v*` → `uv build` + `pypi-publish` determinístico (GA manual `v0.7.0` via tag, CEO GO)
  - `workflow_run` → `python-semantic-release@v9` para patches automáticos `fix/perf` → minor/patch sin tag manual
  - Condición: `if: push || workflow_run.conclusion == 'success'` + `concurrency: release` + `fetch-depth: 0`
- **Version**: `0.7.0` sincronizada `pyproject.toml:project.version` + `src/mcp_gway/__init__.py:__version__` (`[tool.semantic_release]`)
- **Build**: `uv_build` backend — sin Node en CI (`ruff` único linter)

## Key Patterns

### Registry (.pyi + .json) — Única fuente

- `.pyi` = signatures only; `servers/*.json` = OpenCode config (type/url/command etc). Legacy `#` comments only for fallback migration.
- Used by Code Mode y Dashboard para descubrir tools. Dashboard **nunca** hace I/O directo, siempre vía `Registry` class (`get_config`, `add`, `patch_enabled`, `remove`, `list`, `read_pyi`).
- Escrituras atómicas (`*.json` + `*.pyi` juntos), last-write-wins para concurrencia CLI ↔ Dashboard.

### Dashboard Bounded Context (htpy + Starlette embebido)

- **Embebido**: un solo proceso `Gateway(registry, host)` monta `dashboard_routes` en `Starlette(routes=[/health, /mcp, /mcp/messages, *dashboard])`. Un `uvicorn.run(gateway.app)` sirve MCP + Dashboard.
- **Rutas SSR (htpy)**:
  - `GET /dashboard` → HTML completo `layout(servers, warning_banner)` (Tailwind `max-w-6xl mx-auto`, `htmx.min.js`)
  - `GET /dashboard/servers` → fragmento `<tbody id="server-table-body">` (hx polling)
  - `GET /dashboard/servers/{name}` → `server_drawer` con firmas (truncado >50KB)
  - `GET /dashboard/close` → cierra drawer
  - `GET /static/tailwind.css` + `/static/htmx.min.js` → `StaticFiles` vendoreados
- **Rutas API JSON (también consumidas por htmx)**:
  - `GET /api/servers` → `200 [{name, type, enabled, tool_count, url|command, timeout}]` secrets `***`
  - `GET /api/servers/{name}` → `200 {config, tools, pyi_content, truncated}` secrets `***`
  - `POST /api/servers` → `201` + discovery `tools/list` (timeout + transport `streamable-http→sse→http`); si falla → `tools=[]` + toast `No tools discovered`; `409` si duplicado
  - `PATCH /api/servers/{name}` → `{"enabled": bool}` via `Registry.patch_enabled` (badge `disabled`/`healthy`/`unreachable`)
  - `DELETE /api/servers/{name}` → `204` (idempotente, borra `*.json`+`*.pyi`+`tokens/{name}.json`)
  - `POST /api/servers/{name}/refresh` → `202 {status:"refreshing"}` background task no bloqueante (health <50ms), `409` si disabled
  - `POST /api/servers/{name}/reveal` → `200 {headers|oauth|environment}` solo `127.0.0.1` vía POST, rate-limit 5/min, audit log sin valor, `403` si no loopback, `405` si GET
- **Content negotiation**: `HX-Request: true` → `text/html` fragment para swap; sin header → `application/json`
- **Static vendoreado**: `dashboard/static/tailwind.css` (<100KB purged) + `htmx.min.js` (<20KB) commiteados, sin `package.json`/`node_modules`, CI no instala Node, `ruff` único lint.

### Local-First Security

- `serve --host 127.0.0.1` default. Desvío requiere `MCP_GWAY_ALLOW_REMOTE=1`; si no → `sys.exit(2)`.
- Si `host not in (127.0.0.1, ::1, localhost)` → log `warning` + respuesta incluye `X-Warning: exposed` + banner ámbar htpy + botón `Reveal` deshabilitado.
- Masking obligatorio `***` en `GET /api/servers`, `GET /api/servers/{name}`, `GET /dashboard` (headers, `oauth.clientSecret`, `environment`). Reveal solo `POST` loopback.

### OAuth Flow

1. Discover Protected Resource Metadata (RFC 8707)
2. Discover OAuth metadata from authorization server
3. Dynamic client registration (RFC 7591)
4. PKCE authorization code flow
5. Token storage in `~/.config/mcp-gway/tokens/` — reutilizado por Dashboard `refresh` (no duplicado; ver `oauth.py:run_oauth_flow`)

### SSE Transport

- `GET /mcp` → SSE stream with `endpoint` event
- `POST /mcp/messages?session_id=...` → JSON-RPC messages
- Session management via asyncio.Queue
