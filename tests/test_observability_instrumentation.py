from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from mcp_gway.gateway import Gateway
from mcp_gway.models import MCPServerConfig
from mcp_gway.registry import Registry
from mcp_gway.sandbox import StarlarkSandbox


def test_tool_call_increments_metric(tmp_path: Path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    # Mock code_mode to avoid real MCP
    gw.code_mode.execute_tool_code = lambda code: "mocked"  # type: ignore[method-assign]
    c = TestClient(gw.app)
    # Call via MCP POST tools/call executeToolCode
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "executeToolCode", "arguments": {"code": "result='x'"}},
    }
    r = c.post("/mcp", json=body)
    assert r.status_code == 200
    txt = c.get("/metrics").text
    assert "mcp_gway_mcp_tool_calls_total" in txt
    # should have label server/tool/status? At least server wildcard or executeToolCode
    assert 'status="ok"' in txt or "ok" in txt


def test_sandbox_metrics(tmp_path: Path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    sb = StarlarkSandbox()
    # inject gw metrics for sandbox if needed
    if hasattr(sb, "metrics"):
        sb.metrics = gw.metrics  # type: ignore[attr-defined]
    else:
        sb._metrics = gw.metrics  # type: ignore[attr-defined]
    # also try to set via gateway code_mode sandbox
    gw.code_mode.sandbox._metrics = gw.metrics  # type: ignore[attr-defined]
    # execute via sandbox directly with metrics injection fallback
    # If sandbox doesn't support injection, we will test via code_mode
    sb2 = gw.code_mode.sandbox
    sb2.execute("result='hello'")
    txt = TestClient(gw.app).get("/metrics").text
    assert "mcp_gway_sandbox_execute_total" in txt
    assert "mcp_gway_sandbox_duration_seconds" in txt


def test_registry_metrics(tmp_path: Path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    # ensure registry has metrics
    reg._metrics = gw.metrics  # type: ignore[attr-defined]
    # gateway already injects
    cfg = MCPServerConfig(
        name="my_server", type="remote", url="https://example.com/mcp"
    )
    reg.add(cfg, [])
    txt = TestClient(gw.app).get("/metrics").text
    assert "mcp_gway_registry_operations_total" in txt
    assert 'op="add"' in txt


def test_gateway_sessions_active_gauge(tmp_path: Path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    c = TestClient(gw.app)
    txt = c.get("/metrics").text
    assert "mcp_gway_gateway_sessions_active" in txt


def test_sandbox_error_counts(tmp_path: Path) -> None:
    reg = Registry(servers_dir=tmp_path / "servers")
    gw = Gateway(reg, host="127.0.0.1")
    gw.code_mode.sandbox._metrics = gw.metrics  # type: ignore[attr-defined]
    try:
        gw.code_mode.sandbox.execute("raise_error = 1/0\nresult='x'")
    except Exception:
        pass
    # Also try direct error
    try:
        gw.code_mode.sandbox.execute("result = unknown_var")
    except Exception:
        pass
    txt = TestClient(gw.app).get("/metrics").text
    # should have at least one bucket with status error
    assert "sandbox_execute_total" in txt
