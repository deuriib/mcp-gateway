"""Catalog API handlers."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from mcp_gway.catalog.install import discover_and_persist, entry_to_config, is_duplicate
from mcp_gway.dashboard.catalog.views import (
    catalog_drawer,
    catalog_grid,
    catalog_layout,
    drawer_error,
)

logger = logging.getLogger(__name__)


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _csp_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    base = {
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "script-src-elem 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "style-src-elem 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "font-src 'self' data:"
        )
    }
    if extra:
        base.update(extra)
    return base


def _is_exposed(request: Request) -> bool:
    host = getattr(request.app.state, "dashboard_host", "127.0.0.1")
    return host not in ("127.0.0.1", "::1", "localhost")


def _base_headers(
    request: Request, extra: dict[str, str] | None = None
) -> dict[str, str]:
    h = dict(_csp_headers(extra))
    if _is_exposed(request):
        h["X-Warning"] = "exposed"
    return h


def _toast_oob(msg: str, variant: str = "amber") -> str:
    styles = {
        "red": "bg-red-50 border border-red-200 text-red-800",
        "amber": "bg-amber-50 border border-amber-200 text-amber-800",
        "emerald": "bg-emerald-50 border border-emerald-200 text-emerald-700",
    }
    cls = styles.get(variant, styles["amber"])
    return f"<div id='toast' hx-swap-oob='innerHTML'><div class='{cls} px-4 py-3 rounded-xl text-sm'>{msg}</div></div>"


async def _read_limited_json(
    request: Request, limit: int = 65536
) -> dict[str, Any] | JSONResponse:
    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > limit:
        return JSONResponse({"detail": "payload too large"}, status_code=413)
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            return JSONResponse({"detail": "payload too large"}, status_code=413)
    if not body:
        return {}
    try:
        data = json.loads(body.decode("utf-8"))
        if not isinstance(data, dict):
            return JSONResponse({"detail": "Invalid JSON"}, status_code=400)
        return data
    except Exception:
        return JSONResponse({"detail": "Invalid JSON"}, status_code=400)


async def handle_catalog_list(request: Request) -> JSONResponse | HTMLResponse:
    svc = getattr(request.app.state, "catalog_service", None)
    if svc is None:
        return JSONResponse(
            {"detail": "catalog not configured"},
            status_code=500,
            headers=_base_headers(request),
        )
    q = request.query_params.get("q")
    if q is not None and len(q) > 200:
        return JSONResponse(
            {"detail": "q too long (max 200)"},
            status_code=400,
            headers=_base_headers(request),
        )
    fresh = request.query_params.get("fresh") == "true"
    try:
        entries, meta = await svc.get_entries(q=q, fresh=fresh)
    except ValueError as e:
        if "q too long" in str(e).lower():
            return JSONResponse(
                {"detail": "q too long (max 200)"},
                status_code=400,
                headers=_base_headers(request),
            )
        logger.warning("catalog list failed: %s", e)
        entries, meta = (
            [],
            {
                "fetchedAt": None,
                "ttlSec": 21600,
                "stale": False,
                "total": 0,
                "cache": "MISS",
                "invalid_skipped": 0,
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("catalog list failed: %s", e)
        entries, meta = (
            [],
            {
                "fetchedAt": None,
                "ttlSec": 21600,
                "stale": False,
                "total": 0,
                "cache": "MISS",
                "invalid_skipped": 0,
            },
        )
    toast_msg = None
    toast_variant = "amber"
    if meta.get("cache") == "STALE":
        toast_msg = "Catalog offline - showing cached"
    elif meta.get("cache") == "MISS" and meta.get("total") == 0:
        toast_msg = "No catalog available offline"
    headers: dict[str, str] = dict(_base_headers(request))
    headers["X-Cache"] = str(meta.get("cache", "MISS"))
    if toast_msg:
        headers["X-Toast"] = toast_msg
    if _is_htmx(request):
        path = request.url.path
        if path.startswith("/dashboard"):
            html = str(catalog_grid(entries, q, meta))
            if toast_msg:
                html += _toast_oob(toast_msg, toast_variant)
            return HTMLResponse(html, headers=headers)
        html = str(catalog_grid(entries, q, meta))
        if toast_msg:
            html += _toast_oob(toast_msg, toast_variant)
        return HTMLResponse(html, headers=headers)
    data_entries = []
    for e in entries:
        try:
            d = e.model_dump(mode="json")
            data_entries.append(d)
        except Exception:
            continue
    body: dict[str, Any] = {"entries": data_entries, "meta": meta}
    if toast_msg:
        body["toast"] = toast_msg
    return JSONResponse(body, headers=headers)


async def handle_catalog_page(request: Request) -> HTMLResponse:
    svc = getattr(request.app.state, "catalog_service", None)
    if svc is None:
        return HTMLResponse(
            str(drawer_error("catalog not configured", 500)),
            status_code=500,
            headers=_base_headers(request),
        )
    q = request.query_params.get("q")
    if q is not None and len(q) > 200:
        return HTMLResponse(
            str(drawer_error("q too long (max 200)", 400)),
            status_code=400,
            headers=_base_headers(request),
        )
    fresh = request.query_params.get("fresh") == "true"
    try:
        entries, meta = await svc.get_entries(q=q, fresh=fresh)
    except ValueError as e:
        if "q too long" in str(e).lower():
            return HTMLResponse(
                str(drawer_error("q too long (max 200)", 400)),
                status_code=400,
                headers=_base_headers(request),
            )
        logger.warning("catalog page failed: %s", e)
        entries, meta = (
            [],
            {
                "fetchedAt": None,
                "ttlSec": 21600,
                "stale": False,
                "total": 0,
                "cache": "MISS",
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("catalog page failed: %s", e)
        entries, meta = (
            [],
            {
                "fetchedAt": None,
                "ttlSec": 21600,
                "stale": False,
                "total": 0,
                "cache": "MISS",
            },
        )
    warning = _is_exposed(request)
    headers = dict(_base_headers(request))
    headers["X-Cache"] = str(meta.get("cache", "MISS"))
    toast_msg = None
    if meta.get("cache") == "STALE":
        toast_msg = "Catalog offline - showing cached"
        headers["X-Toast"] = toast_msg
    elif meta.get("cache") == "MISS" and not entries:
        toast_msg = "No catalog available offline"
        headers["X-Toast"] = toast_msg
    if _is_htmx(request):
        html = str(catalog_grid(entries, q, meta))
        if toast_msg:
            html += _toast_oob(toast_msg, "amber")
        return HTMLResponse(html, headers=headers)
    html_content = str(catalog_layout(entries, q, meta, warning_banner=warning))
    if toast_msg:
        html_content = html_content.replace(
            '<div id="toast"></div>',
            f'<div id="toast">{_toast_oob(toast_msg, "amber")}</div>',
            1,
        )
    return HTMLResponse(html_content, headers=headers)


async def handle_catalog_drawer(request: Request) -> HTMLResponse | JSONResponse:
    svc = getattr(request.app.state, "catalog_service", None)
    if svc is None:
        return HTMLResponse(
            str(drawer_error("catalog not configured", 500)),
            status_code=500,
            headers=_base_headers(request),
        )
    cid = request.path_params.get("id") or request.path_params.get("name")
    entry = svc.get_by_id(cid) if cid else None
    warning = _is_exposed(request)
    headers = dict(_base_headers(request))
    if not entry:
        if _is_htmx(request) or request.url.path.startswith("/dashboard"):
            html = str(drawer_error(f"Catalog entry '{cid}' not found", status=404))
            return HTMLResponse(html, status_code=404, headers=headers)
        return JSONResponse(
            {"detail": f"Catalog entry '{cid}' not found"},
            status_code=404,
            headers=headers,
        )
    if _is_htmx(request) or request.url.path.startswith("/dashboard"):
        html = str(catalog_drawer(entry, warning_banner=warning))
        return HTMLResponse(html, headers=headers)
    return JSONResponse(entry.model_dump(mode="json"), headers=headers)


async def handle_catalog_install(request: Request) -> JSONResponse | HTMLResponse:
    svc = getattr(request.app.state, "catalog_service", None)
    registry = getattr(request.app.state, "registry", None)
    if svc is None or registry is None:
        return JSONResponse(
            {"detail": "catalog not configured"},
            status_code=500,
            headers=_base_headers(request),
        )
    cid = request.path_params.get("id")
    entry = svc.get_by_id(cid) if cid else None
    if not entry:
        detail = "Catalog entry not found or not installable"
        if _is_htmx(request):
            return HTMLResponse(
                _toast_oob(detail, "red"),
                status_code=404,
                headers=_base_headers(request),
            )
        return JSONResponse(
            {"detail": detail}, status_code=404, headers=_base_headers(request)
        )
    payload_res = await _read_limited_json(request, limit=65536)
    if isinstance(payload_res, JSONResponse):
        if _is_htmx(request):
            html = _toast_oob(
                payload_res.body.decode()
                if hasattr(payload_res, "body")
                else "payload too large",
                "red",
            )
            return HTMLResponse(
                html,
                status_code=payload_res.status_code,
                headers=_base_headers(request),
            )
        return JSONResponse(
            {"detail": "payload too large"},
            status_code=payload_res.status_code,
            headers=_base_headers(request),
        )
    payload: dict[str, Any] = payload_res
    override_name = payload.get("name")
    timeout = payload.get("timeout")
    if timeout is not None:
        try:
            timeout = int(timeout)
            if timeout < 1000 or timeout > 30000:
                raise ValueError()
        except Exception:
            detail = "timeout must be 1000-30000"
            if _is_htmx(request):
                return HTMLResponse(
                    _toast_oob(detail, "red"),
                    status_code=400,
                    headers=_base_headers(request),
                )
            return JSONResponse(
                {"detail": detail}, status_code=400, headers=_base_headers(request)
            )
    try:
        config = entry_to_config(entry, override_name=override_name, timeout=timeout)
    except PermissionError as e:
        detail = str(e)
        logger.warning("catalog install blocked local without allow id=%s", cid)
        if _is_htmx(request):
            return HTMLResponse(
                _toast_oob(detail, "red"),
                status_code=403,
                headers=_base_headers(request),
            )
        return JSONResponse(
            {"detail": detail}, status_code=403, headers=_base_headers(request)
        )
    except ValueError as e:
        detail = str(e)
        if "invalid name" in detail.lower():
            detail = "invalid name derived from catalog id"
        if "timeout" in detail.lower():
            detail = "timeout must be 1000-30000"
        if _is_htmx(request):
            return HTMLResponse(
                _toast_oob(detail, "red"),
                status_code=400,
                headers=_base_headers(request),
            )
        return JSONResponse(
            {"detail": detail}, status_code=400, headers=_base_headers(request)
        )
    except Exception as e:  # noqa: BLE001
        detail = str(e)
        if _is_htmx(request):
            return HTMLResponse(
                _toast_oob(detail, "red"),
                status_code=400,
                headers=_base_headers(request),
            )
        return JSONResponse(
            {"detail": detail}, status_code=400, headers=_base_headers(request)
        )
    try:
        duplicate = is_duplicate(registry, config)
    except ValueError:
        detail = "invalid request"
        if _is_htmx(request):
            return HTMLResponse(
                _toast_oob(detail, "red"),
                status_code=400,
                headers=_base_headers(request),
            )
        return JSONResponse(
            {"detail": detail, "code": "validation_error"},
            status_code=400,
            headers=_base_headers(request),
        )
    if duplicate:
        detail = f"Server '{config.name}' already exists"
        if _is_htmx(request):
            return HTMLResponse(
                _toast_oob(detail, "red"),
                status_code=409,
                headers=_base_headers(request),
            )
        return JSONResponse(
            {"detail": detail}, status_code=409, headers=_base_headers(request)
        )
    try:
        tools = await discover_and_persist(registry, config)
    except Exception as e:  # noqa: BLE001
        if "saturated" in str(e):
            if _is_htmx(request):
                return HTMLResponse(
                    _toast_oob("service busy, try again", "red"),
                    status_code=503,
                    headers=_base_headers(request),
                )
            return JSONResponse(
                {"detail": "service busy, try again"},
                status_code=503,
                headers=_base_headers(request),
            )
        logger.warning("catalog install persist failed: %s", e)
        if _is_htmx(request):
            return HTMLResponse(
                _toast_oob("Corrupt config", "red"),
                status_code=500,
                headers=_base_headers(request),
            )
        return JSONResponse(
            {"detail": "Corrupt config"},
            status_code=500,
            headers=_base_headers(request),
        )
    tool_count = len(tools or [])
    if _is_htmx(request):
        headers = dict(_base_headers(request))
        toast_msg: str | None = None
        if tool_count == 0:
            if config.type == "remote":
                if config.oauth:
                    toast_msg = (
                        f"No tools discovered -- '{config.name}' saved, OAuth enabled. "
                        "Browser will open for authentication, or run: mcp-gway refresh "
                        f"{config.name} --auth"
                    )
                    headers["X-OAuth-Required"] = "1"
                    headers["X-Server-Name"] = config.name
                else:
                    toast_msg = (
                        f"No tools discovered -- '{config.name}' saved but unreachable (401). "
                        'For PAT add Authorization in Advanced -> Headers {"Authorization": "Bearer <token>"}; '
                        f"for OAuth enable the OAuth check or run: mcp-gway refresh {config.name} --auth"
                    )
            else:
                toast_msg = "No tools discovered -- server saved but unreachable. Check command & logs"
            if toast_msg:
                headers["X-Toast"] = toast_msg
            html = _toast_oob(
                toast_msg or f"Added '{config.name}'",
                "amber" if tool_count == 0 else "emerald",
            )
            return HTMLResponse(html, status_code=201, headers=headers)
        headers["X-Toast"] = f"Added '{config.name}' with {tool_count} tools"
        return HTMLResponse(
            _toast_oob(f"Added '{config.name}' with {tool_count} tools", "emerald"),
            status_code=201,
            headers=headers,
        )
    headers = dict(_base_headers(request))
    if tool_count == 0 and config.oauth:
        headers["X-OAuth-Required"] = "1"
        headers["X-Server-Name"] = config.name
    if (
        tool_count == 0
        and "X-Toast" not in headers
        and "x-toast" not in {k.lower(): v for k, v in headers.items()}
    ):
        headers["X-Toast"] = "No tools discovered"
    return JSONResponse(
        {"name": config.name, "tool_count": tool_count},
        status_code=201,
        headers=headers,
    )


async def handle_catalog_refresh(request: Request) -> JSONResponse | HTMLResponse:
    svc = getattr(request.app.state, "catalog_service", None)
    if svc is None:
        return JSONResponse(
            {"detail": "catalog not configured"},
            status_code=500,
            headers=_base_headers(request),
        )
    if getattr(svc, "_refreshing", False):
        if _is_htmx(request):
            return HTMLResponse(
                _toast_oob("already refreshing", "amber"),
                status_code=409,
                headers=_base_headers(request),
            )
        return JSONResponse(
            {"detail": "already refreshing"},
            status_code=409,
            headers=_base_headers(request),
        )
    refresh_lock = getattr(svc, "_refresh_lock", None)
    if refresh_lock is not None and refresh_lock.locked():
        if _is_htmx(request):
            return HTMLResponse(
                _toast_oob("already refreshing", "amber"),
                status_code=409,
                headers=_base_headers(request),
            )
        return JSONResponse(
            {"detail": "already refreshing"},
            status_code=409,
            headers=_base_headers(request),
        )
    # also check task memo
    task = getattr(svc, "_refresh_task", None)
    if task is not None and not task.done():
        if _is_htmx(request):
            return HTMLResponse(
                _toast_oob("already refreshing", "amber"),
                status_code=409,
                headers=_base_headers(request),
            )
        return JSONResponse(
            {"detail": "already refreshing"},
            status_code=409,
            headers=_base_headers(request),
        )
    try:
        created = asyncio.create_task(svc.refresh_background())
        svc._refresh_task = created  # type: ignore[attr-defined]
    except RuntimeError as e:
        logger.warning("catalog refresh no loop: %s", e)
        try:
            await svc.refresh_background()
        except Exception as ex:
            logger.warning("catalog refresh failed: %s", ex)
    headers = dict(_base_headers(request))
    if _is_htmx(request):
        return JSONResponse({"status": "refreshing"}, status_code=202, headers=headers)
    return JSONResponse({"status": "refreshing"}, status_code=202, headers=headers)
