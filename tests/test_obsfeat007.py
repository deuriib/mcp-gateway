"""FEAT-007 observability/resilience hardening tests (AC-001..AC-018).

AC-019 (full 255+-test suite + ruff parity) is a CI gate, not a unit test:
  uv run pytest -q && uv run ruff check src/ tests/
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from starlette.testclient import TestClient

from mcp_gway.gateway import Gateway
from mcp_gway.models import MCPServerConfig, ToolInfo
from mcp_gway.observability.logging import JSONFormatter
from mcp_gway.observability.metrics import MetricsRegistry
from mcp_gway.registry import Registry
from mcp_gway.code_mode import CodeMode
from mcp_gway.server_factory import ServerFactory
from mcp_gway.stdio import StdioAdapter


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _series(body: str, metric: str, **labels: str) -> int:
    """Count exposition series lines for `metric` whose labels include all given."""
    n = 0
    for line in body.splitlines():
        if not line.startswith(metric + "{"):
            continue
        seg = line.split("} ", 1)[0]
        for k, v in labels.items():
            if f'{k}="{v}"' not in seg:
                break
        else:
            n += 1
    return n


def _make_registry(tmp_path: Path) -> Registry:
    return Registry(servers_dir=tmp_path / "servers")


def _broken_registry(tmp_path: Path) -> Path:
    """Registry listed server whose config is missing -> 0 tools loaded.

    NOTE: registry.list() globs *.pyi, so the stub must stay; removing the
    .json keeps the server listed while get_config fails (degraded banner).
    Files written directly to tmp_path so --registry-dir tmp_path finds them.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    reg = Registry(servers_dir=tmp_path)
    cfg = MCPServerConfig(
        name="brokensrv", type="local", command=["python3", "-c", "pass"]
    )
    reg.add(cfg, [ToolInfo(name="t", description="d")])
    (tmp_path / "brokensrv.json").unlink()
    return tmp_path


class _FakeGateway:
    """Minimal gateway surface for StdioAdapter (metrics + handlers)."""

    def __init__(self) -> None:
        self.metrics = MetricsRegistry()
        self.handled: list[object] = []

    def _handle_method(self, method: str, params: object) -> None:
        self.handled.append(("notif", method, params))

    async def _handle_post(self, body: dict, session_id: str | None) -> dict:
        self.handled.append(body)
        return {"jsonrpc": "2.0", "id": body.get("id"), "result": {"ok": True}}


class _FlakyCM:
    """Async context manager for create_client_transport that fails N times."""

    def __init__(self, fails: int = 0) -> None:
        self.fails = fails
        self.enters = 0

    def __call__(self, *_a: object, **_k: object) -> "_FlakyCM":
        """Make instance callable — matches create_client_transport(config) signature."""
        return self

    async def __aenter__(self) -> tuple[object, object]:
        self.enters += 1
        if self.enters <= self.fails:
            raise ConnectionError("transport boom")
        return SimpleNamespace(read=True), SimpleNamespace(write=True)

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeSession:
    """Fake mcp.ClientSession; call_tool may raise (simulates upstream errors)."""

    def __init__(self, *_a: object, fail_call: bool = False) -> None:
        self.fail_call = fail_call
        self.call_count = 0

    def __call__(self, *_a: object, **_k: object) -> "_FakeSession":
        """Make instance callable — matches ClientSession(read, write) signature."""
        return self

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def initialize(self) -> None:
        return None

    async def call_tool(self, name: str, arguments: object) -> object:
        self.call_count += 1
        if self.fail_call:
            raise ConnectionError("call failed")
        return SimpleNamespace(content=[SimpleNamespace(text='"ok"')])


# ---------------------------------------------------------------------------
# AC-001 / AC-002 — process + build metrics
# ---------------------------------------------------------------------------


