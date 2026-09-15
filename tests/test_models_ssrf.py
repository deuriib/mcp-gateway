"""P0-H1 SSRF hardening tests — must fail before fix (RED). Hermetic, no real net."""

from __future__ import annotations

import pytest

from mcp_gway import models as M


def test_validate_url_ssrf_helper_exists():
    assert hasattr(M, "validate_url_ssrf"), "validate_url_ssrf helper missing"
    assert callable(M.validate_url_ssrf)


def test_numeric_int_bypass_blocked():
    # 2130706433 == 127.0.0.1
    with pytest.raises(ValueError, match="private|loopback|not allowed|ssrf|blocked"):
        M.validate_url_ssrf("http://2130706433/mcp")


def test_hex_bypass_blocked():
    with pytest.raises(ValueError, match="private|loopback|not allowed|ssrf|blocked"):
        M.validate_url_ssrf("http://0x7f.0x0.0x0.0x1/mcp")


def test_octal_bypass_blocked():
    with pytest.raises(ValueError, match="private|loopback|not allowed|ssrf|blocked"):
        M.validate_url_ssrf("http://0177.0.0.1/mcp")


def test_ipv4_mapped_ipv6_blocked():
    with pytest.raises(ValueError, match="private|loopback|not allowed|ssrf|blocked"):
        M.validate_url_ssrf("http://[::ffff:127.0.0.1]/mcp")


def test_localhost_blocked_even_under_pytest():
    # PYTEST_CURRENT_TEST bypass must be gone — localhost always blocked
    with pytest.raises(ValueError, match="private|loopback|not allowed|blocked"):
        M.validate_url_ssrf("http://localhost/mcp")
    with pytest.raises(ValueError, match="private|loopback|not allowed|blocked"):
        M.validate_url_ssrf("http://127.0.0.1/mcp")


def test_dns_rebinding_blocked_via_getaddrinfo(monkeypatch):
    import socket

    def fake_getaddrinfo(host, port, *a, **k):
        if host == "evil.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    # Clear cache if present so stub takes effect
    if hasattr(M, "_SSRF_DNS_CACHE"):
        M._SSRF_DNS_CACHE.clear()
    with pytest.raises(ValueError, match="private|loopback|not allowed|blocked"):
        M.validate_url_ssrf("https://evil.example.com/mcp", use_cache=False)


def test_public_url_allows_with_stubbed_dns(monkeypatch):
    import socket

    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    if hasattr(M, "_SSRF_DNS_CACHE"):
        M._SSRF_DNS_CACHE.clear()
    out = M.validate_url_ssrf("https://api.example.com/mcp", use_cache=False)
    assert out == "https://api.example.com/mcp"


def test_model_rejects_numeric_bypass():
    from mcp_gway.models import MCPServerConfig

    with pytest.raises(ValueError, match="private|loopback|not allowed|blocked|url"):
        MCPServerConfig(name="evil1", type="remote", url="http://2130706433/mcp")


def test_no_pytest_env_branch_in_models():
    import pathlib

    src = pathlib.Path("src/mcp_gway/models.py").read_text(encoding="utf-8")
    assert "PYTEST_CURRENT_TEST" not in src, "test bypass must be removed"
