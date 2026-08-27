"""P0 fixes tests - RCE, SSRF, CSRF, race, sanitization, bounds, CSP."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, MockTransport, Response
from pydantic import ValidationError

from mcp_gway.catalog.models import CatalogCache, CatalogEntry
from mcp_gway.catalog.service import CatalogService
from mcp_gway.catalog.store import CatalogStore
from mcp_gway.gateway import Gateway
from mcp_gway.models import MCPServerConfig
from mcp_gway.registry import Registry


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    return Registry(servers_dir=tmp_path / "servers")


@pytest.fixture
def catalog_store(tmp_path: Path) -> CatalogStore:
    return CatalogStore(tmp_path / "catalog.json")


def test_reject_local_command_rm():
    # RCE allowlist: only npx, node, python, python3, uvx allowed
    with pytest.raises((ValidationError, ValueError)):
        CatalogEntry(
            id="evil",
            name="evil",
            title="evil",
            type="local",
            command=["rm", "-rf", "/"],
        )
    with pytest.raises((ValidationError, ValueError)):
        CatalogEntry(
            id="evil2",
            name="evil2",
            title="evil2",
            type="local",
            command=["npx", "pkg; rm -rf /"],
        )
    with pytest.raises((ValidationError, ValueError)):
        CatalogEntry(
            id="evil3",
            name="evil3",
            title="evil3",
            type="local",
            command=["npx", "pkg", "&", "echo"],
        )
    with pytest.raises((ValidationError, ValueError)):
        CatalogEntry(
            id="evil4",
            name="evil4",
            title="evil4",
            type="local",
            command=["npx", "pkg", ".."],
        )
    with pytest.raises((ValidationError, ValueError)):
        CatalogEntry(
            id="evil5",
            name="evil5",
            title="evil5",
            type="local",
            command=["npx"] + ["a"] * 9,
        )
    # valid should pass
    e = CatalogEntry(
        id="ok",
        name="ok",
        title="ok",
        type="local",
        command=["npx", "my-mcp"],
    )
    assert e.command == ["npx", "my-mcp"]
    e2 = CatalogEntry(
        id="ok2",
        name="ok2",
        title="ok2",
        type="local",
        command=["python", "-m", "mcp_server"],
    )
    assert e2.command[0] == "python"


def test_ssrf_169_blocked():
    # catalog model SSRF
    with pytest.raises((ValidationError, ValueError)):
        CatalogEntry(
            id="bad",
            name="bad",
            title="bad",
            type="remote",
            url="http://169.254.169.254/latest/meta-data/",
        )
    with pytest.raises((ValidationError, ValueError)):
        CatalogEntry(
            id="bad2",
            name="bad2",
            title="bad2",
            type="remote",
            url="http://127.0.0.1:8000/mcp",
        )
    with pytest.raises((ValidationError, ValueError)):
        CatalogEntry(
            id="bad3",
            name="bad3",
            title="bad3",
            type="remote",
            url="http://10.0.0.1/mcp",
        )
    with pytest.raises((ValidationError, ValueError)):
        CatalogEntry(
            id="bad4",
            name="bad4",
            title="bad4",
            type="remote",
            url="http://192.168.1.1/mcp",
        )
    with pytest.raises((ValidationError, ValueError)):
        CatalogEntry(
            id="bad5",
            name="bad5",
            title="bad5",
            type="remote",
            url="http://localhost/mcp",
        )
    with pytest.raises((ValidationError, ValueError)):
        CatalogEntry(
            id="bad6",
            name="bad6",
            title="bad6",
            type="remote",
            url="http://[::1]/mcp",
        )
    # also MCPServerConfig - 169 blocked (private), localhost allowed in tests for fixtures
    with pytest.raises((ValidationError, ValueError)):
        MCPServerConfig(name="bad", type="remote", url="http://169.254.169.254/mcp")
    with pytest.raises((ValidationError, ValueError)):
        MCPServerConfig(name="bad2", type="remote", url="http://10.0.0.1/mcp")
    # CR/LF still blocked
    with pytest.raises((ValidationError, ValueError)):
        MCPServerConfig(name="bad3", type="remote", url="http://127.0.0.1/mcp\r\n")
    # valid public should pass
    cfg = MCPServerConfig(name="ok", type="remote", url="https://example.com/mcp")
    assert cfg.url == "https://example.com/mcp"


@pytest.mark.asyncio
async def test_q_too_long_400(registry: Registry, catalog_store: CatalogStore):
    gw = Gateway(registry, catalog_service=CatalogService(catalog_store))
    transport = ASGITransport(app=gw.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        long_q = "a" * 201
        r = await client.get("/api/catalog", params={"q": long_q})
        assert r.status_code == 400
        assert "too long" in r.text.lower()
        r2 = await client.get("/dashboard/catalog", params={"q": long_q})
        assert r2.status_code == 400


@pytest.mark.asyncio
async def test_timeout_bounds(registry: Registry, tmp_path: Path):
    store = CatalogStore(tmp_path / "catalog.json")
    store.save(
        CatalogCache(
            fetchedAt=datetime.now(UTC),
            entries=[
                CatalogEntry(
                    id="github",
                    name="github",
                    title="GitHub",
                    type="remote",
                    url="https://example.com/mcp",
                )
            ],
        )
    )
    svc = CatalogService(store)
    gw = Gateway(registry, catalog_service=svc)
    transport = ASGITransport(app=gw.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # timeout too small
        r = await client.post("/api/catalog/github/install", json={"timeout": 500})
        assert r.status_code == 400
        assert "timeout" in r.text.lower()
        r2 = await client.post("/api/catalog/github/install", json={"timeout": 50000})
        assert r2.status_code == 400

        # valid timeout
        # need mock discover
        async def mock_discover(config, force_auth=False):
            return []

        # monkeypatch via direct attribute
        import mcp_gway.core
        import mcp_gway.core.client

        orig1 = mcp_gway.core.discover_tools
        orig2 = mcp_gway.core.client.discover_tools
        mcp_gway.core.discover_tools = mock_discover
        mcp_gway.core.client.discover_tools = mock_discover
        try:
            r3 = await client.post(
                "/api/catalog/github/install", json={"timeout": 8000}
            )
            assert r3.status_code == 201
        finally:
            mcp_gway.core.discover_tools = orig1
            mcp_gway.core.client.discover_tools = orig2


@pytest.mark.asyncio
async def test_csrf_form_403(registry: Registry, catalog_store: CatalogStore):
    # use non-test host to enforce strict CSRF
    svc = CatalogService(catalog_store)
    gw = Gateway(registry, host="127.0.0.1", catalog_service=svc)
    transport = ASGITransport(app=gw.app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        # no HX, no Origin -> 403
        r = await client.post("/api/catalog/refresh")
        assert r.status_code == 403
        # HX alone without Origin/Referer -> 403 (HX alone not enough)
        r2 = await client.post("/api/catalog/refresh", headers={"HX-Request": "true"})
        assert r2.status_code == 403
        # HX + evil Origin -> 403
        r3 = await client.post(
            "/api/catalog/refresh",
            headers={"HX-Request": "true", "Origin": "http://evil.com"},
        )
        assert r3.status_code == 403
        # HX + loopback Origin -> 202
        r4 = await client.post(
            "/api/catalog/refresh",
            headers={"HX-Request": "true", "Origin": "http://127.0.0.1"},
        )
        assert r4.status_code == 202
        # also test catalog install CSRF
        catalog_store.save(
            CatalogCache(
                fetchedAt=datetime.now(UTC),
                entries=[
                    CatalogEntry(
                        id="github",
                        name="github",
                        title="GitHub",
                        type="remote",
                        url="https://example.com/mcp",
                    )
                ],
            )
        )
        r5 = await client.post("/api/catalog/github/install")
        assert r5.status_code == 403


@pytest.mark.asyncio
async def test_hyphen_skip_count(registry: Registry, tmp_path: Path):
    store = CatalogStore(tmp_path / "catalog.json")

    async def handler(request: httpx.Request) -> Response:
        return Response(
            200,
            json={
                "entries": [
                    {
                        "id": "valid_github",
                        "name": "valid_github",
                        "title": "GitHub",
                        "type": "remote",
                        "url": "https://example.com/mcp",
                    },
                    {
                        "id": "my-server",
                        "name": "my-server",
                        "title": "Bad hyphen",
                        "type": "remote",
                        "url": "https://example.com/mcp",
                    },
                    {
                        "id": "123bad",
                        "name": "123bad",
                        "title": "Bad start digit",
                        "type": "remote",
                        "url": "https://example.com/mcp",
                    },
                ]
            },
        )

    svc = CatalogService(
        store,
        http_factory=lambda timeout=None, **kw: httpx.AsyncClient(
            transport=MockTransport(handler), timeout=timeout, **kw
        ),
    )
    gw = Gateway(registry, catalog_service=svc)
    transport = ASGITransport(app=gw.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/catalog", params={"fresh": "true"})
        assert r.status_code == 200
        body = r.json()
        assert len(body["entries"]) == 1
        assert body["entries"][0]["id"] == "valid_github"
        assert body["meta"]["invalid_skipped"] == 2


@pytest.mark.asyncio
async def test_local_via_dashboard_blocked(
    registry: Registry, tmp_path: Path, monkeypatch
):
    store = CatalogStore(tmp_path / "catalog.json")
    store.save(
        CatalogCache(
            fetchedAt=datetime.now(UTC),
            entries=[
                CatalogEntry(
                    id="local_pg",
                    name="local_pg",
                    title="Local PG",
                    type="local",
                    command=["npx", "pg-mcp"],
                )
            ],
        )
    )
    svc = CatalogService(store)
    gw = Gateway(registry, catalog_service=svc)
    transport = ASGITransport(app=gw.app)
    # without allow env -> 403
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "0")
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/catalog/local_pg/install")
        assert r.status_code == 403
    # with allow -> 201 (mock discover)
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "1")

    async def mock_discover(config, force_auth=False):
        return []

    import mcp_gway.core
    import mcp_gway.core.client

    orig1 = mcp_gway.core.discover_tools
    orig2 = mcp_gway.core.client.discover_tools
    mcp_gway.core.discover_tools = mock_discover
    mcp_gway.core.client.discover_tools = mock_discover
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r2 = await client.post("/api/catalog/local_pg/install")
            assert r2.status_code == 201
    finally:
        mcp_gway.core.discover_tools = orig1
        mcp_gway.core.client.discover_tools = orig2


def test_csp_no_unsafe_eval(registry: Registry, catalog_store: CatalogStore):
    gw = Gateway(registry, catalog_service=CatalogService(catalog_store))
    # check gateway CSP
    import asyncio

    async def _check():
        transport = ASGITransport(app=gw.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/dashboard/catalog")
            csp = r.headers.get("Content-Security-Policy", "")
            assert "unsafe-eval" not in csp
            assert "default-src 'self'" in csp
            r2 = await client.get("/api/catalog")
            csp2 = r2.headers.get("Content-Security-Policy", "")
            assert "unsafe-eval" not in csp2

    asyncio.run(_check())


@pytest.mark.asyncio
async def test_body_limit_65k(registry: Registry, catalog_store: CatalogStore):
    svc = CatalogService(catalog_store)
    catalog_store.save(
        CatalogCache(
            fetchedAt=datetime.now(UTC),
            entries=[
                CatalogEntry(
                    id="github",
                    name="github",
                    title="GitHub",
                    type="remote",
                    url="https://example.com/mcp",
                )
            ],
        )
    )
    gw = Gateway(registry, catalog_service=svc)
    transport = ASGITransport(app=gw.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        big = "a" * 70000
        r = await client.post(
            "/api/catalog/github/install",
            content=big,
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 413
