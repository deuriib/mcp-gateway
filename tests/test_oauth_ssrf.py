"""P0-H1 ssrf_get/post wrapper tests — must fail before fix (RED). Hermetic."""

from __future__ import annotations

from typing import ClassVar

import pytest


def test_ssrf_wrappers_exist():
    from mcp_gway import models as M

    assert hasattr(M, "ssrf_get"), "ssrf_get wrapper missing"
    assert hasattr(M, "ssrf_post"), "ssrf_post wrapper missing"
    assert callable(M.ssrf_get)
    assert callable(M.ssrf_post)


async def test_ssrf_get_https_only():
    from mcp_gway.models import ssrf_get

    with pytest.raises(ValueError, match="https|scheme|not allowed"):
        await ssrf_get("http://api.example.com/mcp")


async def test_ssrf_post_https_only():
    from mcp_gway.models import ssrf_post

    with pytest.raises(ValueError, match="https|scheme|not allowed"):
        await ssrf_post("http://api.example.com/mcp", json={})


async def test_ssrf_get_blocks_private_ip(monkeypatch):
    import socket

    from mcp_gway.models import ssrf_get

    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError, match="private|loopback|not allowed|blocked"):
        await ssrf_get("https://evil.example.com/mcp")


async def test_ssrf_get_manual_redirect_revalidated(monkeypatch):
    """Redirect to private must be blocked; >3 hops rejected. follow_redirects=False."""
    import socket

    from mcp_gway import models as M

    # Stub DNS: public for safe, private for evil
    def fake_getaddrinfo(host, port, *a, **k):
        if "evil" in host or host == "10.0.0.1":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    if hasattr(M, "_SSRF_DNS_CACHE"):
        M._SSRF_DNS_CACHE.clear()

    seen = {}

    class FakeResp:
        def __init__(self, status=302, headers=None, content=b"{}"):
            self.status_code = status
            self.headers = headers or {}
            self.content = content

        def json(self):
            import json as _j

            return _j.loads(self.content.decode() or "{}")

        @property
        def text(self):
            return self.content.decode(errors="replace")

    class FakeClient:
        def __init__(self, *a, **k):
            seen["timeout"] = k.get("timeout")
            seen["follow"] = k.get("follow_redirects")
            assert k.get("follow_redirects") is False, "must be follow_redirects=False"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw):
            assert kw.get("follow_redirects", False) is False
            if url == "https://api.example.com/start":
                return FakeResp(302, {"location": "https://evil.example.com/next"})
            return FakeResp(200, {}, b'{"ok": true}')

        async def post(self, url, **kw):
            return FakeResp(200, {}, b"{}")

        async def aclose(self):
            return None

    monkeypatch.setattr(M.httpx2, "AsyncClient", FakeClient)
    with pytest.raises(
        ValueError, match="private|loopback|not allowed|blocked|redirect"
    ):
        await M.ssrf_get("https://api.example.com/start")


async def test_ssrf_get_enforces_1mb_cap_and_timeout(monkeypatch):
    import socket

    from mcp_gway import models as M

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda h, p, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
        ],
    )
    if hasattr(M, "_SSRF_DNS_CACHE"):
        M._SSRF_DNS_CACHE.clear()

    seen = {}

    class BigResp:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}
        content = b"x" * (1_048_577)

        def json(self):
            return {}

        @property
        def text(self):
            return "big"

    class FakeClient:
        def __init__(self, *a, **k):
            seen["timeout"] = k.get("timeout", None)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw):
            return BigResp()

        async def post(self, url, **kw):
            return BigResp()

        async def aclose(self):
            return None

    monkeypatch.setattr(M.httpx2, "AsyncClient", FakeClient)
    with pytest.raises(ValueError, match="too large|1MB|cap|payload"):
        await M.ssrf_get("https://api.example.com/big")
    assert seen.get("timeout") == 8.0, "timeout must be 8.0"
