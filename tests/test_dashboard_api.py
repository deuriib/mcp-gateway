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
