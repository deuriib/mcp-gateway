"""JSON handlers for dashboard API."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
import shlex
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from mcp_gway.dashboard.views import drawer_error, layout, server_drawer, server_table
from mcp_gway.models import MCPServerConfig, OAuthConfig
from mcp_gway.registry import Registry

logger = logging.getLogger(__name__)

MAX_PAYLOAD_SIZE = 1_048_576
MAX_SMALL_PAYLOAD = 65536
_discovery_sem = asyncio.Semaphore(3)
_reveal_attempts: dict[str, list[float]] = {}


async def _maybe_detect_transport(config: MCPServerConfig) -> None:
    if config.type != "remote" or not config.url:
        return
    if config.resolved_transport:
        return
    try:
        from mcp_gway.core import detect_transport

        timeout = (config.timeout / 1000 + 2) if config.timeout else 7
        detected = await asyncio.wait_for(detect_transport(config), timeout=timeout)
        config.resolved_transport = detected  # type: ignore[assignment]
        logger.info("detected transport %s for %s", detected, config.name)
    except Exception as e:  # noqa: BLE001
        logger.debug("transport detection failed for %s: %s", config.name, e)


def _e(s: str) -> str:
    return html.escape(s, quote=True)


def _toast_oob(msg: str, variant: str = "red") -> str:
    styles = {
        "red": "bg-red-50 border border-red-200 text-red-800",
        "amber": "bg-amber-50 border border-amber-200 text-amber-800",
        "yellow": "bg-amber-50 border border-amber-200 text-amber-800",
    }
    cls = styles.get(variant, styles["red"])
    return f"<div id='toast' hx-swap-oob='innerHTML'><div class='{cls} px-4 py-3 rounded-xl shadow-sm text-sm' role='alert'>{_e(msg)}</div></div>"


def _is_htmx_request(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _is_hx(request: Request) -> bool:
    return _is_htmx_request(request)


def _mask_dict(data: dict[str, str] | None) -> dict[str, str] | None:
    if data is None:
        return None
    return {k: "***" for k in data}


def _mask_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
    return _mask_dict(headers)


def _mask_environment(env: dict[str, str] | None) -> dict[str, str] | None:
    return _mask_dict(env)


def _mask_oauth(oauth: OAuthConfig | bool | dict[str, Any] | None) -> Any:
    if oauth is None:
        return None
    if isinstance(oauth, bool):
        return oauth
    if isinstance(oauth, dict):
        masked = dict(oauth)
        if masked.get("clientSecret"):
            masked["clientSecret"] = "***"
        if masked.get("client_secret"):
            masked["client_secret"] = "***"
        return masked
    if isinstance(oauth, OAuthConfig):
        data = oauth.model_dump()
        if data.get("clientSecret"):
            data["clientSecret"] = "***"
        return data
    return "***"


def _tool_count_for(registry: Registry, name: str) -> int:
    try:
        content = registry.read_pyi(name)
        return content.count("def ")
    except Exception:  # noqa: BLE001
        return 0


def _server_to_dict(registry: Registry, name: str) -> dict[str, Any] | None:
    try:
        cfg = registry.get_config(name)
    except json.JSONDecodeError:
        raise
    except Exception as e:
        if "Expecting" in str(e) or "JSON" in str(e):
            raise json.JSONDecodeError(str(e), "", 0) from e
        raise
    tool_count = _tool_count_for(registry, name)
    result: dict[str, Any] = {
        "name": cfg.name,
        "type": cfg.type,
        "enabled": cfg.enabled,
        "timeout": cfg.timeout,
        "tool_count": tool_count,
    }
    if cfg.type == "remote":
        result["url"] = cfg.url
        if cfg.headers:
            result["headers"] = _mask_dict(cfg.headers)
        if cfg.oauth is not None:
            result["oauth"] = _mask_oauth(cfg.oauth)
        if cfg.resolved_transport:
            result["resolved_transport"] = cfg.resolved_transport
    else:
        result["command"] = cfg.command
        if cfg.cwd:
            result["cwd"] = cfg.cwd
        if cfg.environment:
            result["environment"] = _mask_dict(cfg.environment)
    return result


def _collect_servers(registry: Registry) -> list[dict[str, Any]]:
    servers: list[dict[str, Any]] = []
    for name in registry.list():
        try:
            d = _server_to_dict(registry, name)
            if d:
                servers.append(d)
        except json.JSONDecodeError:  # noqa: S110
            continue
        except Exception:  # noqa: BLE001, S112
            continue
    return servers


async def _read_limited_body(request: Request, limit: int) -> bytes | JSONResponse:
    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > limit:
        return JSONResponse({"detail": "payload too large"}, status_code=413)
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            return JSONResponse({"detail": "payload too large"}, status_code=413)
    return body


def _csp_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    base = {
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
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


def _stats_oob(registry: Registry) -> str:
    try:
        from mcp_gway.dashboard.views import (
            _stats as _render_stats,  # type: ignore[attr-defined]
        )

        servers = _collect_servers(registry)
        html_stats = str(_render_stats(servers))
        return f"<div id='dashboard-stats' hx-swap-oob='outerHTML'>{html_stats}</div>"
    except Exception:
        return ""


def _table_with_oob(
    registry: Registry,
    toast_msg: str | None = None,
    toast_variant: str = "red",
    close_dialog: bool = False,
) -> str:
    servers = _collect_servers(registry)
    table_html = str(server_table(servers))
    oob = _stats_oob(registry)
    toast_oob = _toast_oob(toast_msg, toast_variant) if toast_msg else ""
    dialog_oob = (
        "<div id='server-dialog' hx-swap-oob='innerHTML'></div>" if close_dialog else ""
    )
    return f"{table_html}{oob}{toast_oob}{dialog_oob}"


def _table_oob(registry: Registry) -> str:
    try:
        servers = _collect_servers(registry)
        html = str(server_table(servers))
        if 'id="server-table-body"' in html:
            html = html.replace(
                'id="server-table-body"',
                'id="server-table-body" hx-swap-oob="outerHTML"',
                1,
            )
        elif "id='server-table-body'" in html:
            html = html.replace(
                "id='server-table-body'",
                "id='server-table-body' hx-swap-oob='outerHTML'",
                1,
            )
        return html
    except Exception:
        return ""


def _drawer_feedback_html(msg: str, variant: str = "slate") -> str:
    colors = {
        "slate": "bg-slate-50 border border-slate-200 text-slate-700",
        "amber": "bg-amber-50 border border-amber-200 text-amber-800",
        "emerald": "bg-emerald-50 border border-emerald-200 text-emerald-700",
        "red": "bg-red-50 border border-red-200 text-red-800",
    }
    cls = colors.get(variant, colors["slate"])
    return f"<div class='{cls} px-3 py-2 rounded-xl text-xs'>{_e(msg)}</div>"


async def handle_dashboard(request: Request) -> HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    host = getattr(request.app.state, "dashboard_host", "127.0.0.1")
    warning = host not in ("127.0.0.1", "::1", "localhost")
    servers = _collect_servers(registry)
    html_content = str(layout(servers, warning_banner=warning))
    headers: dict[str, str] = dict(_csp_headers())
    if warning:
        headers["X-Warning"] = "exposed"
    return HTMLResponse(html_content, headers=headers)


async def handle_dashboard_servers(request: Request) -> HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    servers = _collect_servers(registry)
    html_content = str(server_table(servers))
    # include stats OOB so cards stay synced on polling
    stats_oob = _stats_oob(registry)
    full = f"{html_content}{stats_oob}"
    return HTMLResponse(full, headers=_csp_headers())


def _detail_error(e: Exception, name: str) -> HTMLResponse:
    if isinstance(e, json.JSONDecodeError):
        return HTMLResponse(
            str(drawer_error("Corrupt config, remove and re-add", status=500)),
            status_code=500,
            headers=_csp_headers(),
        )
    if isinstance(e, ValueError):
        return HTMLResponse(
            str(drawer_error("invalid request", status=400)),
            status_code=400,
            headers=_csp_headers(),
        )
    if isinstance(e, FileNotFoundError):
        return HTMLResponse(
            str(drawer_error(f"Server '{_e(name)}' not found", status=404)),
            status_code=404,
            headers=_csp_headers(),
        )
    msg = str(e)
    if "Corrupt" in msg or "Expecting" in msg or "JSON" in msg:
        return HTMLResponse(
            str(drawer_error("Corrupt config, remove and re-add", status=500)),
            status_code=500,
            headers=_csp_headers(),
        )
    logger.warning(
        "handle_dashboard_server_detail error for %s: %s",
        re.sub(r"[^A-Za-z0-9_.-]", "_", name),
        type(e).__name__,
    )
    return HTMLResponse(
        str(drawer_error("Corrupt config, remove and re-add", status=500)),
        status_code=500,
        headers=_csp_headers(),
    )


async def handle_dashboard_server_detail(request: Request) -> HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    host = getattr(request.app.state, "dashboard_host", "127.0.0.1")
    warning = host not in ("127.0.0.1", "::1", "localhost")
    try:
        server_dict = _server_to_dict(registry, name)
        if server_dict is None:
            return HTMLResponse(
                str(drawer_error(f"Server '{_e(name)}' not found", status=404)),
                status_code=404,
                headers=_csp_headers(),
            )
    except Exception as e:  # noqa: BLE001
        return _detail_error(e, name)
    try:
        pyi = registry.read_pyi(name)
        truncated = len(pyi) > 50000
        pyi_content = pyi[:50000]
    except Exception:  # noqa: BLE001, S110
        pyi_content = ""
        truncated = False
    html_content = str(
        server_drawer(server_dict, pyi_content, truncated, warning_banner=warning)
    )
    headers = _csp_headers()
    if warning:
        headers["X-Warning"] = "exposed"
    return HTMLResponse(html_content, headers=headers)


async def handle_dashboard_close(request: Request) -> HTMLResponse:
    return HTMLResponse("", headers=_csp_headers())


async def handle_list(request: Request) -> JSONResponse | HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    servers = _collect_servers(registry)
    if _is_htmx_request(request):
        html_content = str(server_table(servers))
        stats_oob = _stats_oob(registry)
        full = f"{html_content}{stats_oob}"
        return HTMLResponse(full, headers=_csp_headers())
    return JSONResponse(servers, headers=_csp_headers())


async def handle_get(request: Request) -> JSONResponse | HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    try:
        data = _server_to_dict(registry, name)
        if data is None:
            return JSONResponse(
                {"detail": f"Server '{_e(name)}' not found"}, status_code=404
            )
    except json.JSONDecodeError:
        return JSONResponse(
            {"detail": "Corrupt config, remove and re-add"}, status_code=500
        )
    except ValueError:
        return JSONResponse(
            {"detail": "invalid request", "code": "validation_error"}, status_code=400
        )
    except FileNotFoundError:
        return JSONResponse(
            {"detail": f"Server '{_e(name)}' not found"}, status_code=404
        )
    except Exception as e:
        msg = str(e)
        if "Corrupt" in msg or "Expecting" in msg or "JSON" in msg:
            return JSONResponse(
                {"detail": "Corrupt config, remove and re-add"}, status_code=500
            )
        logger.warning(
            "handle_get error for %s: %s",
            re.sub(r"[^A-Za-z0-9_.-]", "_", name),
            type(e).__name__,
        )
        return JSONResponse(
            {"detail": "Corrupt config, remove and re-add"}, status_code=500
        )
    try:
        pyi = registry.read_pyi(name)
        data["truncated"] = len(pyi) > 50000
        data["pyi_content"] = pyi[:50000]
    except Exception:  # noqa: BLE001, S110
        data["truncated"] = False
        data["pyi_content"] = ""
    if _is_htmx_request(request):
        html_content = (
            f"<div id='server-detail'><pre>{_e(json.dumps(data, indent=2))}</pre></div>"
        )
        return HTMLResponse(html_content, headers=_csp_headers())
    return JSONResponse(data, headers=_csp_headers())


def _check_payload_size(request: Request) -> JSONResponse | HTMLResponse | None:
    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > MAX_PAYLOAD_SIZE:
        if _is_htmx_request(request):
            return HTMLResponse(
                _toast_oob("payload too large"),
                status_code=413,
            )
        return JSONResponse({"detail": "payload too large"}, status_code=413)
    return None


async def _parse_json_body(
    request: Request,
) -> dict[str, Any] | JSONResponse | HTMLResponse:
    body = await _read_limited_body(request, MAX_PAYLOAD_SIZE)
    if isinstance(body, JSONResponse):
        return body
    try:
        payload = json.loads(body.decode("utf-8") if body else "{}")
        if not isinstance(payload, dict):
            raise TypeError("payload must be object")
        return payload
    except Exception:  # noqa: BLE001
        if _is_htmx_request(request):
            return HTMLResponse(
                _toast_oob("Invalid JSON"),
                status_code=400,
            )
        return JSONResponse({"detail": "Invalid JSON"}, status_code=400)


def _coerce_form_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("headers", "environment"):
        val = payload.get(key)
        if isinstance(val, str):
            if not val.strip():
                payload.pop(key, None)
                continue
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    payload[key] = parsed
            except Exception:  # noqa: BLE001, S110
                pass
    for key in ("url", "cwd"):
        val = payload.get(key)
        if isinstance(val, str) and not val.strip():
            payload.pop(key, None)
    if "timeout" in payload and isinstance(payload["timeout"], str):
        try:
            payload["timeout"] = int(payload["timeout"])
        except Exception:  # noqa: BLE001, S110
            pass
    if "enabled" in payload and isinstance(payload["enabled"], str):
        v = payload["enabled"].lower()
        if v in ("true", "1", "on", "yes"):
            payload["enabled"] = True
        elif v in ("false", "0", "off", "no"):
            payload["enabled"] = False
    if "command" in payload and isinstance(payload["command"], str):
        val = payload["command"].strip()
        if not val:
            payload.pop("command", None)
        elif val.startswith("["):
            try:
                parsed_cmd = json.loads(val)
                if isinstance(parsed_cmd, list):
                    payload["command"] = parsed_cmd
                else:
                    payload["command"] = shlex.split(val)
            except Exception:  # noqa: BLE001, S110
                try:
                    payload["command"] = shlex.split(val)
                except Exception:  # noqa: BLE001, S110
                    pass
        else:
            try:
                parts = shlex.split(val)
                if parts:
                    payload["command"] = parts
            except Exception:  # noqa: BLE001, S110
                pass
    is_oauth = False
    oauth_flag = payload.get(
        "oauth_enabled", payload.get("use_oauth", payload.get("oauth"))
    )
    if isinstance(oauth_flag, bool):
        is_oauth = oauth_flag
    elif isinstance(oauth_flag, str):
        is_oauth = oauth_flag.lower() in ("true", "1", "on", "yes")
    elif oauth_flag is not None:
        is_oauth = bool(oauth_flag)
    if is_oauth:
        scope_val = payload.get("oauth_scope") or payload.get("scope")
        oauth_cfg: dict[str, Any] = {}
        if isinstance(scope_val, str) and scope_val.strip():
            oauth_cfg["scope"] = scope_val.strip()
        cid = payload.get("oauth_client_id") or payload.get("clientId")
        if isinstance(cid, str) and cid.strip():
            try:
                uuid.UUID(cid.strip())
                oauth_cfg["clientId"] = cid.strip()
            except Exception:
                oauth_cfg["clientId"] = str(uuid.uuid4())
        else:
            oauth_cfg["clientId"] = str(uuid.uuid4())
        csec = payload.get("oauth_client_secret") or payload.get("clientSecret")
        if isinstance(csec, str) and csec.strip():
            oauth_cfg["clientSecret"] = csec.strip()
        payload["oauth"] = oauth_cfg
    else:
        if "oauth" in payload and isinstance(payload["oauth"], str):
            v = payload["oauth"].lower()
            if v in ("false", "0", "off", "no"):
                payload.pop("oauth", None)
    for k in (
        "oauth_enabled",
        "use_oauth",
        "oauth_scope",
        "oauth_client_id",
        "oauth_client_secret",
        "scope",
    ):
        if k in payload and k != "oauth":
            payload.pop(k, None)
    return payload


def _parse_urlencoded_bytes(body: bytes) -> dict[str, Any]:
    """Parse application/x-www-form-urlencoded bytes pure without Starlette."""
    text = body.decode("utf-8", errors="strict")
    qs = urllib.parse.parse_qs(text, keep_blank_values=True)
    return {k: v[0] if len(v) == 1 else v for k, v in qs.items()}


def _parse_multipart_bytes(body: bytes, boundary: str) -> dict[str, Any]:
    """Parse multipart/form-data bytes manually without calling request.form()."""
    boundary_b = boundary.encode()
    delimiter = b"--" + boundary_b
    parts = body.split(delimiter)
    payload: dict[str, Any] = {}
    for raw in parts[1:]:
        if raw.startswith(b"\r\n"):
            raw = raw[2:]
        elif raw.startswith(b"\n"):
            raw = raw[1:]
        if raw.startswith(b"--"):
            continue
        if raw.strip() == b"" or raw.strip() == b"--":
            continue
        if b"\r\n\r\n" not in raw:
            continue
        header_block, value_part = raw.split(b"\r\n\r\n", 1)
        if value_part.endswith(b"\r\n"):
            value_part = value_part[:-2]
        header_str = header_block.decode("utf-8", errors="ignore")
        match = re.search(r'name="([^"]*)"', header_str)
        if not match:
            match2 = re.search(r"name=([^;\s]+)", header_str)
            if match2:
                name = match2.group(1).strip('"').strip("'")
            else:
                continue
        else:
            name = match.group(1)
        try:
            value = value_part.decode("utf-8")
        except Exception:  # noqa: BLE001
            value = value_part.decode("utf-8", errors="ignore")
        if name in payload:
            existing = payload[name]
            if isinstance(existing, list):
                existing.append(value)
            else:
                payload[name] = [existing, value]
        else:
            payload[name] = value
    return payload


async def _parse_form_body(
    request: Request,
) -> dict[str, Any] | JSONResponse | HTMLResponse:
    # Streaming limit is the ONLY size gate — executed before any parse
    body = await _read_limited_body(request, MAX_SMALL_PAYLOAD)
    if isinstance(body, JSONResponse):
        if _is_htmx_request(request):
            return HTMLResponse(
                _toast_oob("payload too large"),
                status_code=413,
            )
        return body
    try:
        ctype = request.headers.get("content-type", "")
        ctype_low = ctype.lower()
        payload: dict[str, Any]
        if "multipart/form-data" in ctype_low:
            boundary: str | None = None
            for part in ctype.split(";"):
                part = part.strip()
                if part.lower().startswith("boundary="):
                    boundary = part.split("=", 1)[1].strip().strip('"').strip("'")
                    break
            if not boundary:
                raise ValueError("missing boundary")
            payload = _parse_multipart_bytes(body, boundary)
        elif "application/x-www-form-urlencoded" in ctype_low:
            payload = _parse_urlencoded_bytes(body) if body else {}
        else:
            if body:
                try:
                    payload = _parse_urlencoded_bytes(body)
                except Exception:
                    raise ValueError("Invalid form data") from None
            else:
                payload = {}
        if len(json.dumps(payload, default=str)) > MAX_SMALL_PAYLOAD:
            if _is_htmx_request(request):
                return HTMLResponse(
                    _toast_oob("payload too large"),
                    status_code=413,
                )
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        payload = _coerce_form_payload(payload)
        return payload
    except Exception:  # noqa: BLE001
        if _is_htmx_request(request):
            return HTMLResponse(
                _toast_oob("Invalid form data"),
                status_code=400,
            )
        return JSONResponse({"detail": "Invalid form data"}, status_code=400)


async def _parse_payload(
    request: Request,
) -> dict[str, Any] | HTMLResponse | JSONResponse:
    size_check = _check_payload_size(request)
    if size_check:
        return size_check
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        return await _parse_json_body(request)
    return await _parse_form_body(request)


def _handle_validation_error(
    e: Exception, payload: dict[str, Any], request: Request
) -> JSONResponse | HTMLResponse:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]", "_", str(payload.get("name", ""))[:50])
    logger.warning(
        "validation error for create name=%s type=%s", sanitized, type(e).__name__
    )
    detail_lower = str(e).lower()
    if "url" in detail_lower and payload.get("type") == "remote":
        detail = "'url' required for type=remote"
        if _is_htmx_request(request):
            return HTMLResponse(_toast_oob(detail), status_code=400)
        return JSONResponse({"detail": detail}, status_code=400)
    if "command" in detail_lower and payload.get("type") == "local":
        detail = "'command' required for type=local"
        if _is_htmx_request(request):
            return HTMLResponse(_toast_oob(detail), status_code=400)
        return JSONResponse({"detail": detail}, status_code=400)
    if "headers" in detail_lower:
        detail = "headers must be a JSON object"
        if _is_htmx_request(request):
            return HTMLResponse(_toast_oob(detail), status_code=400)
        return JSONResponse({"detail": detail}, status_code=400)
    if "environment" in detail_lower:
        detail = "environment must be a JSON object"
        if _is_htmx_request(request):
            return HTMLResponse(_toast_oob(detail), status_code=400)
        return JSONResponse({"detail": detail}, status_code=400)
    detail = "invalid request"
    if _is_htmx_request(request):
        return HTMLResponse(_toast_oob(detail), status_code=400)
    return JSONResponse({"detail": detail, "code": "validation_error"}, status_code=400)


def _check_local_gating(
    config: MCPServerConfig, request: Request
) -> JSONResponse | HTMLResponse | None:
    if (
        config.type == "local"
        and os.environ.get("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "1") != "1"
    ):
        detail = "local servers not allowed via dashboard"
        if _is_htmx_request(request):
            return HTMLResponse(_toast_oob(detail), status_code=403)
        return JSONResponse({"detail": detail}, status_code=403)
    return None


def _validate_and_build_config(
    payload: dict[str, Any], request: Request
) -> MCPServerConfig | HTMLResponse | JSONResponse:
    is_oauth = False
    oauth_flag = payload.get("oauth_enabled", payload.get("use_oauth"))
    if oauth_flag is not None:
        if isinstance(oauth_flag, bool):
            is_oauth = oauth_flag
        elif isinstance(oauth_flag, str):
            is_oauth = oauth_flag.lower() in ("true", "1", "on", "yes")
        else:
            is_oauth = bool(oauth_flag)
        if is_oauth:
            scope_val = payload.get("oauth_scope") or payload.get("scope")
            oauth_cfg: dict[str, Any] = {}
            if isinstance(scope_val, str) and scope_val.strip():
                oauth_cfg["scope"] = scope_val.strip()
            existing = (
                payload.get("oauth") if isinstance(payload.get("oauth"), dict) else {}
            )
            cid = (
                payload.get("oauth_client_id")
                or payload.get("clientId")
                or existing.get("clientId")
            )
            if isinstance(cid, str) and cid.strip():
                try:
                    uuid.UUID(cid.strip())
                    oauth_cfg["clientId"] = cid.strip()
                except Exception:
                    oauth_cfg["clientId"] = str(uuid.uuid4())
            else:
                oauth_cfg["clientId"] = str(uuid.uuid4())
            csec = (
                payload.get("oauth_client_secret")
                or payload.get("clientSecret")
                or existing.get("clientSecret")
            )
            if isinstance(csec, str) and csec.strip():
                oauth_cfg["clientSecret"] = csec.strip()
            for k, v in existing.items():
                if k not in oauth_cfg and v is not None:
                    oauth_cfg[k] = v
            payload["oauth"] = oauth_cfg
        else:
            payload.pop("oauth", None)
        for k in (
            "oauth_enabled",
            "use_oauth",
            "oauth_scope",
            "oauth_client_id",
            "oauth_client_secret",
            "scope",
        ):
            if k in payload and k != "oauth":
                payload.pop(k, None)
    if payload.get("oauth") is True:
        payload["oauth"] = {"clientId": str(uuid.uuid4())}
    elif isinstance(payload.get("oauth"), dict):
        cid = payload["oauth"].get("clientId")
        if cid is None:
            payload["oauth"]["clientId"] = str(uuid.uuid4())
        else:
            try:
                uuid.UUID(str(cid))
                payload["oauth"]["clientId"] = str(uuid.UUID(str(cid)))
            except Exception:
                payload["oauth"]["clientId"] = str(uuid.uuid4())
    for k in ("url", "command", "headers", "environment", "cwd", "oauth"):
        v = payload.get(k)
        if isinstance(v, str) and not v.strip():
            payload.pop(k, None)
    name = payload.get("name")
    if not name:
        if _is_htmx_request(request):
            return HTMLResponse(
                _toast_oob("name required"),
                status_code=400,
            )
        return JSONResponse({"detail": "name required"}, status_code=400)
    try:
        config = MCPServerConfig(**payload)
    except ValidationError as e:
        return _handle_validation_error(e, payload, request)
    except ValueError as e:
        return _handle_validation_error(e, payload, request)
    gating = _check_local_gating(config, request)
    if gating:
        return gating
    return config


def _check_duplicate(
    registry: Registry, config: MCPServerConfig, request: Request
) -> HTMLResponse | JSONResponse | None:
    existing_names = set(registry.list())
    try:
        json_exists = registry._safe_path(config.name, ".json").exists()  # type: ignore[attr-defined]
    except ValueError:
        detail = "invalid request"
        if _is_htmx_request(request):
            return HTMLResponse(_toast_oob(detail), status_code=400)
        return JSONResponse(
            {"detail": detail, "code": "validation_error"}, status_code=400
        )
    try:
        pyi_exists = registry._safe_path(config.name, ".pyi").exists()  # type: ignore[attr-defined]
    except ValueError:
        pyi_exists = False
    if config.name in existing_names or json_exists or pyi_exists:
        msg = f"Server '{config.name}' already exists"
        if _is_htmx_request(request):
            return HTMLResponse(_toast_oob(msg), status_code=409)
        return JSONResponse({"detail": msg}, status_code=409)
    return None


async def _acquire_and_discover(config: MCPServerConfig) -> list[Any]:
    from mcp_gway.core import discover_tools as cli_discover  # circular import lazy

    acquired = False
    try:
        try:
            await asyncio.wait_for(_discovery_sem.acquire(), timeout=5)
            acquired = True
        except TimeoutError:
            raise ConnectionError("discovery saturated")
        await _maybe_detect_transport(config)
        tools = await asyncio.wait_for(
            cli_discover(config),
            timeout=(config.timeout / 1000 + 1) if config.timeout else 6,
        )
        if (
            not tools
            and config.type == "remote"
            and getattr(config, "oauth", None) is not False
        ):
            try:
                from mcp_gway.oauth import get_authenticated_client

                client = await get_authenticated_client(config.name)
                if client is not None:
                    try:
                        await client.aclose()
                    except Exception:
                        pass
                    tools2 = await asyncio.wait_for(
                        cli_discover(config, force_auth=True),
                        timeout=6,
                    )
                    if tools2:
                        return tools2
            except Exception:
                pass
        return tools
    except ConnectionError as e:
        if "saturated" in str(e):
            raise
        return []
    except TimeoutError:
        return []
    except Exception:  # noqa: BLE001, S110
        return []
    finally:
        if acquired:
            _discovery_sem.release()


async def _discover_and_persist(
    registry: Registry, config: MCPServerConfig
) -> list[Any]:
    try:
        tools = await _acquire_and_discover(config)
    except ConnectionError:
        raise
    except Exception:  # noqa: BLE001, S110
        tools = []
    try:
        registry.add(config, tools)  # type: ignore[arg-type]
    except Exception as e:  # noqa: BLE001
        logger.warning("registry add failed: %s", type(e).__name__)
        raise
    return tools


async def _safe_discover_wrap(
    registry: Registry, config: MCPServerConfig, request: Request
) -> tuple[list[Any] | None, JSONResponse | HTMLResponse | None]:
    try:
        tools = await _discover_and_persist(registry, config)
        return tools, None
    except ValueError:
        detail = "invalid request"
        if _is_htmx_request(request):
            return None, HTMLResponse(_toast_oob(detail), status_code=400)
        return None, JSONResponse(
            {"detail": detail, "code": "validation_error"}, status_code=400
        )
    except ConnectionError as e:
        if "saturated" in str(e):
            return None, JSONResponse(
                {"detail": "service busy, try again"}, status_code=503
            )
        logger.warning("registry add failed: %s", type(e).__name__)
        return None, JSONResponse(
            {"detail": "Corrupt config, remove and re-add"}, status_code=500
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("registry add failed: %s", type(e).__name__)
        return None, JSONResponse(
            {"detail": "Corrupt config, remove and re-add"}, status_code=500
        )


def _create_success_resp(
    registry: Registry, config: MCPServerConfig, tools: list[Any], request: Request
) -> JSONResponse | HTMLResponse:
    tool_count = len(tools)
    if _is_htmx_request(request):
        servers = _collect_servers(registry)
        table_html = str(server_table(servers))
        stats_oob = _stats_oob(registry)
        toast_msg = None
        headers = _csp_headers()
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
            html_content = f"{table_html}{stats_oob}"
            return HTMLResponse(html_content, status_code=201, headers=headers)
        # success with tools
        toast_oob = (
            _toast_oob(f"Added '{config.name}' with {tool_count} tools", "emerald")
            if tool_count
            else ""
        )
        html_content = f"{table_html}{stats_oob}{toast_oob}"
        return HTMLResponse(html_content, status_code=201, headers=headers)
    return JSONResponse(
        {"name": config.name, "tool_count": tool_count},
        status_code=201,
        headers=_csp_headers(),
    )


async def handle_create(request: Request) -> JSONResponse | HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    parsed = await _parse_payload(request)
    if isinstance(parsed, (JSONResponse, HTMLResponse)):
        return parsed
    payload: dict[str, Any] = parsed  # type: ignore[assignment]
    validated = _validate_and_build_config(payload, request)
    if isinstance(validated, (JSONResponse, HTMLResponse)):
        return validated
    config: MCPServerConfig = validated  # type: ignore[assignment]
    dup = _check_duplicate(registry, config, request)
    if dup:
        return dup
    tools, err = await _safe_discover_wrap(registry, config, request)
    if err:
        return err
    tools = tools or []
    return _create_success_resp(registry, config, tools, request)


async def handle_patch(request: Request) -> JSONResponse | HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    is_hx = _is_htmx_request(request)
    ctype = request.headers.get("content-type", "").lower()
    payload: dict[str, Any]
    if "application/json" in ctype:
        body = await _read_limited_body(request, MAX_SMALL_PAYLOAD)
        if isinstance(body, JSONResponse):
            if is_hx:
                return HTMLResponse(
                    _toast_oob("payload too large"),
                    status_code=413,
                    headers=_csp_headers(),
                )
            return body
        try:
            payload = json.loads(body.decode("utf-8") if body else "{}")
            if not isinstance(payload, dict):
                raise TypeError("payload must be object")
        except Exception:  # noqa: BLE001
            if is_hx:
                return HTMLResponse(
                    _toast_oob("Invalid JSON"), status_code=400, headers=_csp_headers()
                )
            return JSONResponse({"detail": "Invalid JSON"}, status_code=400)
    else:
        parsed = await _parse_form_body(request)
        if isinstance(parsed, (JSONResponse, HTMLResponse)):
            return parsed
        payload = parsed  # type: ignore[assignment]
        if "enabled" in payload and isinstance(payload["enabled"], str):
            v = payload["enabled"].lower()
            if v in ("true", "1", "on", "yes"):
                payload["enabled"] = True
            elif v in ("false", "0", "off", "no"):
                payload["enabled"] = False
    # Edit flow: if payload contains fields beyond enabled (or _from_edit flag), handle as full edit
    has_edit_fields = any(
        k in payload
        for k in (
            "timeout",
            "url",
            "command",
            "headers",
            "environment",
            "cwd",
            "type",
            "oauth",
        )
    )
    from_edit = bool(payload.get("_from_edit")) or has_edit_fields
    if from_edit:
        # Full edit — merge with existing config
        try:
            existing = registry.get_config(name)
        except FileNotFoundError:
            if is_hx:
                return HTMLResponse(
                    _toast_oob(f"Server '{_e(name)}' not found"),
                    status_code=404,
                    headers=_csp_headers(),
                )
            return JSONResponse(
                {"detail": f"Server '{_e(name)}' not found"},
                status_code=404,
                headers=_csp_headers(),
            )
        except json.JSONDecodeError:
            if is_hx:
                return HTMLResponse(
                    _toast_oob("Corrupt config, remove and re-add"),
                    status_code=500,
                    headers=_csp_headers(),
                )
            return JSONResponse(
                {"detail": "Corrupt config, remove and re-add"},
                status_code=500,
                headers=_csp_headers(),
            )
        except ValueError:
            if is_hx:
                return HTMLResponse(
                    _toast_oob("invalid request"),
                    status_code=400,
                    headers=_csp_headers(),
                )
            return JSONResponse(
                {"detail": "invalid request", "code": "validation_error"},
                status_code=400,
                headers=_csp_headers(),
            )
        # Build merged payload
        merged: dict[str, Any] = {
            "name": existing.name,
            "type": payload.get("type") or existing.type,
            "enabled": payload.get("enabled", existing.enabled),
            "timeout": existing.timeout,
        }
        if "timeout" in payload:
            try:
                merged["timeout"] = int(payload["timeout"])
            except Exception:
                merged["timeout"] = existing.timeout
        if existing.type == "remote" or merged["type"] == "remote":
            merged["url"] = payload.get("url") or existing.url
            # headers handling: if empty string, keep existing; if JSON string, parse
            hdr_raw = payload.get("headers")
            if isinstance(hdr_raw, str):
                hdr_raw = hdr_raw.strip()
                if not hdr_raw:
                    merged["headers"] = existing.headers
                else:
                    try:
                        parsed = json.loads(hdr_raw)
                        if isinstance(parsed, dict):
                            merged["headers"] = parsed
                        else:
                            merged["headers"] = existing.headers
                    except Exception:
                        if is_hx:
                            return HTMLResponse(
                                _toast_oob("headers must be a JSON object"),
                                status_code=400,
                                headers=_csp_headers(),
                            )
                        return JSONResponse(
                            {"detail": "headers must be a JSON object"},
                            status_code=400,
                            headers=_csp_headers(),
                        )
            elif isinstance(hdr_raw, dict):
                merged["headers"] = hdr_raw
            else:
                merged["headers"] = existing.headers
            if existing.oauth is not None:
                merged["oauth"] = (
                    existing.oauth
                    if isinstance(existing.oauth, dict)
                    else existing.oauth.model_dump()
                    if hasattr(existing.oauth, "model_dump")
                    else existing.oauth
                )
            if "oauth" in payload and payload["oauth"] is not None:
                merged["oauth"] = payload["oauth"]
        else:
            # local
            cmd_raw = payload.get("command")
            if isinstance(cmd_raw, str):
                cmd_raw = cmd_raw.strip()
                if cmd_raw:
                    try:
                        merged["command"] = shlex.split(cmd_raw)
                    except Exception:
                        merged["command"] = [cmd_raw]
                else:
                    merged["command"] = existing.command
            elif isinstance(cmd_raw, list):
                merged["command"] = cmd_raw
            else:
                merged["command"] = existing.command
            merged["cwd"] = payload.get("cwd") or existing.cwd
            env_raw = payload.get("environment")
            if isinstance(env_raw, str):
                env_raw = env_raw.strip()
                if not env_raw:
                    merged["environment"] = existing.environment
                else:
                    try:
                        parsed_e = json.loads(env_raw)
                        if isinstance(parsed_e, dict):
                            merged["environment"] = parsed_e
                        else:
                            merged["environment"] = existing.environment
                    except Exception:
                        if is_hx:
                            return HTMLResponse(
                                _toast_oob("environment must be a JSON object"),
                                status_code=400,
                                headers=_csp_headers(),
                            )
                        return JSONResponse(
                            {"detail": "environment must be a JSON object"},
                            status_code=400,
                            headers=_csp_headers(),
                        )
            elif isinstance(env_raw, dict):
                merged["environment"] = env_raw
            else:
                merged["environment"] = existing.environment
        # Preserve resolved_transport and other internal fields
        if existing.resolved_transport:
            merged["resolved_transport"] = existing.resolved_transport
        # Clean Nones / empty
        for k in ("url", "command", "headers", "environment", "cwd", "oauth"):
            v = merged.get(k)
            if isinstance(v, str) and not v.strip():
                merged.pop(k, None)
        try:
            new_cfg = MCPServerConfig(
                **{
                    k: v
                    for k, v in merged.items()
                    if v is not None or k in ("name", "type")
                }
            )
        except ValidationError as e:
            return _handle_validation_error(e, merged, request)
        except ValueError as e:
            return _handle_validation_error(e, merged, request)
        # Persist: preserve real tool names via Registry method
        try:
            try:
                tools = registry.get_pyi_tools(name)
            except Exception:
                tools = []
            registry.add(new_cfg, tools)  # type: ignore[arg-type]
        except ValueError:
            if is_hx:
                return HTMLResponse(
                    _toast_oob("invalid request"),
                    status_code=400,
                    headers=_csp_headers(),
                )
            return JSONResponse(
                {"detail": "invalid request", "code": "validation_error"},
                status_code=400,
                headers=_csp_headers(),
            )
        except Exception:
            if is_hx:
                return HTMLResponse(
                    _toast_oob("Corrupt config, remove and re-add"),
                    status_code=500,
                    headers=_csp_headers(),
                )
            return JSONResponse(
                {"detail": "Corrupt config, remove and re-add"},
                status_code=500,
                headers=_csp_headers(),
            )
        if is_hx:
            html_table = _table_with_oob(
                registry,
                toast_msg=f"Updated '{_e(name)}'",
                toast_variant="emerald",
                close_dialog=True,
            )
            return HTMLResponse(html_table, headers=_csp_headers())
        result = _server_to_dict(registry, name)
        return JSONResponse(result, headers=_csp_headers())
    # Simple enabled toggle
    if "enabled" not in payload:
        if is_hx:
            return HTMLResponse(
                _toast_oob("enabled required"), status_code=400, headers=_csp_headers()
            )
        return JSONResponse(
            {"detail": "enabled required"}, status_code=400, headers=_csp_headers()
        )
    enabled_val = payload["enabled"]
    if not isinstance(enabled_val, bool):
        if is_hx:
            return HTMLResponse(
                _toast_oob("enabled must be boolean"),
                status_code=400,
                headers=_csp_headers(),
            )
        return JSONResponse(
            {"detail": "enabled must be boolean"},
            status_code=400,
            headers=_csp_headers(),
        )
    try:
        registry.get_config(name)
    except FileNotFoundError:
        if is_hx:
            return HTMLResponse(
                _toast_oob(f"Server '{_e(name)}' not found"),
                status_code=404,
                headers=_csp_headers(),
            )
        return JSONResponse(
            {"detail": f"Server '{_e(name)}' not found"},
            status_code=404,
            headers=_csp_headers(),
        )
    except json.JSONDecodeError:
        if is_hx:
            return HTMLResponse(
                _toast_oob("Corrupt config, remove and re-add"),
                status_code=500,
                headers=_csp_headers(),
            )
        return JSONResponse(
            {"detail": "Corrupt config, remove and re-add"},
            status_code=500,
            headers=_csp_headers(),
        )
    except ValueError:
        if is_hx:
            return HTMLResponse(
                _toast_oob("invalid request"), status_code=400, headers=_csp_headers()
            )
        return JSONResponse(
            {"detail": "invalid request", "code": "validation_error"},
            status_code=400,
            headers=_csp_headers(),
        )
    try:
        registry.patch_enabled(name, enabled_val)
    except ValueError:
        if is_hx:
            return HTMLResponse(
                _toast_oob("invalid request"), status_code=400, headers=_csp_headers()
            )
        return JSONResponse(
            {"detail": "invalid request", "code": "validation_error"},
            status_code=400,
            headers=_csp_headers(),
        )
    except FileNotFoundError:
        if is_hx:
            return HTMLResponse(
                _toast_oob(f"Server '{_e(name)}' not found"),
                status_code=404,
                headers=_csp_headers(),
            )
        return JSONResponse(
            {"detail": f"Server '{_e(name)}' not found"},
            status_code=404,
            headers=_csp_headers(),
        )
    if is_hx:
        action = "Enabled" if enabled_val else "Disabled"
        html_table = _table_with_oob(
            registry,
            toast_msg=f"{action} '{_e(name)}'",
            toast_variant="emerald",
            close_dialog=True,
        )
        return HTMLResponse(html_table, headers=_csp_headers())
    result = _server_to_dict(registry, name)
    return JSONResponse(result, headers=_csp_headers())


async def handle_delete(request: Request) -> JSONResponse | HTMLResponse:
    from starlette.responses import Response

    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    is_hx = _is_htmx_request(request)
    try:
        safe = registry._safe_path(name, ".pyi")  # type: ignore[attr-defined]
        _ = safe
    except ValueError:
        if is_hx:
            html_table = _table_with_oob(
                registry,
                toast_msg="Invalid name",
                toast_variant="red",
                close_dialog=True,
            )
            return HTMLResponse(html_table, headers=_csp_headers())
        return Response(status_code=204, headers=_csp_headers())
    # check if server actually exists to give proper feedback
    existed = False
    for suffix in (".pyi", ".json"):
        try:
            p = registry._safe_path(name, suffix)  # type: ignore[attr-defined]
            if p.exists():
                existed = True
        except Exception:
            continue
    for suffix in (".pyi", ".json"):
        try:
            p = registry._safe_path(name, suffix)  # type: ignore[attr-defined]
            if p.exists():
                p.unlink()
        except Exception:  # noqa: BLE001, S110
            continue
    tokens_dir = Path.home() / ".config" / "mcp-gway" / "tokens"
    for suffix in ("", "_client"):
        try:
            token_file = tokens_dir / f"{name}{suffix}.json"
            if token_file.exists():
                token_file.unlink()
        except Exception:  # noqa: BLE001, S110
            continue
    if is_hx:
        if not existed:
            html_table = _table_with_oob(
                registry,
                toast_msg=f"Server '{_e(name)}' not found",
                toast_variant="amber",
                close_dialog=True,
            )
            return HTMLResponse(html_table, status_code=404, headers=_csp_headers())
        html_table = _table_with_oob(
            registry,
            toast_msg=f"Deleted '{_e(name)}'",
            toast_variant="emerald",
            close_dialog=True,
        )
        return HTMLResponse(html_table, headers=_csp_headers())
    return Response(status_code=204, headers=_csp_headers())


async def _background_refresh(registry: Registry, name: str) -> None:
    try:
        cfg = registry.get_config(name)
    except Exception:  # noqa: BLE001, S110
        return
    tools: list[Any] = []
    try:
        from mcp_gway.core import discover_tools as cli_discover  # circular import lazy

        acquired = False
        try:
            try:
                await asyncio.wait_for(_discovery_sem.acquire(), timeout=5)
                acquired = True
            except TimeoutError:
                return
            await _maybe_detect_transport(cfg)
            tools = await asyncio.wait_for(
                cli_discover(cfg),
                timeout=(cfg.timeout / 1000 + 1) if cfg.timeout else 6,
            )
            if (
                not tools
                and cfg.type == "remote"
                and getattr(cfg, "oauth", None) is not False
            ):
                try:
                    from mcp_gway.oauth import get_authenticated_client

                    client = await get_authenticated_client(cfg.name)
                    if client is not None:
                        try:
                            await client.aclose()
                        except Exception:
                            pass
                        tools2 = await asyncio.wait_for(
                            cli_discover(cfg, force_auth=True),
                            timeout=6,
                        )
                        if tools2:
                            tools = tools2
                except Exception:
                    pass
        finally:
            if acquired:
                _discovery_sem.release()
    except Exception:  # noqa: BLE001, S110
        tools = []
    if not tools:
        return
    try:
        registry.update(name, tools)
    except Exception:  # noqa: BLE001, S110
        pass


async def _background_oauth_flow(registry: Registry, name: str) -> None:
    try:
        cfg = registry.get_config(name)
    except Exception:  # noqa: BLE001, S110
        return
    if cfg.type != "remote" or not cfg.oauth:
        return
    if _tool_count_for(registry, name) > 0:
        return
    try:
        from mcp_gway.models import OAuthConfig
        from mcp_gway.oauth import run_oauth_flow

        client_metadata = None
        scope_val = None
        if isinstance(cfg.oauth, OAuthConfig):
            scope_val = cfg.oauth.scope
        elif isinstance(cfg.oauth, dict):
            scope_val = cfg.oauth.get("scope")
        if scope_val:
            try:
                from mcp.shared.auth import OAuthClientMetadata

                client_metadata = OAuthClientMetadata(
                    scope=scope_val if isinstance(scope_val, str) else None,
                    redirect_uris=["http://127.0.0.1:8989/callback"],
                )
            except Exception:
                pass
        client = await run_oauth_flow(
            server_url=cfg.url or "",
            server_name=name,
            client_metadata=client_metadata,
            output_callback=lambda msg: logger.info("oauth %s: %s", name, msg),
            callback_port=8989,
            oauth_config=cfg.oauth,
        )
        if client:
            try:
                await client.aclose()
            except Exception:
                pass
            from mcp_gway.core import discover_tools as cli_discover_oauth

            tools = await cli_discover_oauth(cfg, force_auth=True)
            if tools:
                registry.update(name, tools)
                logger.info(
                    "background oauth for %s succeeded with %d tools", name, len(tools)
                )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "background oauth flow for %s failed: %s", name, type(e).__name__
        )


async def handle_refresh(request: Request) -> JSONResponse | HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    is_hx = _is_htmx_request(request)
    body = await _read_limited_body(request, MAX_SMALL_PAYLOAD)
    if isinstance(body, JSONResponse):
        if is_hx:
            return HTMLResponse(
                _toast_oob("payload too large"), status_code=413, headers=_csp_headers()
            )
        return body
    try:
        cfg = registry.get_config(name)
    except FileNotFoundError:
        if is_hx:
            msg = _drawer_feedback_html(f"Server '{_e(name)}' not found", "red")
            return HTMLResponse(
                f"<div id='drawer-feedback' hx-swap-oob='innerHTML'>{msg}</div>",
                status_code=404,
                headers=_csp_headers(),
            )
        return JSONResponse(
            {"detail": f"Server '{_e(name)}' not found"},
            status_code=404,
            headers=_csp_headers(),
        )
    except json.JSONDecodeError:
        if is_hx:
            msg2 = _drawer_feedback_html("Corrupt config, remove and re-add", "red")
            return HTMLResponse(
                f"<div id='drawer-feedback' hx-swap-oob='innerHTML'>{msg2}</div>",
                status_code=500,
                headers=_csp_headers(),
            )
        return JSONResponse(
            {"detail": "Corrupt config, remove and re-add"},
            status_code=500,
            headers=_csp_headers(),
        )
    if not cfg.enabled:
        if is_hx:
            msg3 = _drawer_feedback_html("Server disabled — enable first", "amber")
            return HTMLResponse(
                f"<div id='drawer-feedback' hx-swap-oob='innerHTML'>{msg3}</div>",
                status_code=409,
                headers=_csp_headers(),
            )
        return JSONResponse(
            {"detail": "Server disabled"}, status_code=409, headers=_csp_headers()
        )
    if is_hx:
        # HX refresh is now blocking with timeout so drawer never hangs
        # keep 202 semantics for API clients, but for HX we await discovery and return final state
        tools: list[Any] = []
        try:
            # reuse discovery helper with semaphore/timeout
            tools = await _acquire_and_discover(cfg)
        except Exception:
            tools = []
        if tools:
            try:
                registry.update(name, tools)
            except Exception:
                pass
            feedback = _drawer_feedback_html(
                f"Refreshed '{_e(name)}' — {len(tools)} tool(s) discovered", "emerald"
            )
            stats_oob = _stats_oob(registry)
            toast = _toast_oob(
                f"Refreshed '{_e(name)}' — {len(tools)} tools", "emerald"
            )
            # table is updated via OOB fetch on client to avoid tbody parsing issues inside drawer
            html = f"<div id='drawer-feedback'>{feedback}</div>{stats_oob}{toast}"
            resp = HTMLResponse(html, headers=_csp_headers())
            # also trigger client-side table reload via HX-Trigger header for htmx
            resp.headers["HX-Trigger"] = "refreshDone"
            return resp
        else:
            has_auth = bool(cfg.headers or cfg.oauth)
            if cfg.type == "remote" and not has_auth:
                hint = "No tools discovered (401). Add Authorization header in Edit → Advanced → Headers or enable OAuth."
                variant = "amber"
            elif cfg.type == "remote":
                hint = "No tools discovered — still unreachable. Check URL, headers/token or OAuth."
                variant = "amber"
            else:
                hint = "No tools discovered — check command, cwd and that the local process is reachable."
                variant = "amber"
            feedback = _drawer_feedback_html(
                f"Refresh '{_e(name)}' finished — {hint}", variant
            )
            stats_oob = _stats_oob(registry)
            toast = _toast_oob(f"Refresh '{_e(name)}' — no tools", variant)
            html = f"<div id='drawer-feedback'>{feedback}</div>{stats_oob}{toast}"
            resp = HTMLResponse(html, headers=_csp_headers())
            resp.headers["HX-Trigger"] = "refreshDone"
            return resp
    # non-HX API clients keep old fire-and-forget 202 for backward compat
    asyncio.create_task(_background_refresh(registry, name))
    return JSONResponse(
        {"status": "refreshing"}, status_code=202, headers=_csp_headers()
    )


async def handle_refresh_all(request: Request) -> JSONResponse | HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    is_hx = _is_htmx_request(request)
    body = await _read_limited_body(request, MAX_SMALL_PAYLOAD)
    if isinstance(body, JSONResponse):
        if is_hx:
            return HTMLResponse(
                _toast_oob("payload too large"), status_code=413, headers=_csp_headers()
            )
        return body
    names = registry.list()
    if not names:
        if is_hx:
            table_html = str(server_table([]))
            stats_oob = _stats_oob(registry)
            toast = _toast_oob("No servers to refresh", "amber")
            html = f"{table_html}{stats_oob}{toast}"
            return HTMLResponse(html, headers=_csp_headers())
        return JSONResponse(
            {"status": "no servers", "refreshed": 0}, headers=_csp_headers()
        )
    # Filter enabled only
    enabled_names: list[str] = []
    for n in names:
        try:
            cfg = registry.get_config(n)
            if getattr(cfg, "enabled", True):
                enabled_names.append(n)
        except Exception:
            enabled_names.append(n)
    if not enabled_names:
        if is_hx:
            table_html = str(server_table(_collect_servers(registry)))
            stats_oob = _stats_oob(registry)
            toast = _toast_oob("All servers disabled — nothing to refresh", "amber")
            html = f"{table_html}{stats_oob}{toast}"
            return HTMLResponse(html, headers=_csp_headers())
        return JSONResponse(
            {"status": "all disabled", "refreshed": 0}, headers=_csp_headers()
        )
    # Perform refresh sequentially to avoid overwhelming
    refreshed = 0
    failed: list[str] = []
    total_tools = 0
    for n in enabled_names:
        try:
            cfg = registry.get_config(n)
            tools = await _acquire_and_discover(cfg)
            if tools:
                try:
                    registry.update(n, tools)
                    refreshed += 1
                    total_tools += len(tools)
                except Exception:
                    failed.append(n)
            else:
                failed.append(n)
        except Exception:
            failed.append(n)
    servers = _collect_servers(registry)
    table_html = str(server_table(servers))
    stats_oob = _stats_oob(registry)
    if refreshed == len(enabled_names):
        toast = _toast_oob(
            f"Refreshed {refreshed}/{len(enabled_names)} — {total_tools} tools",
            "emerald",
        )
    elif refreshed > 0:
        toast = _toast_oob(
            f"Refreshed {refreshed}/{len(enabled_names)} — {len(failed)} failed (check URL/auth)",
            "amber",
        )
    else:
        toast = _toast_oob(
            "Refresh finished — no tools discovered (check 401/auth)", "amber"
        )
    html = f"{table_html}{stats_oob}{toast}"
    return (
        HTMLResponse(html, headers=_csp_headers())
        if is_hx
        else JSONResponse(
            {
                "status": "done",
                "refreshed": refreshed,
                "failed": failed,
                "total_tools": total_tools,
            },
            headers=_csp_headers(),
        )
    )


def _is_loopback(request: Request) -> bool:
    client = request.client
    if not client:
        return False
    host = getattr(client, "host", "")
    return host in ("127.0.0.1", "::1", "localhost")


def _check_reveal_rate(ip: str, name: str) -> bool:
    if len(_reveal_attempts) > 1000:
        for k in list(_reveal_attempts.keys())[:100]:
            _reveal_attempts.pop(k, None)
    key = f"{ip}:{name}"
    now = time.monotonic()
    lst = _reveal_attempts.get(key, [])
    lst = [t for t in lst if now - t < 60]
    if not lst:
        _reveal_attempts.pop(key, None)
    if len(lst) >= 5:
        if lst:
            _reveal_attempts[key] = lst
        else:
            _reveal_attempts.pop(key, None)
        return False
    lst.append(now)
    _reveal_attempts[key] = lst
    if not lst:
        _reveal_attempts.pop(key, None)
    return True


async def handle_reveal(request: Request) -> JSONResponse | HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    is_hx = _is_htmx_request(request)
    if not _is_loopback(request):
        if is_hx:
            return HTMLResponse(
                "<div id='drawer-reveal-output' class='rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800'>Forbidden — reveal only allowed from 127.0.0.1</div>",
                status_code=403,
                headers=_csp_headers(),
            )
        return JSONResponse(
            {"detail": "Forbidden"}, status_code=403, headers=_csp_headers()
        )
    client_ip = (
        getattr(request.client, "host", "unknown") if request.client else "unknown"
    )
    if not _check_reveal_rate(str(client_ip), name):
        if is_hx:
            return HTMLResponse(
                "<div id='drawer-reveal-output' class='rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800'>Too many requests — try again in 60s</div>",
                status_code=429,
                headers=_csp_headers(),
            )
        return JSONResponse(
            {"detail": "Too many requests"}, status_code=429, headers=_csp_headers()
        )
    body = await _read_limited_body(request, MAX_SMALL_PAYLOAD)
    if isinstance(body, JSONResponse):
        if is_hx:
            return HTMLResponse(
                _toast_oob("payload too large"), status_code=413, headers=_csp_headers()
            )
        return body
    sanitized = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    logger.info("reveal name=%s ip=%s", sanitized, str(client_ip))
    try:
        cfg = registry.get_config(name)
    except FileNotFoundError:
        if is_hx:
            return HTMLResponse(
                f"<div id='drawer-reveal-output' class='rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800'>Server '{_e(name)}' not found</div>",
                status_code=404,
                headers=_csp_headers(),
            )
        return JSONResponse(
            {"detail": f"Server '{_e(name)}' not found"},
            status_code=404,
            headers=_csp_headers(),
        )
    except json.JSONDecodeError:
        if is_hx:
            return HTMLResponse(
                "<div id='drawer-reveal-output' class='rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800'>Corrupt config, remove and re-add</div>",
                status_code=500,
                headers=_csp_headers(),
            )
        return JSONResponse(
            {"detail": "Corrupt config, remove and re-add"},
            status_code=500,
            headers=_csp_headers(),
        )
    result: dict[str, Any] = {}
    if cfg.type == "remote":
        if cfg.headers:
            result["headers"] = cfg.headers
        if cfg.oauth is not None:
            if isinstance(cfg.oauth, OAuthConfig):
                result["oauth"] = cfg.oauth.model_dump()
            else:
                result["oauth"] = cfg.oauth
        if not result:
            result["headers"] = cfg.headers
    else:
        if cfg.environment:
            result["environment"] = cfg.environment
        if not result:
            result["environment"] = cfg.environment
    if not result:
        result = {
            "headers": cfg.headers,
            "environment": cfg.environment,
            "oauth": cfg.oauth,
        }
        result = {k: v for k, v in result.items() if v is not None}
    if is_hx:
        if not result or all(v is None for v in result.values()):
            out_html = "<div id='drawer-reveal-output' class='rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600'>No secrets stored for this server</div>"
            return HTMLResponse(out_html, headers=_csp_headers())
        pretty = html.escape(json.dumps(result, indent=2), quote=True)
        out_html = f"<div id='drawer-reveal-output' class='rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-mono whitespace-pre-wrap break-all text-emerald-900 max-h-60 overflow-auto' style='display:block'>{pretty}</div><div id='toast' hx-swap-oob='innerHTML'><div class='bg-emerald-50 border border-emerald-200 text-emerald-800 px-4 py-3 rounded-xl shadow-sm text-sm' role='status'>Secrets revealed (local only, not logged)</div></div>"
        return HTMLResponse(out_html, headers=_csp_headers())
    return JSONResponse(result, headers=_csp_headers())


async def handle_oauth_start(request: Request) -> JSONResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    if not _is_loopback(request):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    try:
        cfg = registry.get_config(name)
    except FileNotFoundError:
        return JSONResponse(
            {"detail": f"Server '{_e(name)}' not found"}, status_code=404
        )
    except json.JSONDecodeError:
        return JSONResponse(
            {"detail": "Corrupt config, remove and re-add"}, status_code=500
        )
    if cfg.type != "remote":
        return JSONResponse(
            {"detail": "OAuth only for remote servers"}, status_code=400
        )
    try:
        from mcp_gway.oauth import initiate_web_oauth

        scope = None
        oauth_cfg_for_flow = cfg.oauth
        if isinstance(cfg.oauth, dict):
            scope = cfg.oauth.get("scope")
        elif hasattr(cfg.oauth, "scope"):
            scope = getattr(cfg.oauth, "scope", None)
        from mcp.shared.auth import OAuthClientMetadata

        client_metadata = None
        if scope:
            try:
                client_metadata = OAuthClientMetadata(
                    scope=scope, redirect_uris=["http://127.0.0.1:8989/callback"]
                )
            except Exception:
                pass
        auth_url, err = await initiate_web_oauth(
            server_url=cfg.url or "",
            server_name=name,
            client_metadata=client_metadata,
            oauth_config=oauth_cfg_for_flow,
        )
        if err:
            return JSONResponse({"detail": err}, status_code=400)
        if not auth_url:
            return JSONResponse({"detail": "Could not initiate OAuth"}, status_code=500)
        return JSONResponse({"auth_url": auth_url}, headers=_csp_headers())
    except Exception as e:  # noqa: BLE001
        logger.warning("oauth start failed for %s: %s", name, type(e).__name__)
        return JSONResponse({"detail": "OAuth failed"}, status_code=500)


async def handle_oauth_status(request: Request) -> JSONResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    try:
        registry.get_config(name)
    except FileNotFoundError:
        return JSONResponse(
            {"detail": f"Server '{_e(name)}' not found"}, status_code=404
        )
    try:
        from mcp_gway.oauth import get_pending_oauth_status

        status = get_pending_oauth_status(name)
        tool_count = _tool_count_for(registry, name)
        if tool_count > 0:
            return JSONResponse(
                {"status": "completed", "tool_count": tool_count},
                headers=_csp_headers(),
            )
        if status == "pending":
            return JSONResponse({"status": "pending"}, headers=_csp_headers())
        return JSONResponse(
            {"status": "idle", "tool_count": tool_count}, headers=_csp_headers()
        )
    except Exception:
        return JSONResponse({"status": "unknown"}, headers=_csp_headers())
