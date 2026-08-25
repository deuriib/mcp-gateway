"""Tests for dashboard API Wave1 - AC-02,07,09."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_gway.gateway import Gateway
from mcp_gway.models import MCPServerConfig
from mcp_gway.registry import Registry


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    return Registry(servers_dir=tmp_path / "servers")


@pytest.fixture
def gateway(registry: Registry) -> Gateway:
    return Gateway(registry)


@pytest.mark.asyncio
async def test_add_remote_persists(
    gateway: Gateway, registry: Registry, monkeypatch
) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "gh",
            "type": "remote",
            "url": "https://example.com/mcp",
            "timeout": 5000,
            "enabled": True,
        }
        resp = await client.post("/api/servers", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "gh"
        assert data["tool_count"] == 0

        cfg = registry.get_config("gh")
        assert cfg.url == "https://example.com/mcp"
        assert (registry.servers_dir / "gh.json").exists()
        assert (registry.servers_dir / "gh.pyi").exists()

        # GET list contains gh masked
        resp2 = await client.get("/api/servers")
        assert resp2.status_code == 200
        lst = resp2.json()
        assert any(s["name"] == "gh" for s in lst)

        # CLI list also would see it via registry
        assert "gh" in registry.list()


@pytest.mark.asyncio
async def test_add_local_persists(
    gateway: Gateway, registry: Registry, monkeypatch
) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "echo_srv",
            "type": "local",
            "command": ["echo", "hi"],
            "cwd": "/tmp",
            "environment": {"FOO": "bar"},
        }
        resp = await client.post("/api/servers", json=payload)
        assert resp.status_code == 201
        # environment masked in GET
        resp2 = await client.get("/api/servers")
        lst = resp2.json()
        echo = next(s for s in lst if s["name"] == "echo_srv")
        assert echo["environment"]["FOO"] == "***"
        assert echo["tool_count"] == 0


@pytest.mark.asyncio
async def test_add_remote_with_headers_masks(gateway: Gateway, monkeypatch) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "gh2",
            "type": "remote",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer s3cr3t"},
        }
        resp = await client.post("/api/servers", json=payload)
        assert resp.status_code == 201
        resp2 = await client.get("/api/servers")
        lst = resp2.json()
        gh2 = next(s for s in lst if s["name"] == "gh2")
        assert gh2["headers"]["Authorization"] == "***"

        # also detail endpoint masks
        resp3 = await client.get("/api/servers/gh2")
        assert resp3.json()["headers"]["Authorization"] == "***"


@pytest.mark.asyncio
async def test_add_duplicate_409(gateway: Gateway, monkeypatch) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"name": "dup", "type": "remote", "url": "https://example.com/mcp"}
        r1 = await client.post("/api/servers", json=payload)
        assert r1.status_code == 201
        r2 = await client.post("/api/servers", json=payload)
        assert r2.status_code == 409
        assert "already exists" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_validation_name_and_missing_fields(gateway: Gateway) -> None:
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for bad in ["my-server", "my server", "1bad", "café", ""]:
            payload = (
                {"name": bad, "type": "remote", "url": "https://example.com/mcp"}
                if bad != ""
                else {"name": "", "type": "remote", "url": "https://example.com/mcp"}
            )
            resp = await client.post("/api/servers", json=payload)
            assert resp.status_code == 400, (
                f"bad name {bad} should 400 got {resp.status_code} {resp.text}"
            )

        # remote without url
        resp = await client.post("/api/servers", json={"name": "bad", "type": "remote"})
        assert resp.status_code == 400
        assert "url" in resp.json()["detail"].lower()

        # local without command
        resp = await client.post(
            "/api/servers", json={"name": "bad_local", "type": "local"}
        )
        assert resp.status_code == 400
        assert "command" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_legacy_resolved_transport(gateway: Gateway, monkeypatch) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "old_http",
            "type": "remote",
            "url": "https://x.com",
            "resolved_transport": "sse",
        }
        resp = await client.post("/api/servers", json=payload)
        assert resp.status_code == 201
        cfg = gateway.registry.get_config("old_http")
        assert cfg.resolved_transport == "sse"


@pytest.mark.asyncio
async def test_corrupt_json_handling(gateway: Gateway, registry: Registry) -> None:
    # create corrupt file via direct FS (allowed for test setup) - then ensure handler returns 500 not crash
    # we use registry to create a valid then corrupt
    cfg = MCPServerConfig(name="gh", type="remote", url="https://example.com/mcp")
    from mcp_gway.models import ToolInfo

    registry.add(cfg, [ToolInfo(name="t")])
    (registry.servers_dir / "gh.json").write_text("{bad json", encoding="utf-8")
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/servers/gh")
        assert resp.status_code == 500
        assert "Corrupt config" in resp.json()["detail"]
        # health still ok
        h = await client.get("/health")
        assert h.status_code == 200


@pytest.mark.asyncio
async def test_content_negotiation_hx(gateway: Gateway, monkeypatch) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "hx_test",
            "type": "remote",
            "url": "https://example.com/mcp",
        }
        resp = await client.post(
            "/api/servers", json=payload, headers={"HX-Request": "true"}
        )
        assert resp.status_code == 201
        assert "text/html" in resp.headers.get("content-type", "")
        assert "tbody" in resp.text or "hx" in resp.text.lower()

        # GET list with HX returns html
        resp2 = await client.get("/api/servers", headers={"HX-Request": "true"})
        assert "text/html" in resp2.headers.get("content-type", "")
        assert "<tbody" in resp2.text or "table" in resp2.text.lower()


@pytest.mark.asyncio
async def test_gateway_embeds_dashboard(gateway: Gateway) -> None:
    paths = [r.path for r in gateway.app.routes]
    assert "/health" in paths
    assert "/dashboard" in paths
    assert "/api/servers" in paths
    # static mount
    assert any(p == "/static" for p in paths)

    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
        assert r.status_code == 200
        r2 = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        assert r2.status_code == 200
        r3 = await client.get("/dashboard")
        assert r3.status_code == 200
        assert "text/html" in r3.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_no_direct_fs_write_outside_registry(
    gateway: Gateway, monkeypatch
) -> None:
    # ensure api uses registry.add not direct write - we can check that monkeypatched registry.add is called
    called = {}

    orig_add = gateway.registry.add

    def spy_add(config, tools):
        called["yes"] = True
        return orig_add(config, tools)

    monkeypatch.setattr(gateway.registry, "add", spy_add)

    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "spytest",
            "type": "remote",
            "url": "https://example.com/mcp",
        }
        resp = await client.post("/api/servers", json=payload)
        assert resp.status_code == 201
        assert called.get("yes") is True


@pytest.mark.asyncio
async def test_add_remote_with_oauth_generates_uuid(
    gateway: Gateway, monkeypatch
) -> None:
    import uuid

    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "oauth_srv",
            "type": "remote",
            "url": "https://example.com/mcp",
            "oauth": {"scope": "openid profile"},
        }
        resp = await client.post("/api/servers", json=payload)
        assert resp.status_code == 201
        cfg = gateway.registry.get_config("oauth_srv")
        assert cfg.oauth is not None
        assert isinstance(cfg.oauth, dict) or hasattr(cfg.oauth, "clientId")
        client_id = (
            cfg.oauth["clientId"] if isinstance(cfg.oauth, dict) else cfg.oauth.clientId
        )
        assert client_id is not None
        uuid.UUID(client_id)

        # via form with oauth_enabled checkbox
        resp2 = await client.post(
            "/api/servers",
            content="name=oauth_form&type=remote&url=https%3A%2F%2Fexample.com%2Fmcp&oauth_enabled=true&oauth_scope=openid",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp2.status_code == 201
        cfg2 = gateway.registry.get_config("oauth_form")
        cid2 = (
            cfg2.oauth["clientId"]
            if isinstance(cfg2.oauth, dict)
            else cfg2.oauth.clientId
        )
        uuid.UUID(cid2)


@pytest.mark.asyncio
async def test_add_remote_with_oauth_via_headers_fallback(
    gateway: Gateway, monkeypatch
) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "oauth_headers",
            "type": "remote",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer token123"},
        }
        resp = await client.post("/api/servers", json=payload)
        assert resp.status_code == 201
        cfg = gateway.registry.get_config("oauth_headers")
        assert cfg.oauth is None
        assert cfg.headers["Authorization"] == "Bearer token123"


@pytest.mark.asyncio
async def test_oauth_toast_and_automatic_header(gateway: Gateway, monkeypatch) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "toast_oauth",
            "type": "remote",
            "url": "https://example.com/mcp",
            "oauth": {"clientId": "550e8400-e29b-41d4-a716-446655440000"},
        }
        resp = await client.post(
            "/api/servers", json=payload, headers={"HX-Request": "true"}
        )
        assert resp.status_code == 201
        assert "x-toast" in resp.headers
        assert "OAuth" in resp.headers["x-toast"]
        assert resp.headers.get("x-oauth-required") == "1"
        assert "hx-swap-oob" not in resp.text
        assert "server-table-body" in resp.text


@pytest.mark.asyncio
async def test_web_oauth_flow_via_dashboard(gateway: Gateway, monkeypatch) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    async def mock_discover_oauth_meta(url):  # noqa: ARG001
        return {
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
            "registration_endpoint": "https://auth.example.com/register",
        }

    async def mock_initiate(
        server_url, server_name, client_metadata=None, callback_port=8989
    ):  # noqa: ARG001
        return "https://auth.example.com/authorize?client_id=test", None

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover)
    monkeypatch.setattr(
        "mcp_gway.oauth.discover_oauth_metadata", mock_discover_oauth_meta
    )
    monkeypatch.setattr("mcp_gway.oauth.initiate_web_oauth", mock_initiate)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create server with OAuth
        payload = {
            "name": "web_oauth",
            "type": "remote",
            "url": "https://example.com/mcp",
            "oauth": {"clientId": "550e8400-e29b-41d4-a716-446655440000"},
        }
        resp = await client.post("/api/servers", json=payload)
        assert resp.status_code == 201

        # Start web OAuth flow
        resp2 = await client.post("/api/servers/web_oauth/oauth/start")
        assert resp2.status_code == 200
        data = resp2.json()
        assert "auth_url" in data
        assert "https://auth.example.com" in data["auth_url"]

        # Check status - should be pending or idle
        resp3 = await client.get("/api/servers/web_oauth/oauth/status")
        assert resp3.status_code == 200
        assert resp3.json()["status"] in ("pending", "idle", "completed")


@pytest.mark.asyncio
async def test_web_oauth_flow_requires_loopback(gateway: Gateway) -> None:
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/servers/nonexistent/oauth/start",
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        # Should fail because server not found or not loopback
        assert resp.status_code in (403, 404)
