"""Tests for .pyi file registry operations (OpenCode-only)."""

import json

import pytest

from mcp_gway.models import MCPServerConfig, ToolInfo
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


def test_generate_pyi_no_legacy_comments(registry, http_config):
    """_generate_pyi should NOT include legacy config comments."""
    tools = [ToolInfo(name="search", description="Search videos")]
    content = registry._generate_pyi(http_config, tools)
    assert "# connection_type:" not in content
    assert "# connection_string:" not in content
    assert "# docs_url:" not in content
    assert "# stdio_command:" not in content
    assert "# stdio_args:" not in content


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


def test_remove_cleans_both_files(registry, http_config):
    """remove() should delete both .json and .pyi files."""
    tools = [ToolInfo(name="search", description="Search videos")]
    registry.add(http_config, tools)
    registry.remove("testserver")
    assert not (registry.servers_dir / "testserver.pyi").exists()
    assert not (registry.servers_dir / "testserver.json").exists()


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


def test_patch_enabled(registry, http_config):
    tools = [ToolInfo(name="search", description="Search")]
    registry.add(http_config, tools)
    registry.patch_enabled("testserver", False)
    cfg = registry.get_config("testserver")
    assert cfg.enabled is False
    data = json.loads((registry.servers_dir / "testserver.json").read_text())
    assert data["enabled"] is False


def test_safe_path_traversal_guard(registry):
    with pytest.raises(ValueError):
        registry._safe_path("../evil", ".json")
    with pytest.raises(ValueError):
        registry._safe_path("bad/name", ".pyi")


def test_atomic_write(registry):
    config = MCPServerConfig(
        name="atomic", type="remote", url="https://example.com/mcp"
    )
    registry.add(config, [])
    tmp_path = registry.servers_dir / "atomic.json.tmp"
    assert not tmp_path.exists()


def test_get_config_not_found(registry):
    with pytest.raises(FileNotFoundError):
        registry.get_config("nonexistent")


def test_read_pyi_not_found(registry):
    with pytest.raises(FileNotFoundError):
        registry.read_pyi("nonexistent")
