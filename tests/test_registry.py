"""Tests for .pyi file registry operations."""

import pytest

from mcp_gateway.models import ToolInfo
from mcp_gateway.registry import Registry


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
