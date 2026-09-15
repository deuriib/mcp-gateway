"""Wave-4 P0 Highs — RED-first regression tests (hermetic, no network)."""

from __future__ import annotations

import asyncio
import socket
import threading

import pytest


async def test_transport_headerless_single_pin_no_deadlock(monkeypatch):
    """(1) Headerless streamable-http probe must use a single _pinned_dns (no nested deadlock)."""
    from mcp_gway.core import transport as T

    entries = {"count": 0}
    from mcp_gway import models as _M

    real_pinned = _M._pinned_dns

    import contextlib

    @contextlib.asynccontextmanager
    async def counting_pinned(host, ips):
        entries["count"] += 1
        if entries["count"] > 1:
            raise AssertionError("nested _pinned_dns: deadlock risk")
        # delegate to real implementation without re-entering counter
        async with real_pinned(host, ips):
            yield ips

    monkeypatch.setattr(_M, "_pinned_dns", counting_pinned)

    async def fake_gate(url):
        return "api.example.com"

    monkeypatch.setattr(T, "_ssrf_gate", fake_gate)

    from mcp_gway import models as M

    async def fake_resolve(host, use_cache=False):
        return ["93.184.216.34"]

    monkeypatch.setattr(M, "_aresolve_host_ips", fake_resolve)

    import mcp_gway.models as MM

    monkeypatch.setattr(MM, "_ensure_resolved_ips", lambda ips: None)

    class FakeCM:
        async def __aenter__(self):
            return (None, None)

        async def __aexit__(self, *a):
            return False

    def fake_client(url, http_client=None):
        assert http_client is not None
        return FakeCM()

    import mcp.client.streamable_http as sh

    monkeypatch.setattr(sh, "streamable_http_client", fake_client)

    class FakeHC:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    import httpx2

    monkeypatch.setattr(httpx2, "AsyncClient", FakeHC)

    ok = await asyncio.wait_for(
        T._try_streamable_http("https://api.example.com/mcp"), timeout=5
    )
    assert ok is True
    assert entries["count"] == 1


async def test_oauth_https_only_gate_before_pkce(monkeypatch):
    """(2) OAuth flow must fail-closed on http endpoints with [reason=https_only] before browser."""
    from mcp_gway import oauth as O

    opened = {"called": False}
    monkeypatch.setattr(
        O.webbrowser, "open", lambda url: opened.__setitem__("called", True)
    )

    msgs: list[str] = []
    out = msgs.append
    # http server_url must fail-closed
    res = await O.run_oauth_flow(
        "http://api.example.com/mcp", "srv1", output_callback=out
    )
    assert res is None
    assert opened["called"] is False
    assert any("https_only" in m for m in msgs), msgs


async def test_oauth_token_endpoint_http_blocked(monkeypatch):
    """(2b) http token/auth endpoints must be blocked even when metadata is https-discovered."""
    from mcp_gway import oauth as O

    async def fake_meta(url):
        return {
            "authorization_endpoint": "http://evil.example.com/auth",
            "token_endpoint": "http://evil.example.com/token",
        }

    monkeypatch.setattr(O, "discover_oauth_metadata", fake_meta)
    opened = {"called": False}
    monkeypatch.setattr(
        O.webbrowser, "open", lambda url: opened.__setitem__("called", True)
    )
    msgs: list[str] = []
    res = await O.run_oauth_flow(
        "https://api.example.com/mcp", "srv2", output_callback=msgs.append
    )
    assert res is None
    assert opened["called"] is False
    assert any("https_only" in m for m in msgs), msgs


async def test_ssrf_gate_idn_punycode(monkeypatch):
    """(3) _ssrf_gate must return normalized punycode host, not raw unicode."""
    from mcp_gway import models as M
    from mcp_gway.core.transport import _ssrf_gate

    async def fake_validate(url):
        return None

    monkeypatch.setattr(M, "avalidate_url_ssrf", fake_validate)
    host = await _ssrf_gate("https://münchen.example.com/mcp")
    assert host == "xn--mnchen-3ya.example.com", host
    assert host.isascii()


