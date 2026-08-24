# MCP Gateway CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python CLI tool and gateway server that manages MCP servers via CRUD commands and exposes Code Mode with 4 meta-tools (listToolFiles, readToolFile, getToolDocs, executeToolCode) over HTTP/SSE.

**Architecture:** File-system-based storage using `.pyi` stub files in `servers/` directory. CLI manages these files via click. Gateway server uses starlette + uvicorn to serve MCP protocol over JSON-RPC 2.0. Code Mode uses starlark-pyo3 for hermetic code execution with server proxies injected as globals.

**Tech Stack:** Python 3.12+, mise + uv, mcp SDK 2.0.0, starlark-pyo3 2026.1+, click 8.0+, starlette 0.37+, uvicorn 0.30+, httpx 0.27+

**Spec:** `docs/superpowers/specs/2026-08-23-mcp-gateway-design.md`

## Global Constraints

- Python 3.12+ required (walrus operator, type union syntax)
- All dependencies managed via `uv` in `pyproject.toml`
- No database — storage is `.pyi` files in `servers/` directory
- MCP protocol compliance via `mcp` SDK 2.0.0
- Starlark sandbox via `starlark-pyo3` (Rust-backed, binary wheels available)
- Test framework: `pytest` with `pytest-asyncio`
- Code style: Ruff formatter + linter

---

## File Structure

```
mcp-gateway/
├── pyproject.toml                    # Project config, dependencies, entry points
├── mise.toml                         # mise tool config (python version)
├── src/
│   └── mcp_gateway/
│       ├── __init__.py               # Package version
│       ├── models.py                 # Pydantic models for configs
│       ├── registry.py               # .pyi file CRUD operations
│       ├── sandbox.py                # Starlark sandbox wrapper
│       ├── server_proxy.py           # MCP server proxy for sandbox
│       ├── code_mode.py              # 4 meta-tools implementation
│       ├── gateway.py                # HTTP/SSE server (starlette)
│       └── cli.py                    # click CLI commands
├── servers/                          # Runtime: .pyi stub files
│   └── .gitkeep
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # Shared fixtures
│   ├── test_models.py
│   ├── test_registry.py
│   ├── test_sandbox.py
│   ├── test_server_proxy.py
│   ├── test_code_mode.py
│   ├── test_gateway.py
│   └── test_cli.py
└── docs/
    └── superpowers/
        ├── specs/
        │   └── 2026-08-23-mcp-gateway-design.md
        └── plans/
            └── 2026-08-23-mcp-gateway-implementation.md
```

---

## Task 1: Project Scaffold + Models

**Files:**
- Create: `pyproject.toml`
- Create: `mise.toml`
- Create: `src/mcp_gateway/__init__.py`
- Create: `src/mcp_gateway/models.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_models.py`
- Create: `servers/.gitkeep`

**Interfaces:**
- Produces: `MCPClientConfig` pydantic model used by all subsequent tasks

- [ ] **Step 1: Initialize project with mise + uv**

```bash
cd D:\Projects\mcp-gateway
uv init --name mcp-gateway --lib
```

- [ ] **Step 2: Create mise.toml**

```toml
[tools]
python = "3.12"
```

- [ ] **Step 3: Add dependencies**

```bash
uv add mcp>=2.0.0 starlark-pyo3 click httpx starlette uvicorn
uv add --dev pytest pytest-asyncio ruff
```

- [ ] **Step 4: Create pyproject.toml entry points**

Add to `pyproject.toml`:

```toml
[project.scripts]
mcp-gateway = "mcp_gateway.cli:main"
```

- [ ] **Step 5: Create `src/mcp_gateway/__init__.py`**

```python
"""MCP Gateway CLI — manage MCP servers with Code Mode support."""

__version__ = "0.1.0"
```

- [ ] **Step 6: Create `src/mcp_gateway/models.py`**

```python
"""Pydantic models for MCP client configurations."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ConnectionType(str, Enum):
    HTTP = "http"
    STDIO = "stdio"
    SSE = "sse"


class StdioConfig(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    envs: list[str] = Field(default_factory=list)


class MCPClientConfig(BaseModel):
    name: str
    connection_type: ConnectionType
    connection_string: str | None = None
    stdio_config: StdioConfig | None = None
    tools_to_execute: list[str] = Field(default_factory=lambda: ["*"])
    is_code_mode_client: bool = True

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
        if self.connection_type in (ConnectionType.HTTP, ConnectionType.SSE):
            if not self.connection_string:
                raise ValueError(
                    f"connection_string required for {self.connection_type.value}"
                )
        if self.connection_type == ConnectionType.STDIO:
            if not self.stdio_config:
                raise ValueError("stdio_config required for stdio connection")


class ToolInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPServerState(BaseModel):
    name: str
    config: MCPClientConfig
    tools: list[ToolInfo] = Field(default_factory=list)
    state: str = "healthy"
```

