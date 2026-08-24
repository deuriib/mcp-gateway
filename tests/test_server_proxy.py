"""Tests for MCP server proxy."""

import pytest

from mcp_gway.server_proxy import ServerProxy


class MockMCPClient:
    def __init__(self, tools):
        self._tools = tools

    async def call_tool(self, name, arguments):
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not found")
        return self._tools[name](arguments)


@pytest.fixture
def mock_client():
    tools = {
        "search": lambda args: {
            "items": [{"title": f"Result for {args.get('query', '')}"}]
        },
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
