# AGENTS.md

## Project Overview

**MCP Gateway** — A standalone Python CLI that aggregates multiple MCP servers behind a single headless HTTP/SSE endpoint with Code Mode (v1.4.1 GA, CLI-managed, no UI).

## Tech Stack

- **Language**: Python 3.12+
- **Package Manager**: uv (with mise for tool versions)
- **CLI Framework**: click
- **HTTP Server**: Starlette + uvicorn
- **MCP SDK**: mcp v2.0.0
- **Sandbox**: starlark-pyo3
- **Testing**: pytest + pytest-asyncio (185 tests)
- **Linting**: ruff

## Project Structure

```
src/mcp_gway/
├── __init__.py          # Package version (1.4.1)
├── models.py            # Pydantic models (MCPServerConfig OpenCode + MCPClientConfig deprecated compat, ToolInfo, ConnectionType)
├── registry.py          # .pyi file CRUD (servers/ directory) — única fuente de verdad
├── sandbox.py           # Starlark sandbox (hermetic execution)
├── server_proxy.py      # MCP server wrapper for sandbox
├── code_mode.py         # 4 meta-tools orchestrator
├── gateway.py           # HTTP/SSE server (JSON-RPC 2.0), headless, local-first 127.0.0.1 + CSP
├── cli.py               # CLI commands (add/remove/update/list/inspect/refresh/serve --host 127.0.0.1)
└── oauth.py             # OAuth2 support (dynamic registration, token storage)

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

> **Local-first warning:** `serve` bindea `127.0.0.1` por defecto. `--host 0.0.0.0` sin `MCP_GWAY_ALLOW_REMOTE=1` → `exit 2` + `Error: binding to non-loopback ...`. Con `MCP_GWAY_ALLOW_REMOTE=1` → `WARNING: server exposed on non-loopback` en log + header `X-Warning: exposed`.

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
  - `push v*` → `uv build` + `pypi-publish` determinístico (GA manual `v1.4.1` via tag, CEO GO)
  - `workflow_run` → `python-semantic-release@v9` para patches automáticos `fix/perf` → minor/patch sin tag manual
  - Condición: `if: push || workflow_run.conclusion == 'success'` + `concurrency: release` + `fetch-depth: 0`
- **Version**: `1.4.1` sincronizada `pyproject.toml:project.version` + `src/mcp_gway/__init__.py:__version__` (`[tool.semantic_release]`)
- **Build**: `uv_build` backend — sin Node en CI (`ruff` único linter)

## Key Patterns

### Registry (.pyi + .json) — Única fuente

- `.pyi` = signatures only; `servers/*.json` = OpenCode config (type/url/command etc). Legacy `#` comments only for fallback migration.
- Used by Code Mode para descubrir tools.
- Escrituras atómicas (`*.json` + `*.pyi` juntos), last-write-wins para concurrencia entre escrituras CLI.

### Local-First Security

- `serve --host 127.0.0.1` default. Desvío requiere `MCP_GWAY_ALLOW_REMOTE=1`; si no → `sys.exit(2)`.
- Si `host not in (127.0.0.1, ::1, localhost)` → log `warning` + respuesta incluye `X-Warning: exposed`.

### OAuth Flow

1. Discover Protected Resource Metadata (RFC 8707)
2. Discover OAuth metadata from authorization server
3. Dynamic client registration (RFC 7591)
4. PKCE authorization code flow
5. Token storage in `~/.config/mcp-gway/tokens/` (ver `oauth.py:run_oauth_flow`)

### SSE Transport

- `GET /mcp` → SSE stream with `endpoint` event
- `POST /mcp/messages?session_id=...` → JSON-RPC messages
- Session management via asyncio.Queue
