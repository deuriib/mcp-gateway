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
uv sync
```

## Quick Start

```bash
# Add an MCP server
mcp-gway add youtube --type http --url http://localhost:3001/mcp

# Add a stdio server
mcp-gway add filesystem --type stdio --command npx --args '["-y", "@anthropic/mcp-filesystem"]'

# Add a server requiring OAuth
mcp-gway add supabase --type streamable-http --url https://mcp.supabase.com/mcp

# List all servers
mcp-gway list

# Start the gateway
mcp-gway serve --port 8080
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
| `mcp-gway add` | Add an MCP server and generate `.pyi` stub |
| `mcp-gway remove` | Remove an MCP server |
| `mcp-gway update` | Update tools for a server |
| `mcp-gway list` | List all connected servers |
| `mcp-gway inspect` | Show tool signatures for a server |
| `mcp-gway refresh` | Refresh connection and re-discover tools |
| `mcp-gway serve` | Start the gateway server |

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
mkdir -p ~/.config/mcp-gateway/tokens
echo '{"access_token": "YOUR_TOKEN"}' > ~/.config/mcp-gateway/tokens/supabase.json
```

## Development

```bash
# Install dependencies
mise install
uv sync

# Run tests
uv run pytest -v

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

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
│  Registry (.pyi files)        │  OAuth2 (RFC 7591)     │
│  - servers/*.pyi               │  - Dynamic registration│
│  - Tool signatures             │  - Token storage       │
└─────────────────────────────────────────────────────────┘
         │                │                │
    ┌────┴────┐      ┌────┴────┐      ┌────┴────┐
    │ Server1 │      │ Server2 │      │ Server3 │
    │ (HTTP)  │      │ (SSE)   │      │ (Stdio) │
    └─────────┘      └─────────┘      └─────────┘
```

## License

MIT
