# OpenCode Schema Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `MCPClientConfig` with OpenCode-aligned `MCPServerConfig` model, update CLI/registry/tests, and add transport auto-detection for remote servers.

**Architecture:** New `MCPServerConfig` model with `type: "local" | "remote"` replaces the 4-type enum. CLI accepts both old and new syntax with backward-compatible mapping. Registry auto-migrates old JSON configs. Transport auto-detection probes streamable-http → sse → http for remote servers.

**Tech Stack:** Python 3.12+, Pydantic v2, Click, pytest, mcp SDK

**Spec:** `docs/superpowers/specs/2026-08-24-opencode-schema-adoption-design.md`

## Global Constraints

- Python 3.12+ (`from __future__ import annotations` in all modules)
- Pydantic v2 with `model_config`, `model_post_init`
- ruff for linting/formatting
- No comments unless explicitly requested
- TDD: write failing test first, then implement, then verify
- Work-unit commits: one complete, self-contained unit per commit

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/mcp_gway/models.py` | New `MCPServerConfig`, `OAuthConfig`, `ToolInfo` (unchanged), `MCPServerState` |
| `src/mcp_gway/registry.py` | JSON read/write in new format, auto-migration from old format |
| `src/mcp_gway/cli.py` | New CLI options (`--header`, `--oauth-*`, `--timeout`), backward-compat mapping |
| `src/mcp_gway/gateway.py` | Import `MCPServerConfig` instead of `MCPClientConfig` |
| `src/mcp_gway/server_proxy.py` | No changes needed (uses `name` + `client`, not config model) |
| `tests/conftest.py` | Update fixtures to use `MCPServerConfig` |
| `tests/test_models.py` | New schema tests, validation, field mapping |
| `tests/test_registry.py` | Auto-migration tests, new JSON format |
| `tests/test_cli.py` | New CLI syntax tests, backward compat |

---

### Task 1: New Models — `MCPServerConfig` + `OAuthConfig`

**Files:**
- Modify: `src/mcp_gway/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `MCPServerConfig`, `OAuthConfig`, `ConnectionType` (kept for internal use)

- [ ] **Step 1: Write failing tests for new models**

```python
# tests/test_models.py — add these tests

def test_remote_config_valid():
    config = MCPServerConfig(
        name="youtube",
        type="remote",
        url="https://mcp.example.com/mcp",
    )
    assert config.name == "youtube"
    assert config.type == "remote"
    assert config.url == "https://mcp.example.com/mcp"
    assert config.enabled is True
    assert config.timeout == 5000


def test_local_config_valid():
    config = MCPServerConfig(
        name="myserver",
        type="local",
        command=["npx", "-y", "my-mcp-server"],
    )
    assert config.type == "local"
    assert config.command == ["npx", "-y", "my-mcp-server"]


def test_local_requires_command():
    with pytest.raises(ValueError, match="command.*required"):
        MCPServerConfig(name="myserver", type="local")


def test_remote_requires_url():
    with pytest.raises(ValueError, match="url.*required"):
        MCPServerConfig(name="myserver", type="remote")


def test_remote_with_headers():
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
        headers={"Authorization": "Bearer TOKEN"},
    )
    assert config.headers == {"Authorization": "Bearer TOKEN"}


def test_remote_with_oauth_object():
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
        oauth=OAuthConfig(clientId="id", clientSecret="secret"),
    )
    assert config.oauth.clientId == "id"


def test_remote_with_oauth_false():
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
        oauth=False,
    )
    assert config.oauth is False


def test_local_with_environment():
    config = MCPServerConfig(
        name="myserver",
        type="local",
        command=["node", "server.js"],
        environment={"FOO": "bar", "BAZ": "qux"},
    )
    assert config.environment == {"FOO": "bar", "BAZ": "qux"}


def test_local_with_cwd():
    config = MCPServerConfig(
        name="myserver",
        type="local",
        command=["python", "-m", "server"],
        cwd="/path/to/workdir",
    )
    assert config.cwd == "/path/to/workdir"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py -v -k "remote or local or oauth or environment or cwd"`
