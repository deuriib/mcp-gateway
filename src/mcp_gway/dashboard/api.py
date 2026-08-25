"""JSON handlers for dashboard API."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from typing import Any

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from mcp_gway.dashboard.views import layout, server_table
from mcp_gway.models import MCPServerConfig, OAuthConfig
from mcp_gway.registry import Registry

logger = logging.getLogger(__name__)

MAX_PAYLOAD_SIZE = 1_048_576
_discovery_sem = asyncio.Semaphore(3)


def _e(s: str) -> str:
    return html.escape(s, quote=True)


def _is_htmx_request(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _is_hx(request: Request) -> bool:
    return _is_htmx_request(request)


def _mask_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
    if headers is None:
        return None
    return {k: "***" for k in headers}


def _mask_environment(env: dict[str, str] | None) -> dict[str, str] | None:
    if env is None:
        return None
    return {k: "***" for k in env}


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
            result["headers"] = _mask_headers(cfg.headers)
        if cfg.oauth is not None:
            result["oauth"] = _mask_oauth(cfg.oauth)
        if cfg.resolved_transport:
            result["resolved_transport"] = cfg.resolved_transport
    else:
        result["command"] = cfg.command
        if cfg.cwd:
            result["cwd"] = cfg.cwd
        if cfg.environment:
            result["environment"] = _mask_environment(cfg.environment)
    return result


async def handle_dashboard(request: Request) -> HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    host = getattr(request.app.state, "dashboard_host", "127.0.0.1")
    warning = host not in ("127.0.0.1", "::1", "localhost")
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
    html_content = str(layout(servers, warning_banner=warning))
    headers = {}
    if warning:
        headers["X-Warning"] = "exposed"
    return HTMLResponse(html_content, headers=headers)


async def handle_dashboard_servers(request: Request) -> HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
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
    html_content = str(server_table(servers))
    return HTMLResponse(html_content)


async def handle_list(request: Request) -> JSONResponse | HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
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
    if _is_htmx_request(request):
        html_content = str(server_table(servers))
        return HTMLResponse(html_content)
    return JSONResponse(servers)


async def handle_get(request: Request) -> JSONResponse | HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]
    name = request.path_params["name"]
    try:
        cfg = registry.get_config(name)
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

    tool_count = _tool_count_for(registry, name)
    data: dict[str, Any] = {
        "name": cfg.name,
        "type": cfg.type,
        "enabled": cfg.enabled,
        "timeout": cfg.timeout,
        "tool_count": tool_count,
    }
    if cfg.type == "remote":
        data["url"] = cfg.url
        if cfg.headers:
            data["headers"] = _mask_headers(cfg.headers)
        if cfg.oauth is not None:
            data["oauth"] = _mask_oauth(cfg.oauth)
        if cfg.resolved_transport:
            data["resolved_transport"] = cfg.resolved_transport
    else:
        data["command"] = cfg.command
        if cfg.cwd:
            data["cwd"] = cfg.cwd
        if cfg.environment:
            data["environment"] = _mask_environment(cfg.environment)
    try:
        pyi = registry.read_pyi(name)
        data["pyi_content"] = pyi[:50000]
    except Exception:  # noqa: BLE001, S110
        pass

    if _is_htmx_request(request):
        html_content = (
            f"<div id='server-detail'><pre>{_e(json.dumps(data, indent=2))}</pre></div>"
        )
        return HTMLResponse(html_content)
    return JSONResponse(data)


async def handle_create(request: Request) -> JSONResponse | HTMLResponse:
    registry: Registry = request.app.state.registry  # type: ignore[attr-defined]

    ctype = request.headers.get("content-type", "")
    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > MAX_PAYLOAD_SIZE:
        if _is_htmx_request(request):
            html_content = (
                f"<div class='toast bg-red-100 p-2'>{_e('payload too large')}</div>"
            )
            return HTMLResponse(html_content, status_code=413)
        return JSONResponse({"detail": "payload too large"}, status_code=413)

    payload: dict[str, Any]
    if "application/json" in ctype:
        try:
            body_bytes = await request.body()
        except Exception:  # noqa: BLE001
            body_bytes = b""
        if len(body_bytes) > MAX_PAYLOAD_SIZE:
            if _is_htmx_request(request):
                html_content = (
                    f"<div class='toast bg-red-100 p-2'>{_e('payload too large')}</div>"
                )
                return HTMLResponse(html_content, status_code=413)
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        try:
            payload = json.loads(body_bytes.decode("utf-8") if body_bytes else "{}")
            if not isinstance(payload, dict):
                raise TypeError("payload must be object")
        except Exception:  # noqa: BLE001
            if _is_htmx_request(request):
                html_content = (
                    f"<div class='toast bg-red-100 p-2'>{_e('Invalid JSON')}</div>"
                )
                return HTMLResponse(html_content, status_code=400)
            return JSONResponse({"detail": "Invalid JSON"}, status_code=400)
    else:
        try:
            form = await request.form()
            payload = dict(form)  # type: ignore[arg-type]
            try:
                if len(json.dumps(payload, default=str)) > MAX_PAYLOAD_SIZE:
                    if _is_htmx_request(request):
                        html_content = f"<div class='toast bg-red-100 p-2'>{_e('payload too large')}</div>"
                        return HTMLResponse(html_content, status_code=413)
                    return JSONResponse(
                        {"detail": "payload too large"}, status_code=413
                    )
            except Exception:  # noqa: BLE001, S110
                pass
            for key in ("headers", "environment"):
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    try:
                        parsed = json.loads(val)
                        if isinstance(parsed, dict):
                            payload[key] = parsed
                    except Exception:  # noqa: BLE001, S110
                        pass
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
                if val.startswith("["):
                    try:
                        parsed_cmd = json.loads(val)
                        if isinstance(parsed_cmd, list):
                            payload["command"] = parsed_cmd
                    except Exception:  # noqa: BLE001, S110
                        pass
        except Exception:  # noqa: BLE001
            if _is_htmx_request(request):
                html_content = (
                    f"<div class='toast bg-red-100 p-2'>{_e('Invalid form data')}</div>"
                )
                return HTMLResponse(html_content, status_code=400)
            return JSONResponse({"detail": "Invalid form data"}, status_code=400)

    name = payload.get("name")
    if not name:
        if _is_htmx_request(request):
            html_content = (
                f"<div class='toast bg-red-100 p-2'>{_e('name required')}</div>"
            )
            return HTMLResponse(html_content, status_code=400)
        return JSONResponse({"detail": "name required"}, status_code=400)

    try:
        config = MCPServerConfig(**payload)
    except ValidationError as e:
        sanitized = re.sub(r"[^A-Za-z0-9_.-]", "_", str(payload.get("name", ""))[:50])
        logger.warning(
            "validation error for create name=%s type=%s", sanitized, type(e).__name__
        )
        detail_lower = str(e).lower()
        if "url" in detail_lower and payload.get("type") == "remote":
            detail = "'url' required for type=remote"
            if _is_htmx_request(request):
                html_content = f"<div class='toast bg-red-100 p-2'>{_e(detail)}</div>"
                return HTMLResponse(html_content, status_code=400)
            return JSONResponse({"detail": detail}, status_code=400)
        if "command" in detail_lower and payload.get("type") == "local":
            detail = "'command' required for type=local"
            if _is_htmx_request(request):
                html_content = f"<div class='toast bg-red-100 p-2'>{_e(detail)}</div>"
                return HTMLResponse(html_content, status_code=400)
            return JSONResponse({"detail": detail}, status_code=400)
        detail = "invalid request"
        if _is_htmx_request(request):
            html_content = f"<div class='toast bg-red-100 p-2'>{_e(detail)}</div>"
            return HTMLResponse(html_content, status_code=400)
        return JSONResponse(
            {"detail": detail, "code": "validation_error"}, status_code=400
        )
    except ValueError as e:
        sanitized = re.sub(r"[^A-Za-z0-9_.-]", "_", str(payload.get("name", ""))[:50])
        logger.warning(
            "value error for create name=%s: %s", sanitized, type(e).__name__
        )
        msg = str(e).lower()
        if "url" in msg:
            detail = "'url' required for type=remote"
            if _is_htmx_request(request):
                html_content = f"<div class='toast bg-red-100 p-2'>{_e(detail)}</div>"
                return HTMLResponse(html_content, status_code=400)
            return JSONResponse({"detail": detail}, status_code=400)
        if "command" in msg:
            detail = "'command' required for type=local"
            if _is_htmx_request(request):
                html_content = f"<div class='toast bg-red-100 p-2'>{_e(detail)}</div>"
                return HTMLResponse(html_content, status_code=400)
            return JSONResponse({"detail": detail}, status_code=400)
        detail = "invalid request"
        if _is_htmx_request(request):
            html_content = f"<div class='toast bg-red-100 p-2'>{_e(detail)}</div>"
            return HTMLResponse(html_content, status_code=400)
        return JSONResponse(
            {"detail": detail, "code": "validation_error"}, status_code=400
        )

    if (
        config.type == "local"
        and os.environ.get("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "1") != "1"
    ):
        detail = "local servers not allowed via dashboard"
        if _is_htmx_request(request):
            html_content = f"<div class='toast bg-red-100 p-2'>{_e(detail)}</div>"
            return HTMLResponse(html_content, status_code=403)
        return JSONResponse({"detail": detail}, status_code=403)

    existing_names = set(registry.list())
    try:
        json_exists = registry._safe_path(config.name, ".json").exists()  # type: ignore[attr-defined]
    except ValueError:
        detail = "invalid request"
        if _is_htmx_request(request):
            html_content = f"<div class='toast bg-red-100 p-2'>{_e(detail)}</div>"
            return HTMLResponse(html_content, status_code=400)
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
            html_content = f"<div class='toast bg-red-100 p-2'>{_e(msg)}</div>"
            return HTMLResponse(html_content, status_code=409)
        return JSONResponse({"detail": msg}, status_code=409)

    tools: list[Any] = []
    try:
        from mcp_gway.cli import _discover_tools as cli_discover

        try:
            async with _discovery_sem:
                tools = await asyncio.wait_for(
                    cli_discover(config),
                    timeout=(config.timeout / 1000 + 1) if config.timeout else 6,
                )
        except TimeoutError:  # noqa: S110
            tools = []
        except Exception:  # noqa: BLE001, S110
            tools = []
    except Exception:  # noqa: BLE001, S110
        tools = []

    try:
        registry.add(config, tools)  # type: ignore[arg-type]
    except ValueError:
        detail = "invalid request"
        if _is_htmx_request(request):
            html_content = f"<div class='toast bg-red-100 p-2'>{_e(detail)}</div>"
            return HTMLResponse(html_content, status_code=400)
        return JSONResponse(
            {"detail": detail, "code": "validation_error"}, status_code=400
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("registry add failed: %s", type(e).__name__)
        return JSONResponse(
            {"detail": "Corrupt config, remove and re-add"}, status_code=500
        )

    tool_count = len(tools)
    if _is_htmx_request(request):
        servers: list[dict[str, Any]] = []
        for n in registry.list():
            try:
                d = _server_to_dict(registry, n)
                if d:
                    servers.append(d)
            except Exception:  # noqa: BLE001, S112
                continue
        html_content = str(server_table(servers))
        if tool_count == 0:
            html_content += "<div id='toast' hx-swap-oob='true' class='bg-yellow-100 p-2'>No tools discovered</div>"
        return HTMLResponse(html_content, status_code=201)

    return JSONResponse(
        {"name": config.name, "tool_count": tool_count}, status_code=201
    )
