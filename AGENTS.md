# AGENTS.md

## Project Overview

**MCP Gateway** — A standalone Python CLI that aggregates multiple MCP servers behind a single headless HTTP/SSE endpoint with Code Mode (v2.0.0 interno, CLI-only, headless, sin dashboard/catalog).

> **Nota interna:** ver `CHANGELOG.md` v2.0.0 (2026-09-10). Release interno no publicado — no anuncio externo.

## Tech Stack

- **Language**: Python 3.12+
- **Package Manager**: uv (with mise for tool versions)
- **CLI Framework**: click
- **HTTP Server**: Starlette + uvicorn
- **MCP SDK**: mcp v2.0.0
- **Sandbox**: starlark-pyo3
- **Testing**: pytest + pytest-asyncio (185 tests)
- **Linting**: ruff
- **Nota**: `htpy` retirado en v2.0.0, `httpx` kept.

## Project Structure

```
src/mcp_gway/
├── __init__.py          # Package version (2.0.0)
├── models.py            # Pydantic models (MCPServerConfig OpenCode-only local|remote, ToolInfo, OAuthConfig)
├── registry.py          # .pyi file CRUD (servers/ directory) — única fuente de verdad
├── sandbox.py           # Starlark sandbox (hermetic execution)
├── server_proxy.py      # MCP server wrapper for sandbox
├── code_mode.py         # 4 meta-tools orchestrator
├── gateway.py           # HTTP/SSE server (JSON-RPC 2.0), headless, local-first 127.0.0.1 + CSP — 5 paths lógicos vivos: /mcp (GET+POST), /health, /ready, /live, /metrics (gateway.py:166-175, 7 Route entries; /mcp/messages es alias POST al mismo handler _mcp_post, no endpoint independiente)
├── cli.py               # CLI commands (add/remove/update/list/inspect/refresh/serve --host 127.0.0.1)
└── oauth.py             # OAuth2 support (dynamic registration, token storage)

> **Retirado en v2.0.0 (no servir):** dashboard (`/dashboard`, `/api/servers`, `/static`, `/` alias) y catalog (`/api/catalog`, `/dashboard/catalog`, Bifrost fetch, `~/.config/mcp-gway/catalog.json`). Gestión CLI-only.

tests/
├── test_models.py       # Model validation tests
├── test_registry.py     # Registry CRUD tests
├── test_sandbox.py      # Sandbox execution tests
├── test_server_proxy.py # Server proxy tests
├── test_code_mode.py    # Code mode tests
├── test_gateway.py      # HTTP/SSE server tests
├── test_cli.py          # CLI command tests
└── test_integration.py  # End-to-end flow tests

docs/specs/
├── SPEC-UI-001.md       # SUPERSEDED 2026-09-10 (retirado; headless, CLI-only)
├── SCENARIOS-UI-001.md  # SUPERSEDED 2026-09-10
└── ACCEPTANCE-UI-001.md # SUPERSEDED 2026-09-10
```

## Commands

```bash
# Development
uv sync --all-groups                     # Install dependencies (dev group includes pre-commit)
uv run pre-commit install                # Install git hooks (once per clone)
uv run pre-commit run --all-files        # Run hooks on all files
uv run pytest -v                         # Run tests (185 tests)
uv run ruff check src/ tests/            # Lint (CI parity)
uv run ruff format --check src/ tests/   # Format check (CI parity)

# CLI — OpenCode format (primary)
mcp-gway add <name> --type remote --url <url> [--header "KEY=VALUE"] [--oauth-client-id ID] [--oauth-client-secret SECRET] [--oauth-scope SCOPE] [--timeout 5000] [--enabled] [--oauth-port 8989]
# Shell-history warning: no secretos reales en --header/--oauth-client-secret; preferir `refresh --auth`.
mcp-gway add <name> --type local --command "npx -y my-mcp" [--env KEY=VALUE] [--cwd /path] [--tools "*"]
# Local default-deny: `local` requiere allow-list MCP_GWAY_ALLOW_LOCAL_COMMANDS="npx,uvx,python3,bunx" (vacío = deny); `*` inválido → deny + warn.
# feat-006 allow-list + break-glass 72h (ADR-009 docs/architecture/adr-009-dynamic-local-commands.md,
#   src/mcp_gway/core/policy.py): default-deny empty MCP_GWAY_ALLOW_LOCAL_COMMANDS;
#   CSV basenames, `*` inválido; UNRESTRICTED_TTL 72*3600; break-glass MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL=1
#   + marker ~/.config/mcp-gway/.local_unrestricted (epoch, 0o600, 72h TTL); vars MCP_GWAY_ALLOW_LOCAL_COMMANDS
#   / MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL / MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD (no renombrar).
# Full options: 13 flags (cli.py:45-95): --type/--url/--command/--header/--env/--cwd/--oauth-client-id/--oauth-client-secret/--oauth-scope/--timeout/--enabled/--oauth-port/--tools
# Only --type local|remote (cli.py:50). No --args, no --docs-url. Legacy http|stdio|sse|streamable-http rejected by click.
mcp-gway remove <name>
mcp-gway list
mcp-gway inspect <name>
mcp-gway refresh [<name>] [--auth] [--oauth-port <port>]
mcp-gway serve [--host 127.0.0.1] [--port 8080]   # default local-first; 0.0.0.0 requiere MCP_GWAY_ALLOW_REMOTE=1
```

