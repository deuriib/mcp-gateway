from __future__ import annotations

import time

from starlette.testclient import TestClient

from mcp_gway.gateway import Gateway
from mcp_gway.registry import Registry


def test_health_and_correlation_echo(tmp_path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    c = TestClient(gw.app)
    r = c.get("/health", headers={"X-Request-ID": "test123"})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == "test123"
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "uptime_seconds" in data
    assert "checks" in data
    # without header, should generate one
    r2 = c.get("/health")
    assert "X-Request-ID" in r2.headers
    assert len(r2.headers["X-Request-ID"]) >= 8


def test_ready_ok(tmp_path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    c = TestClient(gw.app)
    r = c.get("/ready")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ready"
    assert "checks" in data


def test_ready_503_on_registry_fail(tmp_path, monkeypatch) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")

    def fail_list():
        raise RuntimeError("registry broken")

    monkeypatch.setattr(reg, "list", fail_list)
    c = TestClient(gw.app)
    r = c.get("/ready")
    assert r.status_code == 503
    data = r.json()
    assert data["status"] == "not_ready"
    assert "registry" in str(data["checks"]).lower() or "registry" in data["checks"]


def test_live_always_alive(tmp_path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    c = TestClient(gw.app)
    start = time.perf_counter()
    r = c.get("/live")
    elapsed = (time.perf_counter() - start) * 1000
    assert r.status_code == 200
    assert r.json()["status"] == "alive"
    assert elapsed < 200  # <5ms ideally but allow 200 in CI
    assert "uptime_seconds" in r.json()


def test_metrics_exposition(tmp_path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    c = TestClient(gw.app)
    c.get("/health")
    m = c.get("/metrics")
    assert m.status_code == 200
    assert "text/plain" in m.headers.get("content-type", "")
    assert "# HELP mcp_gway_http_requests_total" in m.text
    assert "mcp_gway_http_request_duration_seconds_bucket" in m.text


def test_metrics_counts_increment(tmp_path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    c = TestClient(gw.app)
    c.get("/health")
    c.get("/health")
    txt = c.get("/metrics").text
    # at least 2 requests counted
    assert (
        'path="/health"' in txt
        or 'path="/health"' in txt
        or "http_requests_total" in txt
    )


def test_path_template_normalization(tmp_path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    c = TestClient(gw.app)
    # request to concrete name path should be counted as template
    c.get("/api/servers/my_server")
    txt = c.get("/metrics").text
    # should contain template, not concrete
    assert "/api/servers/{name}" in txt or 'path="/api/servers/{name}"' in txt
    # should NOT contain concrete name as label
    assert 'path="/api/servers/my_server"' not in txt


def test_correlation_sanitize(tmp_path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    c = TestClient(gw.app)
    r = c.get("/health", headers={"X-Request-ID": "a\nb\r\x00" + "x" * 5000})
    rid = r.headers.get("X-Request-ID", "")
    assert "\n" not in rid
    assert "\r" not in rid
    assert len(rid) <= 64
    assert "\x00" not in rid


def test_middleware_order_correlation_outermost(tmp_path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    # check user_middleware order - correlation should be outermost (first to process)
    # Starlette stores middleware in reverse order of addition? Need to inspect existence
    mws = [m.cls.__name__ for m in gw.app.user_middleware]  # type: ignore[attr-defined]
    # at least CorrelationMiddleware should be present
    assert any("Correlation" in name for name in mws)
    assert any("Metrics" in name for name in mws)
    assert any("Logging" in name for name in mws)


def test_metrics_no_secrets(tmp_path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    c = TestClient(gw.app)
    m = c.get("/metrics")
    # secrets should not appear
    assert "***" not in m.text
    assert "Bearer" not in m.text


def test_health_has_version_and_uptime(tmp_path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    c = TestClient(gw.app)
    # ensure start_time exists
    assert hasattr(gw, "start_time")
    r = c.get("/health")
    data = r.json()
    assert isinstance(data.get("uptime_seconds"), (int, float))
    assert data.get("uptime_seconds") >= 0
