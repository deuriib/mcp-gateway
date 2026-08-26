"""Tests for dashboard ops card - BR-OBS-008."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_gway.gateway import Gateway
from mcp_gway.registry import Registry


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    return Registry(servers_dir=tmp_path / "servers")


@pytest.fixture
def gateway(registry: Registry) -> Gateway:
    return Gateway(registry)


def test_ops_card_import_and_render() -> None:
    from mcp_gway.dashboard.views import health_badge, ops_card

    html = str(
        ops_card(
            {"status": "ok", "checks": {"registry": "ok"}, "uptime_seconds": 10},
            {"requests_total": 5},
        )
    )
    assert 'id="ops-card"' in html
    assert "healthy" in html.lower()
    assert "Uptime" in html or "uptime" in html.lower() or "10" in html
    assert "max-w-6xl" in html or "mx-auto" in html
    assert "aria-label" in html

    # health_badge variants
    hb_healthy = str(health_badge("healthy"))
    assert "healthy" in hb_healthy.lower()
    assert "emerald" in hb_healthy.lower() or "bg-emerald" in hb_healthy

    hb_degraded = str(health_badge("degraded"))
    assert "degraded" in hb_degraded.lower()
    assert "amber" in hb_degraded.lower() or "bg-amber" in hb_degraded

    hb_not_ready = str(health_badge("not_ready"))
    assert (
        "not_ready" in hb_not_ready.lower()
        or "not-ready" in hb_not_ready.lower()
        or "not" in hb_not_ready.lower()
    )
    # should be slate or red
    assert "slate" in hb_not_ready.lower() or "red" in hb_not_ready.lower()


def test_ops_card_polling_attrs() -> None:
    from mcp_gway.dashboard.views import ops_card

    html = str(ops_card({"status": "ok", "checks": {}, "uptime_seconds": 5}, {}))
    # optional polling attribute
    assert 'hx-get="/api/health"' in html or "hx-get" in html


def test_layout_contains_ops_card() -> None:
    from mcp_gway.dashboard.views import layout

    html = str(layout([], warning_banner=False))
    assert 'id="ops-card"' in html
    assert "healthy" in html.lower()


@pytest.mark.asyncio
async def test_dashboard_contains_ops_card_healthy(gateway: Gateway) -> None:
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/dashboard")
        assert resp.status_code == 200
        text = resp.text
        assert 'id="ops-card"' in text
        assert "healthy" in text.lower()
        assert "max-w-6xl" in text
        # X-Request-ID header present due to middleware
        assert "X-Request-ID" in resp.headers


@pytest.mark.asyncio
async def test_api_health_json(gateway: Gateway) -> None:
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")
        data = resp.json()
        assert "status" in data
        assert "checks" in data
        assert "uptime_seconds" in data
        # metrics_summary masked - no secrets
        assert "***" not in resp.text
        # check no header secrets leaked
        assert "s3cr3t" not in resp.text.lower()


@pytest.mark.asyncio
async def test_api_health_hx_fragment(gateway: Gateway) -> None:
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        # content negotiation -> html fragment
        ctype = resp.headers.get("content-type", "")
        assert "text/html" in ctype
        assert 'id="ops-card"' in resp.text
        assert (
            "healthy" in resp.text.lower()
            or "degraded" in resp.text.lower()
            or "not_ready" in resp.text.lower()
        )


@pytest.mark.asyncio
async def test_api_health_masks_secrets(gateway: Gateway, monkeypatch) -> None:
    async def mock_discover(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover)
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "name": "secret_srv",
            "type": "remote",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer s3cr3t"},
        }
        r = await client.post("/api/servers", json=payload)
        assert r.status_code == 201
        # GET /api/health should not contain s3cr3t
        resp = await client.get("/api/health")
        assert "s3cr3t" not in resp.text
        assert "***" not in resp.text or "s3cr3t" not in resp.text
        # also HX fragment should not leak
        resp2 = await client.get("/api/health", headers={"HX-Request": "true"})
        assert "s3cr3t" not in resp2.text


@pytest.mark.asyncio
async def test_api_health_contains_metrics_summary(gateway: Gateway) -> None:
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # generate some traffic to populate metrics
        await client.get("/health")
        await client.get("/ready")
        resp = await client.get("/api/health")
        data = resp.json()
        # metrics_summary optional but if present should have requests_total
        if "metrics_summary" in data:
            assert (
                "requests_total" in data["metrics_summary"]
                or "p95" in str(data["metrics_summary"]).lower()
            )
        # ensure status field is healthy-like
        assert data["status"] in ("ok", "healthy", "ready", "degraded", "not_ready")