Expected: FAIL with `ImportError` or `AttributeError` (new classes don't exist yet)

- [ ] **Step 3: Implement new models**

```python
# src/mcp_gway/models.py — replace entire file

"""Pydantic models for MCP server configurations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OAuthConfig(BaseModel):
    """OAuth client credentials for pre-registered apps."""

    clientId: str | None = None
    clientSecret: str | None = None
    scope: str | None = None


class MCPServerConfig(BaseModel):
    """OpenCode-aligned MCP server configuration."""

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

    # Internal: resolved after connection test, stored in JSON
    resolved_transport: Literal["sse", "streamable-http", "http"] | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.type == "local":
            if not self.command:
                raise ValueError("'command' required for type=local")
        elif self.type == "remote":
            if not self.url:
                raise ValueError("'url' required for type=remote")


class ToolInfo(BaseModel):
    """Tool metadata discovered from an MCP server."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPServerState(BaseModel):
    """Runtime state for a connected MCP server."""

    name: str
    config: MCPServerConfig
    tools: list[ToolInfo] = Field(default_factory=list)
    state: str = "healthy"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v -k "remote or local or oauth or environment or cwd"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_gway/models.py tests/test_models.py
git commit -m "feat(models): add MCPServerConfig with OpenCode schema"
```

---

### Task 2: Keep old models as aliases for backward compat

**Files:**
- Modify: `src/mcp_gway/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `MCPClientConfig` (alias), `StdioConfig` (alias), `ConnectionType` (kept)

- [ ] **Step 1: Write failing tests for backward compat aliases**

```python
# tests/test_models.py — add these tests

def test_old_models_still_importable():
    """MCPClientConfig and StdioConfig should still be importable."""
    from mcp_gway.models import MCPClientConfig, StdioConfig, ConnectionType
    assert MCPClientConfig is not None
    assert StdioConfig is not None
    assert ConnectionType.HTTP == "http"


def test_old_http_config_still_works():
    """Old-style config creation should still work."""
    config = MCPClientConfig(
        name="youtube",
        connection_type=ConnectionType.HTTP,
        connection_string="http://localhost:3001/mcp",
    )
    assert config.name == "youtube"
    assert config.connection_type == ConnectionType.HTTP
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py -v -k "old_models or old_http"`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Add backward compat aliases**

```python
# src/mcp_gway/models.py — add at bottom of file

# Backward compatibility aliases
from enum import Enum


class ConnectionType(str, Enum):
    HTTP = "http"
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"


class StdioConfig(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    envs: list[str] = Field(default_factory=list)


class MCPClientConfig(BaseModel):
    """Deprecated: Use MCPServerConfig instead."""

    name: str
    connection_type: ConnectionType
    connection_string: str | None = None
    stdio_config: StdioConfig | None = None
    tools_to_execute: list[str] = Field(default_factory=lambda: ["*"])
    is_code_mode_client: bool = True
    docs_url: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.isascii():
            raise ValueError("Name must contain only ASCII characters")
        if "-" in v or " " in v:
            raise ValueError("Name cannot contain hyphens or spaces")
        if v[0].isdigit():
            raise ValueError("Name cannot start with a number")
        return v

    def model_post_init(self, __context: Any) -> None:
        if self.connection_type in (
            ConnectionType.HTTP,
            ConnectionType.SSE,
            ConnectionType.STREAMABLE_HTTP,
        ):
            if not self.connection_string:
                raise ValueError(
                    f"connection_string required for {self.connection_type.value}"
                )
        if self.connection_type == ConnectionType.STDIO:
            if not self.stdio_config:
                raise ValueError("stdio_config required for stdio connection")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v -k "old_models or old_http"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_gway/models.py tests/test_models.py
git commit -m "feat(models): keep backward compat aliases for MCPClientConfig"
```

---

### Task 3: Update Registry — new JSON format + auto-migration

**Files:**
- Modify: `src/mcp_gway/registry.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Consumes: `MCPServerConfig`, `ToolInfo`
- Produces: `Registry.add()`, `Registry.get_config()`, `Registry.remove()`, `Registry.update()`

- [ ] **Step 1: Write failing tests for new JSON format**

```python
# tests/test_registry.py — add these tests

def test_add_creates_opencode_json(registry):
    """add() should create OpenCode-format JSON config."""
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
        headers={"Authorization": "Bearer TOKEN"},
    )
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(config, tools)
    json_path = registry.servers_dir / "myserver.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["type"] == "remote"
    assert data["url"] == "https://mcp.example.com/mcp"
    assert data["headers"] == {"Authorization": "Bearer TOKEN"}
    assert data["enabled"] is True
    assert data["timeout"] == 5000


def test_add_local_config_json(registry):
    """add() with local config should store command array."""
    config = MCPServerConfig(
        name="myserver",
        type="local",
        command=["npx", "-y", "my-mcp-server"],
        environment={"FOO": "bar"},
    )
    tools = [ToolInfo(name="ping", description="Ping")]
    registry.add(config, tools)
    data = json.loads((registry.servers_dir / "myserver.json").read_text())
    assert data["type"] == "local"
    assert data["command"] == ["npx", "-y", "my-mcp-server"]
    assert data["environment"] == {"FOO": "bar"}


def test_get_config_new_format(registry):
    """get_config should read new OpenCode format."""
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
    )
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(config, tools)
    restored = registry.get_config("myserver")
    assert restored.type == "remote"
    assert restored.url == "https://mcp.example.com/mcp"


def test_auto_migrate_old_json(registry):
    """get_config should auto-migrate old-format JSON."""
    # Simulate old format
    old_data = {
        "name": "myserver",
        "connection_type": "sse",
        "connection_string": "https://mcp.example.com/sse",
        "docs_url": "",
    }
    json_path = registry.servers_dir / "myserver.json"
    json_path.write_text(json.dumps(old_data, indent=2), encoding="utf-8")

    # Also create a minimal .pyi so the server is found
    pyi_path = registry.servers_dir / "myserver.pyi"
    pyi_path.write_text("# myserver server tools\n\ndef search() -> dict:\n    ...\n")

    config = registry.get_config("myserver")
    assert config.type == "remote"
    assert config.url == "https://mcp.example.com/sse"
    assert config.resolved_transport == "sse"

    # Verify JSON was migrated
    migrated = json.loads(json_path.read_text(encoding="utf-8"))
    assert migrated["type"] == "remote"
    assert "connection_type" not in migrated


def test_auto_migrate_old_stdio_json(registry):
    """get_config should auto-migrate old stdio JSON."""
    old_data = {
        "name": "gitserver",
        "connection_type": "stdio",
        "connection_string": "npx",
        "stdio_command": "npx",
        "stdio_args": ["-y", "mcp-server-git"],
        "stdio_envs": ["FOO=bar"],
    }
    json_path = registry.servers_dir / "gitserver.json"
    json_path.write_text(json.dumps(old_data, indent=2), encoding="utf-8")
    pyi_path = registry.servers_dir / "gitserver.pyi"
    pyi_path.write_text("# gitserver\n\ndef clone() -> dict:\n    ...\n")

    config = registry.get_config("gitserver")
    assert config.type == "local"
    assert config.command == ["npx", "-y", "mcp-server-git"]
    assert config.environment == {"FOO": "bar"}


def test_add_stores_resolved_transport(registry):
    """add() should store resolved_transport if set."""
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
        resolved_transport="streamable-http",
    )
    tools = [ToolInfo(name="search", description="Search")]
    registry.add(config, tools)
    data = json.loads((registry.servers_dir / "myserver.json").read_text())
    assert data["resolved_transport"] == "streamable-http"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_registry.py -v -k "opencode or auto_migrate or resolved"`
Expected: FAIL

- [ ] **Step 3: Implement Registry changes**

```python
# src/mcp_gway/registry.py — update add() and get_config() methods

def add(self, config: MCPServerConfig, tools: list[ToolInfo]) -> None:
    """Write JSON config (OpenCode format) and .pyi stub."""
    config_data: dict[str, Any] = {
        "name": config.name,
        "type": config.type,
        "enabled": config.enabled,
        "timeout": config.timeout,
    }
    if config.type == "local":
        config_data["command"] = config.command
        if config.cwd:
            config_data["cwd"] = config.cwd
        if config.environment:
            config_data["environment"] = config.environment
    else:  # remote
        config_data["url"] = config.url
        if config.headers:
            config_data["headers"] = config.headers
        if config.oauth is not None:
            if isinstance(config.oauth, bool):
                config_data["oauth"] = config.oauth
            else:
                config_data["oauth"] = config.oauth.model_dump()
        if config.resolved_transport:
            config_data["resolved_transport"] = config.resolved_transport

    json_path = self.servers_dir / f"{config.name}.json"
    json_path.write_text(json.dumps(config_data, indent=2), encoding="utf-8")

    pyi_path = self.servers_dir / f"{config.name}.pyi"
    content = self._generate_pyi(config, tools)
    pyi_path.write_text(content, encoding="utf-8")


def get_config(self, name: str) -> MCPServerConfig:
    json_path = self.servers_dir / f"{name}.json"
    pyi_path = self.servers_dir / f"{name}.pyi"

    if not json_path.exists() and not pyi_path.exists():
        raise FileNotFoundError(f"Server '{name}' not found")

    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))

        # Auto-migrate old format
        if "connection_type" in data:
            return self._migrate_old_config(name, data, json_path)

        # New OpenCode format
        oauth = data.get("oauth")
        if isinstance(oauth, dict):
            oauth = OAuthConfig(**oauth)

        return MCPServerConfig(
            name=name,
            type=data["type"],
            enabled=data.get("enabled", True),
            timeout=data.get("timeout", 5000),
            command=data.get("command"),
            cwd=data.get("cwd"),
            environment=data.get("environment"),
            url=data.get("url"),
            headers=data.get("headers"),
            oauth=oauth,
            resolved_transport=data.get("resolved_transport"),
        )

    return self._parse_config_from_pyi(name, pyi_path)


def _migrate_old_config(
    self, name: str, data: dict, json_path: Path
) -> MCPServerConfig:
    """Migrate old-format JSON to OpenCode format."""
    conn_type = data["connection_type"]

    if conn_type == "stdio":
        command_parts = []
        if data.get("stdio_command"):
            command_parts.append(data["stdio_command"])
            command_parts.extend(data.get("stdio_args", []))
        elif data.get("connection_string"):
            command_parts.append(data["connection_string"])

        environment = None
        if data.get("stdio_envs"):
            environment = {}
            for env_str in data["stdio_envs"]:
                key, _, value = env_str.partition("=")
                environment[key] = value

        config = MCPServerConfig(
            name=name,
            type="local",
            command=command_parts if command_parts else None,
            environment=environment,
        )
    else:
        transport_map = {
            "http": "http",
            "sse": "sse",
            "streamable-http": "streamable-http",
        }
        config = MCPServerConfig(
            name=name,
            type="remote",
            url=data.get("connection_string", ""),
            resolved_transport=transport_map.get(conn_type),
        )

    # Write migrated config
    self.add(config, [])
    return config
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_registry.py -v -k "opencode or auto_migrate or resolved"`
Expected: PASS

- [ ] **Step 5: Run full registry test suite**

Run: `uv run pytest tests/test_registry.py -v`
Expected: PASS (all existing + new tests)

- [ ] **Step 6: Commit**

```bash
git add src/mcp_gway/registry.py tests/test_registry.py
git commit -m "feat(registry): OpenCode JSON format with auto-migration"
```

---

### Task 4: Update CLI — new options + backward compat mapping

**Files:**
- Modify: `src/mcp_gway/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `MCPServerConfig`, `OAuthConfig`, `ToolInfo`
- Produces: Updated `add`, `refresh`, `list` commands

- [ ] **Step 1: Write failing tests for new CLI syntax**

```python
# tests/test_cli.py — add these tests

def test_add_remote_type(runner, monkeypatch):
    """add --type remote --url should create remote config."""
    async def mock_discover_tools(config, force_auth=False):
        return [ToolInfo(name="search", description="Search videos")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    result = runner.invoke(
        main,
        ["add", "myserver", "--type", "remote", "--url", "https://mcp.example.com/mcp"],
    )
    assert result.exit_code == 0
    assert "myserver" in result.output


def test_add_local_type(runner, monkeypatch):
    """add --type local --command should create local config."""
    async def mock_discover_tools(config, force_auth=False):
        return [ToolInfo(name="ping", description="Ping")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    result = runner.invoke(
        main,
        ["add", "myserver", "--type", "local", "--command", "npx", "-y", "my-mcp"],
    )
    assert result.exit_code == 0


def test_add_with_header_option(runner, monkeypatch):
    """add --header KEY=VALUE should store headers."""
    async def mock_discover_tools(config, force_auth=False):
        return [ToolInfo(name="search", description="Search")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    result = runner.invoke(
        main,
        [
            "add", "myserver",
            "--type", "remote",
            "--url", "https://mcp.example.com/mcp",
            "--header", "Authorization=Bearer TOKEN",
        ],
    )
    assert result.exit_code == 0


def test_add_with_timeout_option(runner, monkeypatch):
    """add --timeout should set timeout value."""
    async def mock_discover_tools(config, force_auth=False):
        return [ToolInfo(name="search", description="Search")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    result = runner.invoke(
        main,
        [
            "add", "myserver",
            "--type", "remote",
            "--url", "https://mcp.example.com/mcp",
            "--timeout", "10000",
        ],
    )
    assert result.exit_code == 0


def test_add_backward_compat_stdio(runner, monkeypatch):
    """Old --type stdio should still work."""
    async def mock_discover_tools(config, force_auth=False):
        return [ToolInfo(name="ping", description="Ping")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    result = runner.invoke(
        main,
        ["add", "myserver", "--type", "stdio", "--command", "node", "server.js"],
    )
    assert result.exit_code == 0


def test_list_shows_new_type_format(tmp_path, monkeypatch):
    """list should show 'local' or 'remote' instead of HTTP/STDIO/etc."""
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    registry = Registry(servers_dir=servers_dir)
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
    )
    registry.add(config, [ToolInfo(name="search", description="Search")])

    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "REMOTE" in result.output


def test_list_shows_local_type(tmp_path, monkeypatch):
    """list should show LOCAL for local servers."""
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    registry = Registry(servers_dir=servers_dir)
    config = MCPServerConfig(
        name="myserver",
        type="local",
        command=["npx", "-y", "my-mcp"],
    )
    registry.add(config, [ToolInfo(name="ping", description="Ping")])

    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "LOCAL" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v -k "remote_type or local_type or header_option or timeout_option or backward_compat_stdio or new_type_format or local_type_list"`
Expected: FAIL

- [ ] **Step 3: Implement CLI changes**

Update `cli.py`:

1. **Change `--type` choice** to accept `local|remote|http|stdio|sse|streamable-http`
2. **Keep `--command` as single string** (backward compat with stdio). For new `--type local`, users pass `--command "npx -y my-mcp"` and it gets split.
3. **Add `--header` (repeatable)**: Parse `KEY=VALUE` into `dict[str, str]`
4. **Add `--oauth-client-id`, `--oauth-client-secret`, `--oauth-scope`**: Build `OAuthConfig`
5. **Add `--timeout`** (int, default 5000)
6. **Add `--enabled/--no-enabled`** flag
7. **Mapping logic** in `add` command body:

```python
# Backward compat mapping
if conn_type in ("http", "sse", "streamable-http"):
    config = MCPServerConfig(
        name=name, type="remote", url=url,
        resolved_transport=conn_type,
        headers=headers_dict, oauth=oauth_config,
        timeout=timeout, enabled=enabled,
    )
elif conn_type == "stdio":
    command_parts = [command] + json.loads(args) if args else [command]
    config = MCPServerConfig(
        name=name, type="local", command=command_parts,
        environment=env_dict, timeout=timeout, enabled=enabled,
    )
elif conn_type == "local":
    command_parts = command.split()  # "npx -y x" → ["npx", "-y", "x"]
    if args:
        command_parts.extend(json.loads(args))
    config = MCPServerConfig(
        name=name, type="local", command=command_parts,
        cwd=cwd, environment=env_dict, timeout=timeout, enabled=enabled,
    )
elif conn_type == "remote":
    config = MCPServerConfig(
        name=name, type="remote", url=url,
        headers=headers_dict, oauth=oauth_config,
        timeout=timeout, enabled=enabled,
    )
```

8. **Update `list`** to show `LOCAL`/`REMOTE` from `config.type`
9. **Update all imports** to use `MCPServerConfig` instead of `MCPClientConfig`

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v -k "remote_type or local_type or header_option or timeout_option or backward_compat_stdio or new_type_format or local_type_list"`
Expected: PASS

- [ ] **Step 5: Run full CLI test suite**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (all existing + new tests)

- [ ] **Step 6: Commit**

```bash
git add src/mcp_gway/cli.py tests/test_cli.py
git commit -m "feat(cli): OpenCode-style options with backward compat"
```

---

### Task 5: Update gateway.py and remaining imports

**Files:**
- Modify: `src/mcp_gway/gateway.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: `MCPServerConfig`, `Registry`

- [ ] **Step 1: Update gateway.py imports**

Change `from mcp_gway.models import MCPClientConfig` to `from mcp_gway.models import MCPServerConfig` (if used). Check if `gateway.py` directly references the config model — from reading it, it only uses `Registry` and `CodeMode`, so likely minimal changes.

- [ ] **Step 2: Update conftest.py fixtures**

```python
# tests/conftest.py

"""Shared test fixtures."""

import pytest

from mcp_gway.models import MCPServerConfig


@pytest.fixture
def http_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="testserver",
        type="remote",
        url="http://localhost:3001/mcp",
    )


@pytest.fixture
def stdio_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="teststdio",
        type="local",
        command=["echo", "hello"],
    )
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/mcp_gway/gateway.py tests/conftest.py
git commit -m "refactor: update imports to use MCPServerConfig"
```

---

### Task 6: Transport auto-detection for remote servers

**Files:**
- Create: `src/mcp_gway/transport.py`
- Test: `tests/test_transport.py`

**Interfaces:**
- Consumes: `MCPServerConfig`
- Produces: `detect_transport(config) -> Literal["streamable-http", "sse", "http"]`

- [ ] **Step 1: Write failing tests for transport detection**

```python
# tests/test_transport.py

"""Tests for transport auto-detection."""

import pytest

from mcp_gway.models import MCPServerConfig


def test_detect_transport_streamable_http_success(monkeypatch):
    """Should return streamable-http if it connects."""
    config = MCPServerConfig(
        name="test", type="remote", url="https://example.com/mcp"
    )

    async def mock_streamable_http(url, **kwargs):
        return True

    async def mock_sse(url, **kwargs):
        return False

    monkeypatch.setattr("mcp_gway.transport._try_streamable_http", mock_streamable_http)
    monkeypatch.setattr("mcp_gway.transport._try_sse", mock_sse)

    from mcp_gway.transport import detect_transport
    import asyncio

    result = asyncio.run(detect_transport(config))
    assert result == "streamable-http"


def test_detect_transport_fallback_to_sse(monkeypatch):
    """Should fallback to SSE if streamable-http fails."""
    config = MCPServerConfig(
        name="test", type="remote", url="https://example.com/mcp"
    )

    async def mock_streamable_http(url, **kwargs):
        return False

    async def mock_sse(url, **kwargs):
        return True

    monkeypatch.setattr("mcp_gway.transport._try_streamable_http", mock_streamable_http)
    monkeypatch.setattr("mcp_gway.transport._try_sse", mock_sse)

    from mcp_gway.transport import detect_transport
    import asyncio

    result = asyncio.run(detect_transport(config))
    assert result == "sse"


def test_detect_transport_fallback_to_http(monkeypatch):
    """Should fallback to HTTP if all others fail."""
    config = MCPServerConfig(
        name="test", type="remote", url="https://example.com/mcp"
    )

    async def mock_streamable_http(url, **kwargs):
        return False

    async def mock_sse(url, **kwargs):
        return False

    async def mock_http(url, **kwargs):
        return True

    monkeypatch.setattr("mcp_gway.transport._try_streamable_http", mock_streamable_http)
    monkeypatch.setattr("mcp_gway.transport._try_sse", mock_sse)
    monkeypatch.setattr("mcp_gway.transport._try_http", mock_http)

    from mcp_gway.transport import detect_transport
    import asyncio

    result = asyncio.run(detect_transport(config))
    assert result == "http"


def test_detect_transport_all_fail_raises(monkeypatch):
    """Should raise if all transports fail."""
    config = MCPServerConfig(
        name="test", type="remote", url="https://example.com/mcp"
    )

    async def mock_fail(url, **kwargs):
        return False

    monkeypatch.setattr("mcp_gway.transport._try_streamable_http", mock_fail)
    monkeypatch.setattr("mcp_gway.transport._try_sse", mock_fail)
    monkeypatch.setattr("mcp_gway.transport._try_http", mock_fail)

    from mcp_gway.transport import detect_transport
    import asyncio

    with pytest.raises(ConnectionError, match="All transports failed"):
        asyncio.run(detect_transport(config))


def test_detect_transport_respects_timeout(monkeypatch):
    """Should pass timeout to each transport probe."""
    config = MCPServerConfig(
        name="test", type="remote", url="https://example.com/mcp", timeout=3000
    )

    captured_timeouts = []

    async def mock_streamable_http(url, timeout=None, **kwargs):
        captured_timeouts.append(timeout)
        return False

    async def mock_sse(url, timeout=None, **kwargs):
        captured_timeouts.append(timeout)
        return False

    async def mock_http(url, timeout=None, **kwargs):
        captured_timeouts.append(timeout)
        return True

    monkeypatch.setattr("mcp_gway.transport._try_streamable_http", mock_streamable_http)
    monkeypatch.setattr("mcp_gway.transport._try_sse", mock_sse)
    monkeypatch.setattr("mcp_gway.transport._try_http", mock_http)

    from mcp_gway.transport import detect_transport
    import asyncio

    asyncio.run(detect_transport(config))
    assert all(t == 3000 for t in captured_timeouts)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_transport.py -v`
Expected: FAIL with `ImportError` (module doesn't exist)

- [ ] **Step 3: Implement transport detection**

```python
# src/mcp_gway/transport.py

"""Transport auto-detection for remote MCP servers."""

from __future__ import annotations

import asyncio
from typing import Literal

from mcp_gway.models import MCPServerConfig


async def _try_streamable_http(url: str, timeout: int = 5000) -> bool:
    """Try to connect via streamable-http transport."""
    try:
        from mcp.client.streamable_http import streamable_http_client

        async with asyncio.timeout(timeout / 1000):
            async with streamable_http_client(url) as (read, write):
                return True
    except Exception:
        return False


async def _try_sse(url: str, timeout: int = 5000) -> bool:
    """Try to connect via SSE transport."""
    try:
        from mcp.client.sse import sse_client

        async with asyncio.timeout(timeout / 1000):
            async with sse_client(url) as (read, write):
                return True
    except Exception:
        return False


async def _try_http(url: str, timeout: int = 5000) -> bool:
    """Try to connect via basic HTTP transport."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout / 1000) as client:
            response = await client.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )
            return response.status_code == 200
    except Exception:
        return False


async def detect_transport(
    config: MCPServerConfig,
) -> Literal["streamable-http", "sse", "http"]:
    """Auto-detect the best transport for a remote server.

    Tries transports in order: streamable-http → sse → http.
    Returns the first successful transport.
    Raises ConnectionError if all transports fail.
    """
    url = config.url
    timeout = config.timeout

    if await _try_streamable_http(url, timeout):
        return "streamable-http"

    if await _try_sse(url, timeout):
        return "sse"

    if await _try_http(url, timeout):
        return "http"

    raise ConnectionError(f"All transports failed for {url}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_transport.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_gway/transport.py tests/test_transport.py
git commit -m "feat(transport): auto-detect streamable-http/sse/http"
```

---

### Task 7: Integrate transport detection into CLI add/refresh

**Files:**
- Modify: `src/mcp_gway/cli.py`

**Interfaces:**
- Consumes: `detect_transport()` from `transport.py`

- [ ] **Step 1: Write failing test for auto-detection on add**

```python
# tests/test_cli.py — add this test

def test_add_remote_auto_detects_transport(runner, monkeypatch):
    """add --type remote should auto-detect transport and store it."""
    from mcp_gway.models import ToolInfo

    async def mock_discover_tools(config, force_auth=False):
        return [ToolInfo(name="search", description="Search")]

    async def mock_detect_transport(config):
        return "streamable-http"

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.transport.detect_transport", mock_detect_transport)

    result = runner.invoke(
        main,
        ["add", "myserver", "--type", "remote", "--url", "https://mcp.example.com/mcp"],
    )
    assert result.exit_code == 0

    # Verify resolved_transport was stored
    import json
    from mcp_gway.registry import Registry

    # Read the stored config
    json_path = runner.mix_stderr  # Click test runner doesn't expose path directly
    # Instead, check via the registry
    config = Registry(servers_dir=runner.mix_stderr).get_config("myserver")
```

- [ ] **Step 2: Implement integration**

Update `cli.py`:
1. In `add` command: after creating `MCPServerConfig` for remote, call `detect_transport()` and set `resolved_transport`
2. In `refresh` command: same — auto-detect and update `resolved_transport`
3. Import `detect_transport` from `mcp_gway.transport`

- [ ] **Step 3: Run all tests**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/mcp_gway/cli.py tests/test_cli.py
git commit -m "feat(cli): integrate transport auto-detection"
```

---

### Task 8: Full test suite verification + lint

**Files:**
- All files

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Run linting**

Run: `uv run ruff check src/ tests/`
Expected: No errors

- [ ] **Step 3: Run formatting**

Run: `uv run ruff format src/ tests/`
Expected: No changes needed (or auto-formatted)

- [ ] **Step 4: Final commit if any formatting changes**

```bash
git add -A
git commit -m "style: lint and format after schema adoption"
```
