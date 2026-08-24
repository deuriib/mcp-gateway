"""Tests for ServerFactory — MCP tool bridge for sandbox."""

import pytest

from mcp_gway.models import ConnectionType, MCPClientConfig, ToolInfo
from mcp_gway.registry import Registry
from mcp_gway.server_factory import ServerFactory, _extract_result


@pytest.fixture
def registry(tmp_path):
    """Create a registry with a mock server."""
    reg = Registry(servers_dir=tmp_path / "servers")
    config = MCPClientConfig(
        name="youtube",
        connection_type=ConnectionType.HTTP,
        connection_string="http://localhost:3001/mcp",
    )
    tools = [
        ToolInfo(
            name="search",
            description="Search for videos",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        ToolInfo(
            name="get_video",
            description="Get video details",
            input_schema={
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        ),
    ]
    reg.add(config, tools)
    return reg


@pytest.fixture
def factory(registry):
    return ServerFactory(registry)


def test_get_tool_names(factory):
    """Should extract tool names from .pyi stub."""
    names = factory._get_tool_names("youtube")
    assert "search" in names
    assert "get_video" in names


def test_get_tool_names_not_found(factory):
    """Should raise FileNotFoundError for unknown server."""
    with pytest.raises(FileNotFoundError):
        factory._get_tool_names("nonexistent")


def test_make_server_struct(factory):
    """Should create a struct with tool methods."""
    struct = factory.make_server_struct("youtube")
    assert hasattr(struct, "search")
    assert hasattr(struct, "get_video")
    assert callable(struct.search)
    assert callable(struct.get_video)


def test_make_server_struct_not_found(factory):
    """Should raise FileNotFoundError for unknown server."""
    with pytest.raises(FileNotFoundError):
        factory.make_server_struct("nonexistent")


def test_extract_result_with_text():
    """Should extract text from MCP result with content."""

    class MockContent:
        def __init__(self, text):
            self.text = text

    class MockResult:
        def __init__(self, texts):
            self.content = [MockContent(t) for t in texts]

    result = _extract_result(MockResult(["hello", "world"]))
    assert result == "hello\nworld"


def test_extract_result_with_json():
    """Should parse JSON from MCP result text."""

    class MockContent:
        def __init__(self, text):
            self.text = text

    class MockResult:
        def __init__(self, text):
            self.content = [MockContent(text)]

    result = _extract_result(MockResult('{"key": "value"}'))
    assert result == {"key": "value"}


def test_extract_result_passthrough():
    """Should pass through non-MCP results."""
    result = _extract_result({"direct": "dict"})
    assert result == {"direct": "dict"}


def test_extract_result_without_content():
    """Should handle objects without content attribute."""

    class PlainResult:
        pass

    result = _extract_result(PlainResult())
    assert isinstance(result, PlainResult)
