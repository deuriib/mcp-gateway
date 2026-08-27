"""Wave 2 Gate minors — hardening tests for api.py.

Minor 1: Form multipart bypass must be gated by streaming 64KB limit.
Minor 2: handle_get JSON must include truncated bool flag.
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_gway.gateway import Gateway
from mcp_gway.models import MCPServerConfig, ToolInfo
from mcp_gway.registry import Registry


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    return Registry(servers_dir=tmp_path / "servers")


@pytest.fixture
def gateway(registry: Registry) -> Gateway:
    return Gateway(registry)


@pytest.mark.asyncio
async def test_form_multipart_exceeds_64kb_returns_413(
    gateway: Gateway, registry: Registry, monkeypatch
) -> None:
    """Multipart body >64KB must return 413 before Registry.add."""
    called = {"add": False}
    orig_add = registry.add

    def spy_add(cfg, tools):  # type: ignore[no-untyped-def]
        called["add"] = True
        return orig_add(cfg, tools)

    monkeypatch.setattr(registry, "add", spy_add)

    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        boundary = "----TestBoundary413"
        big = "y" * 70000
        part1 = (
            "--"
            + boundary
            + '\r\nContent-Disposition: form-data; name="name"\r\n\r\nbig2\r\n'
        )
        part2 = (
            "--"
            + boundary
            + '\r\nContent-Disposition: form-data; name="type"\r\n\r\nlocal\r\n'
        )
        part3 = (
            "--"
            + boundary
            + '\r\nContent-Disposition: form-data; name="command"\r\n\r\n'
            + big
            + "\r\n"
        )
        part4 = "--" + boundary + "--\r\n"
        body = (part1 + part2 + part3 + part4).encode()
        assert len(body) > 65536
        resp = await client.post(
            "/api/servers",
            content=body,
            headers={"content-type": f"multipart/form-data; boundary={boundary}"},
        )
        assert resp.status_code == 413
        assert resp.json() == {"detail": "payload too large"}
        assert called["add"] is False
        assert "big2" not in registry.list()

        # urlencoded >64KB also 413
        payload = {
            "name": "big3",
            "type": "local",
            "command": "npx hi",
            "extra": "x" * 70000,
        }
        body2 = urllib.parse.urlencode(payload)
        assert len(body2.encode()) > 65536
        resp2 = await client.post(
            "/api/servers",
            content=body2,
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert resp2.status_code == 413
        assert resp2.json() == {"detail": "payload too large"}
        assert "big3" not in registry.list()

        # HX variant must return HTML toast, not JSON
        resp_hx = await client.post(
            "/api/servers",
            content=body,
            headers={
                "content-type": f"multipart/form-data; boundary={boundary}",
                "HX-Request": "true",
            },
        )
        assert resp_hx.status_code == 413
        assert "payload too large" in resp_hx.text.lower()
        assert "text/html" in resp_hx.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_form_small_multipart_still_works(
    gateway: Gateway, registry: Registry, monkeypatch
) -> None:
    """Small multipart (<64KB) with name/type local/command must create 201."""

    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        boundary = "----SmallBoundaryOK"
        s1 = (
            "--"
            + boundary
            + '\r\nContent-Disposition: form-data; name="name"\r\n\r\nsmall1\r\n'
        )
        s2 = (
            "--"
            + boundary
            + '\r\nContent-Disposition: form-data; name="type"\r\n\r\nlocal\r\n'
        )
        s3 = (
            "--"
            + boundary
            + '\r\nContent-Disposition: form-data; name="command"\r\n\r\nnpx hi\r\n'
        )
        s4 = "--" + boundary + "--\r\n"
        body = (s1 + s2 + s3 + s4).encode()
        assert len(body) < 65536
        resp = await client.post(
            "/api/servers",
            content=body,
            headers={"content-type": f"multipart/form-data; boundary={boundary}"},
        )
        assert resp.status_code == 201
        assert "small1" in registry.list()
        cfg = registry.get_config("small1")
        assert cfg.command == ["npx", "hi"]

        # also small urlencoded must work
        body2 = urllib.parse.urlencode(
            {"name": "small2", "type": "local", "command": "npx hi"}
        )
        resp2 = await client.post(
            "/api/servers",
            content=body2,
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert resp2.status_code == 201
        assert "small2" in registry.list()


@pytest.mark.asyncio
async def test_handle_get_truncated_flag_true(
    gateway: Gateway, registry: Registry, monkeypatch
) -> None:
    """pyi >50000 chars → JSON truncated true and pyi_content len 50000."""

    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        cfg = MCPServerConfig(
            name="trunc_big", type="remote", url="https://example.com/mcp"
        )
        registry.add(cfg, [])
        big_pyi = "x" * 60000
        (registry.servers_dir / "trunc_big.pyi").write_text(big_pyi, encoding="utf-8")
        resp = await client.get("/api/servers/trunc_big")
        assert resp.status_code == 200
        data = resp.json()
        assert "truncated" in data
        assert "pyi_content" in data
        assert data["truncated"] is True
        assert isinstance(data["truncated"], bool)
        assert len(data["pyi_content"]) == 50000
        # CSP intact
        assert resp.headers.get("content-security-policy") == "default-src 'self'"


@pytest.mark.asyncio
async def test_handle_get_truncated_flag_false(
    gateway: Gateway, registry: Registry, monkeypatch
) -> None:
    """pyi <50000 chars → truncated false."""

    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return [ToolInfo(name="t1")]

    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        cfg = MCPServerConfig(
            name="trunc_small", type="remote", url="https://example.com/mcp"
        )
        registry.add(cfg, [ToolInfo(name="t1")])
        (registry.servers_dir / "trunc_small.pyi").write_text(
            "def foo(): pass", encoding="utf-8"
        )
        resp = await client.get("/api/servers/trunc_small")
        assert resp.status_code == 200
        data = resp.json()
        assert data["truncated"] is False
        assert isinstance(data["truncated"], bool)
        assert data["pyi_content"] == "def foo(): pass"
        assert len(data["pyi_content"]) < 50000
