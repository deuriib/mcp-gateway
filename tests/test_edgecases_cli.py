"""Hermetic edge tests: CLI 13 flags + serve guards + local-unrestricted."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from mcp_gway import cli as C
from mcp_gway.models import MCPServerConfig, ToolInfo
from mcp_gway.registry import Registry


def _runner():
    return CliRunner()


def test_resolve_log_level_branches(monkeypatch):
    assert C._resolve_log_level("DEBUG") == "debug"
    monkeypatch.delenv("MCP_GWAY_LOG_LEVEL", raising=False)
    assert C._resolve_log_level(None) == "info"
    monkeypatch.setenv("MCP_GWAY_LOG_LEVEL", "warn")
    assert C._resolve_log_level(None) == "warning"
    monkeypatch.setenv("MCP_GWAY_LOG_LEVEL", "WARN")
    assert C._resolve_log_level(None) == "warning"
    monkeypatch.setenv("MCP_GWAY_LOG_LEVEL", "bogus!!!")
    assert C._resolve_log_level(None) == "info"


def test_serve_stdio_rejects_host_port():
    r = _runner().invoke(
        C.main, ["serve", "--transport", "stdio", "--host", "127.0.0.1"]
    )
    assert r.exit_code == 2
    r = _runner().invoke(C.main, ["serve", "--transport", "stdio", "--port", "8080"])
    assert r.exit_code == 2


def test_serve_http_rejects_non_loopback_without_optin(monkeypatch, tmp_path):
    monkeypatch.delenv("MCP_GWAY_ALLOW_REMOTE", raising=False)
    with patch("uvicorn.run", side_effect=AssertionError("should not bind")) as run:
        r = _runner().invoke(
            C.main,
            [
                "serve",
                "--transport",
                "http",
                "--host",
                "0.0.0.0",
                "--port",
                "18080",
                "--registry-dir",
                str(tmp_path),
            ],
        )
        assert r.exit_code == 2
        assert "MCP_GWAY_ALLOW_REMOTE" in r.output
        run.assert_not_called()


def test_serve_http_guard_direct(monkeypatch, tmp_path):
    monkeypatch.delenv("MCP_GWAY_ALLOW_REMOTE", raising=False)
    with patch("uvicorn.run", side_effect=AssertionError("should not bind")):
        r = _runner().invoke(
            C.main,
            [
                "serve",
                "--transport",
                "http",
                "--host",
                "0.0.0.0",
                "--port",
                "18080",
                "--registry-dir",
                str(tmp_path),
            ],
        )
        assert r.exit_code == 2
        assert "MCP_GWAY_ALLOW_REMOTE" in r.output


def test_serve_http_invalid_registry_dir(tmp_path):
    f = tmp_path / "afile"
    f.write_text("x", encoding="utf-8")
    with patch("uvicorn.run", side_effect=AssertionError("should not bind")):
        r = _runner().invoke(
            C.main,
            [
                "serve",
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                "18081",
                "--registry-dir",
                str(f / "sub"),
            ],
        )
        assert r.exit_code == 2
        assert "reason=" in r.output


def test_add_local_missing_command():
    r = _runner().invoke(C.main, ["add", "x1", "--type", "local"])
    assert r.exit_code == 1


def test_add_local_invalid_syntax():
    with patch("shlex.split", side_effect=ValueError("bad")):
        r = _runner().invoke(
            C.main, ["add", "x1", "--type", "local", "--command", "npx y"]
        )
        assert r.exit_code == 1


def test_add_local_cwd_error():
    r = _runner().invoke(
        C.main,
        [
            "add",
            "x1",
            "--type",
            "local",
            "--command",
            "npx y",
            "--cwd",
            "relative/path",
        ],
    )
    assert r.exit_code == 1


def test_add_local_policy_denied(monkeypatch):
    # Setting env to a value that does NOT include npx causes denial
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "otherbin")
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    with (
        patch("mcp_gway.cli._get_registry") as gr,
        patch("mcp_gway.core.discover_tools", new=AsyncMock(return_value=[])),
    ):
        gr.return_value = MagicMock()
        r = _runner().invoke(
            C.main, ["add", "denyx", "--type", "local", "--command", "npx y"]
        )
        assert r.exit_code == 1


def test_add_remote_missing_url():
    r = _runner().invoke(C.main, ["add", "r1", "--type", "remote"])
    assert r.exit_code == 1


def test_add_remote_ok_hermetic(monkeypatch):
    reg = MagicMock()
    monkeypatch.setattr(C, "_get_registry", lambda: reg)
    monkeypatch.setattr("mcp_gway.cli.detect_transport", AsyncMock(return_value="sse"))
    monkeypatch.setattr(
        "mcp_gway.cli.discover_tools", AsyncMock(return_value=[ToolInfo(name="t")])
    )
    r = _runner().invoke(
        C.main,
        [
            "add",
            "rok",
            "--type",
            "remote",
            "--url",
            "https://api.example.com/mcp",
            "--header",
            "K=V",
            "--tools",
            "t",
        ],
    )
    assert r.exit_code == 0
    assert reg.add.called


def test_add_remote_detect_warn_and_oauth(monkeypatch):
    reg = MagicMock()
    monkeypatch.setattr(C, "_get_registry", lambda: reg)
    monkeypatch.setattr(
        "mcp_gway.cli.detect_transport", AsyncMock(side_effect=RuntimeError("down"))
    )
    monkeypatch.setattr("mcp_gway.cli.discover_tools", AsyncMock(side_effect=[[], []]))
    with patch("mcp_gway.oauth.run_oauth_flow", new=AsyncMock(return_value=None)):
        r = _runner().invoke(
            C.main,
            [
                "add",
                "rwarn",
                "--type",
                "remote",
                "--url",
                "https://api.example.com/mcp",
                "--oauth-client-id",
                "11111111-1111-1111-1111-111111111111",
            ],
        )
        assert r.exit_code == 0


def test_remove_update_inspect_list(monkeypatch, tmp_path):
    reg = Registry(servers_dir=tmp_path / "srv")
    monkeypatch.setattr(C, "_get_registry", lambda: reg)
    r = _runner().invoke(C.main, ["remove", "nosuch"])
    assert r.exit_code == 1
    r = _runner().invoke(C.main, ["update", "nosuch", "--tools", "a,b"])
    assert r.exit_code == 1
    r = _runner().invoke(C.main, ["inspect", "nosuch"])
    assert r.exit_code == 1
    r = _runner().invoke(C.main, ["list"])
    assert "No servers" in r.output
    reg.add(
        MCPServerConfig(name="l1", type="remote", url="https://api.example.com/mcp"),
        [ToolInfo(name="t")],
    )
    r = _runner().invoke(C.main, ["list"])
    assert "l1" in r.output
    r = _runner().invoke(C.main, ["inspect", "l1"])
    assert "t" in r.output
    r = _runner().invoke(C.main, ["update", "l1", "--tools", "a,b"])
    assert r.exit_code == 0
    r = _runner().invoke(C.main, ["remove", "l1"])
    assert r.exit_code == 0


def _seed_refresh_registry(tmp_path):
    reg = Registry(servers_dir=tmp_path / "srv")
    return reg


def test_refresh_empty_registry(monkeypatch, tmp_path):
    reg = _seed_refresh_registry(tmp_path)
    monkeypatch.setattr(C, "_get_registry", lambda: reg)
    r = _runner().invoke(C.main, ["refresh"])
    assert "No servers" in r.output


def test_refresh_disabled_and_missing(monkeypatch, tmp_path):
    reg = _seed_refresh_registry(tmp_path)
    monkeypatch.setattr(C, "_get_registry", lambda: reg)
    reg.add(
        MCPServerConfig(
            name="d1", type="remote", url="https://api.example.com/mcp", enabled=False
        ),
        [],
    )
    r = _runner().invoke(C.main, ["refresh", "d1"])
    assert "disabled" in r.output
    r = _runner().invoke(C.main, ["refresh", "nosuch"])
    assert r.exit_code == 0
    assert "not found" in r.output.lower() or "warning" in r.output.lower()


@pytest.mark.parametrize("tools,expect", [([], 0), ([ToolInfo(name="t")], 0)])
def test_refresh_remote_ok(monkeypatch, tmp_path, tools, expect):
    reg = _seed_refresh_registry(tmp_path)
    monkeypatch.setattr(C, "_get_registry", lambda: reg)
    reg.add(
        MCPServerConfig(name="r2", type="remote", url="https://api.example.com/mcp"), []
    )
    with patch("mcp_gway.cli.refresh_server", new=AsyncMock(return_value=tools)):
        r = _runner().invoke(C.main, ["refresh", "r2"])
        assert r.exit_code == expect


def test_refresh_remote_error_continues(monkeypatch, tmp_path):
    reg = _seed_refresh_registry(tmp_path)
    monkeypatch.setattr(C, "_get_registry", lambda: reg)
    reg.add(
        MCPServerConfig(name="r2", type="remote", url="https://api.example.com/mcp"), []
    )
    with patch(
        "mcp_gway.cli.refresh_server", new=AsyncMock(side_effect=RuntimeError("boom"))
    ):
        r = _runner().invoke(C.main, ["refresh", "r2"])
        assert r.exit_code == 0


def test_refresh_local_denied_continues(monkeypatch, tmp_path):
    reg = _seed_refresh_registry(tmp_path)
    monkeypatch.setattr(C, "_get_registry", lambda: reg)
    # Setting env to a value that does NOT include npx causes denial
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "otherbin")
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    reg.add(MCPServerConfig(name="loc9", type="local", command=["npx", "y"]), [])
    r = _runner().invoke(C.main, ["refresh", "loc9"])
    assert r.exit_code == 0


def test_local_unrestricted_status_enable_disable(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    r = _runner().invoke(C.main, ["local-unrestricted", "status"])
    assert r.exit_code == 0 and "env" in r.output
    r = _runner().invoke(C.main, ["local-unrestricted", "enable"])
    assert r.exit_code == 0 and "marker" in r.output.lower()
    r = _runner().invoke(C.main, ["local-unrestricted", "disable"])
    assert r.exit_code == 0
    r = _runner().invoke(C.main, ["local-unrestricted", "disable"])
    assert "not present" in r.output


def test_mcp_deprecated_alias(tmp_path):
    with patch("mcp_gway.cli._serve_stdio") as m:
        r = _runner().invoke(C.main, ["mcp", "--registry-dir", str(tmp_path)])
        assert "deprecated" in r.output
        assert m.called
