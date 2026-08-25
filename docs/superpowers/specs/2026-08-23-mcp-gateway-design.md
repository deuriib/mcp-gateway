# MCP Gateway CLI — Design Spec

## Overview

A standalone Python CLI tool and gateway server for managing MCP (Model Context Protocol) servers with Code Mode support. Exposes 4 meta-tools (`listToolFiles`, `readToolFile`, `getToolDocs`, `executeToolCode`) that allow LLMs to discover and orchestrate tools through a Starlark sandbox — reducing input token usage by up to 92% when using multiple MCP servers.

## Goals

1. **CRUD MCP clients** via CLI commands (add/remove/update/list)
2. **Gateway server** exposing MCP protocol over HTTP/SSE (compatible with Claude Desktop, Cursor, etc.)
3. **Code Mode** with 4 meta-tools identical to Bifrost's implementation
4. **File-system storage** — `.pyi` stub files in `servers/` directory, no database
5. **Starlark sandbox** for safe, hermetic code execution

## Non-Goals

- User authentication / virtual keys (future enhancement)
- Agent Mode auto-execution (future enhancement)
- Cluster mode / multi-node (future enhancement)

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.12+ |
| Package Manager | mise + uv | Latest |
| MCP Protocol | `mcp` SDK | 2.0.0 |
| Sandbox | `starlark-pyo3` | 2026.1+ |
| CLI Framework | `click` | 8.0+ |
| HTTP Server | `starlette` + `uvicorn` | 0.37+ / 0.30+ |
| HTTP Client | `httpx` | 0.27+ |

## Project Structure

```
mcp-gateway/
├── pyproject.toml
├── src/
│   └── mcp_gateway/
│       ├── __init__.py
│       ├── cli.py              # click CLI commands
│       ├── gateway.py           # HTTP/SSE server
│       ├── registry.py          # .pyi file management
│       ├── code_mode.py         # 4 meta-tools implementation
│       ├── sandbox.py           # Starlark sandbox wrapper
│       └── models.py            # Pydantic models for configs
├── servers/                     # .pyi stub files (runtime data)
├── tests/
│   ├── test_cli.py
│   ├── test_registry.py
│   ├── test_code_mode.py
│   └── test_gateway.py
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-08-23-mcp-gateway-design.md
```

## Data Model

### MCP Client Config

```python
class MCPClientConfig(BaseModel):
    name: str                    # Unique identifier (ASCII, no hyphens)
    connection_type: str         # "http" | "stdio" | "sse"
    connection_string: str       # URL for http/sse, command for stdio
    stdio_config: dict | None    # {"command": "...", "args": [...]}
    tools_to_execute: list[str]  # ["*"] or specific tool names
    is_code_mode_client: bool    # Always true for our use case
```

### .pyi Stub File Format

```python
# <server_name> server tools
# Usage: <server_name>.tool_name(param=value)
# For detailed docs: use getToolDocs(server="<server_name>", tool="tool_name")

def tool_name(param1: str, param2: int = None) -> dict:  # Description
    ...
```

## CLI Commands

### `mcp-gateway add <name>`

Add a new MCP client and generate its `.pyi` stub file.

```bash
# HTTP server
mcp-gateway add youtube --type http --url http://localhost:3001/mcp

# STDIO server
mcp-gateway add filesystem --type stdio --command npx --args '["-y", "@anthropic/mcp-filesystem"]'

# SSE server
mcp-gateway add realtime --type sse --url https://stream.example.com/sse

# With tool filtering
mcp-gateway add youtube --type http --url http://localhost:3001/mcp --tools "search,get_video"
```

**Flow:**
1. Validate name (ASCII, no hyphens, no leading digit)
2. Connect to MCP server and discover tools via `tools/list`
3. Generate `.pyi` stub in `servers/<name>.pyi`
4. Print discovered tools

### `mcp-gateway remove <name>`

Remove an MCP client and its `.pyi` stub.

```bash
mcp-gateway remove youtube
```

### `mcp-gateway update <name>`

Update tools list for an existing client, regenerate `.pyi`.

```bash
mcp-gateway update youtube --tools "search,get_video,delete_video"
```

### `mcp-gateway list`

List all connected MCP servers and their tool counts.

```bash
mcp-gateway list
# Output:
# Name        Type   Tools  State
# youtube     HTTP   3      healthy
# filesystem  STDIO  5      healthy
```

