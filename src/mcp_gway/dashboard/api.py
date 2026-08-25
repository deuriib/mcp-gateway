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
    base = {"Content-Security-Policy": "default-src 'self'"}
    if extra:
        base.update(extra)
    return base


async def handle_dashboard(request: Request) -> HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    host = getattr(request.app.state, "dashboard_host", "127.0.0.1")
    warning = host not in ("127.0.0.1", "::1", "localhost")
    servers = _collect_servers(registry)
    html_content = str(layout(servers, warning_banner=warning))
    headers = {}
    if warning:
        headers["X-Warning"] = "exposed"
    headers["Content-Security-Policy"] = "default-src 'self'"
    return HTMLResponse(html_content, headers=headers)


async def handle_dashboard_servers(request: Request) -> HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    servers = _collect_servers(registry)
    html_content = str(server_table(servers))
    return HTMLResponse(html_content, headers=_csp_headers())


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
        return HTMLResponse(html_content, headers=_csp_headers())
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
    from mcp_gway.cli import _discover_tools as cli_discover  # circular import lazy

    acquired = False
    try:
        try:
            await asyncio.wait_for(_discovery_sem.acquire(), timeout=5)
            acquired = True
        except TimeoutError:
            raise ConnectionError("discovery saturated")
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
        html_content = str(server_table(servers))
        if tool_count == 0:
            headers = _csp_headers()
            if config.type == "remote":
                if config.oauth:
                    headers["X-Toast"] = (
                        f"No tools discovered -- '{config.name}' saved, OAuth enabled. "
                        "Browser will open for authentication, or run: mcp-gway refresh "
                        f"{config.name} --auth"
                    )
                    headers["X-OAuth-Required"] = "1"
                else:
                    headers["X-Toast"] = (
                        f"No tools discovered -- '{config.name}' saved but unreachable (401). "
                        'For PAT add Authorization in Advanced -> Headers {"Authorization": "Bearer <token>"}; '
                        f"for OAuth enable the OAuth check or run: mcp-gway refresh {config.name} --auth"
                    )
            else:
                headers["X-Toast"] = (
                    "No tools discovered -- server saved but unreachable. Check command & logs"
                )
            return HTMLResponse(html_content, status_code=201, headers=headers)
        return HTMLResponse(html_content, status_code=201, headers=_csp_headers())
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


async def handle_patch(request: Request) -> JSONResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    body = await _read_limited_body(request, MAX_SMALL_PAYLOAD)
    if isinstance(body, JSONResponse):
        return body
    try:
        payload = json.loads(body.decode("utf-8") if body else "{}")
    except Exception:  # noqa: BLE001
        return JSONResponse({"detail": "Invalid JSON"}, status_code=400)
    if "enabled" not in payload:
        return JSONResponse({"detail": "enabled required"}, status_code=400)
    enabled_val = payload["enabled"]
    if not isinstance(enabled_val, bool):
        return JSONResponse({"detail": "enabled must be boolean"}, status_code=400)
    try:
        registry.get_config(name)
    except FileNotFoundError:
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
    try:
        registry.patch_enabled(name, enabled_val)
    except ValueError:
        return JSONResponse(
            {"detail": "invalid request", "code": "validation_error"}, status_code=400
        )
    except FileNotFoundError:
        return JSONResponse(
            {"detail": f"Server '{_e(name)}' not found"}, status_code=404
        )
    result = _server_to_dict(registry, name)
    return JSONResponse(result, headers=_csp_headers())


async def handle_delete(request: Request) -> JSONResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    try:
        safe = registry._safe_path(name, ".pyi")  # type: ignore[attr-defined]
        _ = safe
    except ValueError:
        return JSONResponse(None, status_code=204, headers=_csp_headers())
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
    return JSONResponse(None, status_code=204, headers=_csp_headers())


async def _background_refresh(registry: Registry, name: str) -> None:
    try:
        cfg = registry.get_config(name)
    except Exception:  # noqa: BLE001, S110
        return
    tools: list[Any] = []
    try:
        from mcp_gway.cli import _discover_tools as cli_discover  # circular import lazy

        acquired = False
        try:
            try:
                await asyncio.wait_for(_discovery_sem.acquire(), timeout=5)
                acquired = True
            except TimeoutError:
                return
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
            scope_val = cfg.oauth.get("scope") or cfg.oauth.get("clientId")
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
        )
        if client:
            try:
                await client.aclose()
            except Exception:
                pass
            from mcp_gway.cli import _discover_tools as cli_discover_oauth

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


async def handle_refresh(request: Request) -> JSONResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    body = await _read_limited_body(request, MAX_SMALL_PAYLOAD)
    if isinstance(body, JSONResponse):
        return body
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
    if not cfg.enabled:
        return JSONResponse({"detail": "Server disabled"}, status_code=409)
    asyncio.create_task(_background_refresh(registry, name))
    return JSONResponse(
        {"status": "refreshing"}, status_code=202, headers=_csp_headers()
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


async def handle_reveal(request: Request) -> JSONResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    if not _is_loopback(request):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    client_ip = (
        getattr(request.client, "host", "unknown") if request.client else "unknown"
    )
    if not _check_reveal_rate(str(client_ip), name):
        return JSONResponse({"detail": "Too many requests"}, status_code=429)
    body = await _read_limited_body(request, MAX_SMALL_PAYLOAD)
    if isinstance(body, JSONResponse):
        return body
    sanitized = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    logger.info("reveal name=%s ip=%s", sanitized, str(client_ip))
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
            server_url=cfg.url or "", server_name=name, client_metadata=client_metadata
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
