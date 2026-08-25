# MCP Gateway

[![PyPI version](https://badge.fury.io/py/mcp-gway.svg)](https://pypi.org/project/mcp-gway/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-gway)](https://pypi.org/project/mcp-gway/)
[![License](https://img.shields.io/pypi/l/mcp-gway)](https://github.com/deuriib/mcp-gateway/blob/main/LICENSE)

A standalone CLI gateway that aggregates multiple MCP (Model Context Protocol) servers behind a single HTTP/SSE endpoint with **Code Mode** — reducing LLM input token usage by up to 92% when using multiple MCP servers.

## Features

- **Multi-Server Aggregation** — Connect to multiple MCP servers (HTTP, SSE, Stdio, Streamable HTTP) and expose them through a single endpoint
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

# List and serve
mcp-gway list
mcp-gway serve --port 8080
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
| `mcp-gway serve [--host <host>] [--port <port>]` | Start the gateway server |

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
uv run pytest -v
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

Pre-commit is already in place (`.pre-commit-config.yaml` — `ruff` v0.16.4, `ruff-format`, `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-added-large-files`).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    MCP Gateway                          │
├─────────────────────────────────────────────────────────┤
│  CLI (click)     │  HTTP/SSE Server (Starlette)        │
│  - add           │  - POST /mcp (JSON-RPC)             │
│  - remove        │  - GET /mcp (SSE stream)            │
│  - list          │  - POST /mcp/messages               │
│  - refresh       │                                     │
├─────────────────────────────────────────────────────────┤
│  Code Mode (4 meta-tools)     │  Starlark Sandbox      │
│  - listToolFiles               │  - Hermetic execution  │
│  - readToolFile                │  - Server injection    │
│  - getToolDocs                 │                        │
│  - executeToolCode             │                        │
├─────────────────────────────────────────────────────────┤
│  Registry                      │  OAuth2 (RFC 7591)     │
│  - servers/*.pyi = signatures  │  - Dynamic registration│
│  - servers/*.json = config     │  - Token storage       │
│  - legacy # comments fallback  │                        │
└─────────────────────────────────────────────────────────┘
         │                │                │
    ┌────┴────┐      ┌────┴────┐      ┌────┴────┐
    │ Server1 │      │ Server2 │      │ Server3 │
    │ (HTTP)  │      │ (SSE)   │      │ (Stdio) │
    └─────────┘      └─────────┘      └─────────┘
```

## License

MIT
