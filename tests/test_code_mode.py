"""Tests for Code Mode meta-tools."""

import pytest

from mcp_gateway.code_mode import CodeMode
from mcp_gateway.models import ConnectionType, MCPClientConfig, ToolInfo
from mcp_gateway.registry import Registry


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
