"""P0-H1 transport/client SSRF re-validation — must fail before fix (RED). Hermetic."""

from __future__ import annotations

import inspect

import pytest


def test_transport_validates_ssrf():
    from mcp_gway.core import transport as T

    src = inspect.getsource(T.detect_transport) + inspect.getsource(T._try_http)
    assert "validate_url_ssrf" in src, "transport must re-validate URL (SSRF)"


def test_client_validates_ssrf():
    from mcp_gway.core import client as C

    src = inspect.getsource(C._create_remote_transport)
    assert "validate_url_ssrf" in src, "client remote transport must re-validate URL"


async def test_detect_transport_blocks_private_dns(monkeypatch):
    import socket

    from mcp_gway.core.transport import detect_transport
    from mcp_gway.models import MCPServerConfig

    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    cfg = MCPServerConfig.__new__(MCPServerConfig)
    object.__setattr__(cfg, "name", "evil")
    object.__setattr__(cfg, "url", "https://evil.example.com/mcp")
    object.__setattr__(cfg, "timeout", 5000)
    object.__setattr__(cfg, "headers", None)
    with pytest.raises(ValueError, match="private|loopback|not allowed|blocked"):
        await detect_transport(cfg)


async def test_create_remote_transport_blocks_private_dns(monkeypatch):
    import socket

    from mcp_gway.core import client as C

    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    from mcp_gway.models import MCPServerConfig as MC

    bad = MC.__new__(MC)
    object.__setattr__(bad, "name", "evil2")
    object.__setattr__(bad, "type", "remote")
    object.__setattr__(bad, "url", "https://evil.example.com/mcp")
    object.__setattr__(bad, "resolved_transport", "http")
    object.__setattr__(bad, "headers", None)

    async def go():
        async with C.create_client_transport(bad):
            pass

    with pytest.raises(ValueError, match="private|loopback|not allowed|blocked"):
        await go()