> **Local-first warning:** `serve` bindea `127.0.0.1` por defecto. `--host 0.0.0.0` sin `MCP_GWAY_ALLOW_REMOTE=1` → `exit 2` + `Error: binding to non-loopback ...`. Con `MCP_GWAY_ALLOW_REMOTE=1` → `WARNING: server exposed on non-loopback` en log; `X-Warning: exposed` solo en `GET /metrics` → `403` cuando se expone sin opt-in. No exponer `0.0.0.0` sin firewall/auth delante.

## Code Conventions

- Type hints on all public functions
- `from __future__ import annotations` in all modules
- Docstrings on classes and public methods
- ruff for linting and formatting
- No comments unless explicitly requested

## Testing

- Tests in `tests/` mirror `src/mcp_gway/` structure
- Use `tmp_path` fixture for file system tests
- Use `monkeypatch` for mocking
- Async tests with `@pytest.mark.asyncio`
- Mock MCP clients for unit tests

## Deployment

- **PyPI**: Hybrid workflow `.github/workflows/release.yml` — `on: push tags v*` **+** `on: workflow_run Tests completed` (ver ADR-007)
  - `push v*` → `uv build` + `pypi-publish` determinístico (GA interno `v2.0.0` via tag, nota interna no publicada — no anuncio externo)
  - `workflow_run` → `python-semantic-release@v10 (>=10.0.0, uv.lock 10.6.1)` para patches automáticos `fix/perf` → minor/patch sin tag manual
  - Condición: `if: push || workflow_run.conclusion == 'success'` + `concurrency: release` + `fetch-depth: 0`
- **Version**: `2.0.0` sincronizada `pyproject.toml:project.version` + `src/mcp_gway/__init__.py:__version__` (`[tool.semantic_release]`)
- **Build**: `uv_build` backend — sin Node en CI (`ruff` único linter)

## Key Patterns

### Endpoints vivos + Retiro dashboard/catalog

- **Vivos (v2.0.0):** `/mcp` (GET+POST), `/health`, `/ready`, `/live`, `/metrics` (`gateway.py:166-175`, 7 Route entries; `/mcp/messages` es alias POST al mismo handler `_mcp_post`, no endpoint independiente). Gestión CLI-only.
- **Retirados (no servir):** dashboard (`/dashboard`, `/api/servers`, `/static`, `/` alias) y catalog (`/api/catalog`, `/dashboard/catalog`, Bifrost fetch, `~/.config/mcp-gway/catalog.json` — borrar caché vieja manualmente).

### Registry (.pyi + .json) — Única fuente

- `.pyi` = signatures only; `servers/*.json` = OpenCode config (type/url/command etc). Legacy `#` comments only for fallback migration.
- Used by Code Mode para descubrir tools.
- Escrituras atómicas (`*.json` + `*.pyi` juntos), last-write-wins para concurrencia entre escrituras CLI.

### Local-First Security

- `serve --host 127.0.0.1` default. Desvío requiere `MCP_GWAY_ALLOW_REMOTE=1`; si no → `sys.exit(2)`.
- `remote --url` con SSRF-guard (`models.py:115-163`): hosts privados/loopback/link-local rechazados; ejemplo vivo `https://api.example.com/mcp`.
- Si `host not in (127.0.0.1, ::1, localhost)` → log `warning` + banner consola; `X-Warning: exposed` solo en `GET /metrics` → `403` (observability/health.py:127-139).
- feat-006 allow-list + break-glass 72h (`src/mcp_gway/core/policy.py`, ADR-009):
  - default-deny con `MCP_GWAY_ALLOW_LOCAL_COMMANDS` vacío; ejemplo recomendado `"npx,uvx,python3,bunx"`.
  - CSV basenames case-insensitive, `*`/paths inválidos → deny + warn.
  - Nota CISO opt-in: `bunx` solo recomendado en docs (no default en código, default-deny vacío se mantiene), solo opt-in con pin + owner + regate 90d; `bun` runtime fuera; denylist EXACT PATH,PATHEXT,SYSTEMROOT,COMSPEC,LD_PRELOAD,LD_LIBRARY_PATH,PYTHONPATH,PYTHONHOME,NODE_OPTIONS,NODE_PATH,NODE_EXTRA_CA_CERTS,NODE_TLS_REJECT_UNAUTHORIZED + PREFIXES DYLD_,NPM_CONFIG_,BUN_,UV_ + PATH controlado (`NODE_ENV` permitido, no denylisted); prohibido `*`, paths o shell.
  - Break-glass `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL=1` + marker `~/.config/mcp-gway/.local_unrestricted` (epoch, `0o600`, 72h TTL).
  - No renombrar `MCP_GWAY_ALLOW_LOCAL_COMMANDS` / `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL` / `MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD` (`VIA_DASHBOARD` inerte desde v2.0.0 headless CLI-only).

### OAuth Flow

1. Discover Protected Resource Metadata (RFC 8707)
2. Discover OAuth metadata from authorization server
3. Dynamic client registration (RFC 7591)
4. PKCE authorization code flow
5. Token storage in `~/.config/mcp-gway/tokens/` (`0o600` via `_secure_atomic_write`, ver `oauth.py:run_oauth_flow`; preferir `refresh --auth`, manual solo con `chmod 600`)

### SSE Transport

- `GET /mcp` → SSE stream with `endpoint` event
- `POST /mcp/messages?session_id=...` → JSON-RPC messages
- Session management via asyncio.Queue
