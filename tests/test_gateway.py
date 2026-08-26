"""Tests for the HTTP/SSE gateway server."""

import asyncio
import time

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_gway.gateway import Gateway
from mcp_gway.models import MCPServerConfig, ToolInfo
from mcp_gway.registry import Registry


@pytest.fixture
def registry(tmp_path):
    reg = Registry(servers_dir=tmp_path / "servers")
    config = MCPServerConfig(
        name="youtube",
        type="remote",
        url="http://localhost:3001/mcp",
    )
    tools = [ToolInfo(name="search", description="Search videos")]
    reg.add(config, tools)
    return reg


@pytest.fixture
def gateway(registry):
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


# --- Session TTL + Cleanup Tests ---


@pytest.mark.asyncio
async def test_session_tracks_last_activity(gateway):
    """Each session should track its last activity timestamp."""
    session_id = "test-session-1"
    gateway._create_session(session_id)
    session = gateway._sessions[session_id]
    before = time.monotonic()
    assert session.last_activity >= before - 0.1
    assert session.last_activity <= before + 0.1


@pytest.mark.asyncio
async def test_session_last_activity_updates_on_message(gateway):
    """Posting a message should update the session's last_activity."""
    session_id = "test-session-2"
    gateway._create_session(session_id)
    initial_time = gateway._sessions[session_id].last_activity
    await asyncio.sleep(0.05)
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    await gateway._handle_post(payload, session_id=session_id)
    assert gateway._sessions[session_id].last_activity > initial_time


@pytest.mark.asyncio
async def test_cleanup_evicts_idle_sessions(gateway):
    """Sessions idle beyond TTL should be evicted."""
    session_id = "idle-session"
    gateway._create_session(session_id)
    gateway._sessions[session_id].last_activity = time.monotonic() - 9999
    evicted = gateway.cleanup_expired_sessions(max_idle_seconds=300)
    assert evicted == 1
    assert session_id not in gateway._sessions


@pytest.mark.asyncio
async def test_cleanup_keeps_active_sessions(gateway):
    """Active sessions should survive cleanup."""
    session_id = "active-session"
    gateway._create_session(session_id)
    evicted = gateway.cleanup_expired_sessions(max_idle_seconds=300)
    assert evicted == 0
    assert session_id in gateway._sessions


@pytest.mark.asyncio
async def test_cleanup_sends_none_to_queue(gateway):
    """Evicted sessions should receive None sentinel to close the SSE stream."""
    session_id = "closing-session"
    gateway._create_session(session_id)
    queue = gateway._sessions[session_id].queue
    gateway._sessions[session_id].last_activity = time.monotonic() - 9999
    gateway.cleanup_expired_sessions(max_idle_seconds=300)
    assert await queue.get() is None


@pytest.mark.asyncio
async def test_post_to_expired_session_returns_404(gateway):
    """Posting to a non-existent (evicted) session should return JSON-RPC error."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    response = await gateway._handle_post(payload, session_id="expired-session")
    assert "error" in response
    assert response["error"]["code"] == -32001


# --- executeToolCode with MCP tool access ---


@pytest.mark.asyncio
async def test_execute_tool_code_has_call_tool(gateway):
    """executeToolCode sandbox should have call_tool injected."""
    assert "call_tool" in gateway.code_mode.sandbox._custom_globals


@pytest.mark.asyncio
async def test_execute_tool_code_has_server_structs(gateway):
    """executeToolCode sandbox should have server structs for registered servers."""
    assert "youtube" in gateway.code_mode.sandbox._modules


@pytest.mark.asyncio
async def test_execute_code_with_server_struct_via_gateway(gateway, monkeypatch):
    """Gateway should execute code that calls MCP tools via server struct."""

    async def mock_call_tool_async(config, tool_name, arguments):
        return {"query": arguments.get("query", ""), "items": []}

    monkeypatch.setattr(
        gateway.code_mode.server_factory,
        "_call_tool_async",
        mock_call_tool_async,
    )
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "executeToolCode",
                "arguments": {"code": 'result = youtube.search(query="gateway test")'},
            },
        }
        response = await client.post("/mcp/messages", json=payload)
        assert response.status_code == 200
        data = response.json()
        text = data["result"]["content"][0]["text"]
        assert "query" in text
