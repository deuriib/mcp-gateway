"""Hermetic edge tests: allow-list / break-glass / denylist / cwd / env."""

from __future__ import annotations

import time

import pytest

from mcp_gway.core import policy as P


def test_allow_list_parsing(monkeypatch):
    monkeypatch.setenv(P.ALLOW_LIST_ENV, "npx, uvx , python3")
    assert P.get_allow_list() == {"npx", "uvx", "python3"}
    # Empty string falls back to DEFAULT_ALLOW_LIST
    monkeypatch.setenv(P.ALLOW_LIST_ENV, "")
    assert P.get_allow_list() == {"npx", "bunx", "uvx", "pipx"}
    monkeypatch.setenv(P.ALLOW_LIST_ENV, "*, npx, /bin/x, .., bad!name, a/b\\c")
    assert P.get_allow_list() == {"npx"}
    monkeypatch.setenv(P.ALLOW_LIST_ENV, "Npx")
    assert P.get_allow_list() == {"npx"}


def test_create_and_status_marker(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "config_dir", lambda: tmp_path)
    monkeypatch.setenv(P.UNRESTRICTED_ENV, "1")
    path = P.create_unrestricted_marker(now=time.time())
    assert path.exists()
    st = P.unrestricted_status()
    assert st.active and st.state == "active" and st.marker_exists
    assert P.is_unrestricted_active()
    assert st.expires_in_seconds is not None and st.age_seconds is not None


def test_status_disabled_no_env(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "config_dir", lambda: tmp_path)
    monkeypatch.delenv(P.UNRESTRICTED_ENV, raising=False)
    st = P.unrestricted_status()
    assert st.state == "disabled" and not st.active


def test_status_marker_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "config_dir", lambda: tmp_path / "nomarker")
    monkeypatch.setenv(P.UNRESTRICTED_ENV, "1")
    st = P.unrestricted_status()
    assert st.state == "marker-missing" and not st.active


def test_status_expired_future_invalid(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "config_dir", lambda: tmp_path)
    monkeypatch.setenv(P.UNRESTRICTED_ENV, "1")
    mp = P.marker_path()
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(
        str(int(time.time()) - P.UNRESTRICTED_TTL_SECONDS - 10), encoding="utf-8"
    )
    assert P.unrestricted_status().state == "expired"
    mp.write_text(str(int(time.time()) + 1000), encoding="utf-8")
    assert P.unrestricted_status().state == "future"
    mp.write_text("", encoding="utf-8")
    assert P.unrestricted_status().state == "marker-invalid"
    mp.write_text("notanint", encoding="utf-8")
    assert P.unrestricted_status().state == "marker-invalid"


def test_remove_marker(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "config_dir", lambda: tmp_path)
    assert P.remove_unrestricted_marker() is False
    P.create_unrestricted_marker()
    assert P.remove_unrestricted_marker() is True


@pytest.mark.parametrize(
    "command",
    [
        "notalist",
        [],
        ["a"] * 9,
        ["/bin/npx"],
        ["bad!bin"],
        ["npx", "a" * 81],
        ["npx", "a..b"],
        ["npx", "/"],
        ["npx", "a;b"],
        [123],
        ["npx", 123],
    ],
    ids=[
        "not-a-list",
        "empty",
        "too-many-tokens",
        "path-basename",
        "bad-basename",
        "arg-too-long",
        "dotdot",
        "slash",
        "semicolon",
        "non-string-basename",
        "non-string-arg",
    ],
)
def test_validate_command_syntax_edges(command):
    with pytest.raises(ValueError, match="reason=invalid_syntax"):
        P.validate_command_syntax(command)


def test_validate_command_syntax_ok():
    assert P.validate_command_syntax(["npx", "run"]) == "npx"