- [ ] **Step 7: Create test fixtures in `tests/conftest.py`**

```python
"""Shared test fixtures."""

import pytest
from mcp_gateway.models import ConnectionType, MCPClientConfig, StdioConfig


@pytest.fixture
def http_config() -> MCPClientConfig:
    return MCPClientConfig(
        name="testserver",
        connection_type=ConnectionType.HTTP,
        connection_string="http://localhost:3001/mcp",
    )


@pytest.fixture
def stdio_config() -> MCPClientConfig:
    return MCPClientConfig(
        name="teststdio",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(command="echo", args=["hello"]),
    )
```

- [ ] **Step 8: Write model tests in `tests/test_models.py`**

```python
"""Tests for MCP client config models."""

import pytest
from mcp_gateway.models import ConnectionType, MCPClientConfig, StdioConfig


def test_http_config_valid():
    config = MCPClientConfig(
        name="youtube",
        connection_type=ConnectionType.HTTP,
        connection_string="http://localhost:3001/mcp",
    )
    assert config.name == "youtube"
    assert config.connection_type == ConnectionType.HTTP
    assert config.is_code_mode_client is True


def test_stdio_config_valid():
    config = MCPClientConfig(
        name="filesystem",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["-y", "@anthropic/mcp-filesystem"]),
    )
    assert config.stdio_config.command == "npx"


def test_name_rejects_hyphens():
    with pytest.raises(ValueError, match="hyphens"):
        MCPClientConfig(
            name="my-tools",
            connection_type=ConnectionType.HTTP,
            connection_string="http://localhost:3001/mcp",
        )


def test_name_rejects_leading_digit():
    with pytest.raises(ValueError, match="number"):
        MCPClientConfig(
            name="123tools",
            connection_type=ConnectionType.HTTP,
            connection_string="http://localhost:3001/mcp",
        )


def test_name_rejects_non_ascii():
    with pytest.raises(ValueError, match="ASCII"):
        MCPClientConfig(
            name="datös",
            connection_type=ConnectionType.HTTP,
            connection_string="http://localhost:3001/mcp",
        )


def test_http_requires_connection_string():
    with pytest.raises(ValueError, match="connection_string required"):
        MCPClientConfig(
            name="youtube",
            connection_type=ConnectionType.HTTP,
        )


def test_stdio_requires_stdio_config():
    with pytest.raises(ValueError, match="stdio_config required"):
        MCPClientConfig(
            name="filesystem",
            connection_type=ConnectionType.STDIO,
        )
```

- [ ] **Step 9: Run tests**

Run: `uv run pytest tests/test_models.py -v`
Expected: All 7 tests PASS

- [ ] **Step 10: Commit**

```bash
git init
git add pyproject.toml mise.toml src/ tests/ servers/ docs/
git commit -m "feat: project scaffold with models and tests"
```

---

## Task 2: Registry — .pyi File CRUD

**Files:**
- Create: `src/mcp_gateway/registry.py`
- Create: `tests/test_registry.py`

**Interfaces:**
- Consumes: `MCPClientConfig` from Task 1
- Produces: `Registry` class with `add()`, `remove()`, `update()`, `list()`, `get_config()`, `generate_pyi()`, `read_pyi()`, `get_tool_docs()`

- [ ] **Step 1: Write failing tests in `tests/test_registry.py`**

```python
"""Tests for .pyi file registry operations."""

import pytest
from mcp_gateway.registry import Registry
from mcp_gateway.models import ConnectionType, MCPClientConfig, ToolInfo


@pytest.fixture
def registry(tmp_path):
    return Registry(servers_dir=tmp_path / "servers")


def test_list_empty(registry):
    assert registry.list() == []


def test_add_creates_pyi(registry, http_config):
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(http_config, tools)
    assert (registry.servers_dir / "testserver.pyi").exists()


def test_add_pyi_content(registry, http_config):
    tools = [
        ToolInfo(name="search", description="Search videos"),
        ToolInfo(name="get_video", description="Get video details"),
    ]
    registry.add(http_config, tools)
    content = (registry.servers_dir / "testserver.pyi").read_text()
    assert "def search(" in content
    assert "def get_video(" in content
    assert "# Search videos" in content


def test_remove_deletes_pyi(registry, http_config):
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(http_config, tools)
    registry.remove("testserver")
    assert not (registry.servers_dir / "testserver.pyi").exists()


def test_remove_nonexistent_raises(registry):
    with pytest.raises(FileNotFoundError):
        registry.remove("nonexistent")


def test_list_returns_names(registry, http_config):
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(http_config, tools)
    names = registry.list()
    assert "testserver" in names


def test_get_config(registry, http_config):
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(http_config, tools)
    config = registry.get_config("testserver")
    assert config.name == "testserver"


def test_read_pyi(registry, http_config):
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(http_config, tools)
    content = registry.read_pyi("testserver")
    assert "def search(" in content


def test_get_tool_docs(registry, http_config):
    tools = [ToolInfo(name="search", description="Search for videos on YouTube")]
    registry.add(http_config, tools)
    docs = registry.get_tool_docs("testserver", "search")
    assert "search" in docs
    assert "Search for videos" in docs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_gateway.registry'`