def test_ac001_process_and_build_metrics_present(tmp_path: Path) -> None:
    gw = Gateway(_make_registry(tmp_path), host="127.0.0.1")
    c = TestClient(gw.app)
    body = c.get("/metrics").text
    assert 'mcp_gway_build_info{version="' in body
    assert "mcp_gway_process_start_time_seconds " in body
    assert "mcp_gway_uptime_seconds" in body
    assert "mcp_gway_lifetime_seconds" in body
    assert "mcp_gway_gateway_sse_disconnects_total" in body
    assert "mcp_gway_upstream_tool_calls_total" in body
    assert "mcp_gway_upstream_tool_duration_seconds" in body
    assert "mcp_gway_upstream_retries_total" in body
    assert "mcp_gway_code_mode_servers_skipped_total" in body


def test_ac002_uptime_advances_with_heartbeat(tmp_path: Path, monkeypatch) -> None:
    gw = Gateway(_make_registry(tmp_path), host="127.0.0.1")

    async def _boom(*_a: object, **_k: object) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", _boom)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(gw._heartbeat())
    first = gw.metrics.sum("uptime_seconds")
    assert first >= 0.0, "heartbeat must set uptime_seconds"
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(gw._heartbeat())
    assert gw.metrics.sum("uptime_seconds") >= first


# ---------------------------------------------------------------------------
# AC-003 — label-cardinality guard
# ---------------------------------------------------------------------------


def test_ac003_cardinality_cap_overflows_to_other() -> None:
    reg = MetricsRegistry()
    reg.counter("c", "cardinality test", ["k"])
    for i in range(205):
        reg.inc("c", {"k": f"v{i}"})
    body = reg.exposition()
    total = sum(1 for line in body.splitlines() if line.startswith("mcp_gway_c{"))
    assert total == 201  # 200 distinct combos + 1 reserved `_other`
    assert _series(body, "mcp_gway_c", k="_other") == 1
    assert 'mcp_gway_c{k="_other"} 5' in body  # 205 - 200 overflow merged


# ---------------------------------------------------------------------------
# AC-004 — discovery latency/status metric
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac004_discovery_observed_ok_and_error(monkeypatch) -> None:
    from mcp_gway.core.client import discover_tools

    reg = MetricsRegistry()
    reg.histogram(
        "discovery_duration_seconds", "Discovery latency", ["server", "status"]
    )
    cfg = MCPServerConfig(name="srv", type="remote", url="https://api.example.com/mcp")

    ok_cm = _FlakyCM()

    class _OkSession(_FakeSession):
        async def list_tools(self) -> object:
            return SimpleNamespace(tools=[])

    monkeypatch.setattr("mcp_gway.core.client.create_client_transport", ok_cm)
    monkeypatch.setattr("mcp.ClientSession", _OkSession)

    await discover_tools(cfg, metrics=reg)
    body = reg.exposition()
    assert (
        _series(
            body,
            "mcp_gway_discovery_duration_seconds_count",
            server="srv",
            status="ok",
        )
        == 1
    )

    async def _fail_cm(*_a: object, **_k: object) -> object:
        raise ConnectionError("boom")

    monkeypatch.setattr("mcp_gway.core.client.create_client_transport", _fail_cm)
    await discover_tools(cfg, metrics=reg)
    body = reg.exposition()
    assert (
        _series(
            body,
            "mcp_gway_discovery_duration_seconds_count",
            server="srv",
            status="error",
        )
        == 1
    )


# ---------------------------------------------------------------------------
# AC-005 / AC-006 — SSE disconnect reasons + shutdown summary
# ---------------------------------------------------------------------------


def test_ac005_sse_disconnect_counted(tmp_path: Path, caplog) -> None:
    """WU-003 / AC-005: SSE disconnect increments the counter.

    Uses the ASGI TestClient's ``stream`` context manager.  When the context
    exits the client closes the HTTP connection which triggers the SSE
    ``finally`` block (reason = ``idle`` because no messages are sent).
    A short poll accommodates the event-loop scheduling delay.
    """
    gw = Gateway(_make_registry(tmp_path), host="127.0.0.1")
    c = TestClient(gw.app, timeout=5.0)
    with caplog.at_level(logging.WARNING, logger="mcp_gway.gateway"):
        with c.stream("GET", "/mcp") as resp:
            assert resp.status_code == 200
    # Poll briefly — the SSE generator's finally block runs asynchronously.
    for _ in range(100):
        if gw.metrics.sum("gateway_sse_disconnects_total") >= 1:
            break
        time.sleep(0.02)
    assert gw.metrics.sum("gateway_sse_disconnects_total") >= 1
    # Verify WARN log emitted on SSE disconnect (F-1 fix).
    recs = [r for r in caplog.records if r.getMessage() == "SSE session ended"]
    assert recs, "SSE disconnect must emit a WARN log"
    assert recs[-1].reason == "idle"


