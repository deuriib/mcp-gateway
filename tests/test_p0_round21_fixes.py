"""P0 round-2.1 fixes: R1/R2/R3 hermetic regression tests (no real net)."""

from __future__ import annotations

import inspect
import re

_SYNC_VALIDATE_RE = re.compile(r"(?<![a-zA-Z_])validate_url_ssrf\s*\(")


def test_r1_client_else_branch_explicit_http_client() -> None:
    from mcp_gway.core import client as C

    src = inspect.getsource(C._create_remote_transport)
    assert "avalidate_url_ssrf" in src
    assert _SYNC_VALIDATE_RE.search(src) is None, (
        "sync validate blocks loop; use avalidate only"
    )
    assert src.count("http_client=") >= 2
    assert "follow_redirects=False" in src
    assert "SSRF_TIMEOUT" in src


def test_r1_transport_else_branch_explicit_http_client() -> None:
    from mcp_gway.core import transport as T

    src = inspect.getsource(T._try_streamable_http)
    assert "http_client=hc" in src, "else branch must pass explicit http_client"
    assert "follow_redirects=False" in src
    assert "SSRF_TIMEOUT" in src
    gate_src = inspect.getsource(T._ssrf_gate)
    assert "avalidate_url_ssrf" in gate_src


def test_r1_oauth_constructors_no_redirect() -> None:
    from mcp_gway import oauth as O

    src = inspect.getsource(O)
    assert src.count("follow_redirects=False") >= 3, "3 oauth constructors need flag"
    for fn in ("run_oauth_flow", "get_authenticated_client"):
        fsrc = inspect.getsource(getattr(O, fn))
        assert "follow_redirects=False" in fsrc, fn


def test_r1_oauth_async_path_no_sync_validate() -> None:
    from mcp_gway import oauth as O

    for fn in ("discover_oauth_metadata", "run_oauth_flow"):
        fsrc = inspect.getsource(getattr(O, fn))
        assert "avalidate_url_ssrf" in fsrc, f"{fn} must use async gate"
        assert _SYNC_VALIDATE_RE.search(fsrc) is None, (
            f"{fn} must not call sync validate"
        )


def test_r2_pin_locks_weakkey_and_no_id_loop() -> None:
    from mcp_gway import models as M

    # Wave-4: pin lock is process-global (socket.getaddrinfo is process-global;
    # per-loop locks race across threads/loops). Acquired via to_thread.
    assert hasattr(M, "_PIN_THREAD_LOCK")
    assert hasattr(M, "_pinned_dns")
    src = inspect.getsource(M._pinned_dns)
    assert "to_thread" in src, "global lock must not block the event loop"
    src2 = inspect.getsource(M._get_pin_lock)
    assert "id(" not in src2, "integer-keyed map reuse risk"


def test_r2_resolve_and_pin_removed_or_privatized() -> None:
    from mcp_gway import models as M

    assert not hasattr(M, "_resolve_and_pin"), (
        "_resolve_and_pin must be deleted/privatized"
    )
    assert hasattr(M, "_pinned_dns"), "_pinned_dns must remain"


async def test_r3_post_contention_429_with_retry_after(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import httpx2

    from mcp_gway.gateway import Gateway
    from mcp_gway.registry import Registry

    reg = Registry(servers_dir=tmp_path / "r21post")
    gw = Gateway(reg)
    for _ in range(32):
        await gw._post_sem.acquire()
    try:
        transport = httpx2.ASGITransport(app=gw.app)
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            r = await client.post(
                "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}
            )
            assert r.status_code == 429, f"expected 429, got {r.status_code}"
            hdrs = {k.lower(): v for k, v in r.headers.items()}
            assert "retry-after" in hdrs, "Retry-After parity with SSE"
    finally:
        for _ in range(32):
            gw._post_sem.release()


def test_r3_read_outside_semaphore_or_read_timeout() -> None:
    from mcp_gway.gateway import Gateway

    src = inspect.getsource(Gateway._mcp_post)
    assert "_read_limited_json" in src
    assert "wait_for" in src, "bounded slot wait/read required"
    assert "429" in src and "Retry-After" in src
    assert src.index("_read_limited_json") < src.index("_post_sem.acquire"), (
        "body read must be outside semaphore (slow-loris)"
    )


def test_r3_post_constants() -> None:
    from mcp_gway import gateway as G

    assert hasattr(G, "POST_ACQUIRE_TIMEOUT")
    assert hasattr(G, "POST_READ_TIMEOUT")
    assert G.MAX_POST_CONCURRENT == 32