- [ ] **Step 3: Implement `src/mcp_gateway/registry.py`**

```python
"""Registry for managing .pyi stub files in the servers/ directory."""

from __future__ import annotations

from pathlib import Path

from mcp_gateway.models import MCPClientConfig, ToolInfo


class Registry:
    def __init__(self, servers_dir: Path | str = "servers") -> None:
        self.servers_dir = Path(servers_dir)
        self.servers_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[str]:
        """List all registered server names."""
        return sorted(
            p.stem for p in self.servers_dir.glob("*.pyi")
        )

    def add(self, config: MCPClientConfig, tools: list[ToolInfo]) -> None:
        """Create a .pyi stub file for the given server."""
        pyi_path = self.servers_dir / f"{config.name}.pyi"
        content = self._generate_pyi(config.name, tools)
        pyi_path.write_text(content, encoding="utf-8")

    def remove(self, name: str) -> None:
        """Remove a .pyi stub file."""
        pyi_path = self.servers_dir / f"{name}.pyi"
        if not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")
        pyi_path.unlink()

    def update(self, name: str, tools: list[ToolInfo]) -> None:
        """Update tools for an existing server."""
        config = self.get_config(name)
        self.add(config, tools)

    def get_config(self, name: str) -> MCPClientConfig:
        """Load config from .pyi file metadata."""
        pyi_path = self.servers_dir / f"{name}.pyi"
        if not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")
        content = pyi_path.read_text(encoding="utf-8")
        connection_type = "http"
        connection_string = ""
        for line in content.splitlines():
            if line.startswith("# connection_type:"):
                connection_type = line.split(":", 1)[1].strip()
            elif line.startswith("# connection_string:"):
                connection_string = line.split(":", 1)[1].strip()
        return MCPClientConfig(
            name=name,
            connection_type=connection_type,
            connection_string=connection_string or None,
        )

    def read_pyi(self, name: str) -> str:
        """Read the .pyi file content."""
        pyi_path = self.servers_dir / f"{name}.pyi"
        if not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")
        return pyi_path.read_text(encoding="utf-8")

    def get_tool_docs(self, server: str, tool: str) -> str:
        """Extract documentation for a specific tool."""
        content = self.read_pyi(server)
        lines = content.splitlines()
        in_tool = False
        doc_lines: list[str] = []
        for line in lines:
            if line.startswith(f"def {tool}("):
                in_tool = True
                doc_lines.append(line)
                continue
            if in_tool:
                if line.startswith("def ") or (line.strip() and not line.startswith(" ") and not line.startswith("\t")):
                    break
                doc_lines.append(line)
        if not doc_lines:
            return f"Tool '{tool}' not found on server '{server}'"
        return "\n".join(doc_lines)

    def _generate_pyi(self, name: str, tools: list[ToolInfo]) -> str:
        """Generate .pyi stub content."""
        lines = [
            f"# {name} server tools",
            f"# Usage: {name}.tool_name(param=value)",
            f"# For detailed docs: use getToolDocs(server=\"{name}\", tool=\"tool_name\")",
            f"# connection_type: http",
            f"# connection_string: ",
            "",
        ]
        for tool in tools:
            sig = self._make_signature(tool)
            lines.append(f"def {sig} -> dict:  # {tool.description}")
            lines.append("    ...")
            lines.append("")
        return "\n".join(lines)

    def _make_signature(self, tool: ToolInfo) -> str:
        """Build a function signature from tool info."""
        params = []
        schema = tool.input_schema.get("properties", {})
        required = tool.input_schema.get("required", [])
        for param_name, param_info in schema.items():
            py_type = self._json_type_to_python(param_info.get("type", "string"))
            if param_name in required:
                params.append(f"{param_name}: {py_type}")
            else:
                params.append(f"{param_name}: {py_type} = None")
        return f"{tool.name}({', '.join(params)})"

    @staticmethod
    def _json_type_to_python(json_type: str) -> str:
        mapping = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "array": "list",
            "object": "dict",
        }
        return mapping.get(json_type, "Any")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_registry.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_gateway/registry.py tests/test_registry.py
git commit -m "feat: registry for .pyi file CRUD operations"
```

---

## Task 3: Starlark Sandbox + Server Proxy

**Files:**
- Create: `src/mcp_gateway/sandbox.py`
- Create: `src/mcp_gateway/server_proxy.py`
- Create: `tests/test_sandbox.py`
- Create: `tests/test_server_proxy.py`

