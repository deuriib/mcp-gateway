"""P0 round-2 backend hardening — 8 deterministic hermetic tests (no network)."""

from __future__ import annotations

import asyncio
import socket
from typing import ClassVar, Self

import pytest


def _clear_dns_cache() -> None:
    from mcp_gway import models as M

    if hasattr(M, "_SSRF_DNS_CACHE"):
        M._SSRF_DNS_CACHE.clear()  # type: ignore[attr-defined]


def test_round2_dns_exception_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_gway import models as M

    def _boom(host: str, port: object, *a: object, **k: object) -> list[object]:
        raise socket.gaierror("stub DNS failure")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    _clear_dns_cache()
    with pytest.raises(ValueError, match="dns|resolve|not allowed|blocked|private"):
        M.validate_url_ssrf("https://api.example.com/mcp", use_cache=False)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.com%2Fmcp",
        "https://api.example.com%40evil/mcp",
    ],
)
def test_round2_percent_hosts_blocked(url: str) -> None:
    from mcp_gway import models as M

    _clear_dns_cache()
    with pytest.raises(ValueError, match="encoded|userinfo|not allowed|host"):
        M.validate_url_ssrf(url, use_cache=False)


def test_round2_redirect_encoded_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_gway import models as M

    def _fake_gai(host: str, port: object, *a: object, **k: object) -> list[object]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_gai)
    _clear_dns_cache()

    class _FakeResp:
        def __init__(
            self, status: int = 200, headers: dict[str, str] | None = None
        ) -> None:
            self.status_code = status
            self.headers = headers or {}
            self.content = b"{}"

    class _FakeClient:
        def __init__(self, *a: object, **k: object) -> None:
            assert k.get("follow_redirects") is False

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *a: object) -> bool:
            return False

        async def get(self, url: str, **kw: object) -> _FakeResp:
            if url == "https://api.example.com/start":
                return _FakeResp(302, {"location": "https://api.example.com%2Fevil"})
            return _FakeResp(200, {})

        async def post(self, url: str, **kw: object) -> _FakeResp:
            return _FakeResp(200, {})

    monkeypatch.setattr(M.httpx2, "AsyncClient", _FakeClient)
    with pytest.raises(
        ValueError, match="encoded|private|loopback|not allowed|blocked|redirect|host"
    ):
        asyncio.run(M.ssrf_get("https://api.example.com/start"))


