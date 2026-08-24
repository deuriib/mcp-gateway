"""Tests for .pyi file registry operations."""

import json

import pytest

from mcp_gway.models import ConnectionType, MCPClientConfig, StdioConfig, ToolInfo
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
    """_generate_pyi should write stdio_command and stdio_args comments."""
    config = MCPClientConfig(
        name="myserver",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["-y", "mcp-server-git"]),
    )
    tools = [ToolInfo(name="clone", description="Clone a repo")]
    content = registry._generate_pyi(config, tools)
    assert "# stdio_command: npx" in content
    assert f"# stdio_args: {json.dumps(['-y', 'mcp-server-git'])}" in content


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


def test_get_config_stdio_without_comments_backward_compat(registry):
    """Old .pyi files without stdio_command should reconstruct stdio_config from connection_string."""
    # Manually write a .pyi without stdio comments (simulates old format)
    content = """\
# myserver server tools
# Usage: myserver.tool_name(param=value)
# For detailed docs: use getToolDocs(server="myserver", tool="tool_name")
# connection_type: stdio
# connection_string: npx
# docs_url:

def clone(repo: str) -> dict:  # Clone a repo
    ...
"""
    (registry.servers_dir / "myserver.pyi").write_text(content, encoding="utf-8")
    # get_config reconstructs stdio_config from connection_string for old files
    restored = registry.get_config("myserver")
    assert restored.name == "myserver"
    assert restored.connection_type == ConnectionType.STDIO
    assert restored.stdio_config is not None
    assert restored.stdio_config.command == "npx"
    assert restored.stdio_config.args == []
