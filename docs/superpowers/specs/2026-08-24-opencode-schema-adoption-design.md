# Design Spec: Adopt OpenCode MCP Server Schema

**Date:** 2026-08-24
**Author:** Vasquez (CTO Orchestrator)
**Status:** Draft — pending user review

## Problem Statement

MCP Gateway's current configuration model uses 4 explicit connection types (`http`, `stdio`, `sse`, `streamable-http`). OpenCode's MCP server schema simplifies this to 2 types (`local`, `remote`), with transport auto-detection for remote servers. Adopting this schema:

1. Aligns MCP Gateway with the OpenCode ecosystem standard
2. Simplifies the user-facing CLI (fewer type choices)
3. Adds missing config fields (`headers`, `oauth`, `enabled`, `timeout`)
4. Enables resilient connection testing with transport fallback

## Design Decision

**Option A: Complete replacement** — Replace `MCPClientConfig` with a new `MCPServerConfig` model that mirrors OpenCode's schema. CLI accepts both old and new formats; internal representation is always OpenCode-style. Auto-migration for existing JSON configs.

## New Configuration Schema

### `ToolInfo` (unchanged)

```python
class ToolInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
```

### `MCPServerConfig` (replaces `MCPClientConfig`)

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Any

class OAuthConfig(BaseModel):
    clientId: str | None = None
    clientSecret: str | None = None
    scope: str | None = None

class MCPServerConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    type: Literal["local", "remote"]
    enabled: bool = True
    timeout: int = 5000  # milliseconds

    # type=local
    command: list[str] | None = None
    cwd: str | None = None
    environment: dict[str, str] | None = None

    # type=remote
    url: str | None = None
    headers: dict[str, str] | None = None
    oauth: OAuthConfig | bool | None = None
    # None = auto-detect (try OAuth on 401)
    # bool False = explicitly disable OAuth, use static headers only
    # OAuthConfig object = pre-registered client credentials

    # Internal: resolved after connection test, stored in JSON
    resolved_transport: Literal["sse", "streamable-http", "http"] | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.type == "local":
            if not self.command:
                raise ValueError("'command' required for type=local")
        elif self.type == "remote":
            if not self.url:
                raise ValueError("'url' required for type=remote")
```

### Field Mapping (Old → New)

| Old Field | New Field | Notes |
|-----------|-----------|-------|
| `connection_type` | `type` | `stdio` → `local`, `http/sse/streamable-http` → `remote` |
| `connection_string` (stdio) | `command` | Parsed from string to array |
| `connection_string` (remote) | `url` | Direct mapping |
| `stdio_config.command` | `command[0]` | First element of command array |
| `stdio_config.args` | `command[1:]` | Rest of command array |
| `stdio_config.envs` | `environment` | `["KEY=VAL"]` → `{"KEY": "VAL"}` |
| — | `headers` | New: HTTP headers for remote |
| — | `oauth` | New: OAuth config (was implicit in CLI) |
| — | `enabled` | New: toggle without removal |
| — | `timeout` | New: connection timeout in ms |
| `tools_to_execute` | — | Removed: handled at gateway level |
| `is_code_mode_client` | — | Removed: always true |
| `docs_url` | — | Removed: not part of OpenCode schema |
| — | `resolved_transport` | New: cached transport after auto-detection |

### `MCPServerState` (updated)

```python
class MCPServerState(BaseModel):
    name: str
    config: MCPServerConfig  # was MCPClientConfig
    tools: list[ToolInfo] = Field(default_factory=list)
    state: str = "healthy"
```

## Transport Auto-Detection (`type=remote`)

When connecting to a remote server, the gateway probes transports in order:

1. **Streamable HTTP** (preferred, newest protocol)
2. **SSE** (widely supported)
3. **HTTP** (basic JSON-RPC)

Each probe uses the configured `timeout` (default 5000ms). The first successful transport is cached in `_resolved_transport` for subsequent calls.

```
┌─────────────────────────────────────────┐
│  Remote Connection Flow                 │
│                                         │
│  1. Try streamable-http                 │
│     ├─ Success → cache, return          │
│     └─ Fail/Timeout → continue          │
│  2. Try SSE                             │
│     ├─ Success → cache, return          │
│     └─ Fail/Timeout → continue          │
│  3. Try HTTP                            │
│     ├─ Success → cache, return          │
│     └─ Fail → return error              │
└─────────────────────────────────────────┘
```

### OAuth Integration

- **Auto-detect** (`oauth: None`): If server returns 401, initiate OAuth flow (PKCE + Dynamic Client Registration)
- **Pre-registered** (`oauth: {clientId, clientSecret, scope}`): Use provided credentials
- **Disabled** (`oauth: false`): Skip OAuth entirely, use static `headers` for auth

This matches OpenCode's behavior: `oauth: false` disables auto-detection.

## CLI Changes

### New Commands (OpenCode-style)

```bash
# Remote server (auto-detect transport)
mcp-gway add myserver --type remote --url https://mcp.example.com/mcp
mcp-gway add myserver --type remote --url https://mcp.example.com/mcp \
  --header "Authorization=Bearer TOKEN"