**Interfaces:**
- Consumes: `MCPClientConfig` from Task 1, `Registry` from Task 2
- Produces: `StarlarkSandbox` class with `execute()`, `inject_server()`; `ServerProxy` class that wraps MCP clients

- [ ] **Step 1: Write failing sandbox tests in `tests/test_sandbox.py`**

```python
"""Tests for Starlark sandbox execution."""

import pytest
from mcp_gateway.sandbox import StarlarkSandbox


def test_execute_simple_expression():
    sandbox = StarlarkSandbox()
    result = sandbox.execute("result = 2 + 3")
    assert result == 5


def test_execute_string_operations():
    sandbox = StarlarkSandbox()
    result = 'result = "hello " + "world"'
    assert sandbox.execute(result) == "hello world"


def test_execute_list_comprehension():
    sandbox = StarlarkSandbox()
    code = "result = [x * 2 for x in [1, 2, 3]]"
    assert sandbox.execute(code) == [2, 4, 6]


def test_execute_with_injected_object():
    sandbox = StarlarkSandbox()

    class MockServer:
        def search(self, query=""):
            return {"items": [{"title": f"Result for {query}"}]}

    sandbox.inject_server("youtube", MockServer())
    code = 'result = youtube.search(query="test")'
    result = sandbox.execute(code)
    assert result["items"][0]["title"] == "Result for test"


def test_execute_syntax_error():
    sandbox = StarlarkSandbox()
    with pytest.raises(Exception):
        sandbox.execute("def broken(")


def test_execute_undefined_variable_error():
    sandbox = StarlarkSandbox()
    with pytest.raises(Exception):
        sandbox.execute("result = nonexistent_var")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sandbox.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_gateway.sandbox'`

- [ ] **Step 3: Implement `src/mcp_gateway/sandbox.py`**

```python
"""Starlark sandbox for safe code execution."""

from __future__ import annotations

import starlark as sl


class StarlarkSandbox:
    def __init__(self) -> None:
        self.globals = sl.Globals.standard()
        self._modules: dict[str, sl.Module] = {}

    def inject_server(self, name: str, server_proxy: object) -> None:
        """Inject a server proxy as a global object accessible in code."""
        self._modules[name] = server_proxy

    def execute(self, code: str, timeout: float = 30.0) -> object:
        """Execute code in the sandbox and return the 'result' variable."""
        mod = sl.Module()
        for name, proxy in self._modules.items():
            mod[name] = proxy
        ast = sl.parse("code.star", code)
        sl.eval(mod, ast, self.globals)
        if "result" not in mod:
            raise RuntimeError(
                "Code did not assign to 'result' variable. "
                "Assign your output to 'result' to return it."
            )
        return mod["result"]
```

- [ ] **Step 4: Run sandbox tests**

Run: `uv run pytest tests/test_sandbox.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Write failing server proxy tests in `tests/test_server_proxy.py`**

```python
"""Tests for MCP server proxy."""

import pytest
from mcp_gateway.server_proxy import ServerProxy


class MockMCPClient:
    def __init__(self, tools: dict):
        self._tools = tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not found")
        return self._tools[name](arguments)


@pytest.fixture
def mock_client():
    tools = {
        "search": lambda args: {"items": [{"title": f"Result for {args.get('query', '')}"}]},
        "get_video": lambda args: {"id": args.get("id"), "title": "Test Video"},
    }
    return MockMCPClient(tools)


@pytest.mark.asyncio
async def test_proxy_attribute_access(mock_client):
    proxy = ServerProxy("youtube", mock_client)
    result = await proxy.search(query="test")
    assert result["items"][0]["title"] == "Result for test"


@pytest.mark.asyncio
async def test_proxy_tool_not_found(mock_client):
    proxy = ServerProxy("youtube", mock_client)
    with pytest.raises(ValueError, match="not found"):
        await proxy.nonexistent_tool()
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_server_proxy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_gateway.server_proxy'`

- [ ] **Step 7: Implement `src/mcp_gateway/server_proxy.py`**

```python
"""Server proxy that wraps MCP clients for sandbox use."""

from __future__ import annotations

from typing import Any


class ServerProxy:
    """Wraps an MCP client so tools can be called as attributes.

    Usage in sandbox:
        result = youtube.search(query="test")
    """

    def __init__(self, name: str, client: Any) -> None:
        self._name = name
        self._client = client
        self._tool_names: list[str] = []

    def set_tool_names(self, names: list[str]) -> None:
        """Set the list of available tool names."""
        self._tool_names = names

    def __getattr__(self, tool_name: str) -> Any:
        if tool_name.startswith("_"):
            raise AttributeError(tool_name)

        async def tool_fn(**kwargs: Any) -> dict:
            return await self._client.call_tool(tool_name, kwargs)

        return tool_fn

    def __repr__(self) -> str:
        return f"ServerProxy(name={self._name!r}, tools={self._tool_names})"
```

- [ ] **Step 8: Run proxy tests**

