# MCP Gateway

[![PyPI version](https://badge.fury.io/py/mcp-gway.svg)](https://pypi.org/project/mcp-gway/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-gway)](https://pypi.org/project/mcp-gway/)
[![License](https://img.shields.io/pypi/l/mcp-gway)](https://github.com/deuriib/mcp-gateway/blob/main/LICENSE)

A standalone CLI gateway that aggregates multiple MCP (Model Context Protocol) servers behind a single headless HTTP/SSE endpoint with **Code Mode** — reducing LLM input token usage by up to 92% when using multiple MCP servers. Headless gateway (**v1.5.0 GA**): CLI-managed, no UI dependencies.

## Features

- **Multi-Server Aggregation** — Connect to multiple MCP servers (`remote` / `local`, OpenCode format) and expose them through a single endpoint
- **Code Mode** — 4 meta-tools that let LLMs discover and use tools dynamically without loading all schemas upfront
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
mcp-gway add youtube --type remote --url https://api.example.com/mcp
# SSRF-guard: private/loopback/link-local hosts rejected (src/mcp_gway/models.py:115-163); localhost solo en tests.

# Remote with headers
mcp-gway add supabase --type remote --url https://mcp.supabase.com/mcp --header "Authorization=Bearer TOKEN"

# Remote with pre-registered OAuth
mcp-gway add supabase --type remote --url https://mcp.supabase.com/mcp --oauth-client-id ID --oauth-client-secret SECRET --oauth-scope "openid profile"

> **Shell-history warning:** no pases secretos reales en `--header` / `--oauth-client-secret` (quedan en `~/.bash_history` / `ps`). Prefiere `mcp-gway refresh <name> --auth` o variables de entorno efímeras.

# Remote with timeout and enable toggle
mcp-gway add api --type remote --url https://api.example.com/mcp --timeout 10000 --enabled
mcp-gway add api --type remote --url https://api.example.com/mcp --timeout 10000 --no-enabled

# Local
mcp-gway add filesystem --type local --command "npx -y @anthropic/mcp-filesystem"
mcp-gway add tools --type local --command "python -m my_mcp_server" --env MY_VAR=value --cwd /path/to/workdir
mcp-gway add tools --type local --command "npx -y my-mcp" --env KEY=VALUE --env OTHER=123 --cwd /srv/mcp/workdir

# List and serve (local-first)
mcp-gway list
mcp-gway serve --port 8080              # bindea 127.0.0.1 por defecto
mcp-gway serve --host 127.0.0.1 --port 8080
curl -s http://127.0.0.1:8080/health | jq
```

### Server Types (only `remote` / `local`)

`--type` only accepts `local|remote` (`cli.py:50`). Legacy values `http|stdio|sse|streamable-http` are rejected by click, and `--args` / `--docs-url` do not exist. For `local`, `--command` is a single string (split via `shlex`).

## Management — CLI-Only

Headless gateway: all server management (`add`/`remove`/`list`/`inspect`/`refresh`) is CLI-only.
One `Gateway(registry, host)` process serves `/mcp`, `/health`, `/ready`, `/live` and `/metrics` on the same `Starlette` app. Registry (`servers/*.json` + `servers/*.pyi`) is the single source of truth.

### Local-First Security

```bash
# Default seguro — solo loopback
mcp-gway serve --port 8080            # bindea 127.0.0.1

# Exponer en 0.0.0.0 requiere opt-in explícito
MCP_GWAY_ALLOW_REMOTE=1 mcp-gway serve --host 0.0.0.0 --port 8080
# └─ log warning "server exposed on non-loopback host"
# Protege con firewall + auth reversa: nunca expongas 0.0.0.0 sin firewall/auth delante.

# Sin opt-in → error controlado
mcp-gway serve --host 0.0.0.0
# Error: binding to non-loopback host '0.0.0.0' requires MCP_GWAY_ALLOW_REMOTE=1
# exit 2
```

## Observability — Logs + Metrics + Health (Approach C, v1.5.0)

> **Zero vendor lock-in:** stdlib `json` logs (no `structlog`), vendored `MetricsRegistry` (no `prometheus_client`), correlation via `X-Request-ID` + `contextvars`, health probes `/health|/ready|/live` + Prometheus text `/metrics`. Local-first + masking `***` preserved; `X-Warning: exposed` solo en `GET /metrics` → `403`.

**Health & Metrics:**

```bash
curl -s http://127.0.0.1:8080/health | jq
# {"status":"ok","version":"1.5.0","checks":{"registry":"ok","routes":"ok"},"uptime_seconds":42}
curl -s http://127.0.0.1:8080/ready | jq   # 200 ready / 503 not_ready (registry/routes/event_loop checks)
curl -s http://127.0.0.1:8080/live | jq    # 200 alive — no FS I/O, <5ms
curl -s http://127.0.0.1:8080/metrics | head -n 20
# # HELP mcp_gway_http_requests_total Total HTTP requests
# # TYPE mcp_gway_http_requests_total counter
# mcp_gway_http_requests_total{method="GET",path="/health",status="200"} 7
```

**Correlation & JSON logs:**

```bash
curl -s -H "X-Request-ID: demo123" http://127.0.0.1:8080/health -D - | grep -i X-Request-ID
# X-Request-ID: demo123  ← echo on every response; json log line also has "request_id":"demo123"
uv run mcp-gway serve --port 8080 2>&1 | head   # each line valid JSON: timestamp, level, logger, message, request_id, method, path, status, duration_ms
```

- `X-Request-ID` or `X-Correlation-ID` accepted, sanitized to `^[A-Za-z0-9_-]{1,64}$`, truncated; auto `uuid4` if absent.
- Labels bounded: `path` collapsed to `/mcp` or `/mcp/messages` (all other routes recorded as-is), server sanitized `[^A-Za-z0-9_]`→`_` 32 chars.
- Metrics: `http_requests_total`, `http_request_duration_seconds` (buckets 0.005..5), `mcp_tool_calls_total{server,tool,status}`, `discovery_duration_seconds`, `sandbox_execute_total{status}`, `registry_operations_total{op}`, `gateway_sessions_active`.

**Local-first gating:** `/metrics` never leaks secrets; `serve` on non-loopback without `MCP_GWAY_ALLOW_REMOTE=1` exits 2; `X-Warning: exposed` only on `GET /metrics` → `403` (src/mcp_gway/observability/health.py:127-139).

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
| `mcp-gway serve [--host 127.0.0.1] [--port <port>]` | Start gateway (MCP + health probes). Default `127.0.0.1`; `0.0.0.0` necesita `MCP_GWAY_ALLOW_REMOTE=1` |

> **Types:** only `--type local|remote` (`cli.py:50`). Legacy `http|stdio|sse|streamable-http` are rejected by click. There is no `--args` / `--docs-url`.

Options for `add` (OpenCode) — 13 flags (cli.py:45-95):

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

## Local Commands — Dynamic Allow-List (feat-006)

> **Dynamic-no-static:** no hardcoded binaries. Operators allow-list once via env; see [ADR-009](docs/architecture/adr-009-dynamic-local-commands.md).

**Default-deny:** empty `MCP_GWAY_ALLOW_LOCAL_COMMANDS` denies every `local` command.

```bash
# Allow-list (CSV basenames, `*` = invalid → deny + warn)
export MCP_GWAY_ALLOW_LOCAL_COMMANDS="npx,uvx,python3,agentmemory"
mcp-gway add mem --type local --command "agentmemory mcp local"
mcp-gway add fs --type local --command "npx -y @anthropic/mcp-filesystem" --cwd /srv/mcp/workdir

# Break-glass 72h (bootstrap only, time-boxed)
export MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL=1
unset MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL
```

- Marker `~/.config/mcp-gway/.local_unrestricted` (epoch, `0o600`, 72h TTL) — fail-closed: missing, expired, or invalid → deny.
- Any syntactically valid basename allowed while marker fresh; otherwise deny.
- `unset` returns to allow-list mode.
- CLI `add`/`refresh` enforces allow-list/unrestricted plus re-validation before persist.
- `cwd` must be absolute + real + `is_dir`, else `reason_code=invalid_cwd`. Env denylist (`PATH`, `LD_PRELOAD`, `PYTHONPATH`, …) → `reason_code=denied_env`.
- Spawn only resolved via PATH lookup (`shutil.which(basename)`); never `shell=True` / `cmd /c` / `sh -c`. Errors carry `reason_code` (`not_allowlisted`, `binary_not_found`, …).

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
# Trigger OAuth flow (preferido — no deja secretos en shell-history)
mcp-gway refresh supabase --auth

# Or store token manually (solo fallback; chmod 600 obligatorio)
mkdir -p ~/.config/mcp-gway/tokens
echo '{"access_token": "YOUR_TOKEN"}' > ~/.config/mcp-gway/tokens/supabase.json
chmod 600 ~/.config/mcp-gway/tokens/supabase.json
```

## Development

```bash
# Install dependencies
uv sync --all-groups  # installs dev group with pre-commit
uv run pre-commit install  # once per clone — hooks already configured in .pre-commit-config.yaml

# Run checks
uv run pre-commit run --all-files  # ruff + ruff-format + hygiene (trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files)
uv run pytest -v  # 185 tests — CLI, MCP, Code Mode, OAuth, observability
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Verification probes (sin Node, sin build)
curl -s http://127.0.0.1:8080/health | jq .status             # "ok"
curl -s http://127.0.0.1:8080/ready | jq .status              # "ready"
curl -s http://127.0.0.1:8080/metrics | head -n 5             # # HELP mcp_gway_...

# Local-first check
mcp-gway serve --host 0.0.0.0 2>&1 | grep -q "requires MCP_GWAY_ALLOW_REMOTE" && echo "gate ok"
```

Pre-commit is already in place (`.pre-commit-config.yaml` — `ruff` v0.16.4, `ruff-format`, `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`).

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        MCP Gateway v1.5.0 GA                         │
├──────────────────────────────────────────────────────────────────────┤
│  CLI (click)              │  Gateway (Starlette + uvicorn, CSP)      │
│  - add remote/local       │  - POST /mcp (JSON-RPC)                  │
│  - remove/inspect/list    │  - GET  /mcp (SSE endpoint event)        │
│  - refresh --auth         │  - POST /mcp/messages?session_id=...     │
│  - serve --host 127.0.0.1 │  - GET  /health                          │
│  (local-first default)    │  - GET  /ready, /live, /metrics           │
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

- **Sin Node** en runtime ni CI: sin UI ni assets vendoreados, `ruff` único linter, `uv_build` backend.
- **Release híbrido** (ADR-007): `push tags v*` → `uv build` + `pypi-publish` (GA `v1.5.0` tag manual) + `workflow_run Tests completed` → `python-semantic-release@v9` para `fix/perf` patches auto. `concurrency: release`, `fetch-depth:0`, `[tool.semantic_release]` sync `pyproject.toml` + `__init__.py` (`1.5.0` exacta).

## License

MIT
