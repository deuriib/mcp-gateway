"""Tests for .pyi file registry operations."""

import json

import pytest

from mcp_gway.models import (
    ConnectionType,
    MCPClientConfig,
    MCPServerConfig,
    StdioConfig,
    ToolInfo,
)
from mcp_gway.registry import Registry


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


# --- Bug 2: stdio_config in .pyi files ---


def test_generate_pyi_includes_stdio_config(registry):
    """_generate_pyi should NOT include stdio config comments (now in JSON)."""
    config = MCPClientConfig(
        name="myserver",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["-y", "mcp-server-git"]),
    )
    tools = [ToolInfo(name="clone", description="Clone a repo")]
    content = registry._generate_pyi(config, tools)
    assert "# stdio_command:" not in content
    assert "# stdio_args:" not in content


def test_generate_pyi_no_stdio_comments_for_http(registry, http_config):
    """HTTP servers should NOT have stdio_command/stdio_args comments."""
    tools = [ToolInfo(name="search", description="Search videos")]
    content = registry._generate_pyi(http_config, tools)
    assert "# stdio_command:" not in content
    assert "# stdio_args:" not in content


def test_get_config_stdio_roundtrip(registry):
    """get_config should reconstruct stdio_config from .pyi comments."""
    config = MCPClientConfig(
        name="myserver",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["-y", "mcp-server-git"]),
    )
    tools = [ToolInfo(name="clone", description="Clone a repo")]
    registry.add(config, tools)

    restored = registry.get_config("myserver")
    assert restored.connection_type == ConnectionType.STDIO
    assert restored.stdio_config is not None
    assert restored.stdio_config.command == "npx"
    assert restored.stdio_config.args == ["-y", "mcp-server-git"]


# --- Fix 7: JSON config + clean .pyi ---


def test_add_creates_json_config(registry, http_config):
    """add() should create a separate JSON config file."""
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(http_config, tools)
    json_path = registry.servers_dir / "testserver.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["name"] == "testserver"
    assert data["connection_type"] == "http"
    assert data["connection_string"] == "http://localhost:3001/mcp"


def test_pyi_file_no_config_comments(registry, http_config):
    """The .pyi file should not contain config metadata comments."""
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(http_config, tools)
    content = (registry.servers_dir / "testserver.pyi").read_text()
    assert "# connection_type:" not in content
    assert "# connection_string:" not in content
    assert "# docs_url:" not in content


def test_pyi_still_has_usage_comments(registry, http_config):
    """The .pyi file should still have usage hints."""
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(http_config, tools)
    content = (registry.servers_dir / "testserver.pyi").read_text()
    assert "# Usage:" in content
    assert "# For detailed docs:" in content


def test_get_config_reads_json(registry, http_config):
    """get_config should read from JSON file."""
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(http_config, tools)
    config = registry.get_config("testserver")
    assert config.connection_type == ConnectionType.HTTP
    assert config.connection_string == "http://localhost:3001/mcp"


def test_get_config_stdio_reads_json(registry):
    """get_config should reconstruct stdio_config from JSON."""
    config = MCPClientConfig(
        name="myserver",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["-y", "mcp-server-git"]),
    )
    tools = [ToolInfo(name="clone", description="Clone a repo")]
    registry.add(config, tools)

    restored = registry.get_config("myserver")
    assert restored.connection_type == ConnectionType.STDIO
    assert restored.stdio_config is not None
    assert restored.stdio_config.command == "npx"
    assert restored.stdio_config.args == ["-y", "mcp-server-git"]


def test_remove_cleans_both_files(registry, http_config):
    """remove() should delete both .json and .pyi files."""
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(http_config, tools)
    registry.remove("testserver")
    assert not (registry.servers_dir / "testserver.pyi").exists()
    assert not (registry.servers_dir / "testserver.json").exists()


def test_backward_compat_old_pyi_comments(registry):
    """get_config should still work with old .pyi files that have config comments."""
    # Simulate an old-style .pyi file
    old_pyi = """# testserver server tools
# Usage: testserver.tool_name(param=value)
# connection_type: http
# connection_string: http://localhost:3001/mcp
# docs_url:

def search(query: str) -> dict:  # Search videos
    ...
"""
    registry.servers_dir.mkdir(parents=True, exist_ok=True)
    (registry.servers_dir / "testserver.pyi").write_text(old_pyi)

    config = registry.get_config("testserver")
    assert config.connection_type == ConnectionType.HTTP
    assert config.connection_string == "http://localhost:3001/mcp"


