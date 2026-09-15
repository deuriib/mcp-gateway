"""P0-H2 SSE limits tests — must fail before fix (RED). Hermetic."""

from __future__ import annotations

import asyncio

import pytest

from mcp_gway.gateway import Gateway
from mcp_gway.registry import Registry


def test_sse_limit_constants():
    from mcp_gway import gateway as G

    assert getattr(G, "MAX_SESSIONS", None) == 128, "MAX_SESSIONS=128 missing"
    assert getattr(G, "MAX_QUEUE", None) == 32, "MAX_QUEUE=32 missing"
    assert (
        getattr(G, "MAX_IDLE", None) == 300
        or getattr(G, "MAX_IDLE_SECONDS", None) == 300
    ), "MAX_IDLE=300s missing"


def test_session_queue_bounded(tmp_path):
    reg = Registry(servers_dir=tmp_path / "s1")
    gw = Gateway(reg)
    info = gw._create_session("q-test")
    assert info.queue.maxsize == 32, "queue must be bounded MAX_QUEUE=32"
    # cleanup
    gw._sessions.pop("q-test", None)


def test_create_session_full_returns_429(tmp_path):
    import httpx2

    reg = Registry(servers_dir=tmp_path / "s2")
    gw = Gateway(reg)
    # Fill to MAX_SESSIONS
    for i in range(128):
        gw._create_session(f"s-{i}")

    # Next SSE request must be 429 with Retry-After.
    # NOTE: unfixed code hangs forever on SSE stream, so bound with timeout
    # and treat timeout as RED (no 429 enforcement).
    async def _run():
        transport = httpx2.ASGITransport(app=gw.app)
        async with httpx2.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await asyncio.wait_for(c.get("/mcp"), timeout=3.0)
            return r

    try:
        r = asyncio.run(_run())
    except TimeoutError:
        pytest.fail("RED: /mcp hung instead of 429 when full (limit missing)")
        return
    assert r.status_code == 429, f"expected 429 when full, got {r.status_code}"
    assert "retry-after" in {k.lower(): v for k, v in r.headers.items()}, (
        "Retry-After missing"
    )


def test_handle_post_drop_on_full_queue(tmp_path):
    reg = Registry(servers_dir=tmp_path / "s3")
    gw = Gateway(reg)
    # ensure drop metric registered
    gw.metrics.counter("gateway_sse_dropped_total", "dropped", ["reason"])
    info = gw._create_session("full-q")
    # Fill queue
    for _ in range(32):
        info.queue.put_nowait({"x": 1})
    assert info.queue.full()

    # _handle_post must not block; must drop via put_nowait + metric
    async def _run():
        payload = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        # should return quickly, not hang
        resp = await asyncio.wait_for(
            gw._handle_post(payload, session_id="full-q"), timeout=2.0
        )
        return resp

    resp = asyncio.run(_run())
    assert resp["result"] == {}
    # queue still at max, drop counted
    assert info.queue.qsize() <= 32


def test_heartbeat_is_real_reaper(tmp_path):
    import inspect

    from mcp_gway.gateway import Gateway as G

    src = inspect.getsource(G._heartbeat)
    assert "cleanup_expired_sessions" in src, (
        "_heartbeat must call cleanup_expired_sessions"
    )
    assert "sleep" in src and "30" in src, "_heartbeat must sleep 30s"
    # must have aclose/cancel wiring
    gw_src = inspect.getsource(G)
    assert "aclose" in gw_src or "cancel" in gw_src, (
        "heartbeat cancel/aclose wiring missing"
    )
    assert "lifespan" in gw_src.lower() or "_heartbeat_task" in gw_src, (
        "lifespan/task wiring missing"
    )


def test_sse_idle_drops_queue_get(tmp_path):
    import inspect

    from mcp_gway.gateway import Gateway as G

    src = inspect.getsource(G._mcp_sse)
    # event_stream must bound queue.get with timeout (idle disconnect)
    assert "wait_for" in src or "wait-for" in src or "timeout" in src.lower(), (
        "queue.get idle timeout missing"
    )
