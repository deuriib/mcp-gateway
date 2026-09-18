"""Hermetic edge tests: health/metrics/logging/middleware exposition."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from starlette.requests import Request
from starlette.testclient import TestClient

from mcp_gway.gateway import Gateway
from mcp_gway.observability import health as H
from mcp_gway.observability import logging as LG
from mcp_gway.observability import metrics as M
from mcp_gway.observability import middleware as MW
from mcp_gway.registry import Registry


def _gw(tmp_path):
    return Gateway(Registry(servers_dir=tmp_path / "srv"))


def test_check_registry_and_routes(tmp_path):
    reg = Registry(servers_dir=tmp_path / "r")
    status, _reason = H.check_registry(reg)
    assert status == "ok"
    with patch.object(reg, "list", side_effect=RuntimeError("down")):
        status, reason = H.check_registry(reg)
        assert status == "fail"
        assert "RuntimeError" in reason
    status, _ = H.check_routes(MagicMock(routes=[1]))
    assert status == "ok"
    status, reason = H.check_routes(MagicMock(routes=[]))
    assert status == "fail"
    assert reason == "no routes mounted"
    status, reason = H.check_routes(None)
    assert status == "fail"
    assert reason == "no routes mounted"


def test_ready_not_ready_and_loop_blocked(tmp_path):
    gw = _gw(tmp_path)
    c = TestClient(gw.app)
    assert c.get("/ready").json()["status"] == "ready"
    # Contract: drift threshold is 35s (30s heartbeat + 5s buffer, health.py:88).
    # Drift below threshold stays ready; only drift above threshold is 503.
    gw._last_loop_tick -= 10
    assert c.get("/ready").status_code == 200
    gw._last_loop_tick += 10
    gw._last_loop_tick -= 40
    assert c.get("/ready").status_code == 503
    gw._last_loop_tick += 40
    with patch.object(gw.registry, "list", side_effect=RuntimeError("down")):
        assert c.get("/ready").status_code == 503


def test_metrics_exposition_all_types():
    r = M.MetricsRegistry()
    r.counter("c1", "help c", ["a"])
    r.inc("c1", {"a": "x"})
    r.inc("auto_c", {"k": "v"})
    r.gauge("g1", "help g")
    r.set("g1", 3.0, {})
    r.set("auto_g", 1.5, {"k": "v"})
    r.histogram("h1", "help h", ["p"])
    r.observe("h1", 0.04, {"p": "q"})
    r.observe("auto_h", 0.2, {"z": "1"})
    text = r.exposition()
    assert (
        "mcp_gway_c1" in text and "mcp_gway_g1" in text and "mcp_gway_h1_bucket" in text
    )
    assert "_sum" in text and "_count" in text
    r2 = M.MetricsRegistry()
    r2.histogram("empty_h", "help", [])
    assert "+Inf" in r2.exposition()
    r2.reset()
    assert r2.exposition() == ""
    assert M._prefixed("mcp_gway_x") == "mcp_gway_x"
    assert M._prefixed("x") == "mcp_gway_x"
    assert M._label_str({}) == ""
    assert "le=" in M._hist_bucket_label({"p": "q"}, ["p"], "0.05")
    assert M._hist_labels_only({}, []) == ""
    assert M._format_le(5.0) == "5" and M._format_sum(3.0) == "3.0"


def test_metrics_label_escape_and_counter_update():
    r = M.MetricsRegistry()
    r.counter("c2", "h1", ["a"])
    r.counter("c2", "h2", ["a"])
    r.gauge("g2", "h1")
    r.gauge("g2", "h2")
    r.histogram("h2", "h1", ["p"])
    r.histogram("h2", "h2", ["p"])
    r.inc("c2", {"a": 'x\ny"z\\'})
    assert "mcp_gway_c2" in r.exposition()


def test_logging_sanitize_format_levels():
    assert LG.sanitize_request_id("  abc-123_!@#  ") != ""
    assert LG.sanitize_request_id("!!!") == "unknown"
    rec = logging.LogRecord("n", logging.INFO, "p", 1, "hello", (), None)
    rec.request_id = "r1"
    out = LG.JSONFormatter().format(rec)
    assert "r1" in out and "hello" in out
    LG.request_id_ctx.set("ctx1")
    rec2 = logging.LogRecord("n", logging.INFO, "p", 1, "hi2", (), None)
    assert "ctx1" in LG.JSONFormatter().format(rec2)
    LG.request_id_ctx.set(None)
    assert LG._level_from_str("trace") == logging.DEBUG
    assert LG._level_from_str("warn") == logging.WARNING
    assert LG._level_from_str("bogus") == logging.INFO
    LG.setup_logging("info")
    LG.setup_logging("info")
    assert len(logging.getLogger("mcp_gway").handlers) >= 1


def test_middleware_ids_templates_labels():
    def req(headers):
        return Request(
            {"type": "http", "method": "GET", "path": "/", "headers": headers}
        )

    assert MW._get_request_id(req([])) != ""
    assert MW._get_request_id(req([(b"x-request-id", b"abc-123")])) == "abc-123"
    assert MW._get_request_id(req([(b"x-correlation-id", b"corr1")])) == "corr1"
    assert MW._get_request_id(req([(b"x-request-id", b"!!!")])) != "!!!"
    assert MW.path_template("/mcp") == "/mcp"
    assert MW.path_template("/mcp/messages?x=1") == "/mcp/messages"
    assert MW.path_template("/health") == "/health"
    assert MW.sanitize_label("a-b!c") == "a_b_c"
    assert MW.sanitize_label("!!!") == "_other"


def test_correlation_and_metrics_middleware(tmp_path):
    gw = _gw(tmp_path)
    c = TestClient(gw.app)
    r = c.get("/health", headers={"X-Request-ID": "myid-1"})
    assert r.headers.get("X-Request-ID") == "myid-1"
    r = c.get("/health")
    assert r.headers.get("X-Request-ID")
    assert "http_requests_total" in gw.metrics.exposition()