def test_backward_compat_stdio_old_format(registry):
    """Old STDIO .pyi with command in connection_string, no stdio_command comment."""
    old_pyi = """# agentmemory server tools
# Usage: agentmemory.tool_name(param=value)
# connection_type: stdio
# connection_string: npx
# docs_url:

def memory_recall() -> dict:  # Recall memories
    ...
"""
    registry.servers_dir.mkdir(parents=True, exist_ok=True)
    (registry.servers_dir / "agentmemory.pyi").write_text(old_pyi)

    config = registry.get_config("agentmemory")
    assert config.connection_type == ConnectionType.STDIO
    assert config.stdio_config is not None
    assert config.stdio_config.command == "npx"


# --- FIX 1: envs roundtrip ---


def test_registry_stores_and_restores_envs(registry):
    """add() with envs should store them in JSON, get_config should restore them."""
    config = MCPClientConfig(
        name="envserver",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(
            command="node",
            args=["server.js"],
            envs=["FOO=bar", "BAZ=qux"],
        ),
    )
    tools = [ToolInfo(name="ping", description="Ping")]
    registry.add(config, tools)

    restored = registry.get_config("envserver")
    assert restored.stdio_config is not None
    assert restored.stdio_config.envs == ["FOO=bar", "BAZ=qux"]

    json_path = registry.servers_dir / "envserver.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if "environment" in data:
        assert data["environment"] == {"FOO": "bar", "BAZ": "qux"}
    else:
        assert data["stdio_envs"] == ["FOO=bar", "BAZ=qux"]


def test_add_creates_opencode_json(registry):
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
        headers={"Authorization": "Bearer TOKEN"},
    )
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(config, tools)
    data = json.loads(
        (registry.servers_dir / "myserver.json").read_text(encoding="utf-8")
    )
    assert data["type"] == "remote"
    assert data["url"] == "https://mcp.example.com/mcp"
    assert data["headers"] == {"Authorization": "Bearer TOKEN"}
    assert data["enabled"] is True
    assert data["timeout"] == 5000


def test_add_local_config_json(registry):
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
    config = MCPServerConfig(
        name="myserver", type="remote", url="https://mcp.example.com/mcp"
    )
    registry.add(config, [ToolInfo(name="search", description="Search videos")])
    restored = registry.get_config("myserver")
    assert restored.type == "remote"
    assert restored.url == "https://mcp.example.com/mcp"


def test_auto_migrate_old_json(registry):
    old_data = {
        "name": "myserver",
        "connection_type": "sse",
        "connection_string": "https://mcp.example.com/sse",
        "docs_url": "",
    }
    json_path = registry.servers_dir / "myserver.json"
    json_path.write_text(json.dumps(old_data, indent=2), encoding="utf-8")
    (registry.servers_dir / "myserver.pyi").write_text(
        "# myserver server tools\n\ndef search() -> dict:\n    ...\n"
    )
    config = registry.get_config("myserver")
    assert config.type == "remote"
    assert config.url == "https://mcp.example.com/sse"
    assert config.resolved_transport == "sse"
    migrated = json.loads(json_path.read_text(encoding="utf-8"))
    assert migrated["type"] == "remote"
    assert "connection_type" not in migrated


def test_auto_migrate_old_stdio_json(registry):
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
    (registry.servers_dir / "gitserver.pyi").write_text(
        "# gitserver\n\ndef clone() -> dict:\n    ...\n"
    )
    config = registry.get_config("gitserver")
    assert config.type == "local"
    assert config.command == ["npx", "-y", "mcp-server-git"]
    assert config.environment == {"FOO": "bar"}


def test_add_stores_resolved_transport(registry):
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
        resolved_transport="streamable-http",
    )
    registry.add(config, [ToolInfo(name="search", description="Search")])
    data = json.loads((registry.servers_dir / "myserver.json").read_text())
    assert data["resolved_transport"] == "streamable-http"