def test_round2_concurrent_129_returns_429(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import httpx2

    from mcp_gway.gateway import Gateway
    from mcp_gway.registry import Registry

    reg = Registry(servers_dir=tmp_path / "r2c")
    gw = Gateway(reg)
    for i in range(128):
        gw._create_session(f"pre-{i}")

    async def _run() -> object:
        transport = httpx2.ASGITransport(app=gw.app)
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            tasks = [client.get("/mcp") for _ in range(5)]
            results = await asyncio.gather(*tasks)
            return results

    results = asyncio.run(_run())  # type: ignore[assignment]
    assert isinstance(results, list)
    statuses = [r.status_code for r in results]  # type: ignore[union-attr]
    assert all(s == 429 for s in statuses), f"expected all 429, got {statuses}"
    assert len(gw._sessions) == 128


def test_round2_empty_resolve_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_gway import models as M

    def _empty(host: str, port: object, *a: object, **k: object) -> list[object]:
        return []

    monkeypatch.setattr(socket, "getaddrinfo", _empty)
    _clear_dns_cache()
    with pytest.raises(ValueError, match="dns|no addresses|not allowed|blocked"):
        M.validate_url_ssrf("https://api.example.com/mcp", use_cache=False)


def test_round2_dns_timeout_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio as _aio

    from mcp_gway import models as M

    async def _slow_to_thread(*a: object, **k: object) -> list[str]:
        await _aio.sleep(5.0)
        return ["93.184.216.34"]

    monkeypatch.setattr(M.asyncio, "to_thread", _slow_to_thread)  # type: ignore[attr-defined]
    monkeypatch.setattr(M, "_SSRF_DNS_TIMEOUT", 0.05)
    with pytest.raises(ValueError, match="dns|timeout|not allowed|blocked"):
        _aio.run(M._aresolve_host_ips("api.example.com", use_cache=False))


def test_round2_helpers_cover_branches() -> None:
    import ipaddress

    from mcp_gway import models as M

    assert M._is_redirect_status(301) is True
    assert M._is_redirect_status(200) is False
    assert M._parse_int_part("") is None
    assert M._parse_int_part("0x10") == 16
    assert M._parse_int_part("010") == 8
    assert M._parse_int_part("09") is None
    assert M._parse_int_part("12") == 12
    assert M._parse_int_part("zz") is None
    assert M._legacy_ipv4_to_canonical("") is None
    assert M._legacy_ipv4_to_canonical("a/b") is None
    assert M._legacy_ipv4_to_canonical("1.2.3.4.5") is None
    assert M._legacy_ipv4_to_canonical("999.0.0.1") is None
    assert M._legacy_ipv4_to_canonical("2130706433") == "127.0.0.1"
    assert M._legacy_ipv4_to_canonical("::1") is None
    assert M._is_blocked_ip(ipaddress.ip_address("8.8.8.8")) is False
    assert M._is_blocked_ip(ipaddress.ip_address("10.0.0.1")) is True
    assert M._is_blocked_ip(ipaddress.ip_address("::")) is True
    assert M._is_blocked_ip(ipaddress.ip_address("::ffff:10.0.0.1")) is True
    with pytest.raises(ValueError, match="encoded|invalid"):
        M._normalize_host("api%2Eexample.com")
    with pytest.raises(ValueError, match="invalid|host"):
        M._normalize_host("a/b")
    assert M._normalize_host("API.Example.COM.") == "api.example.com"
    assert M._normalize_host("münchen.de") == "xn--mnchen-3ya.de"

    class _R:
        def __init__(self, clen: str | None, body: bytes) -> None:
            self.headers = {"content-length": clen} if clen is not None else {}
            self.content = body

    M._check_body_limits(_R(None, b"hi"))
    with pytest.raises(ValueError, match="too large"):
        M._check_body_limits(_R(str(M._SSRF_MAX_BODY + 1), b"hi"))
    with pytest.raises(ValueError, match="too large"):
        M._check_body_limits(_R(None, b"x" * (M._SSRF_MAX_BODY + 1)))
    with pytest.raises(ValueError, match="redirect"):
        M._resolve_redirect_target("https://api.example.com/a", "", 0)
    with pytest.raises(ValueError, match="redirect"):
        M._resolve_redirect_target(
            "https://api.example.com/a",
            "https://api.example.com/b",
            M._SSRF_MAX_REDIRECTS,
        )


def test_round2_pin_ipv6_and_literal_send() -> None:
    import ipaddress

    from mcp_gway import models as M

    with M._pin_host_to_ips("api.example.com", ["93.184.216.34", "::1"]):
        infos = socket.getaddrinfo("api.example.com", 443)
        assert infos, "pinned DNS must return addresses"
    with M._pin_host_to_ips("api.example.com", ["2001:db8::1"]):
        infos6 = socket.getaddrinfo("api.example.com", 443)
        fams = {fam for fam, *_ in infos6}
        assert socket.AF_INET6 in fams
    assert ipaddress.ip_address("8.8.8.8").is_private is False

    class _Resp:
        status_code: ClassVar[int] = 200
        headers: ClassVar[dict[str, str]] = {}
        content: ClassVar[bytes] = b"{}"

    class _Client:
        async def get(self, url: str, **kw: object) -> _Resp:
            return _Resp()

        async def post(self, url: str, **kw: object) -> _Resp:
            return _Resp()

    async def _run() -> None:
        c = _Client()
        r = await M._send_pinned(
            c,  # type: ignore[arg-type]
            "GET",
            "https://93.184.216.34/mcp",
            "93.184.216.34",
            headers=None,
            json_body=None,
            data=None,
        )
        assert r.status_code == 200
        r2 = await M._send_pinned(
            c,  # type: ignore[arg-type]
            "POST",
            "https://93.184.216.34/mcp",
            "93.184.216.34",
            headers=None,
            json_body=None,
            data=None,
        )
        assert r2.status_code == 200

    asyncio.run(_run())