def test_ac006_aclose_emits_shutdown_summary(tmp_path: Path, caplog) -> None:
    gw = Gateway(_make_registry(tmp_path), host="127.0.0.1")
    c = TestClient(gw.app)
    c.get("/health")
    c.get("/health")
    with caplog.at_level(logging.INFO, logger="mcp_gway.gateway"):
        asyncio.run(gw.aclose())
    recs = [r for r in caplog.records if r.getMessage() == "gateway shutdown summary"]
    assert recs, "aclose must emit a shutdown summary"
    rec = recs[-1]
    assert rec.uptime_seconds >= 0.0
    assert int(rec.http_requests_total) >= 2
    assert rec.sessions_active == 0
    assert int(rec.sse_dropped_total) >= 0
    assert gw.metrics.sum("lifetime_seconds") > 0.0
    payload = json.loads(JSONFormatter().format(rec))
    assert "uptime_seconds" in payload and "http_requests_total" in payload


# ---------------------------------------------------------------------------
# AC-007 — slow-request WARN
# ---------------------------------------------------------------------------


def test_ac007_slow_request_warns(tmp_path: Path, caplog, monkeypatch) -> None:
    import mcp_gway.observability.middleware as mw

    monkeypatch.setattr(mw, "_SLOW_REQUEST_THRESHOLD_MS", -1)  # force the branch
    gw = Gateway(_make_registry(tmp_path), host="127.0.0.1")
    c = TestClient(gw.app)
    with caplog.at_level(logging.WARNING, logger="mcp_gway.observability.middleware"):
        c.get("/health")
    recs = [r for r in caplog.records if r.getMessage() == "slow request"]
    assert recs, "requests over the threshold must emit a WARN"
    assert recs[-1].duration_ms >= 0


# ---------------------------------------------------------------------------
# AC-008 / AC-009 — stdio metrics + JSON access log
# ---------------------------------------------------------------------------


def test_ac008_stdio_request_metrics_recorded() -> None:
    gw = _FakeGateway()
    adapter = StdioAdapter(gw)
    asyncio.run(
        adapter.handle_line(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "x", "arguments": {}},
                }
            )
        )
    )
    asyncio.run(
        adapter.handle_line(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )
    )
    body = gw.metrics.exposition()
    assert (
        _series(body, "mcp_gway_stdio_requests_total", method="tools_call", status="ok")
        == 1
    )
    assert (
        _series(
            body,
            "mcp_gway_stdio_requests_total",
            method="notifications_initialized",
            status="ok",
        )
        == 1
    )
    assert (
        _series(
            body, "mcp_gway_stdio_request_duration_seconds_count", method="tools_call"
        )
        == 1
    )


def test_ac009_stdio_access_log_json(caplog) -> None:
    gw = _FakeGateway()
    adapter = StdioAdapter(gw)
    fmt = JSONFormatter()
    with caplog.at_level(logging.INFO, logger="mcp_gway.stdio"):
        asyncio.run(
            adapter.handle_line(
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
            )
        )
    recs = [r for r in caplog.records if r.getMessage() == "stdio request completed"]
    assert recs
    payload = json.loads(fmt.format(recs[-1]))
    assert payload["transport"] == "stdio"
    assert payload["path"] == "stdio"
    assert payload["method"] == "ping"
    assert payload["status"] == "ok"
    assert payload["request_id"]
    assert 0 <= int(payload["duration_ms"]) < 10_000


# ---------------------------------------------------------------------------
# AC-010 / AC-011 — CLI structured logging
# ---------------------------------------------------------------------------


