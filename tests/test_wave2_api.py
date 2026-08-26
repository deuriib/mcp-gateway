"""Wave2 AC tests - PATCH/DELETE/refresh/reveal."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_gway.gateway import Gateway
from mcp_gway.models import ToolInfo
from mcp_gway.registry import Registry


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    return Registry(servers_dir=tmp_path / "servers")


@pytest.fixture
def gateway(registry: Registry) -> Gateway:
    return Gateway(registry)


@pytest.mark.asyncio
async def test_patch_toggle(gateway: Gateway, registry: Registry, monkeypatch) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return [ToolInfo(name="t1")]

    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/servers",
            json={"name": "srv1", "type": "remote", "url": "https://example.com/mcp"},
        )
        r = await client.patch("/api/servers/srv1", json={"enabled": False})
        assert r.status_code == 200
        assert r.json()["enabled"] is False
        if "headers" in r.json() and r.json()["headers"] is not None:
            assert r.json()["headers"].get("Authorization") != "secret"
        r2 = await client.get("/api/servers/srv1")
        assert r2.json()["enabled"] is False


@pytest.mark.asyncio
async def test_patch_validation(
    gateway: Gateway, registry: Registry, monkeypatch
) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/servers",
            json={"name": "srv2", "type": "remote", "url": "https://example.com/mcp"},
        )
        r = await client.patch("/api/servers/srv2", json={"enabled": "notbool"})
        assert r.status_code == 400
        r = await client.patch("/api/servers/nonexist", json={"enabled": True})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_idempotent(gateway: Gateway, monkeypatch) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/servers",
            json={"name": "todel", "type": "remote", "url": "https://example.com/mcp"},
        )
        r = await client.delete("/api/servers/todel")
        assert r.status_code == 204
        r = await client.delete("/api/servers/todel")
        assert r.status_code == 204
        r = await client.delete("/api/servers/never")
        assert r.status_code == 204


@pytest.mark.asyncio
async def test_refresh_nonblocking(gateway: Gateway, monkeypatch) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return [ToolInfo(name="t1")]

    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/servers",
            json={"name": "r1", "type": "remote", "url": "https://example.com/mcp"},
        )
        r = await client.post("/api/servers/r1/refresh", json={})
        assert r.status_code == 202
        assert r.json()["status"] == "refreshing"
        # disabled should 409
        await client.post(
            "/api/servers",
            json={
                "name": "r2",
                "type": "remote",
                "url": "https://example.com/mcp",
                "enabled": False,
            },
        )
        r = await client.post("/api/servers/r2/refresh", json={})
        assert r.status_code == 409
        r = await client.post("/api/servers/notfound/refresh", json={})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_reveal_loopback_and_rate(gateway: Gateway, monkeypatch) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/servers",
            json={
                "name": "sec",
                "type": "remote",
                "url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer s3cr3t"},
            },
        )
        r = await client.get("/api/servers/sec")
        assert r.json()["headers"]["Authorization"] == "***"
        r = await client.post("/api/servers/sec/reveal", json={})
        assert r.status_code == 200
        assert r.json()["headers"]["Authorization"] == "Bearer s3cr3t"
        # rate limit 5/min
        for _ in range(4):
            await client.post("/api/servers/sec/reveal", json={})
        r = await client.post("/api/servers/sec/reveal", json={})
        assert r.status_code == 429


@pytest.mark.asyncio
async def test_csp_header(gateway: Gateway) -> None:
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
        assert r.headers.get("content-security-policy") == "default-src 'self'"
        r = await client.get("/dashboard")
        csp = r.headers.get("content-security-policy", "")
        assert "default-src 'self'" in csp
        assert "style-src" in csp
        assert "'unsafe-inline'" in csp
