"""Tests for stdio/local NDJSON transport (mcp command)."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from mcp_gway.models import MCPServerConfig, ToolInfo
from mcp_gway.registry import Registry


@pytest.fixture
def registry(tmp_path: Any) -> Registry:
    reg = Registry(servers_dir=tmp_path / "servers")
    config = MCPServerConfig(
        name="youtube",
        type="remote",
        url="http://localhost:3001/mcp",
    )
    reg.add(config, [ToolInfo(name="search", description="Search videos")])
    return reg


@pytest.fixture
def gateway(registry: Registry) -> Any:
    from mcp_gway.gateway import Gateway

    return Gateway(registry)


@pytest.fixture
def adapter(gateway: Any) -> Any:
    from mcp_gway.stdio import StdioAdapter

    return StdioAdapter(gateway)


@pytest.mark.asyncio
async def test_framing_initialize(adapter: Any) -> None:
    line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    out = await adapter.handle_line(line)
    assert out is not None
    data = json.loads(out)
    assert data["id"] == 1
    assert data["result"]["protocolVersion"] == "2024-11-05"


@pytest.mark.asyncio
async def test_notifications_no_response(adapter: Any) -> None:
    line = json.dumps(
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    )
    out = await adapter.handle_line(line)
    assert out is None


@pytest.mark.asyncio
async def test_empty_line_ignored(adapter: Any) -> None:
    assert await adapter.handle_line("") is None
    assert await adapter.handle_line("   ") is None
    assert await adapter.handle_line("\n") is None


@pytest.mark.asyncio
async def test_invalid_json_parse_error(adapter: Any) -> None:
    out = await adapter.handle_line("not json {{{")
    assert out is not None
    data = json.loads(out)
    assert data["error"]["code"] == -32700
    # process survives: next valid line still works
    ok = await adapter.handle_line(
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})
    )
    assert ok is not None
    assert json.loads(ok)["id"] == 2


@pytest.mark.asyncio
async def test_line_over_1mib_parse_error(adapter: Any) -> None:
    big = "x" * (1_048_577)
    out = await adapter.handle_line(big)
    assert out is not None
    data = json.loads(out)
    assert data["error"]["code"] == -32700


@pytest.mark.asyncio
async def test_batch_list_invalid_request(adapter: Any) -> None:
    line = json.dumps(
        [{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "id": 2}]
    )
    out = await adapter.handle_line(line)
    assert out is not None
    data = json.loads(out)
    assert data["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_tools_list_via_stdio(adapter: Any) -> None:
    line = json.dumps({"jsonrpc": "2.0", "id": 10, "method": "tools/list"})
    out = await adapter.handle_line(line)
    assert out is not None
    data = json.loads(out)
    names = [t["name"] for t in data["result"]["tools"]]
    assert "listToolFiles" in names


@pytest.mark.asyncio
async def test_tools_call_via_stdio(adapter: Any) -> None:
    line = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "listToolFiles", "arguments": {}},
        }
    )
    out = await adapter.handle_line(line)
    assert out is not None
    data = json.loads(out)
    assert "youtube.pyi" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_stdout_pure_json_only(gateway: Any) -> None:
    from mcp_gway.stdio import run_stdio_async

    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        + "\n"
        + "not json\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        + "\n"
        + "\n"
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    rc = await run_stdio_async(gateway, stdin, stdout, stderr)
    assert rc == 0
    lines = [ln for ln in stdout.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 2
    for ln in lines:
        json.loads(ln)


@pytest.mark.asyncio
async def test_eof_exit_zero(gateway: Any) -> None:
    from mcp_gway.stdio import run_stdio_async

    rc = await run_stdio_async(gateway, io.StringIO(""), io.StringIO(), io.StringIO())
    assert rc == 0


def test_cli_mcp_options() -> None:
    from click.testing import CliRunner

    from mcp_gway.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["mcp", "--help"])
    assert result.exit_code == 0
    assert "--log-level" in result.output
    assert "--registry-dir" in result.output
    assert "--host" not in result.output
    assert "--port" not in result.output


@pytest.mark.asyncio
async def test_tools_call_without_id_dropped_no_side_effect(
    adapter: Any, gateway: Any, monkeypatch: Any
) -> None:
    called: list[str] = []
    orig = gateway._handle_method

    def spy(method: str, params: dict[str, Any]) -> Any:
        called.append(method)
        return orig(method, params)

    monkeypatch.setattr(gateway, "_handle_method", spy)
    line = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "listToolFiles", "arguments": {}},
        }
    )
    out = await adapter.handle_line(line)
    assert out is None
    assert called == []


@pytest.mark.asyncio
async def test_request_methods_without_id_dropped(adapter: Any, gateway: Any) -> None:
    for method in ("tools/list", "initialize", "ping", "tools/call"):
        params: dict[str, Any] = (
            {"name": "listToolFiles", "arguments": {}} if method == "tools/call" else {}
        )
        line = json.dumps({"jsonrpc": "2.0", "method": method, "params": params})
        out = await adapter.handle_line(line)
        assert out is None, method


@pytest.mark.asyncio
async def test_id_null_responds_with_null_id(adapter: Any) -> None:
    line = json.dumps({"jsonrpc": "2.0", "id": None, "method": "ping", "params": {}})
    out = await adapter.handle_line(line)
    assert out is not None
    data = json.loads(out)
    assert "id" in data
    assert data["id"] is None


@pytest.mark.asyncio
async def test_missing_method_no_id_returns_none(adapter: Any) -> None:
    out = await adapter.handle_line(json.dumps({"foo": 1}))
    assert out is None


@pytest.mark.asyncio
async def test_missing_method_with_id_returns_invalid_request(adapter: Any) -> None:
    out = await adapter.handle_line(json.dumps({"foo": 1, "id": 7}))
    assert out is not None
    data = json.loads(out)
    assert data["error"]["code"] == -32600
    assert data["id"] == 7
    out_null = await adapter.handle_line(json.dumps({"foo": 1, "id": None}))
    assert out_null is not None
    data_null = json.loads(out_null)
    assert data_null["error"]["code"] == -32600
    assert data_null["id"] is None


@pytest.mark.asyncio
async def test_non_string_method_with_id_returns_invalid_request(adapter: Any) -> None:
    out = await adapter.handle_line(
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": 123})
    )
    assert out is not None
    data = json.loads(out)
    assert data["error"]["code"] == -32600
    assert data["id"] == 3


@pytest.mark.asyncio
async def test_params_list_returns_invalid_params(adapter: Any) -> None:
    line = json.dumps(
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": [1, 2]}
    )
    out = await adapter.handle_line(line)
    assert out is not None
    data = json.loads(out)
    assert data["error"]["code"] == -32602
    assert data["id"] == 5


@pytest.mark.asyncio
async def test_params_string_returns_invalid_params(adapter: Any) -> None:
    line = json.dumps({"jsonrpc": "2.0", "id": 6, "method": "ping", "params": "oops"})
    out = await adapter.handle_line(line)
    assert out is not None
    data = json.loads(out)
    assert data["error"]["code"] == -32602
    assert data["id"] == 6


@pytest.mark.asyncio
async def test_broken_pipe_no_crash(gateway: Any) -> None:
    from mcp_gway.stdio import run_stdio_async

    class BrokenStdout(io.StringIO):
        def write(self, s: str) -> int:
            raise BrokenPipeError(32, "Broken pipe")

    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"
    )
    rc = await run_stdio_async(gateway, stdin, BrokenStdout(), io.StringIO())
    assert rc == 0


def test_setup_logging_uses_stderr() -> None:
    import inspect

    from mcp_gway.observability import logging as obs_logging

    src = inspect.getsource(obs_logging.setup_logging)
    assert "stderr" in src


@pytest.mark.asyncio
async def test_giant_line_without_newline_bounded_parse_error(
    gateway: Any,
) -> None:
    from mcp_gway.stdio import run_stdio_async

    payload = "A" * (2 * 1_048_576)
    stdin = io.StringIO(payload)
    stdout = io.StringIO()
    stderr = io.StringIO()
    rc = await run_stdio_async(gateway, stdin, stdout, stderr)
    assert rc == 0
    lines = [ln for ln in stdout.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["error"]["code"] == -32700
    assert data["jsonrpc"] == "2.0"


@pytest.mark.asyncio
async def test_overlong_line_with_newline_keeps_framing(gateway: Any) -> None:
    from mcp_gway.stdio import run_stdio_async

    big = "B" * (1_048_576 + 100) + "\n"
    ping = json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}) + "\n"
    stdin = io.StringIO(big + ping)
    stdout = io.StringIO()
    rc = await run_stdio_async(gateway, stdin, stdout, io.StringIO())
    assert rc == 0
    lines = [ln for ln in stdout.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["error"]["code"] == -32700
    second = json.loads(lines[1])
    assert second["id"] == 9
    assert second["jsonrpc"] == "2.0"


@pytest.mark.asyncio
async def test_stdout_pure_jsonrpc_invariant(gateway: Any) -> None:
    from mcp_gway.stdio import run_stdio_async

    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        + "\n"
        + "not json\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        + "\n"
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    rc = await run_stdio_async(gateway, stdin, stdout, stderr)
    assert rc == 0
    raw = stdout.getvalue()
    assert raw.strip() != ""
    for ln in raw.splitlines():
        if not ln.strip():
            continue
        data = json.loads(ln)
        assert data.get("jsonrpc") == "2.0"
        assert "result" in data or "error" in data


def test_no_stdout_prints_in_mcp_path() -> None:
    import inspect

    import mcp_gway.cli as cli_mod
    import mcp_gway.stdio as stdio_mod

    stdio_src = inspect.getsource(stdio_mod.run_stdio_async)
    assert "del stderr" not in stdio_src
    for ln in stdio_src.splitlines():
        s = ln.strip()
        if s.startswith("print("):
            assert "file=stderr" in s or "file = stderr" in s, s
    assert "stdout.write" in stdio_src
    mcp_src = inspect.getsource(cli_mod.mcp_cmd.callback)
    assert "err=True" in mcp_src
    assert "run_stdio_async" in mcp_src


def test_stdio_vs_transport_docstrings_crosslinked() -> None:
    import mcp_gway.stdio as stdio_mod
    import mcp_gway.stdio_transport as transport_mod

    assert "server-side" in (stdio_mod.__doc__ or "").lower()
    assert "client-side" in (transport_mod.__doc__ or "").lower()
    assert "stdio_transport" in (stdio_mod.__doc__ or "")
    assert "mcp_gway.stdio" in (transport_mod.__doc__ or "")


@pytest.mark.asyncio
async def test_handle_line_exception_emits_internal_error(
    gateway: Any, monkeypatch: Any
) -> None:
    from mcp_gway import stdio as stdio_mod
    from mcp_gway.stdio import run_stdio_async

    async def _boom(self: Any, raw: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(stdio_mod.StdioAdapter, "handle_line", _boom)
    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 77, "method": "ping"}) + "\n"
    )
    stdout = io.StringIO()
    rc = await run_stdio_async(gateway, stdin, stdout, io.StringIO())
    assert rc == 0
    lines = [ln for ln in stdout.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["error"]["code"] == -32603
    assert data["id"] == 77


@pytest.mark.asyncio
async def test_handle_line_exception_notification_silent(
    gateway: Any, monkeypatch: Any
) -> None:
    from mcp_gway import stdio as stdio_mod
    from mcp_gway.stdio import run_stdio_async

    async def _boom(self: Any, raw: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(stdio_mod.StdioAdapter, "handle_line", _boom)
    stdin = io.StringIO(
        "not json\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        + "\n"
    )
    stdout = io.StringIO()
    rc = await run_stdio_async(gateway, stdin, stdout, io.StringIO())
    assert rc == 0
    assert stdout.getvalue().strip() == ""


@pytest.mark.asyncio
async def test_readline_capped_unexpected_type_clean_exit(
    gateway: Any,
) -> None:
    from mcp_gway.stdio import run_stdio_async

    class BadTypeStdin:
        def read(self, n: int = -1) -> Any:
            return 12345

    stdout = io.StringIO()
    rc = await run_stdio_async(gateway, BadTypeStdin(), stdout, io.StringIO())
    assert rc == 0
    assert stdout.getvalue() == ""


@pytest.mark.asyncio
async def test_handle_post_unknown_method_maps_32601(gateway: Any) -> None:
    body = {"jsonrpc": "2.0", "id": 41, "method": "nope/missing", "params": {}}
    resp = await gateway._handle_post(body, session_id=None)
    assert resp["error"]["code"] == -32601
    assert resp["error"]["message"] == "Method not found"
    assert resp["id"] == 41


@pytest.mark.asyncio
async def test_handle_post_internal_error_sanitized(gateway: Any) -> None:
    def _boom(method: str, params: dict[str, Any]) -> Any:
        raise RuntimeError("super secret internals traceback XYZ")

    gateway._handle_method = _boom  # type: ignore[method-assign]
    resp = await gateway._handle_post(
        {"jsonrpc": "2.0", "id": 42, "method": "ping", "params": {}},
        session_id=None,
    )
    assert resp["error"]["code"] == -32603
    assert resp["error"]["message"] == "Internal error"
    assert "secret" not in json.dumps(resp)