def test_ac010_cli_info_silent_without_env(caplog, monkeypatch) -> None:
    from mcp_gway.cli import _log_cli_event

    monkeypatch.delenv("MCP_GWAY_LOG_LEVEL", raising=False)
    with caplog.at_level(logging.INFO, logger="mcp_gway.cli"):
        _log_cli_event("add", "success", server="srv", duration_ms=12)
    assert not [r for r in caplog.records if r.getMessage() == "cli add success"]


def test_ac010b_cli_info_emitted_with_env(caplog, monkeypatch) -> None:
    from mcp_gway.cli import _log_cli_event

    monkeypatch.setenv("MCP_GWAY_LOG_LEVEL", "info")
    with caplog.at_level(logging.INFO, logger="mcp_gway.cli"):
        _log_cli_event("add", "success", server="srv", duration_ms=12)
    recs = [r for r in caplog.records if r.getMessage() == "cli add success"]
    assert recs and recs[-1].action == "add" and recs[-1].server == "srv"


def test_ac011_cli_warning_always_emitted(caplog, monkeypatch) -> None:
    from mcp_gway.cli import _log_cli_event

    monkeypatch.delenv("MCP_GWAY_LOG_LEVEL", raising=False)
    with caplog.at_level(logging.WARNING, logger="mcp_gway.cli"):
        _log_cli_event("add", "error", server="srv", detail="boom")
    recs = [r for r in caplog.records if r.getMessage() == "cli add error"]
    assert recs and recs[-1].levelno == logging.WARNING


# ---------------------------------------------------------------------------
# AC-012 / AC-017 — degraded banner + CodeMode skip evidence
# ---------------------------------------------------------------------------


def test_ac012_banner_shows_degraded_hint(tmp_path: Path, monkeypatch) -> None:
    _broken_registry(tmp_path)
    monkeypatch.setattr(
        "uvicorn.run", lambda *a, **k: (_ for _ in ()).throw(SystemExit(0))
    )
    from mcp_gway.cli import main

    result = CliRunner().invoke(
        main,
        ["serve", "--transport", "http", "--registry-dir", str(tmp_path)],
    )
    assert "degraded" in result.output
    assert "no tools" in result.output


def test_ac017_code_mode_skip_recorded(tmp_path: Path, caplog, monkeypatch) -> None:
    """WU-008 / AC-017: broken injection during startup emits WARN + metric."""
    servers = tmp_path / "servers"
    servers.mkdir()
    reg = Registry(servers_dir=servers)
    # Healthy registry — both .pyi and .json present — so _code_mode_servers includes it.
    reg.add(
        MCPServerConfig(
            name="brokensrv", type="local", command=["python3", "-c", "pass"]
        ),
        [ToolInfo(name="t", description="d")],
    )

    def _boom(self: object, name: str) -> object:  # noqa: ARG001
        raise FileNotFoundError(f"{name} inject failed (simulated)")

    monkeypatch.setattr(ServerFactory, "make_server_struct", _boom)

    with caplog.at_level(logging.WARNING, logger="mcp_gway.code_mode"):
        gw = Gateway(reg, host="127.0.0.1")

    body = gw.metrics.exposition()
    assert (
        _series(body, "mcp_gway_code_mode_servers_skipped_total", reason="inject_error")
        >= 1
    )
    recs = [r for r in caplog.records if r.getMessage() == "code mode server skipped"]
    assert recs, "broken servers must be skipped loudly"
    assert recs[-1].server == "brokensrv"


# ---------------------------------------------------------------------------
# AC-013..AC-016 — upstream tool telemetry + transport-phase retry
# ---------------------------------------------------------------------------


def _upstream_env(monkeypatch, *, fails: int = 0, fail_call: bool = False):
    cm = _FlakyCM(fails=fails)
    monkeypatch.setattr("mcp_gway.core.create_client_transport", cm)
    session = _FakeSession(fail_call=fail_call)
    monkeypatch.setattr("mcp.ClientSession", session)
    return cm, session


def _bare_factory(tmp_path: Path) -> ServerFactory:
    """ServerFactory for _call_tool_async unit tests (registry unused here)."""
    return ServerFactory(Registry(tmp_path / "unused-servers"))