async def test_client_uses_normalized_host(monkeypatch):
    """(3b) client transport must pin normalized host (no raw unicode to getaddrinfo)."""
    from mcp_gway.core import client as C

    seen: list[str] = []

    async def fake_validate(url):
        return url

    import mcp_gway.models as M

    monkeypatch.setattr(M, "avalidate_url_ssrf", fake_validate)

    async def fake_resolve(host, use_cache=False):
        seen.append(host)
        return ["93.184.216.34"]

    monkeypatch.setattr(M, "_aresolve_host_ips", fake_resolve)
    monkeypatch.setattr(M, "_ensure_resolved_ips", lambda ips: None)

    import contextlib

    @contextlib.asynccontextmanager
    async def fake_pin(host, ips):
        yield ips

    monkeypatch.setattr(M, "_pinned_dns", fake_pin)

    from mcp_gway.models import MCPServerConfig

    cfg = MCPServerConfig.__new__(MCPServerConfig)
    object.__setattr__(cfg, "url", "https://münchen.example.com/mcp")
    object.__setattr__(cfg, "headers", None)
    object.__setattr__(cfg, "resolved_transport", "http")
    object.__setattr__(cfg, "name", "idntest")
    object.__setattr__(cfg, "timeout", 5000)

    from mcp.client import sse

    @contextlib.asynccontextmanager
    async def fake_sse(url, headers=None, httpx_client_factory=None):
        yield (None, None)

    monkeypatch.setattr(sse, "sse_client", fake_sse)
    async with C._create_remote_transport(cfg):
        pass
    assert seen and seen[0] == "xn--mnchen-3ya.example.com", seen


async def test_ssrf_streaming_cap_chunked(monkeypatch):
    """(4) Chunked body without content-length must be capped incrementally (~1MB)."""
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

    class ChunkResp:
        from typing import ClassVar

        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        async def aiter_bytes(self, chunk_size=65536):
            for _ in range(200):  # ~13MB in 64KB chunks
                yield b"x" * 65536

    class FakeClient:
        def __init__(self, *a, **k):
            assert k.get("follow_redirects") is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url, **kw):
            import contextlib

            @contextlib.asynccontextmanager
            async def cm():
                yield ChunkResp()

            return cm()

        async def get(self, url, **kw):
            raise AssertionError("buffered get must not be used for streaming cap")

        async def post(self, url, **kw):
            raise AssertionError("buffered post must not be used for streaming cap")

    monkeypatch.setattr(M.httpx2, "AsyncClient", FakeClient)
    with pytest.raises(ValueError, match="too large"):
        await M.ssrf_get("https://api.example.com/chunked")


async def test_gateway_execute_offloaded(monkeypatch):
    """(5a) executeToolCode must not block the event loop (via to_thread)."""
    import asyncio as _aio

    from mcp_gway.gateway import Gateway
    from mcp_gway.registry import Registry

    gw = Gateway(Registry(servers_dir=__import__("pathlib").Path("servers")))
    calls = {"to_thread": False}
    real_to_thread = _aio.to_thread

    async def spy_to_thread(fn, *a, **k):
        calls["to_thread"] = True
        return await real_to_thread(fn, *a, **k)

    monkeypatch.setattr(_aio, "to_thread", spy_to_thread)
    monkeypatch.setattr(gw.code_mode, "execute_tool_code", lambda code: "ok")
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "executeToolCode", "arguments": {"code": "result=1"}},
    }
    resp = await gw._handle_post(body)
    assert resp["result"]["content"][0]["text"] == "ok"
    assert calls["to_thread"] is True
    await gw.aclose()


def test_codemode_reload_on_registry_change(tmp_path):
    """(5b) CodeMode must see servers added/removed after init."""
    from mcp_gway.code_mode import CodeMode
    from mcp_gway.models import MCPServerConfig
    from mcp_gway.registry import Registry

    reg = Registry(servers_dir=tmp_path / "servers")
    cm = CodeMode(reg)
    assert "No servers" in cm.list_tool_files()
    cfg = MCPServerConfig(name="alpha", type="local", command=["python3", "-m", "x"])
    reg.add(cfg, [])
    assert "alpha" in cm.list_tool_files()
    reg.remove("alpha")
    assert "alpha" not in cm.list_tool_files()


