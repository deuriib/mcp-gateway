"""Tests for Code Mode meta-tools."""

import json

import pytest

from mcp_gway.code_mode import CodeMode
from mcp_gway.models import MCPServerConfig, ToolInfo
from mcp_gway.registry import Registry


@pytest.fixture
def code_mode(tmp_path):
    registry = Registry(servers_dir=tmp_path / "servers")
    config = MCPServerConfig(
        name="youtube",
        type="remote",
        url="https://api.example.com/mcp",
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


# --- Server struct injection ---


def test_sandbox_has_server_structs(code_mode):
    """The sandbox should have server structs injected."""
    assert "youtube" in code_mode.sandbox._modules
    struct = code_mode.sandbox._modules["youtube"]
    assert hasattr(struct, "search")
    assert hasattr(struct, "get_video")


def test_sandbox_no_call_tool(code_mode):
    """call_tool should NOT be injected anymore."""
    assert "call_tool" not in code_mode.sandbox._custom_globals


def test_execute_code_with_server_struct(code_mode, monkeypatch):
    """Execute code that uses the injected server struct."""

    async def mock_call_tool_async(config, tool_name, arguments):
        return {"query": arguments.get("query", ""), "items": []}

    monkeypatch.setattr(
        code_mode.server_factory, "_call_tool_async", mock_call_tool_async
    )
    result = json.loads(
        code_mode.execute_tool_code('result = youtube.search(query="test")')
    )
    assert result["result"]["query"] == "test"
    assert result["logs"] == []


def test_execute_code_print_captured(code_mode):
    """print() output should be captured in logs."""
    result = json.loads(code_mode.execute_tool_code('print("hello")\nresult = 1'))
    assert result["result"] == 1
    assert result["logs"] == ["hello"]


# --- Hyphenated tool name tests ---


@pytest.fixture
def code_mode_hyphens(tmp_path):
    """CodeMode with a server that has hyphenated tool names (like context7)."""
    registry = Registry(servers_dir=tmp_path / "servers")
    config = MCPServerConfig(
        name="context7",
        type="remote",
        url="https://api.example.com/mcp",
    )
    tools = [
        ToolInfo(
            name="query-docs",
            description="Query documentation",
            input_schema={
                "type": "object",
                "properties": {
                    "library_id": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["library_id", "query"],
            },
        ),
        ToolInfo(
            name="resolve-library-id",
            description="Resolve a library name to its ID",
            input_schema={
                "type": "object",
                "properties": {"library_name": {"type": "string"}},
                "required": ["library_name"],
            },
        ),
    ]
    registry.add(config, tools)
    return CodeMode(registry)


def test_hyphenated_tools_injected(code_mode_hyphens):
    """Server with hyphenated tool names should be injected with sanitized attrs."""
    assert "context7" in code_mode_hyphens.sandbox._modules
    struct = code_mode_hyphens.sandbox._modules["context7"]
    assert hasattr(struct, "query_docs")
    assert hasattr(struct, "resolve_library_id")
    assert not hasattr(struct, "query-docs")


def test_execute_hyphenated_tool_via_struct(code_mode_hyphens, monkeypatch):
    """Execute code using sanitized struct method names for hyphenated tools."""

    async def mock_call_tool_async(config, tool_name, arguments):
        return {"tool": tool_name, "args": arguments}

    monkeypatch.setattr(
        code_mode_hyphens.server_factory, "_call_tool_async", mock_call_tool_async
    )
    result = json.loads(
        code_mode_hyphens.execute_tool_code(
            'result = context7.query_docs(library_id="react", query="hooks")'
        )
    )
    assert result["result"]["tool"] == "query-docs"


# --- Code validation ---


def test_execute_rejects_imports(code_mode):
    with pytest.raises(Exception, match="rejects"):
        code_mode.execute_tool_code("import os\nresult = 1")


def test_execute_rejects_classes(code_mode):
    with pytest.raises(Exception, match="rejects"):
        code_mode.execute_tool_code("class X:\n  pass\nresult = 1")


# --- Agent Mode ---


def test_classify_tool_calls_all_manual(code_mode):
    """tools_to_auto_execute=[] (default) means all tool calls are manual."""
    calls = [
        {"server": "youtube", "tool": "search", "arguments": {}, "id": "1"},
    ]
    auto, manual = code_mode.classify_tool_calls(calls)
    assert auto == []
    assert len(manual) == 1


def test_classify_tool_calls_all_auto(code_mode, monkeypatch):
    """tools_to_auto_execute=['*'] means all are auto."""

    def _always_auto(server, tool):
        return True

    monkeypatch.setattr(code_mode.server_factory, "is_auto_executable", _always_auto)
    calls = [
        {"server": "youtube", "tool": "search", "arguments": {}, "id": "1"},
    ]
    auto, manual = code_mode.classify_tool_calls(calls)
    assert len(auto) == 1
    assert manual == []


def test_classify_tool_calls_partial_auto(tmp_path):
    """Only named tools are auto."""
    registry = Registry(servers_dir=tmp_path / "servers")
    registry.add(
        MCPServerConfig(
            name="fs",
            type="remote",
            url="https://api.example.com/mcp",
            tools_to_auto_execute=["read_file"],
        ),
        [
            ToolInfo(name="read_file", description="read"),
            ToolInfo(name="write_file", description="write"),
        ],
    )
    cm = CodeMode(registry)
    calls = [
        {"server": "fs", "tool": "read_file", "arguments": {}},
        {"server": "fs", "tool": "write_file", "arguments": {}},
    ]
    auto, manual = cm.classify_tool_calls(calls)
    assert len(auto) == 1
    assert auto[0]["tool"] == "read_file"
    assert len(manual) == 1
    assert manual[0]["tool"] == "write_file"