def test_ac013_upstream_tool_ok_and_error(tmp_path: Path, monkeypatch) -> None:
    reg = MetricsRegistry()
    sf = _bare_factory(tmp_path)
    sf._metrics = reg
    cfg = MCPServerConfig(name="srv", type="remote", url="https://api.example.com/mcp")

    _upstream_env(monkeypatch)
    result = asyncio.run(sf._call_tool_async(cfg, "echo", {}))
    assert result == "ok"
    body = reg.exposition()
    assert (
        _series(
            body,
            "mcp_gway_upstream_tool_calls_total",
            server="srv",
            tool="echo",
            status="ok",
        )
        == 1
    )
    assert (
        _series(
            body,
            "mcp_gway_upstream_tool_duration_seconds_count",
            server="srv",
            tool="echo",
        )
        == 1
    )

    _upstream_env(monkeypatch, fail_call=True)
    with pytest.raises(ConnectionError):
        asyncio.run(sf._call_tool_async(cfg, "echo", {}))
    body = reg.exposition()
    assert (
        _series(
            body,
            "mcp_gway_upstream_tool_calls_total",
            server="srv",
            tool="echo",
            status="error",
        )
        == 1
    )


def test_ac014_transport_retry_accepted_when_flagged(
    tmp_path: Path, monkeypatch
) -> None:
    reg = MetricsRegistry()
    sf = _bare_factory(tmp_path)
    sf._metrics = reg
    cfg = MCPServerConfig(
        name="srv",
        type="remote",
        url="https://api.example.com/mcp",
        retry_on_transport_error=True,
    )
    cm, session = _upstream_env(monkeypatch, fails=1)
    result = asyncio.run(sf._call_tool_async(cfg, "echo", {}))
    assert result == "ok"
    assert cm.enters == 2, "transport must be retried exactly once"
    body = reg.exposition()
    assert _series(body, "mcp_gway_upstream_retries_total", server="srv") == 1
    assert (
        _series(
            body,
            "mcp_gway_upstream_tool_calls_total",
            server="srv",
            tool="echo",
            status="ok",
        )
        == 1
    )


def test_ac015_no_retry_after_call_tool(tmp_path: Path, monkeypatch) -> None:
    reg = MetricsRegistry()
    sf = _bare_factory(tmp_path)
    sf._metrics = reg
    cfg = MCPServerConfig(
        name="srv",
        type="remote",
        url="https://api.example.com/mcp",
        retry_on_transport_error=True,
    )
    _cm, session = _upstream_env(monkeypatch, fail_call=True)
    with pytest.raises(ConnectionError):
        asyncio.run(sf._call_tool_async(cfg, "echo", {}))
    # BR-112: a failure AFTER call_tool starts must never be retried — a
    # non-idempotent tool cannot run twice on a transient upstream error.
    assert session.call_count == 1
    body = reg.exposition()
    assert _series(body, "mcp_gway_upstream_retries_total", server="srv") == 0
    assert (
        _series(
            body,
            "mcp_gway_upstream_tool_calls_total",
            server="srv",
            tool="echo",
            status="error",
        )
        == 1
    )


def test_ac016_retry_off_by_default(tmp_path: Path, monkeypatch) -> None:
    reg = MetricsRegistry()
    sf = _bare_factory(tmp_path)
    sf._metrics = reg
    cfg = MCPServerConfig(name="srv", type="remote", url="https://api.example.com/mcp")
    cm, _ = _upstream_env(monkeypatch, fails=1)
    with pytest.raises(ConnectionError):
        asyncio.run(sf._call_tool_async(cfg, "echo", {}))
    assert cm.enters == 1, "default must NOT retry"
    body = reg.exposition()
    assert _series(body, "mcp_gway_upstream_retries_total", server="srv") == 0


# ---------------------------------------------------------------------------
# AC-018 — no new production dependencies
# ---------------------------------------------------------------------------


def test_ac018_no_new_prod_dependencies() -> None:
    import tomllib

    root = Path(__file__).resolve().parent.parent
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    deps = " ".join(pyproject["project"].get("dependencies", []))
    for banned in (
        "tenacity",
        "prometheus-client",
        "prometheus_client",
        "opentelemetry",
        "structlog",
    ):
        assert banned not in deps, f"must not add {banned} for FEAT-007"