def test_pin_lock_global_across_threads():
    """(5c) Overlapping pins from distinct threads/loops must stay isolated (global lock)."""
    import asyncio as _aio

    from mcp_gway import models as M

    results: dict[str, str] = {}

    def worker(host, ip):
        async def go():
            async with M._pinned_dns(host, [ip]):
                await _aio.sleep(0.05)
                infos = await _aio.to_thread(socket.getaddrinfo, host, 443)
                results[host] = infos[0][4][0]

        _aio.run(go())

    t1 = threading.Thread(target=worker, args=("host-a.example.com", "93.184.216.34"))
    t2 = threading.Thread(target=worker, args=("host-b.example.com", "8.8.4.4"))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert results.get("host-a.example.com") == "93.184.216.34", results
    assert results.get("host-b.example.com") == "8.8.4.4", results


async def test_force_auth_none_fail_closed(monkeypatch):
    """(6) force_auth with no tokens must fail-closed, never pass None to SDK."""
    from mcp_gway import models as M
    from mcp_gway.core import client as C

    async def fake_validate(url):
        return url

    monkeypatch.setattr(M, "avalidate_url_ssrf", fake_validate)

    async def fake_resolve(host, use_cache=False):
        return ["93.184.216.34"]

    monkeypatch.setattr(M, "_aresolve_host_ips", fake_resolve)
    monkeypatch.setattr(M, "_ensure_resolved_ips", lambda ips: None)

    from mcp_gway import oauth as O

    async def no_tokens(name):
        return None

    monkeypatch.setattr(O, "get_authenticated_client", no_tokens)

    cfg = M.MCPServerConfig(
        name="authtest", type="remote", url="https://api.example.com/mcp"
    )
    object.__setattr__(cfg, "resolved_transport", "streamable-http")
    with pytest.raises(
        (PermissionError, ValueError), match="auth|token|login|401|forbidden"
    ):
        async with C._create_remote_transport(cfg, force_auth=True):
            pass


def test_readability_single_security_middleware():
    """(7) Gateway must expose a single security middleware (no dual CSP/Security split)."""
    from mcp_gway import gateway as G

    assert hasattr(G, "_SecurityMiddleware"), "single _SecurityMiddleware missing"
    from pathlib import Path as _P

    src = _P(G.__file__).read_text(encoding="utf-8")
    assert src.count("Content-Security-Policy") <= 2, "CSP set in more than one place"


def test_readability_symlink_helper_dedup():
    """(7b) Symlink-safe atomic write must live in one helper, reused by registry+oauth."""
    import inspect as _in

    from mcp_gway import oauth as O
    from mcp_gway import registry as R

    assert hasattr(R.Registry, "_atomic_write_text")
    # oauth must delegate to shared helper, not duplicate 60-line lstat dance
    src = _in.getsource(O._secure_atomic_write)
    assert (
        "secure_atomic" in src.lower()
        or "secureio" in src.lower()
        or len(src.splitlines()) < 20
    ), "oauth _secure_atomic_write still duplicated"


def test_readability_no_dual_ssrf_constants():
    """(7c) No dual SSRF_* / _SSRF_* literal duplication; canonical SSRF_* is source of truth."""
    import inspect as _in

    from mcp_gway import models as M

    src = _in.getsource(M)
    # _SSRF_* may exist only as aliases to SSRF_*, never as fresh literals
    assert "1_048_576" in src
    assert src.count("1_048_576") == 1, "body-cap literal duplicated"


def test_readability_literal_ip_name():
    """(7d) Literal-IP gate must use bool-honest name (not ensure_* returning bool)."""
    from mcp_gway import models as M

    assert hasattr(M, "_is_public_literal_ip") or hasattr(M, "is_public_literal_ip")
