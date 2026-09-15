"""Round-2 P0 fixes — RED first (hermetic, deterministic, no real net)."""

from __future__ import annotations

import asyncio
import inspect
import socket

import pytest


def _clear_dns_cache():
    from mcp_gway import models as M

    if hasattr(M, "_SSRF_DNS_CACHE"):
        M._SSRF_DNS_CACHE.clear()


def test_dns_exception_fail_closed(monkeypatch):
    from mcp_gway import models as M

    def boom(host, port, *a, **k):
        raise socket.gaierror("stub DNS failure")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    _clear_dns_cache()
    with pytest.raises(ValueError, match="dns|resolve|not allowed|blocked|private"):
        M.validate_url_ssrf("https://api.example.com/mcp", use_cache=False)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.com%2emalicious.com/mcp",
        "https://api.example.com%2Fevil/mcp",
        "https://evil.com@api.example.com/mcp",
        "https://user:pass@api.example.com/mcp",
    ],
)
def test_encoded_userinfo_hosts_blocked(url):
    from mcp_gway import models as M

    _clear_dns_cache()
    with pytest.raises(ValueError, match="encoded|userinfo|not allowed|host"):
        M.validate_url_ssrf(url, use_cache=False)


def test_async_resolver_off_loop():
    from mcp_gway import models as M

    src = inspect.getsource(M._ssrf_fetch) + inspect.getsource(M)
    assert "to_thread" in src, "getaddrinfo must run via to_thread (non-blocking loop)"


def test_redirect_pinned_socket_revalidated(monkeypatch):
    from mcp_gway import models as M

    def fake_getaddrinfo(host, port, *a, **k):
        if "evil" in host:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    _clear_dns_cache()

    class FakeResp:
        def __init__(self, status=302, headers=None, content=b"{}"):
            self.status_code = status
            self.headers = headers or {}
            self.content = content

        def json(self):
            import json as _j

            return _j.loads(self.content.decode() or "{}")

    class FakeClient:
        def __init__(self, *a, **k):
            assert k.get("follow_redirects") is False

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

    monkeypatch.setattr(M.httpx2, "AsyncClient", FakeClient)
    src = inspect.getsource(M._ssrf_fetch)
    assert "follow_redirects" in src
    with pytest.raises(
        ValueError, match="private|loopback|not allowed|blocked|redirect"
    ):
        asyncio.run(M.ssrf_get("https://api.example.com/start"))


def test_oauth_client_has_timeout():
    from mcp_gway import oauth as O

    src = inspect.getsource(O.get_authenticated_client)
    assert "timeout" in src and ("8" in src or "SSRF_TIMEOUT" in src), (
        "authenticated client must set timeout 8.0 (single-sourced as SSRF_TIMEOUT)"
    )


def test_sse_concurrent_limit_documented(tmp_path):
    from mcp_gway import gateway as G

    assert hasattr(G, "MAX_CONCURRENT_SSE"), "MAX_CONCURRENT_SSE missing"
    src = inspect.getsource(G.Gateway._mcp_sse) + inspect.getsource(G)
    assert "429" in src
    assert "per-process" in src.lower() or "per_process" in src.lower(), (
        "concurrency limit must be documented per-process"
    )


def test_no_exception_sniffing_in_models():
    import pathlib

    src = pathlib.Path("src/mcp_gway/models.py").read_text(encoding="utf-8")
    assert 'if "private" in msg' not in src, "exception message sniffing must go"
    assert "not allowed" not in src or "[reason=" in src, "keep reason tokens only"
