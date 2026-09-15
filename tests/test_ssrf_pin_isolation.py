"""SSRF pin isolation: 2 overlapping hosts must not cross-contaminate (hermetic)."""

from __future__ import annotations

import asyncio
import socket
from urllib.parse import urlparse


async def test_pinned_dns_overlapping_hosts_isolated() -> None:
    """Concurrent _pinned_dns pins for A/B must each resolve to their own IP."""
    from mcp_gway import models as M

    seen: dict[str, str] = {}

    async def _fetch(host: str, ip: str) -> None:
        async with M._pinned_dns(host, [ip]):
            await asyncio.sleep(0.05)
            infos = socket.getaddrinfo(host, 443)
            assert infos, "pinned DNS must return addresses"
            seen[host] = infos[0][4][0]

    await asyncio.gather(
        _fetch("host-a.example.com", "93.184.216.34"),
        _fetch("host-b.example.com", "8.8.4.4"),
    )
    assert seen["host-a.example.com"] == "93.184.216.34"
    assert seen["host-b.example.com"] == "8.8.4.4"


async def test_overlapping_ssrf_fetch_isolated(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Concurrent ssrf_get for A/B must connect each URL to its own pinned IP."""
    from mcp_gway import models as M

    observed: dict[str, str] = {}

    class _Resp:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers: dict[str, str] = {}
            self.content = b"{}"

    class _Client:
        def __init__(self, *a: object, **k: object) -> None:
            assert k.get("follow_redirects") is False

        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *a: object) -> bool:
            return False

        async def get(self, url: str, **kw: object) -> _Resp:
            host = urlparse(url).hostname or ""
            infos = socket.getaddrinfo(host, 443)
            await asyncio.sleep(0.05)
            # re-read under pin: with isolation this is still our own IP
            infos2 = socket.getaddrinfo(host, 443)
            observed[url] = infos2[0][4][0]
            assert infos and infos2
            return _Resp()

        async def post(self, url: str, **kw: object) -> _Resp:
            return _Resp()

    monkeypatch.setattr(M.httpx2, "AsyncClient", _Client)
    await asyncio.gather(
        M.ssrf_get("https://host-a.example.com/mcp"),
        M.ssrf_get("https://host-b.example.com/mcp"),
    )
    assert observed["https://host-a.example.com/mcp"] == "93.184.216.34"
    assert observed["https://host-b.example.com/mcp"] == "8.8.4.4"
