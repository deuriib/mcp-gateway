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


def test_layout_has_dialog() -> None:
    html = str(layout([]))
    assert '<dialog id="server-dialog"' in html
    assert 'id="drawer"' not in html
    assert "/static/dialog.js" in html
    assert "backdrop:bg-slate-900/30" in html


def test_server_row_targets_dialog() -> None:
    from mcp_gway.dashboard.views import server_row

    html = str(
        server_row(
            {
                "name": "demo",
                "type": "remote",
                "enabled": True,
                "tool_count": 2,
                "timeout": 5000,
            }
        )
    )
    assert 'hx-target="#server-dialog"' in html
    assert 'hx-indicator="#global-spinner"' in html


def test_drawer_returns_aside_region() -> None:
    from mcp_gway.dashboard.views import drawer_error, server_drawer

    err_html = str(drawer_error("not found", status=404))
    assert "<aside" in err_html
    assert 'role="region"' in err_html
    assert 'role="dialog"' not in err_html

    drawer_html = str(
        server_drawer(
            {
                "name": "x",
                "type": "remote",
                "enabled": True,
                "tool_count": 1,
                "timeout": 5000,
            },
            "def foo(): pass",
            False,
        )
    )
    assert "<aside" in drawer_html
    assert 'role="region"' in drawer_html
    assert 'role="dialog"' not in drawer_html


@pytest.mark.asyncio
async def test_dialog_js_served_and_resilient(gateway: Gateway) -> None:
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/static/dialog.js")
        assert resp.status_code == 200
        text = resp.text
        assert "showModal" in text
        assert "htmx:responseError" in text
        assert "htmx:sendError" in text
        assert "htmx:timeout" in text
        assert "DIALOG_ID" in text
        assert "openDialog" in text
        assert "handleDialogError" in text


@pytest.mark.asyncio
async def test_detail_renders_inside_dialog_panel(
    gateway: Gateway, registry: Registry
) -> None:
    from mcp_gway.models import MCPServerConfig, ToolInfo

    cfg = MCPServerConfig(
        name="detail_srv", type="remote", url="https://example.com/mcp"
    )
    registry.add(cfg, [ToolInfo(name="foo")])
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/dashboard/servers/detail_srv")
        assert resp.status_code == 200
        text = resp.text
        assert "<aside" in text
        assert 'role="region"' in text
        assert ('hx-target="#server-dialog"' in text) or ("fixed inset" not in text)
        assert "fixed inset-0" not in text


@pytest.mark.asyncio
async def test_close_clears_dialog(gateway: Gateway) -> None:
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/dashboard/close")
        assert resp.status_code == 200
        assert resp.text == ""


def test_no_inline_onclick() -> None:
    views_src = Path("src/mcp_gway/dashboard/views.py").read_text(encoding="utf-8")
    assert "onclick" not in views_src.lower()


def test_add_form_has_oauth_checkbox() -> None:
    from mcp_gway.dashboard.views import add_form

    html = str(add_form())
    assert 'id="field-oauth"' in html
    assert 'name="oauth_enabled"' in html
    assert "Enable OAuth" in html
    assert 'id="group-oauth"' in html
    assert 'name="oauth_scope"' in html
    assert "Dynamic client_id auto-generated as UUID" in html


def test_dashboard_js_has_oauth_and_reset() -> None:
    js = Path("src/mcp_gway/dashboard/static/dashboard.js").read_text(encoding="utf-8")
    assert "syncOAuth" in js
    assert "setupOAuth" in js
    assert "setupFormReset" in js
    assert "setupVisualFeedback" in js
    assert "form.reset()" in js
    assert "field-oauth" in js

    htmx = Path("src/mcp_gway/dashboard/static/htmx.min.js").read_text(encoding="utf-8")
    assert "X-Toast" in htmx
    assert "X-OAuth-Required" in htmx
    assert "form.reset()" in htmx or "t.reset()" in htmx