### `mcp-gateway inspect <name>`

Show detailed tool signatures for a server.

```bash
mcp-gateway inspect youtube
# Output:
# search(query: str, maxResults: int = None) -> dict  # Search for videos
# get_video(id: str) -> dict  # Get video details
```

### `mcp-gateway serve`

Start the gateway server.

```bash
mcp-gateway serve --host 0.0.0.0 --port 8080
```

## Gateway Server

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/mcp` | POST | JSON-RPC 2.0 (tool discovery + execution) |
| `/mcp` | GET | SSE stream for persistent connections |
| `/health` | GET | Health check |

### JSON-RPC Methods

#### `tools/list`

Returns the 4 Code Mode meta-tools.

```json
{
  "tools": [
    {"name": "listToolFiles", "description": "Lists all available virtual .pyi stub files"},
    {"name": "readToolFile", "description": "Reads a .pyi file for compact function signatures"},
    {"name": "getToolDocs", "description": "Gets detailed documentation for a specific tool"},
    {"name": "executeToolCode", "description": "Executes Python code in sandboxed Starlark"}
  ]
}
```

#### `tools/call`

Routes to the appropriate meta-tool handler.

## Code Mode Implementation

### listToolFiles

Scans `servers/` directory and returns all `.pyi` files.

```
Output: servers/youtube.pyi, servers/filesystem.pyi
```

### readToolFile

Reads a `.pyi` file and returns its content (function signatures).

**Parameters:**
- `fileName` (required): e.g., `servers/youtube.pyi`
- `startLine` (optional): 1-based start line
- `endLine` (optional): 1-based end line

### getToolDocs

Extracts the docstring for a specific tool from the `.pyi` file.

**Parameters:**
- `server` (required): e.g., `"youtube"`
- `tool` (required): e.g., `"search"`

### executeToolCode

Executes user-written code in a Starlark sandbox with server objects injected as globals.

**Parameters:**
- `code` (required): Python/Starlark code

**Execution Environment:**
- Starlark interpreter (Python subset, hermetic)
- Server objects exposed as globals (e.g., `youtube.search(...)`)
- Synchronous tool calls only
- No `import`, no file I/O, no network access
- 30-second timeout
- `result` variable returned as response

## Sandbox (starlark-pyo3)

```python
import starlark as sl

class StarlarkSandbox:
    def __init__(self):
        self.globals = sl.Globals.standard()

    def inject_server(self, name: str, server_proxy):
        """Inject a server proxy as a global object."""
        self.modules[name] = server_proxy

    def execute(self, code: str, timeout: float = 30.0) -> dict:
        """Execute code in sandbox, return result."""
        mod = sl.Module()
        ast = sl.parse("code.star", code)
        val = sl.eval(mod, ast, self.globals)
        return {"result": val}
```

### Server Proxy

Each MCP server is wrapped in a proxy that translates attribute access into MCP `tools/call`:

```python
class ServerProxy:
    def __init__(self, name: str, client: MCPClient):
        self.name = name
        self.client = client

    def __getattr__(self, tool_name: str):
        def tool_fn(**kwargs):
            return self.client.call_tool(tool_name, kwargs)
        return tool_fn
```

## Error Handling

| Error | Response |
|-------|----------|
| Unknown server in `executeToolCode` | `"Variable 'X' not defined. Available: youtube, filesystem"` |
| Tool not found | `"Tool 'X' not found on server 'Y'"` |
| Execution timeout | `"Execution timed out after 30s"` |
| Invalid Starlark syntax | `"Syntax error: ..."` |
| MCP server unreachable | `"Connection failed to 'X': ..."` |

## Testing Strategy

1. **Unit tests** — registry (.pyi CRUD), sandbox (Starlark execution), models
2. **Integration tests** — CLI commands with mock MCP servers
3. **E2E tests** — Full gateway with real MCP server (e.g., filesystem)

## Implementation Order

1. **Phase 1:** Project scaffold, models, registry (.pyi CRUD)
2. **Phase 2:** Starlark sandbox + server proxy
3. **Phase 3:** 4 Code Mode meta-tools
4. **Phase 4:** Gateway server (HTTP/SSE + JSON-RPC)
5. **Phase 5:** CLI commands (add/remove/update/list/inspect/serve)
6. **Phase 6:** Tests, docs, cleanup
