"""Tests for the HTTP/SSE gateway server."""

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_gateway.gateway import Gateway
from mcp_gateway.models import ConnectionType, MCPClientConfig, ToolInfo
from mcp_gateway.registry import Registry


@pytest.fixture
def gateway(tmp_path):
    registry = Registry(servers_dir=tmp_path / "servers")
    config = MCPClientConfig(
        name="youtube",
        connection_type=ConnectionType.HTTP,
        connection_string="http://localhost:3001/mcp",
    )
    tools = [ToolInfo(name="search", description="Search videos")]
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
async def test_initialize(gateway):
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.1.0"},
            },
        }
        response = await client.post("/mcp/messages", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["protocolVersion"] == "2024-11-05"
        assert "tools" in data["result"]["capabilities"]


@pytest.mark.asyncio
async def test_tools_list(gateway):
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        response = await client.post("/mcp/messages", json=payload)
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
            "id": 3,
            "method": "tools/call",
            "params": {"name": "listToolFiles", "arguments": {}},
        }
        response = await client.post("/mcp/messages", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "youtube.pyi" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_tools_call_execute_code(gateway):
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "executeToolCode", "arguments": {"code": "result = 42"}},
        }
        response = await client.post("/mcp/messages", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "42" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_unknown_method(gateway):
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"jsonrpc": "2.0", "id": 5, "method": "unknown/method"}
        response = await client.post("/mcp/messages", json=payload)
        data = response.json()
        assert "error" in data


@pytest.mark.asyncio
async def test_sse_endpoint(gateway):
    routes = [r.path for r in gateway.app.routes]
    assert "/mcp" in routes
    assert "/mcp/messages" in routes


@pytest.mark.asyncio
async def test_post_mcp_direct(gateway):
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        response = await client.post("/mcp", json=payload)
        assert response.status_code == 200
        data = response.json()
        tools = data["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "listToolFiles" in names