mcp-gway add myserver --type remote --url https://mcp.example.com/mcp \
  --oauth-client-id ID --oauth-client-secret SECRET --oauth-scope "tools:read"

# Local server
mcp-gway add myserver --type local --command npx -y my-mcp-server
mcp-gway add myserver --type local --command python -m my_mcp_server \
  --env MY_VAR=value --cwd /path/to/workdir
```

### Backward Compatibility

Old format still works, internally mapped:

```bash
# This still works:
mcp-gway add myserver --type sse --url https://...
# Internally becomes: type=remote, url=..., resolved_transport=sse

# This still works:
mcp-gway add myserver --type stdio --command "npx -y x" --args '["--flag"]'
# Internally becomes: type=local, command=["npx", "-y", "x", "--flag"]
```

### New CLI Options

| Option | Type | Description |
|--------|------|-------------|
| `--header` | `KEY=VALUE` (repeatable) | HTTP headers for remote |
| `--oauth-client-id` | string | Pre-registered OAuth client ID |
| `--oauth-client-secret` | string | Pre-registered OAuth client secret |
| `--oauth-scope` | string | OAuth scopes to request |
| `--timeout` | int (ms) | Connection timeout (default 5000) |
| `--enabled / --no-enabled` | flag | Enable/disable server (default: enabled) |

## Registry Changes

### JSON Config Format

Old format (current):
```json
{
  "name": "myserver",
  "connection_type": "sse",
  "connection_string": "https://...",
  "docs_url": ""
}
```

New format (OpenCode-aligned):
```json
{
  "name": "myserver",
  "type": "remote",
  "url": "https://mcp.example.com/mcp",
  "enabled": true,
  "timeout": 5000,
  "headers": {"Authorization": "Bearer TOKEN"},
  "oauth": null,
  "resolved_transport": "streamable-http"
}
```

### Auto-Migration

When `Registry.get_config()` reads an old-format JSON:
1. Detect old fields (`connection_type`, `connection_string`, `stdio_*`)
2. Map to new schema
3. Write new-format JSON (one-time migration)
4. Return `MCPServerConfig`

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Remote timeout on all transports | Clear error: "Could not connect to {url}. All transports failed." |
| OAuth required but not configured | Auto-initiate OAuth flow (current behavior preserved) |
| Local command not found | Clear error: "Command '{cmd}' not found. Is it installed?" |
| Invalid config (missing required fields) | Pydantic validation error with specific field message |
| `resolved_transport` stale | Re-probe on next connection if cached transport fails |

## Testing Strategy

### Unit Tests
- `test_models.py`: Validate new `MCPServerConfig` schema, field mapping, validation errors
- `test_registry.py`: Auto-migration from old format, JSON read/write in new format
- `test_cli.py`: Both old and new CLI syntax, header parsing, OAuth flags

### Integration Tests
- Transport auto-detection: mock servers for each transport type, verify fallback chain
- OAuth flow: mock 401 response → trigger OAuth → verify token storage
- Timeout behavior: mock slow servers, verify timeout per transport

### Resilient Connection Tests
- **Happy path**: streamable-http works on first try
- **Fallback**: streamable-http fails → SSE succeeds
- **All fail**: all transports timeout → error message
- **OAuth trigger**: 401 on first attempt → OAuth → retry with token
- **Headers preserved**: verify headers sent on every retry

## Files Affected

| File | Change |
|------|--------|
| `src/mcp_gway/models.py` | Replace `MCPClientConfig` with `MCPServerConfig`, add `OAuthConfig` |
| `src/mcp_gway/cli.py` | Update `add` command, add new options, backward-compat mapping |
| `src/mcp_gway/registry.py` | Update JSON format, add auto-migration |
| `src/mcp_gway/gateway.py` | Update to use new config model |
| `src/mcp_gway/server_proxy.py` | Update to use new config model |
| `tests/test_models.py` | New schema tests |
| `tests/test_registry.py` | Migration tests |
| `tests/test_cli.py` | New CLI option tests |

## Out of Scope

- Changing the `.pyi` stub generation format (stays the same)
- Code Mode meta-tools (no changes needed)
- Starlark sandbox (no changes needed)
- WebSocket transport (not in OpenCode schema)
- Server-side config serving (`.well-known/opencode` endpoint)

## Success Criteria

1. `mcp-gway add --type remote --url ...` works with auto-detection
2. `mcp-gway add --type local --command ...` works
3. Old CLI syntax (`--type sse`, `--type stdio`) still works
4. Existing JSON configs auto-migrate on first read
5. Transport fallback works: streamable-http → sse → http
6. OAuth flow preserved and enhanced with explicit config
7. All existing tests pass (adapted to new models)
8. New tests cover auto-detection and fallback scenarios
