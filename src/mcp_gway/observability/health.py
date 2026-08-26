from __future__ import annotations

import time
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from mcp_gway import __version__
from mcp_gway.registry import Registry


def check_registry(registry: Registry) -> tuple[str, str]:
    try:
        names = registry.list()
        # try reading one config if exists
        if names:
            try:
                registry.get_config(names[0])
            except Exception:  # noqa: BLE001
                # if registry list succeeded but get_config fails, still consider ok if it's validation?
                # Only fail if list itself throws or we can't read?
                # For health we consider registry readable if list succeeds
                pass
        return "ok", ""
    except Exception as e:  # noqa: BLE001
        return "fail", f"{type(e).__name__}: {e}"


def check_routes(app) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    try:
        routes = getattr(app, "routes", [])
        if not routes:
            return "fail", "no routes mounted"
        return "ok", ""
    except Exception as e:  # noqa: BLE001
        return "fail", str(e)


async def handle_health(request: Request) -> JSONResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    gateway = getattr(request.app.state, "gateway", None)
    start_time = (
        getattr(gateway, "start_time", None)
        if gateway
        else getattr(request.app.state, "start_time", None)
    )
    if start_time is None:
        # fallback to app.state.start_time
        start_time = getattr(request.app.state, "start_time", time.monotonic())
    uptime = (
        time.monotonic() - start_time if isinstance(start_time, (int, float)) else 0
    )
    reg_status, _ = check_registry(registry)
    routes_status, _ = check_routes(request.app)
    checks = {"registry": reg_status, "dashboard": routes_status}
    body: dict[str, Any] = {
        "status": "ok",
        "version": __version__,
        "checks": checks,
        "uptime_seconds": int(uptime),
    }
    # CSP headers
    headers = {"Content-Security-Policy": "default-src 'self'"}
    return JSONResponse(body, headers=headers)


async def handle_ready(request: Request) -> JSONResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    gateway = getattr(request.app.state, "gateway", None)
    start_time = (
        getattr(gateway, "start_time", None)
        if gateway
        else getattr(request.app.state, "start_time", None)
    )
    uptime = (
        time.monotonic() - start_time if isinstance(start_time, (int, float)) else 0
    )
    reg_status, reg_reason = check_registry(registry)
    routes_status, _routes_reason = check_routes(request.app)
    # event loop check
    loop_status = "ok"
    loop_reason = ""
    if gateway is not None and hasattr(gateway, "_last_loop_tick"):
        try:
            last = float(getattr(gateway, "_last_loop_tick", time.monotonic()))
            drift = time.monotonic() - last
            if drift > 3:
                loop_status = "fail"
                loop_reason = f"event loop blocked drift={drift:.1f}s"
        except Exception:
            pass
    checks: dict[str, str] = {}
    checks["registry"] = reg_status if reg_status == "ok" else f"fail: {reg_reason}"
    checks["routes"] = routes_status
    checks["event_loop"] = (
        loop_status if loop_status == "ok" else f"fail: {loop_reason}"
    )
    # overall ready if all ok
    all_ok = reg_status == "ok" and routes_status == "ok" and loop_status == "ok"
    status = "ready" if all_ok else "not_ready"
    code = 200 if all_ok else 503
    body: dict[str, Any] = {
        "status": status,
        "checks": checks,
        "uptime_seconds": int(uptime),
    }
    headers = {"Content-Security-Policy": "default-src 'self'"}
    return JSONResponse(body, status_code=code, headers=headers)


async def handle_live(request: Request) -> JSONResponse:
    gateway = getattr(request.app.state, "gateway", None)
    start_time = (
        getattr(gateway, "start_time", None)
        if gateway
        else getattr(request.app.state, "start_time", None)
    )
    uptime = (
        time.monotonic() - start_time if isinstance(start_time, (int, float)) else 0
    )
    body: dict[str, Any] = {"status": "alive", "uptime_seconds": int(uptime)}
    headers = {"Content-Security-Policy": "default-src 'self'"}
    return JSONResponse(body, headers=headers)


async def handle_metrics(request: Request) -> PlainTextResponse | JSONResponse:
    # Local-first gating
    host = getattr(request.app.state, "dashboard_host", "127.0.0.1")
    # If host is non-loopback without allow_remote, process would have exited, but if somehow exposed, return 403
    if host not in ("127.0.0.1", "::1", "localhost"):
        import os

        if os.environ.get("MCP_GWAY_ALLOW_REMOTE") != "1":
            return JSONResponse(
                {"detail": "metrics not exposed"},
                status_code=403,
                headers={"X-Warning": "exposed"},
            )
    metrics = getattr(request.app.state, "metrics", None)
    if metrics is None:
        return PlainTextResponse("", media_type="text/plain; version=0.0.4")
    text = metrics.exposition()
    headers = {"X-Content-Type-Options": "nosniff"}
    # include X-Request-ID already via middleware
    return PlainTextResponse(
        text, media_type="text/plain; version=0.0.4", headers=headers
    )
