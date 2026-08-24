"""Tests for Code Mode meta-tools."""

import pytest

from mcp_gway.code_mode import CodeMode
from mcp_gway.models import ConnectionType, MCPClientConfig, ToolInfo
from mcp_gway.registry import Registry


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


# --- call_tool injection tests ---


def test_sandbox_has_call_tool(code_mode):
    """The sandbox should have call_tool injected."""
    assert "call_tool" in code_mode.sandbox._custom_globals
    assert callable(code_mode.sandbox._custom_globals["call_tool"])


def test_sandbox_has_server_structs(code_mode):
    """The sandbox should have server structs injected."""
    assert "youtube" in code_mode.sandbox._modules
    struct = code_mode.sandbox._modules["youtube"]
    assert hasattr(struct, "search")
    assert hasattr(struct, "get_video")


def test_execute_code_with_server_struct(code_mode, monkeypatch):
    """Execute code that uses the injected server struct."""

    # Mock the async MCP call to avoid real network
    async def mock_call_tool_async(config, tool_name, arguments):
        return {"query": arguments.get("query", ""), "items": []}

    monkeypatch.setattr(
        code_mode.server_factory, "_call_tool_async", mock_call_tool_async
    )
    result = code_mode.execute_tool_code('result = youtube.search(query="test")')
    assert "query" in result


def test_execute_code_with_call_tool(code_mode, monkeypatch):
    """Execute code that uses the call_tool function."""

    async def mock_call_tool_async(config, tool_name, arguments):
        return {"tool": tool_name, "args": arguments}

    monkeypatch.setattr(
        code_mode.server_factory, "_call_tool_async", mock_call_tool_async
    )
    result = code_mode.execute_tool_code(
        'result = call_tool("youtube", "search", query="hello")'
    )
    assert "search" in result


def test_execute_code_call_tool_not_found(code_mode):
    """call_tool should raise error for unknown server."""
    with pytest.raises(Exception, match="nonexistent"):
        code_mode.execute_tool_code('result = call_tool("nonexistent", "tool")')
