"""Break-glass marker lifecycle — create/active, missing/expired/mode deny, default-deny."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path


def _patch_marker(monkeypatch, tmp_path: Path):
    from mcp_gway.core import policy

    marker = tmp_path / ".local_unrestricted"
    monkeypatch.setattr(policy, "marker_path", lambda: marker)
    return marker


def test_create_then_active(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy

    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    monkeypatch.delenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", raising=False)
    marker = _patch_marker(monkeypatch, tmp_path)
    created = policy.create_unrestricted_marker()
    assert created == marker
    assert marker.exists()
    assert policy.is_unrestricted_active() is True
    status = policy.unrestricted_status()
    assert status.active is True
    assert status.state == "active"
    assert status.marker_exists is True
    if os.name != "nt":
        assert stat.S_IMODE(marker.stat().st_mode) == 0o600
    decision = policy.check_basename_allowed("anything-valid", host_loopback=True)
    assert decision.allowed is True
    assert decision.reason_code == "unrestricted"


def test_missing_marker_denies_with_hint(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy

    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    monkeypatch.delenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", raising=False)
    _patch_marker(monkeypatch, tmp_path)
    assert policy.is_unrestricted_active() is False
    assert policy.unrestricted_status().state == "marker-missing"
    decision = policy.check_local_command(["mybin"], require_binary=False)
    assert decision.allowed is False
    assert decision.reason_code == "not_allowlisted"
    assert "local-unrestricted enable" in decision.message


def test_expired_marker_denies(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy

    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    monkeypatch.delenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", raising=False)
    _patch_marker(monkeypatch, tmp_path)
    old = time.time() - (72 * 3600 + 60)
    policy.create_unrestricted_marker(now=old)
    assert policy.is_unrestricted_active() is False
    assert policy.unrestricted_status().state == "expired"
    decision = policy.check_local_command(["mybin"], require_binary=False)
    assert decision.allowed is False
    assert decision.reason_code == "not_allowlisted"
    assert "expired" in decision.message


def test_wrong_mode_denies_posix(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy

    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    marker = tmp_path / ".local_unrestricted"
    marker.write_text(str(int(time.time())))
    monkeypatch.setattr(policy, "marker_path", lambda: marker)

    class _FakeStat:
        st_mode = stat.S_IFREG | 0o644

    _orig_stat = Path.stat

    def _fake_stat(self, *args, **kwargs):
        if self == marker:
            return _FakeStat()
        return _orig_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _fake_stat)
    monkeypatch.setattr(os, "name", "posix")
    assert policy.is_unrestricted_active() is False
    assert policy.unrestricted_status().state == "marker-insecure"


def test_default_deny_empty_allow_list(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy

    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "")
    _patch_marker(monkeypatch, tmp_path)
    assert policy.get_allow_list() == set()
    decision = policy.check_local_command(["mybin"], require_binary=False)
    assert decision.allowed is False
    assert decision.reason_code == "not_allowlisted"
    assert "empty" in decision.message


def test_wildcard_invalid_denies(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy

    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "*")
    _patch_marker(monkeypatch, tmp_path)
    assert policy.get_allow_list() == set()
    decision = policy.check_local_command(["mybin"], require_binary=False)
    assert decision.allowed is False
    assert decision.reason_code == "not_allowlisted"


def test_cli_enable_status_disable(monkeypatch, tmp_path: Path) -> None:
    from click.testing import CliRunner

    from mcp_gway.cli import main
    from mcp_gway.core import policy

    marker = tmp_path / ".local_unrestricted"
    monkeypatch.setattr(policy, "marker_path", lambda: marker)
    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    runner = CliRunner()
    result = runner.invoke(main, ["local-unrestricted", "enable"])
    assert result.exit_code == 0, result.output
    assert marker.exists()
    assert policy.is_unrestricted_active() is True
    result = runner.invoke(main, ["local-unrestricted", "status"])
    assert result.exit_code == 0, result.output
    assert "active=True" in result.output
    result = runner.invoke(main, ["local-unrestricted", "disable"])
    assert result.exit_code == 0, result.output
    assert not marker.exists()
    assert policy.is_unrestricted_active() is False


def test_allow_list_fallthrough_when_break_glass_inactive(
    monkeypatch, tmp_path: Path
) -> None:
    from mcp_gway.core import policy

    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "mybin")
    _patch_marker(monkeypatch, tmp_path)
    assert policy.unrestricted_status().state == "marker-missing"
    decision = policy.check_basename_allowed("mybin", host_loopback=True)
    assert decision.allowed is True
    assert decision.reason_code == "allow_list"
    denied = policy.check_basename_allowed("otherbin", host_loopback=True)
    assert denied.allowed is False
    assert denied.reason_code == "not_allowlisted"
    assert "local-unrestricted enable" in denied.message


def test_future_marker_denies(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy

    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    monkeypatch.delenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", raising=False)
    _patch_marker(monkeypatch, tmp_path)
    policy.create_unrestricted_marker(now=time.time() + 3600)
    assert policy.is_unrestricted_active() is False
    assert policy.unrestricted_status().state == "future"
    decision = policy.check_local_command(["mybin"], require_binary=False)
    assert decision.allowed is False
    assert decision.reason_code == "not_allowlisted"
    assert "future" in decision.message
    assert "marker-missing" not in decision.message


def test_invalid_marker_denies(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy

    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    monkeypatch.delenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", raising=False)
    marker = _patch_marker(monkeypatch, tmp_path)
    marker.write_text("not-a-number")
    if os.name != "nt":
        os.chmod(marker, 0o600)
    assert policy.is_unrestricted_active() is False
    assert policy.unrestricted_status().state == "marker-invalid"
    decision = policy.check_local_command(["mybin"], require_binary=False)
    assert decision.allowed is False
    assert decision.reason_code == "not_allowlisted"
    assert "invalid" in decision.message
    assert "marker-invalid" not in decision.message


def test_unreadable_marker_denies(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy

    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    monkeypatch.delenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", raising=False)
    marker = _patch_marker(monkeypatch, tmp_path)
    policy.create_unrestricted_marker()
    _orig_open = Path.open

    def _fake_open(self, *args, **kwargs):
        if self == marker:
            raise OSError("denied")
        return _orig_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _fake_open)
    assert policy.is_unrestricted_active() is False
    assert policy.unrestricted_status().state == "marker-unreadable"
    decision = policy.check_local_command(["mybin"], require_binary=False)
    assert decision.allowed is False
    assert decision.reason_code == "not_allowlisted"
    assert "unreadable" in decision.message
    assert "marker-unreadable" not in decision.message


def test_ttl_boundary_active_then_expired(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy
    from mcp_gway.core.policy import UNRESTRICTED_TTL_SECONDS

    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    monkeypatch.delenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", raising=False)
    _patch_marker(monkeypatch, tmp_path)
    base = 1_700_000_000
    policy.create_unrestricted_marker(now=base)
    at_boundary = policy.unrestricted_status(now=base + UNRESTRICTED_TTL_SECONDS)
    assert at_boundary.active is True
    assert at_boundary.state == "active"
    just_after = policy.unrestricted_status(now=base + UNRESTRICTED_TTL_SECONDS + 1)
    assert just_after.active is False
    assert just_after.state == "expired"


def test_cli_enable_without_env_still_inactive(monkeypatch, tmp_path: Path) -> None:
    from click.testing import CliRunner

    from mcp_gway.cli import main
    from mcp_gway.core import policy

    marker = tmp_path / ".local_unrestricted"
    monkeypatch.setattr(policy, "marker_path", lambda: marker)
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    runner = CliRunner()
    result = runner.invoke(main, ["local-unrestricted", "enable"])
    assert result.exit_code == 0, result.output
    assert marker.exists()
    assert policy.is_unrestricted_active() is False
    assert "still inactive" in result.output
    assert "$env:" in result.output


def test_cli_status_when_disabled(monkeypatch, tmp_path: Path) -> None:
    from click.testing import CliRunner

    from mcp_gway.cli import main
    from mcp_gway.core import policy

    marker = tmp_path / ".local_unrestricted"
    monkeypatch.setattr(policy, "marker_path", lambda: marker)
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    runner = CliRunner()
    result = runner.invoke(main, ["local-unrestricted", "status"])
    assert result.exit_code == 0, result.output
    assert "state=disabled" in result.output
    assert "active=False" in result.output
    assert "unset" in result.output
