# AGENTS.md

## Project Overview

**MCP Gateway** — A standalone Python CLI that aggregates multiple MCP servers behind a single HTTP/SSE endpoint with Code Mode.

## Tech Stack

- **Language**: Python 3.12+
- **Package Manager**: uv (with mise for tool versions)
- **CLI Framework**: click
- **HTTP Server**: Starlette + uvicorn
- **MCP SDK**: mcp v2.0.0
- **Sandbox**: starlark-pyo3
- **Testing**: pytest + pytest-asyncio
- **Linting**: ruff

## Project Structure

```
src/mcp_gway/
├── __init__.py          # Package version
├── models.py            # Pydantic models (MCPClientConfig, ToolInfo, ConnectionType)
├── registry.py          # .pyi file CRUD (servers/ directory)
├── sandbox.py           # Starlark sandbox (hermetic execution)
├── server_proxy.py      # MCP server wrapper for sandbox
├── code_mode.py         # 4 meta-tools orchestrator
├── gateway.py           # HTTP/SSE server (JSON-RPC 2.0)
├── cli.py               # CLI commands (add/remove/update/list/inspect/refresh/serve)
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
```

## Commands

```bash
# Development
uv sync                    # Install dependencies
uv run pytest -v           # Run tests
uv run ruff check src/     # Lint
uv run ruff format src/    # Format

# CLI
mcp-gway add <name> --type <http|stdio|sse|streamable-http> [--url <url>] [--command <cmd>]
mcp-gway remove <name>
mcp-gway list
mcp-gway inspect <name>
mcp-gway refresh [<name>] [--auth]
mcp-gway serve [--port 8080]
```

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

- **PyPI**: GitHub Actions workflow triggers on `v*` tags
- **Version**: Semantic versioning in `pyproject.toml`
- **Build**: `uv_build` backend

## Key Patterns

### Registry (.pyi files)
- Each server has a `.pyi` file in `servers/`
- Contains tool signatures and metadata as comments
- Used by Code Mode to discover available tools

### OAuth Flow
1. Discover Protected Resource Metadata (RFC 8707)
2. Discover OAuth metadata from authorization server
3. Dynamic client registration (RFC 7591)
4. PKCE authorization code flow
5. Token storage in `~/.config/mcp-gway/tokens/`

### SSE Transport
- `GET /mcp` → SSE stream with `endpoint` event
- `POST /mcp/messages?session_id=...` → JSON-RPC messages
- Session management via asyncio.Queue
