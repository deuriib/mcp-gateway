# MCP Gateway CLI

Manage MCP servers with Code Mode support. Reduces LLM input token usage by up to 92% when using multiple MCP servers.

## Install

```bash
mise install
uv sync
```

## Usage

```bash
# Add an MCP server
mcp-gateway add youtube --type http --url http://localhost:3001/mcp

# List servers
mcp-gateway list

# Inspect tools
mcp-gateway inspect youtube

# Start gateway
mcp-gateway serve --port 8080
```

## Connect from Claude Desktop

```json
{
  "mcpServers": {
    "bifrost": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

## Code Mode

When connected, the gateway exposes 4 meta-tools:
- `listToolFiles` — discover servers
- `readToolFile` — load tool signatures
- `getToolDocs` — detailed tool docs
- `executeToolCode` — run code in sandbox
