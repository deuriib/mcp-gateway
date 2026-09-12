"""Tests for unified serve (ADR-010): default stdio, transport gate, alias."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from click.testing import CliRunner

import mcp_gway.cli as cli_mod
from mcp_gway.cli import main


def test_serve_unified_default_stdio(monkeypatch: Any) -> None:
    """AC-01: serve defaults to stdio transport."""
    runner = CliRunner()
    help_result = runner.invoke(main, ["serve", "--help"])
    assert help_result.exit_code == 0
    assert "--transport" in help_result.output
    assert "stdio" in help_result.output

    called: dict[str, Any] = {}

    def _fake_stdio(log_level: str | None, registry_dir: str | None) -> None:
        called["log_level"] = log_level
        called["registry_dir"] = registry_dir

    monkeypatch.setattr(cli_mod, "_serve_stdio", _fake_stdio)
    result = runner.invoke(main, ["serve"])
    assert result.exit_code == 0
    assert "log_level" in called


def test_serve_unified_equivalence(monkeypatch: Any) -> None:
    """AC-02: serve --transport stdio ≡ mcp alias (both delegate to _serve_stdio)."""
    runner = CliRunner()
    calls: list[tuple[str | None, str | None]] = []

    def _fake_stdio(log_level: str | None, registry_dir: str | None) -> None:
        calls.append((log_level, registry_dir))

    monkeypatch.setattr(cli_mod, "_serve_stdio", _fake_stdio)
    r1 = runner.invoke(main, ["serve", "--transport", "stdio"])
    assert r1.exit_code == 0
    r2 = runner.invoke(main, ["mcp"])
    assert r2.exit_code == 0
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert "[mcp] deprecated, use serve --transport stdio" in r2.output


def test_serve_unified_transport_option_gate(monkeypatch: Any) -> None:
    """AC-03: --host/--port with stdio → Error + exit 2 (hard error)."""
    runner = CliRunner()

    def _fail_stdio(log_level: str | None, registry_dir: str | None) -> None:
        raise AssertionError("must not reach stdio")

    def _fail_http(
        host: str, port: int, log_level: str | None, registry_dir: str | None
    ) -> None:
        raise AssertionError("must not reach http")

    monkeypatch.setattr(cli_mod, "_serve_stdio", _fail_stdio)
    monkeypatch.setattr(cli_mod, "_serve_http", _fail_http)

    r1 = runner.invoke(main, ["serve", "--transport", "stdio", "--host", "127.0.0.1"])
    assert r1.exit_code == 2
    assert "--host/--port only apply to --transport http|sse" in r1.output

    r2 = runner.invoke(main, ["serve", "--transport", "stdio", "--port", "9000"])
    assert r2.exit_code == 2
    assert "--host/--port only apply to --transport http|sse" in r2.output

    called: dict[str, Any] = {}

    def _ok_http(
        host: str, port: int, log_level: str | None, registry_dir: str | None
    ) -> None:
        called["host"] = host
        called["port"] = port

    monkeypatch.setattr(cli_mod, "_serve_http", _ok_http)
    r3 = runner.invoke(
        main, ["serve", "--transport", "http", "--host", "127.0.0.1", "--port", "9000"]
    )
    assert r3.exit_code == 0
    assert called == {"host": "127.0.0.1", "port": 9000}


def test_serve_unified_local_first_intact(monkeypatch: Any) -> None:
    """AC-04: non-loopback without opt-in → exit 2 legacy text."""
    runner = CliRunner()
    monkeypatch.delenv("MCP_GWAY_ALLOW_REMOTE", raising=False)
    for transport in ("http", "sse"):
        result = runner.invoke(
            main, ["serve", "--transport", transport, "--host", "0.0.0.0"]
        )
        assert result.exit_code == 2
        assert (
            "Error: binding to non-loopback host '0.0.0.0' "
            "requires MCP_GWAY_ALLOW_REMOTE=1" in result.output
        )


def test_serve_unified_http_sse_same_app(monkeypatch: Any) -> None:
    """AC-05: http and sse start the same Gateway.app (no fork)."""
    src = inspect.getsource(cli_mod.serve.callback)
    assert "_serve_http" in src
    http_src = inspect.getsource(cli_mod._serve_http)
    assert "gateway.app" in http_src
    assert "uvicorn.run" in http_src

    runner = CliRunner()
    calls: list[str] = []

    def _fake_http(
        host: str, port: int, log_level: str | None, registry_dir: str | None
    ) -> None:
        calls.append(f"{host}:{port}")

    monkeypatch.setattr(cli_mod, "_serve_http", _fake_http)
    assert runner.invoke(main, ["serve", "--transport", "http"]).exit_code == 0
    assert runner.invoke(main, ["serve", "--transport", "sse"]).exit_code == 0
    assert len(calls) == 2


def test_serve_unified_stdout_pure_ndjson() -> None:
    """AC-06: stdio keeps stdout pure NDJSON (banners only err=True)."""
    src = inspect.getsource(cli_mod._serve_stdio)
    assert "err=True" in src
    assert "run_stdio_async" in src
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("print("):
            assert "err=True" in stripped or "stderr" in stripped, stripped


def test_serve_unified_mcp_alias_deprecated(monkeypatch: Any) -> None:
    """AC-07: mcp is a hidden deprecated alias delegating to _serve_stdio."""
    runner = CliRunner()
    help_out = runner.invoke(main, ["--help"]).output
    assert "mcp" not in help_out

    called: dict[str, Any] = {}

    def _fake_stdio(log_level: str | None, registry_dir: str | None) -> None:
        called["done"] = True

    monkeypatch.setattr(cli_mod, "_serve_stdio", _fake_stdio)
    result = runner.invoke(main, ["mcp"])
    assert result.exit_code == 0
    assert "[mcp] deprecated, use serve --transport stdio" in result.output
    assert called.get("done") is True

    mcp_src = inspect.getsource(cli_mod.mcp_cmd.callback)
    assert "_serve_stdio" in mcp_src
    assert "run_stdio_async" not in mcp_src
    assert "Gateway" not in mcp_src


def test_serve_unified_registry_dir_common(tmp_path: Path, monkeypatch: Any) -> None:
    """AC-08: --registry-dir is a common serve option (stdio + http)."""
    runner = CliRunner()
    assert "--registry-dir" in runner.invoke(main, ["serve", "--help"]).output

    custom = tmp_path / "custom-servers"
    custom.mkdir()

    seen: dict[str, Any] = {}

    async def _fake_run_stdio(
        gateway: Any, stdin: Any, stdout: Any, stderr: Any = None
    ) -> int:
        seen["stdio_dir"] = str(gateway.registry.servers_dir)
        return 0

    monkeypatch.setattr("mcp_gway.stdio.run_stdio_async", _fake_run_stdio)
    result = runner.invoke(
        main, ["serve", "--transport", "stdio", "--registry-dir", str(custom)]
    )
    assert result.exit_code == 0
    assert seen.get("stdio_dir") == str(custom)

    captured: dict[str, Any] = {}
    real_registry = cli_mod.Registry

    class _CaptureRegistry(real_registry):  # type: ignore[misc]
        def __init__(self, servers_dir: Any = None) -> None:
            captured["dir"] = str(servers_dir)
            super().__init__(servers_dir=servers_dir)

    monkeypatch.setattr(cli_mod, "Registry", _CaptureRegistry)
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None, raising=False)
    http_dir = tmp_path / "http-servers"
    http_dir.mkdir()
    result_http = runner.invoke(
        main,
        ["serve", "--transport", "http", "--registry-dir", str(http_dir)],
    )
    assert result_http.exit_code == 0
    assert captured.get("dir") == str(http_dir)


def test_serve_host_without_transport_flag_exits_2(monkeypatch: Any) -> None:
    """serve --host X without --transport → exit 2 (default stdio gate)."""

    def _fail_stdio(log_level: str | None, registry_dir: str | None) -> None:
        raise AssertionError("must not reach stdio")

    def _fail_http(
        host: str, port: int, log_level: str | None, registry_dir: str | None
    ) -> None:
        raise AssertionError("must not reach http")

    monkeypatch.setattr(cli_mod, "_serve_stdio", _fail_stdio)
    monkeypatch.setattr(cli_mod, "_serve_http", _fail_http)
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--host", "127.0.0.1"])
    assert result.exit_code == 2
    assert "--host/--port only apply to --transport http|sse" in result.output


def test_serve_allow_remote_reaches_uvicorn(tmp_path: Path, monkeypatch: Any) -> None:
    """MCP_GWAY_ALLOW_REMOTE=1 + 0.0.0.0 reaches uvicorn (robust mock)."""
    import uvicorn

    assert hasattr(uvicorn, "run")
    captured: dict[str, Any] = {}
    reg_dir = tmp_path / "servers"
    reg_dir.mkdir()

    def _fake_run(*args: Any, **kwargs: Any) -> None:
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setenv("MCP_GWAY_ALLOW_REMOTE", "1")
    monkeypatch.setattr("uvicorn.run", _fake_run)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "serve",
            "--transport",
            "http",
            "--host",
            "0.0.0.0",
            "--registry-dir",
            str(reg_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "args" in captured, "uvicorn.run was not reached (mock not applied?)"
    assert captured["kwargs"].get("host") == "0.0.0.0"


def test_serve_stdio_eof_broken_pipe_exit_zero(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """EOF/BrokenPipe at CLI level → exit 0."""
    reg_dir = tmp_path / "servers"
    reg_dir.mkdir()
    runner = CliRunner()

    async def _raise_eof(*args: Any, **kwargs: Any) -> int:
        raise EOFError("eof")

    monkeypatch.setattr("mcp_gway.stdio.run_stdio_async", _raise_eof)
    r1 = runner.invoke(
        main, ["serve", "--transport", "stdio", "--registry-dir", str(reg_dir)]
    )
    assert r1.exit_code == 0

    async def _raise_broken(*args: Any, **kwargs: Any) -> int:
        raise BrokenPipeError("broken")

    monkeypatch.setattr("mcp_gway.stdio.run_stdio_async", _raise_broken)
    r2 = runner.invoke(
        main, ["serve", "--transport", "stdio", "--registry-dir", str(reg_dir)]
    )
    assert r2.exit_code == 0


def test_serve_stdio_equivalence_with_args(tmp_path: Path, monkeypatch: Any) -> None:
    """serve --transport stdio --log-level debug --registry-dir X ≡ mcp same args."""
    reg_dir = tmp_path / "servers"
    reg_dir.mkdir()
    calls: list[tuple[str | None, str | None]] = []

    def _fake_stdio(log_level: str | None, registry_dir: str | None) -> None:
        calls.append((log_level, registry_dir))

    monkeypatch.setattr(cli_mod, "_serve_stdio", _fake_stdio)
    runner = CliRunner()
    r1 = runner.invoke(
        main,
        [
            "serve",
            "--transport",
            "stdio",
            "--log-level",
            "debug",
            "--registry-dir",
            str(reg_dir),
        ],
    )
    assert r1.exit_code == 0
    r2 = runner.invoke(
        main, ["mcp", "--log-level", "debug", "--registry-dir", str(reg_dir)]
    )
    assert r2.exit_code == 0
    assert len(calls) == 2
    assert calls[0] == calls[1] == ("debug", str(reg_dir))


def test_serve_port_out_of_range_exits_2() -> None:
    """--port outside 1..65535 → exit 2."""
    runner = CliRunner()
    for bad in ("0", "70000", "99999"):
        result = runner.invoke(main, ["serve", "--transport", "http", "--port", bad])
        assert result.exit_code == 2, bad
