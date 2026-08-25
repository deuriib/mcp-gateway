"""Tests for dashboard views htpy - AC-01."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_gway.dashboard.views import layout, server_table
from mcp_gway.gateway import Gateway
from mcp_gway.registry import Registry


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    return Registry(servers_dir=tmp_path / "servers")


@pytest.fixture
def gateway(registry: Registry) -> Gateway:
    return Gateway(registry)


def test_tailwind_vendored_no_node() -> None:
    css_path = Path("src/mcp_gway/dashboard/static/tailwind.css")
    assert css_path.exists()
    assert css_path.stat().st_size < 100 * 1024
    htmx_path = Path("src/mcp_gway/dashboard/static/htmx.min.js")
    assert htmx_path.exists()
    assert htmx_path.stat().st_size < 20 * 1024
    assert not Path("package.json").exists()
    assert not Path("node_modules").exists()


def test_layout_contains_required_elements() -> None:
    html = str(layout([]))
    assert "<table" in html
    assert "max-w-6xl mx-auto" in html
    assert (
        '<link href="/static/tailwind.css"' in html
        or 'href="/static/tailwind.css"' in html
    )
    assert "hx-get" in html or "htmx" in html


def test_server_table_empty_shows_cta() -> None:
    html = str(server_table([]))
    assert "Add your first server" in html
    assert "<tbody" in html


def test_server_table_with_servers() -> None:
    servers = [
        {"name": "gh", "type": "remote", "enabled": True, "tool_count": 3},
        {"name": "local_echo", "type": "local", "enabled": False, "tool_count": 0},
    ]
    html = str(server_table(servers))
    assert "gh" in html
    assert "local_echo" in html
    assert "disabled" in html
    assert "3" in html


@pytest.mark.asyncio
async def test_dashboard_ssr_renders_table(gateway: Gateway) -> None:
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        text = resp.text
        assert "<table" in text
        assert "max-w-6xl mx-auto" in text
        assert "/static/tailwind.css" in text
        assert "hx-get" in text


@pytest.mark.asyncio
async def test_dashboard_servers_fragment(gateway: Gateway, registry: Registry) -> None:
    # add one server via registry directly
    from mcp_gway.models import MCPServerConfig, ToolInfo

    cfg = MCPServerConfig(name="gh", type="remote", url="https://example.com/mcp")
    registry.add(cfg, [ToolInfo(name="search")])
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/dashboard/servers", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "<tbody" in resp.text
        assert "gh" in resp.text


@pytest.mark.asyncio
async def test_static_files_served(gateway: Gateway) -> None:
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.get("/static/tailwind.css")
        assert r1.status_code == 200
        r2 = await client.get("/static/htmx.min.js")
        assert r2.status_code == 200


@pytest.mark.asyncio
async def test_local_first_host_warning() -> None:
    # gateway with non-loopback host should return X-Warning
    import tempfile

    tmp = tempfile.mkdtemp()
    reg = Registry(servers_dir=Path(tmp) / "servers")
    gw = Gateway(reg, host="0.0.0.0")
    transport = ASGITransport(app=gw.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/dashboard")
        assert resp.status_code == 200
        assert resp.headers.get("X-Warning") == "exposed"
        assert "dashboard exposed" in resp.text.lower() or "Warning" in resp.text


def test_no_jinja_import() -> None:
    # ensure views don't use Jinja

    views_src = Path("src/mcp_gway/dashboard/views.py").read_text(encoding="utf-8")
    assert "jinja" not in views_src.lower()
    assert "htpy" in views_src.lower()
