"""FEAT-006 harden loop — marker 644, strip-env, allow-list case-insensitive."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path


def test_marker_wrong_mode_denied(monkeypatch, tmp_path: Path) -> None:
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


def test_marker_read_capped_no_crash(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy

    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    marker = tmp_path / ".local_unrestricted"
    marker.write_text("not-a-number-" + "x" * 5000)
    monkeypatch.setattr(policy, "marker_path", lambda: marker)
    assert policy.is_unrestricted_active() is False


def test_strip_env_and_allow_list_case_insensitive(monkeypatch) -> None:
    from mcp_gway.core.parsing import parse_envs, parse_headers
    from mcp_gway.core.policy import (
        UnrestrictedStatus,
        check_basename_allowed,
        get_allow_list,
    )

    assert parse_envs([" PATH = x "]) == {"PATH": "x"}
    assert parse_headers([" Authorization = Bearer t "]) == {
        "Authorization": "Bearer t"
    }
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "MyBin, mybin , MYBIN")
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    assert get_allow_list() == {"mybin"}
    monkeypatch.setattr(
        "mcp_gway.core.policy.unrestricted_status",
        lambda now=None: UnrestrictedStatus(
            active=False,
            state="disabled",
            marker_exists=False,
            age_seconds=None,
            expires_in_seconds=None,
        ),
    )
    monkeypatch.setattr(
        "mcp_gway.core.policy.resolve_binary", lambda b: "/usr/bin/mybin"
    )
    d = check_basename_allowed("MYBIN", host_loopback=True)
    assert d.allowed is True
    assert d.reason_code == "allow_list"
