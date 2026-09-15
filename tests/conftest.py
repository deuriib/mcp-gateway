"""Shared test fixtures."""

from __future__ import annotations

import io
import socket
import sys

import pytest

from mcp_gway.models import MCPServerConfig

_PUBLIC_A = "93.184.216.34"
_PUBLIC_B = "8.8.4.4"
_PRIVATE = "10.0.0.1"


@pytest.fixture(autouse=True)
def _stub_dns_hermetic(monkeypatch: pytest.MonkeyPatch):
    """Hermetic DNS: deterministic only, never touches real network.

    evil/malicious/attacker/private/internal -> private 10.0.0.1 (blocked);
    host-b.example.com -> public 8.8.4.4; every other name -> public
    93.184.216.34. IP literals resolve to themselves. No _real fallback.
    """
    from mcp_gway import models as _M

    if hasattr(_M, "_SSRF_DNS_CACHE"):
        _M._SSRF_DNS_CACHE.clear()  # type: ignore[attr-defined]

    def _fake(
        host: str, port: object, *a: object, **k: object
    ) -> list[tuple[object, object, object, object, object]]:
        h = str(host).lower().rstrip(".")
        try:
            import ipaddress as _ip

            _ip.ip_address(h)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (h, 0))]  # type: ignore[misc]
        except ValueError:
            pass
        if (
            "evil" in h
            or "malicious" in h
            or "attacker" in h
            or "private" in h
            or "internal" in h
        ):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PRIVATE, 0))]  # type: ignore[misc]
        if "host-b" in h:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_B, 0))]  # type: ignore[misc]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_A, 0))]  # type: ignore[misc]

    monkeypatch.setattr(socket, "getaddrinfo", _fake)
    yield
    if hasattr(_M, "_SSRF_DNS_CACHE"):
        _M._SSRF_DNS_CACHE.clear()  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _restore_stderr():
    orig_stderr = sys.__stderr__
    orig_stdout = sys.__stdout__
    # If previous test left wrapped streams, restore
    if isinstance(sys.stderr, io.TextIOWrapper) and hasattr(sys.stderr, "_original_fd"):
        try:
            if getattr(sys.stderr, "_original_fd", -1) == -1:
                sys.stderr = orig_stderr
        except Exception:
            # WHY narrow-broad: stream restore must never fail a test; any
            # error type falls back to the original stderr.
            sys.stderr = orig_stderr
    if isinstance(sys.stdout, io.TextIOWrapper) and hasattr(sys.stdout, "_original_fd"):
        try:
            if getattr(sys.stdout, "_original_fd", -1) == -1:
                sys.stdout = orig_stdout
        except Exception:
            # WHY broad: same restore-must-not-fail rationale as above.
            sys.stdout = orig_stdout
    yield
    if isinstance(sys.stderr, io.TextIOWrapper) and hasattr(sys.stderr, "_original_fd"):
        try:
            if getattr(sys.stderr, "_original_fd", -1) == -1:
                sys.stderr = orig_stderr
        except Exception:
            sys.stderr = orig_stderr
    if isinstance(sys.stdout, io.TextIOWrapper) and hasattr(sys.stdout, "_original_fd"):
        try:
            if getattr(sys.stdout, "_original_fd", -1) == -1:
                sys.stdout = orig_stdout
        except Exception:
            sys.stdout = orig_stdout


@pytest.fixture
def http_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="testserver",
        type="remote",
        url="https://api.example.com/mcp",
    )


@pytest.fixture
def stdio_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="teststdio",
        type="local",
        command=["npx", "hello"],
    )
