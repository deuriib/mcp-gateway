"""P0 round-2 verification: lock new SSRF/timeout/semaphore behavior (hermetic)."""

from __future__ import annotations

import asyncio
import inspect
from contextlib import asynccontextmanager
from typing import ClassVar

import pytest


def test_single_source_constants() -> None:
    from mcp_gway import gateway as G
    from mcp_gway import models as M
    from mcp_gway import oauth as O

    assert M.SSRF_TIMEOUT == 8.0
    assert M.SSRF_MAX_BODY == 1_048_576
    assert M.SSRF_IDLE_TIMEOUT == 300.0
    assert M.SSRF_DNS_TIMEOUT == 3.0
    assert M.SSRF_MAX_REDIRECTS == 3
    assert G.MAX_BODY_BYTES == M.SSRF_MAX_BODY
    assert G.MAX_IDLE_SECONDS == M.SSRF_IDLE_TIMEOUT
    assert G.MAX_POST_CONCURRENT == 32
    assert O._OAUTH_HTTP_TIMEOUT == M.SSRF_TIMEOUT
    assert M._ensure_resolved_ips is M._check_resolved_ips
    assert M._ensure_body_limits is M._check_body_limits
    assert M._ensure_literal_ip is M._check_literal_ip


def test_ensure_resolved_zero_parsable_fail_closed() -> None:
    from mcp_gway import models as M

    with pytest.raises(ValueError, match="dns_error"):
        M._ensure_resolved_ips(["not-an-ip", "also-bad"])
    with pytest.raises(ValueError, match="dns_error"):
        M._ensure_resolved_ips([])


async def test_try_http_via_ssrf_port(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from mcp_gway import models as M
    from mcp_gway.core import transport as T

    class _Resp:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}
        content = b"{}"

    class _Client:
        def __init__(self, *a: object, **k: object) -> None:
            assert k.get("follow_redirects") is False

        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *a: object) -> bool:
            return False

        async def post(self, url: str, **kw: object) -> _Resp:
            return _Resp()

        async def get(self, url: str, **kw: object) -> _Resp:
            return _Resp()

    monkeypatch.setattr(M.httpx2, "AsyncClient", _Client)
    assert await T._try_http("https://api.example.com/mcp") is True
    assert await T._try_http("https://evil.example.com/mcp") is False
    assert await T._try_http("http://api.example.com/mcp") is False


async def test_client_streamable_pinned_path(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from unittest.mock import AsyncMock, MagicMock, patch

    from mcp_gway.core import client as C
    from mcp_gway.models import MCPServerConfig

    cfg = MCPServerConfig(
        name="pin1",
        type="remote",
        url="https://api.example.com/mcp",
        resolved_transport="streamable-http",
    )
    with patch("mcp.client.streamable_http.streamable_http_client") as sh:
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        cm.__aexit__ = AsyncMock(return_value=False)
        sh.return_value = cm

        async def go():  # type: ignore[no-untyped-def]
            async with C.create_client_transport(cfg):
                pass

        await go()
        assert sh.called


async def test_client_sse_pinned_path(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from unittest.mock import AsyncMock, MagicMock, patch

    from mcp_gway.core import client as C
    from mcp_gway.models import MCPServerConfig

    cfg = MCPServerConfig(
        name="pin2",
        type="remote",
        url="https://api.example.com/mcp",
        resolved_transport="http",
    )
    with patch("mcp.client.sse.sse_client") as sc:
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        cm.__aexit__ = AsyncMock(return_value=False)
        sc.return_value = cm

        async def go():  # type: ignore[no-untyped-def]
            async with C.create_client_transport(cfg):
                pass

        await go()
        assert sc.called
        _, kwargs = sc.call_args
        assert "httpx_client_factory" in kwargs


async def test_gateway_post_semaphore_and_metric(tmp_path) -> None:
    import httpx2

    from mcp_gway.gateway import Gateway
    from mcp_gway.registry import Registry

    reg = Registry(servers_dir=tmp_path / "postm")
    gw = Gateway(reg)
    assert gw._post_inflight == 0
    transport = httpx2.ASGITransport(app=gw.app)
    async with httpx2.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        r = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}
        )
        assert r.status_code == 200
    assert gw._post_inflight == 0
    names = set()
    try:
        for fam in gw.metrics._families.values():  # type: ignore[attr-defined]
            names.add(fam.name)
    except Exception:
        names = set()
    src = inspect.getsource(Gateway._mcp_post)
    assert "_post_sem" in src and "gateway_post_inflight" in src


async def test_call_tool_async_bounded(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    import mcp_gway.core as core  # noqa: PLR0402 - attribute patch needs module alias
    from mcp_gway.models import MCPServerConfig
    from mcp_gway.registry import Registry
    from mcp_gway.server_factory import ServerFactory

    src = inspect.getsource(ServerFactory._call_tool_async)
    assert "asyncio.timeout" in src

    @asynccontextmanager
    async def _slow(config, **kw):  # type: ignore[no-untyped-def]
        await asyncio.sleep(5.0)
        yield (None, None)

    monkeypatch.setattr(core, "create_client_transport", _slow)
    reg = Registry(servers_dir=tmp_path / "tbo")
    factory = ServerFactory(reg)
    cfg = MCPServerConfig(
        name="slow1", type="remote", url="https://api.example.com/mcp", timeout=100
    )
    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        await factory._call_tool_async(cfg, "tool", {})


async def test_aresolve_redirect_async_bounded(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import socket as _sock

    from mcp_gway import models as M

    def _fake(host: str, port: object, *a: object, **k: object) -> list[object]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(_sock, "getaddrinfo", _fake)
    out = await M._aresolve_redirect_target("https://api.example.com/a", "/b", 0)
    assert out == "https://api.example.com/b"
    with pytest.raises(ValueError, match="redirect"):
        await M._aresolve_redirect_target(
            "https://api.example.com/a", "http://api.example.com/b", 0
        )

    def _evil(host: str, port: object, *a: object, **k: object) -> list[object]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 6, "", ("10.0.0.1", 0))]

    monkeypatch.setattr(_sock, "getaddrinfo", _evil)
    M._SSRF_DNS_CACHE.clear()
    with pytest.raises(ValueError, match="private|not allowed|blocked"):
        await M._aresolve_redirect_target(
            "https://api.example.com/a", "https://evil.example.com/x", 0
        )