def test_check_local_command_branches(monkeypatch):
    d = P.check_local_command(None)
    assert d.reason_code == "invalid_syntax" and not d.allowed
    d = P.check_local_command(["bad!bin"])
    assert d.reason_code == "invalid_syntax"
    monkeypatch.setenv(P.ALLOW_LIST_ENV, "")
    monkeypatch.delenv(P.UNRESTRICTED_ENV, raising=False)
    d = P.check_local_command(["somemissingbinary123"])
    assert not d.allowed and d.reason_code == "not_allowlisted"
    monkeypatch.setenv(P.ALLOW_LIST_ENV, "npx")
    monkeypatch.setattr(P, "resolve_binary", lambda b: None)
    d = P.check_local_command(["npx"], require_binary=True)
    assert d.reason_code == "binary_not_found"
    monkeypatch.setattr(P, "resolve_binary", lambda b: "/usr/bin/npx")
    d = P.check_local_command(["npx"], require_binary=True)
    assert d.allowed is True
    assert d.reason_code == "allow_list"


def test_check_basename_break_glass_details(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "config_dir", lambda: tmp_path)
    monkeypatch.setenv(P.UNRESTRICTED_ENV, "1")
    mp = P.marker_path()
    mp.parent.mkdir(parents=True, exist_ok=True)
    for content in ["", "xx"]:
        mp.write_text(content, encoding="utf-8")
        d = P.check_basename_allowed("whatever", host_loopback=True)
        assert d.allowed is False
        assert d.reason_code == "not_allowlisted"
    monkeypatch.setenv(P.ALLOW_LIST_ENV, "okbin")
    monkeypatch.setattr(P, "resolve_binary", lambda b: "/x/okbin")
    d = P.check_basename_allowed("okbin", host_loopback=True)
    assert d.allowed is True
    assert d.reason_code == "allow_list"


def test_check_cwd_edges(tmp_path):
    assert P.check_cwd(None) is None
    with pytest.raises(ValueError, match="reason=invalid_cwd"):
        P.check_cwd("")
    with pytest.raises(ValueError, match="reason=invalid_cwd"):
        P.check_cwd("relative/path")
    with pytest.raises(ValueError, match="reason=invalid_cwd"):
        P.check_cwd("/nonexistent-dir-xyz-123")
    out = P.check_cwd(str(tmp_path))
    assert out is not None


def test_check_environment_denylist():
    assert P.check_environment(None) is None
    with pytest.raises(ValueError, match="reason=denied_env"):
        P.check_environment({"PATH": "x"})
    with pytest.raises(ValueError, match="reason=denied_env"):
        P.check_environment({"LD_PRELOAD": "x"})
    with pytest.raises(ValueError, match="reason=denied_env"):
        P.check_environment({"DYLD_FOO": "x"})
    with pytest.raises(ValueError, match="reason=denied_env"):
        P.check_environment({"NPM_CONFIG_X": "x"})
    with pytest.raises(ValueError, match="reason=denied_env"):
        P.check_environment({"BUN_INSTALL": "x"})
    with pytest.raises(ValueError, match="reason=denied_env"):
        P.check_environment({"UV_CACHE": "x"})
    with pytest.raises(ValueError, match="reason=invalid_env"):
        P.check_environment("notadict")
    assert P.check_environment({"NODE_ENV": "prod", "MY_VAR": "1"}) == {
        "NODE_ENV": "prod",
        "MY_VAR": "1",
    }


def test_audit_does_not_raise():
    P.audit_local_action(
        "act", "na/me..", "bin;name", P.PolicyDecision(True, "allow_list", "ok")
    )
    assert P._break_glass_detail(
        P.UnrestrictedStatus(False, "marker-missing", False, None, None)
    ).startswith("break-glass marker missing")
    assert "expired" in P._break_glass_detail(
        P.UnrestrictedStatus(False, "expired", True, 1.0, None)
    )
    assert "future" in P._break_glass_detail(
        P.UnrestrictedStatus(False, "future", True, -1.0, None)
    )
    assert "insecure" in P._break_glass_detail(
        P.UnrestrictedStatus(False, "marker-insecure", True, None, None)
    )
    assert "unreadable" in P._break_glass_detail(
        P.UnrestrictedStatus(False, "marker-unreadable", True, None, None)
    )
    assert "invalid" in P._break_glass_detail(
        P.UnrestrictedStatus(False, "marker-invalid", True, None, None)
    )
    assert "status" in P._break_glass_detail(
        P.UnrestrictedStatus(False, "disabled", False, None, None)
    )
    assert P.resolve_binary("definitely-not-a-real-binary-xyz") is None