Run: `uv run pytest tests/test_server_proxy.py -v`
Expected: All 2 tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/mcp_gateway/sandbox.py src/mcp_gateway/server_proxy.py tests/test_sandbox.py tests/test_server_proxy.py
git commit -m "feat: starlark sandbox and server proxy for code mode"
```

---

## Task 4: Code Mode — 4 Meta-Tools

**Files:**
- Create: `src/mcp_gateway/code_mode.py`
- Create: `tests/test_code_mode.py`

**Interfaces:**
- Consumes: `Registry` from Task 2, `StarlarkSandbox` from Task 3, `ServerProxy` from Task 3
- Produces: `CodeMode` class with `list_tool_files()`, `read_tool_file()`, `get_tool_docs()`, `execute_tool_code()`

- [ ] **Step 1: Write failing tests in `tests/test_code_mode.py`**

```python
"""Tests for Code Mode meta-tools."""

import pytest
from mcp_gateway.code_mode import CodeMode
from mcp_gateway.registry import Registry
from mcp_gateway.models import ConnectionType, MCPClientConfig, ToolInfo


@pytest.fixture
def code_mode(tmp_path):
    registry = Registry(servers_dir=tmp_path / "servers")
    config = MCPClientConfig(
        name="youtube",
        connection_type=ConnectionType.HTTP,
        connection_string="http://localhost:3001/mcp",
    )
    tools = [
        ToolInfo(
            name="search",
            description="Search for videos on YouTube",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        ToolInfo(
            name="get_video",
            description="Get video details by ID",
            input_schema={
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        ),
    ]
    registry.add(config, tools)
    return CodeMode(registry)


def test_list_tool_files(code_mode):
    result = code_mode.list_tool_files()
    assert "youtube.pyi" in result


def test_read_tool_file(code_mode):
    result = code_mode.read_tool_file(fileName="servers/youtube.pyi")
    assert "def search(" in result
    assert "def get_video(" in result


def test_read_tool_file_not_found(code_mode):
    with pytest.raises(FileNotFoundError):
        code_mode.read_tool_file(fileName="servers/nonexistent.pyi")


def test_get_tool_docs(code_mode):
    result = code_mode.get_tool_docs(server="youtube", tool="search")
    assert "search" in result
    assert "Search for videos" in result


def test_get_tool_docs_unknown_server(code_mode):
    with pytest.raises(FileNotFoundError):
        code_mode.get_tool_docs(server="nonexistent", tool="search")


def test_get_tool_docs_unknown_tool(code_mode):
    result = code_mode.get_tool_docs(server="youtube", tool="nonexistent")
    assert "not found" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_code_mode.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_gateway.code_mode'`

- [ ] **Step 3: Implement `src/mcp_gateway/code_mode.py`**

```python
"""Code Mode — 4 meta-tools for LLM-driven tool orchestration."""

from __future__ import annotations

from mcp_gateway.registry import Registry
from mcp_gateway.sandbox import StarlarkSandbox


class CodeMode:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.sandbox = StarlarkSandbox()

    def list_tool_files(self) -> str:
        """List all available .pyi stub files."""
        names = self.registry.list()
        if not names:
            return "No servers connected."
        lines = ["servers/"]
        for name in names:
            lines.append(f"  {name}.pyi")
        return "\n".join(lines)

    def read_tool_file(self, fileName: str, startLine: int | None = None, endLine: int | None = None) -> str:
        """Read a .pyi file and return function signatures."""
        if not fileName.startswith("servers/"):
            fileName = f"servers/{fileName}"
        if not fileName.endswith(".pyi"):
            fileName += ".pyi"
        name = fileName.removeprefix("servers/").removesuffix(".pyi")
        content = self.registry.read_pyi(name)
        if startLine is not None or endLine is not None:
            lines = content.splitlines()
            start = (startLine or 1) - 1
            end = endLine or len(lines)
            content = "\n".join(lines[start:end])
        return content

    def get_tool_docs(self, server: str, tool: str) -> str:
        """Get detailed documentation for a specific tool."""
        return self.registry.get_tool_docs(server, tool)

    def execute_tool_code(self, code: str) -> str:
        """Execute Python/Starlark code in the sandbox."""
        result = self.sandbox.execute(code)
        return str(result)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_code_mode.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_gateway/code_mode.py tests/test_code_mode.py
git commit -m "feat: code mode with 4 meta-tools"
```

---

## Task 5: Gateway Server (HTTP/SSE + JSON-RPC)

**Files:**
- Create: `src/mcp_gateway/gateway.py`
- Create: `tests/test_gateway.py`

**Interfaces:**
- Consumes: `CodeMode` from Task 4, `Registry` from Task 2
- Produces: `Gateway` class with `app` (Starlette) for uvicorn

- [ ] **Step 1: Write failing gateway tests in `tests/test_gateway.py`**

```python
"""Tests for the HTTP/SSE gateway server."""

import json
import pytest
from httpx import AsyncClient, ASGITransport
from mcp_gateway.gateway import Gateway
from mcp_gateway.registry import Registry
from mcp_gateway.models import ConnectionType, MCPClientConfig, ToolInfo


@pytest.fixture
def gateway(tmp_path):
    registry = Registry(servers_dir=tmp_path / "servers")
    config = MCPClientConfig(
        name="youtube",
        connection_type=ConnectionType.HTTP,
        connection_string="http://localhost:3001/mcp",
    )
    tools = [
        ToolInfo(name="search", description="Search videos"),
    ]
    registry.add(config, tools)
    return Gateway(registry)


@pytest.mark.asyncio
async def test_health_endpoint(gateway):
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_tools_list(gateway):
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
        }
        response = await client.post("/mcp", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        tools = data["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "listToolFiles" in names
        assert "readToolFile" in names
        assert "getToolDocs" in names
        assert "executeToolCode" in names


@pytest.mark.asyncio
async def test_tools_call_list_tool_files(gateway):
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "listToolFiles",
                "arguments": {},
            },
        }
        response = await client.post("/mcp", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "youtube.pyi" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_tools_call_execute_code(gateway):
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "executeToolCode",
                "arguments": {"code": "result = 42"},
            },
        }
        response = await client.post("/mcp", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "42" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_unknown_method(gateway):
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "unknown/method",
        }
        response = await client.post("/mcp", json=payload)
        data = response.json()
        assert "error" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gateway.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_gateway.gateway'`

- [ ] **Step 3: Implement `src/mcp_gateway/gateway.py`**

```python
"""HTTP/SSE gateway server for MCP protocol."""

from __future__ import annotations

import json
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_gateway.code_mode import CodeMode
from mcp_gateway.registry import Registry

CODE_MODE_TOOLS = [
    {
        "name": "listToolFiles",
        "description": "Lists all available virtual .pyi stub files for connected MCP servers.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "readToolFile",
        "description": "Reads a virtual .pyi file to get compact Python function signatures for tools.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fileName": {"type": "string", "description": "Path like servers/youtube.pyi"},
                "startLine": {"type": "integer", "description": "Optional 1-based start line"},
                "endLine": {"type": "integer", "description": "Optional 1-based end line"},
            },
            "required": ["fileName"],
        },
    },
    {
        "name": "getToolDocs",
        "description": "Get detailed documentation for a specific tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "The server name"},
                "tool": {"type": "string", "description": "The tool name"},
            },
            "required": ["server", "tool"],
        },
    },
    {
        "name": "executeToolCode",
        "description": "Executes Python code in a sandboxed Starlark interpreter with tool access.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
            },
            "required": ["code"],
        },
    },
]


class Gateway:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.code_mode = CodeMode(registry)
        self.app = Starlette(
            routes=[
                Route("/health", self._health, methods=["GET"]),
                Route("/mcp", self._mcp_post, methods=["POST"]),
                Route("/mcp", self._mcp_sse, methods=["GET"]),
            ],
        )

    async def _health(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def _mcp_post(self, request: Request) -> JSONResponse:
        body = await request.json()
        method = body.get("method")
        req_id = body.get("id")
        params = body.get("params", {})
        try:
            result = self._handle_method(method, params)
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})
        except Exception as e:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": req_id, "error": {"code": -1, "message": str(e)}}
            )

    async def _mcp_sse(self, request: Request) -> JSONResponse:
        return JSONResponse({"message": "SSE not yet implemented"})

    def _handle_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "tools/list":
            return {"tools": CODE_MODE_TOOLS}
        if method == "tools/call":
            return self._handle_tool_call(params)
        raise ValueError(f"Unknown method: {method}")

    def _handle_tool_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        if name == "listToolFiles":
            result = self.code_mode.list_tool_files()
        elif name == "readToolFile":
            result = self.code_mode.read_tool_file(
                fileName=arguments["fileName"],
                startLine=arguments.get("startLine"),
                endLine=arguments.get("endLine"),
            )
        elif name == "getToolDocs":
            result = self.code_mode.get_tool_docs(
                server=arguments["server"],
                tool=arguments["tool"],
            )
        elif name == "executeToolCode":
            result = self.code_mode.execute_tool_code(code=arguments["code"])
        else:
            raise ValueError(f"Unknown tool: {name}")
        return {"content": [{"type": "text", "text": result}]}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_gateway.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_gateway/gateway.py tests/test_gateway.py
git commit -m "feat: HTTP/SSE gateway server with JSON-RPC 2.0"
```

---

## Task 6: CLI Commands

**Files:**
- Create: `src/mcp_gateway/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `Registry` from Task 2, `Gateway` from Task 5
- Produces: `main()` entry point with add/remove/update/list/inspect/serve commands

- [ ] **Step 1: Write failing CLI tests in `tests/test_cli.py`**

```python
"""Tests for CLI commands."""

import pytest
from click.testing import CliRunner
from mcp_gateway.cli import main
from mcp_gateway.registry import Registry


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "servers").mkdir()
    return CliRunner()


def test_list_empty(runner):
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "No servers" in result.output


def test_add_http_server(runner, monkeypatch):
    async def mock_discover_tools(config):
        from mcp_gateway.models import ToolInfo
        return [ToolInfo(name="search", description="Search videos")]

    monkeypatch.setattr("mcp_gateway.cli._discover_tools", mock_discover_tools)
    result = runner.invoke(main, [
        "add", "youtube",
        "--type", "http",
        "--url", "http://localhost:3001/mcp",
    ])
    assert result.exit_code == 0
    assert "youtube" in result.output


def test_inspect_server(runner, monkeypatch):
    async def mock_discover_tools(config):
        from mcp_gateway.models import ToolInfo
        return [ToolInfo(name="search", description="Search videos")]

    monkeypatch.setattr("mcp_gateway.cli._discover_tools", mock_discover_tools)
    runner.invoke(main, [
        "add", "youtube",
        "--type", "http",
        "--url", "http://localhost:3001/mcp",
    ])
    result = runner.invoke(main, ["inspect", "youtube"])
    assert result.exit_code == 0
    assert "search" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_gateway.cli'`

- [ ] **Step 3: Implement `src/mcp_gateway/cli.py`**

```python
"""CLI commands for MCP Gateway management."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from mcp_gateway.models import ConnectionType, MCPClientConfig, StdioConfig, ToolInfo
from mcp_gateway.registry import Registry


def _get_registry() -> Registry:
    return Registry(servers_dir=Path("servers"))


async def _discover_tools(config: MCPClientConfig) -> list[ToolInfo]:
    """Connect to MCP server and discover available tools."""
    try:
        if config.connection_type == ConnectionType.STDIO:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=config.stdio_config.command,
                args=config.stdio_config.args,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [
                        ToolInfo(
                            name=t.name,
                            description=t.description or "",
                            input_schema=t.inputSchema if hasattr(t, "inputSchema") else {},
                        )
                        for t in result.tools
                    ]
        else:
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            url = config.connection_string
            async with sse_client(url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [
                        ToolInfo(
                            name=t.name,
                            description=t.description or "",
                            input_schema=t.inputSchema if hasattr(t, "inputSchema") else {},
                        )
                        for t in result.tools
                    ]
    except Exception as e:
        click.echo(f"Warning: Could not connect to server: {e}", err=True)
        return []


@click.group()
def main() -> None:
    """MCP Gateway CLI — manage MCP servers with Code Mode."""


@main.command()
@click.argument("name")
@click.option("--type", "conn_type", type=click.Choice(["http", "stdio", "sse"]), required=True)
@click.option("--url", help="Connection URL for http/sse")
@click.option("--command", help="Command for stdio connection")
@click.option("--args", help="JSON array of arguments for stdio", default="[]")
@click.option("--tools", help="Comma-separated tool names (default: all)", default="*")
def add(name: str, conn_type: str, url: str | None, command: str | None, args: str, tools: str) -> None:
    """Add an MCP server and generate its .pyi stub."""
    stdio_config = None
    connection_string = url

    if conn_type == "stdio":
        if not command:
            click.echo("Error: --command required for stdio connection", err=True)
            sys.exit(1)
        stdio_config = StdioConfig(command=command, args=json.loads(args))
        connection_string = command

    config = MCPClientConfig(
        name=name,
        connection_type=conn_type,
        connection_string=connection_string,
        stdio_config=stdio_config,
    )

    tool_filter = tools.split(",") if tools != "*" else ["*"]
    config.tools_to_execute = tool_filter

    click.echo(f"Discovering tools from {name}...")
    discovered = asyncio.run(_discover_tools(config))

    if tools != "*":
        discovered = [t for t in discovered if t.name in tool_filter]

    if not discovered:
        click.echo("Warning: No tools discovered. Adding server with empty tool list.")

    registry = _get_registry()
    registry.add(config, discovered)
    click.echo(f"Added {name} with {len(discovered)} tools.")


@main.command()
@click.argument("name")
def remove(name: str) -> None:
    """Remove an MCP server."""
    registry = _get_registry()
    try:
        registry.remove(name)
        click.echo(f"Removed {name}.")
    except FileNotFoundError:
        click.echo(f"Error: Server '{name}' not found.", err=True)
        sys.exit(1)


@main.command()
@click.argument("name")
@click.option("--tools", help="Comma-separated tool names", required=True)
def update(name: str, tools: str) -> None:
    """Update tools for an existing server."""
    registry = _get_registry()
    tool_list = [ToolInfo(name=t.strip(), description="") for t in tools.split(",")]
    try:
        registry.update(name, tool_list)
        click.echo(f"Updated {name} with {len(tool_list)} tools.")
    except FileNotFoundError:
        click.echo(f"Error: Server '{name}' not found.", err=True)
        sys.exit(1)


@main.command(name="list")
def list_servers() -> None:
    """List all connected MCP servers."""
    registry = _get_registry()
    names = registry.list()
    if not names:
        click.echo("No servers connected.")
        return
    click.echo(f"{'Name':<20} {'Type':<10} {'Tools':<8}")
    click.echo("-" * 38)
    for name in names:
        content = registry.read_pyi(name)
        tool_count = content.count("def ")
        conn_type = "http"
        for line in content.splitlines():
            if line.startswith("# connection_type:"):
                conn_type = line.split(":", 1)[1].strip()
                break
        click.echo(f"{name:<20} {conn_type.upper():<10} {tool_count:<8}")


@main.command()
@click.argument("name")
def inspect(name: str) -> None:
    """Show tool signatures for a server."""
    registry = _get_registry()
    try:
        content = registry.read_pyi(name)
        click.echo(content)
    except FileNotFoundError:
        click.echo(f"Error: Server '{name}' not found.", err=True)
        sys.exit(1)


@main.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8080, type=int, help="Bind port")
def serve(host: str, port: int) -> None:
    """Start the gateway server."""
    import uvicorn

    registry = _get_registry()
    from mcp_gateway.gateway import Gateway

    gateway = Gateway(registry)
    click.echo(f"Starting MCP Gateway on {host}:{port}")
    uvicorn.run(gateway.app, host=host, port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_gateway/cli.py tests/test_cli.py
git commit -m "feat: CLI commands for MCP gateway management"
```

---

## Task 7: Integration Test + Polish

**Files:**
- Create: `tests/test_integration.py`
- Modify: `pyproject.toml` (if needed)
- Modify: `src/mcp_gateway/__init__.py` (version bump)

**Interfaces:**
- Consumes: All previous tasks
- Produces: Full integration test proving end-to-end flow

- [ ] **Step 1: Write integration test in `tests/test_integration.py`**

```python
"""Integration test: full end-to-end flow."""

import pytest
from click.testing import CliRunner
from mcp_gateway.cli import main
from mcp_gateway.registry import Registry
from mcp_gateway.code_mode import CodeMode
from mcp_gateway.gateway import Gateway
from mcp_gateway.models import ConnectionType, MCPClientConfig, ToolInfo


def test_full_flow(tmp_path, monkeypatch):
    """Test: add server -> inspect -> list -> code mode -> gateway."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "servers").mkdir()

    async def mock_discover(config):
        return [
            ToolInfo(name="search", description="Search videos", input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }),
            ToolInfo(name="get_video", description="Get video details", input_schema={
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            }),
        ]

    monkeypatch.setattr("mcp_gateway.cli._discover_tools", mock_discover)
    runner = CliRunner()

    # Add server
    result = runner.invoke(main, [
        "add", "youtube",
        "--type", "http",
        "--url", "http://localhost:3001/mcp",
    ])
    assert result.exit_code == 0
    assert "2 tools" in result.output

    # List servers
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "youtube" in result.output

    # Inspect
    result = runner.invoke(main, ["inspect", "youtube"])
    assert result.exit_code == 0
    assert "def search(" in result.output

    # Code mode
    registry = Registry(servers_dir=tmp_path / "servers")
    code_mode = CodeMode(registry)

    files = code_mode.list_tool_files()
    assert "youtube.pyi" in files

    stubs = code_mode.read_tool_file(fileName="servers/youtube.pyi")
    assert "def search(" in stubs

    docs = code_mode.get_tool_docs(server="youtube", tool="search")
    assert "Search videos" in docs
```

- [ ] **Step 2: Run integration test**

Run: `uv run pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Run linter/formatter**

Run: `uv run ruff format src/ tests/ && uv run ruff check src/ tests/`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "feat: integration test for full end-to-end flow"
```

---

## Task 8: Project Polish + README

**Files:**
- Create: `README.md`
- Modify: `pyproject.toml` (metadata)

- [ ] **Step 1: Update pyproject.toml metadata**

Add description, license, authors to `pyproject.toml`.

- [ ] **Step 2: Create README.md**

```markdown
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
```

- [ ] **Step 3: Final commit**

```bash
git add README.md pyproject.toml
git commit -m "docs: README and project metadata"
```

---

## Verification

After all tasks complete:

1. `uv run pytest -v` — all tests pass
2. `uv run ruff check src/ tests/` — no lint errors
3. `uv run ruff format --check src/ tests/` — formatted
4. `uv run mcp-gateway list` — CLI works
5. `uv run mcp-gateway serve` — server starts on :8080
6. `curl http://localhost:8080/health` — returns `{"status":"ok"}`
7. `curl -X POST http://localhost:8080/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'` — returns 4 tools
