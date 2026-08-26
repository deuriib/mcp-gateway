from __future__ import annotations

from mcp_gway.observability.metrics import MetricsRegistry


def test_counter_exposition() -> None:
    r = MetricsRegistry()
    r.counter(
        "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
    )
    r.inc("http_requests_total", {"method": "GET", "path": "/health", "status": "200"})
    txt = r.exposition()
    assert "# HELP mcp_gway_http_requests_total Total HTTP requests" in txt
    assert "# TYPE mcp_gway_http_requests_total counter" in txt
    assert (
        'mcp_gway_http_requests_total{method="GET",path="/health",status="200"} 1'
        in txt
    )


def test_histogram_buckets() -> None:
    r = MetricsRegistry()
    r.histogram("http_request_duration_seconds", "HTTP latency", ["path"])
    r.observe("http_request_duration_seconds", 0.04, {"path": "/health"})
    txt = r.exposition()
    assert (
        'mcp_gway_http_request_duration_seconds_bucket{path="/health",le="0.05"} 1'
        in txt
    )
    assert 'mcp_gway_http_request_duration_seconds_count{path="/health"} 1' in txt
    assert 'mcp_gway_http_request_duration_seconds_sum{path="/health"}' in txt


def test_counter_increment_multiple() -> None:
    r = MetricsRegistry()
    r.counter("test_counter_total", "help", ["label"])
    r.inc("test_counter_total", {"label": "a"})
    r.inc("test_counter_total", {"label": "a"})
    r.inc("test_counter_total", {"label": "b"})
    txt = r.exposition()
    assert 'test_counter_total{label="a"} 2' in txt
    assert 'test_counter_total{label="b"} 1' in txt


def test_gauge_set_and_exposition() -> None:
    r = MetricsRegistry()
    r.gauge("gateway_sessions_active", "Current SSE sessions", [])
    r.set("gateway_sessions_active", 5, {})
    txt = r.exposition()
    assert "# HELP mcp_gway_gateway_sessions_active Current SSE sessions" in txt
    assert "# TYPE mcp_gway_gateway_sessions_active gauge" in txt
    assert "mcp_gway_gateway_sessions_active 5" in txt


def test_exposition_sorted_deterministic() -> None:
    r = MetricsRegistry()
    r.counter("http_requests_total", "Total HTTP requests", ["method"])
    r.inc("http_requests_total", {"method": "POST"})
    r.inc("http_requests_total", {"method": "GET"})
    txt = r.exposition()
    # sorted order: GET before POST
    pos_get = txt.index('method="GET"')
    pos_post = txt.index('method="POST"')
    assert pos_get < pos_post


def test_histogram_buckets_upper_bound() -> None:
    r = MetricsRegistry()
    r.histogram(
        "http_request_duration_seconds",
        "HTTP latency",
        ["path"],
        buckets=[0.05, 0.1, 0.5],
    )
    r.observe("http_request_duration_seconds", 0.2, {"path": "/api"})
    txt = r.exposition()
    # 0.2 should be in 0.5 bucket but not in 0.05 or 0.1
    assert 'le="0.05"} 0' in txt
    assert 'le="0.1"} 0' in txt
    assert 'le="0.5"} 1' in txt


def test_histogram_default_buckets() -> None:
    r = MetricsRegistry()
    r.histogram("http_request_duration_seconds", "HTTP latency", ["path"])
    # default buckets include 0.005,0.01,...,5
    txt = r.exposition()
    assert 'le="0.005"' in txt
    assert 'le="5"' in txt
    assert 'le="+Inf"' in txt


def test_prefix_added() -> None:
    r = MetricsRegistry()
    r.counter("my_metric_total", "help", [])
    r.inc("my_metric_total", {})
    txt = r.exposition()
    assert "mcp_gway_my_metric_total" in txt


def test_reset_clears() -> None:
    r = MetricsRegistry()
    r.counter("http_requests_total", "help", ["method"])
    r.inc("http_requests_total", {"method": "GET"})
    r.reset()
    txt = r.exposition()
    assert txt.strip() == ""
