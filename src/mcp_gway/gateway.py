"""HTTP/SSE gateway server for MCP protocol."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from mcp_gway import __version__
from mcp_gway.code_mode import CodeMode
from mcp_gway.dashboard.routes import get_dashboard_routes
from mcp_gway.observability.health import (
    handle_health,
    handle_live,
    handle_metrics,
    handle_ready,
)
from mcp_gway.observability.metrics import MetricsRegistry
from mcp_gway.observability.middleware import (
    CorrelationMiddleware,
    LoggingMiddleware,
    MetricsMiddleware,
)
from mcp_gway.registry import Registry


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response


class _CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            path = request.url.path
            if path.startswith(("/api/", "/dashboard")):
                hx = request.headers.get("HX-Request") or request.headers.get(
                    "hx-request"
                )
                origin = request.headers.get("origin") or request.headers.get("Origin")
                referer = request.headers.get("referer") or request.headers.get(
                    "Referer"
                )
                if hx == "true":
                    pass
                elif origin:
                    try:
                        from urllib.parse import urlparse

                        o_host = urlparse(origin).hostname or ""
                        req_host = request.url.hostname or ""
                        host_hdr = request.headers.get("host", "")
                        allowed = {req_host, host_hdr.split(":")[0] if host_hdr else ""}
                        allowed.update(
                            {"127.0.0.1", "localhost", "::1", "test", "testserver"}
                        )
                        if o_host and o_host not in allowed and o_host != req_host:
                            return JSONResponse(
                                {"detail": "CSRF check failed"}, status_code=403
                            )
                    except Exception:
                        return JSONResponse(
                            {"detail": "CSRF check failed"}, status_code=403
                        )
                elif referer:
                    try:
                        from urllib.parse import urlparse

                        r_host = urlparse(referer).hostname or ""
                        req_host = request.url.hostname or ""
                        host_hdr = request.headers.get("host", "")
                        allowed = {req_host, host_hdr.split(":")[0] if host_hdr else ""}
                        allowed.update(
                            {"127.0.0.1", "localhost", "::1", "test", "testserver"}
                        )
                        if r_host and r_host not in allowed and r_host != req_host:
                            return JSONResponse(
                                {"detail": "CSRF check failed"}, status_code=403
                            )
                    except Exception:
                        return JSONResponse(
                            {"detail": "CSRF check failed"}, status_code=403
                        )
                else:
                    pass
        return await call_next(request)


class _CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith(("/dashboard", "/static")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "script-src-elem 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "style-src-elem 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "connect-src 'self'; "
                "font-src 'self' data:"
            )
        else:
            response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response


CODE_MODE_TOOLS = [
    {
        "name": "listToolFiles",
        "description": "See every registered server in one place so you find the right capability instantly.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "readToolFile",
        "description": "Peek inside any server to see its tools and how to call them correctly.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fileName": {
                    "type": "string",
                    "description": "Server to preview — e.g., youtube or servers/youtube.pyi",
                },
                "startLine": {
                    "type": "integer",
                    "description": "Where to start reading — useful for large servers (leave empty for full view).",
                },
                "endLine": {
                    "type": "integer",
                    "description": "Where to stop reading — useful for large servers (leave empty for full view).",
                },
            },
            "required": ["fileName"],
        },
    },
    {
        "name": "getToolDocs",
        "description": "Get the full details on any tool — what it needs and what it returns — so you build the right call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {
                    "type": "string",
                    "description": "The server that owns the tool, like youtube",
                },
                "tool": {
                    "type": "string",
                    "description": "The tool you want to explore, like searchVideos",
                },
            },
            "required": ["server", "tool"],
        },
    },
    {
        "name": "executeToolCode",
        "description": 'Run and chain one or many tools together — just use call_tool("server-name", "tool-name", param1="value1", param2="value2") and put your answer in result.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": 'Code that calls tools with result = call_tool("server-name", "tool-name", param1="value1", param2="value2") — set result to your final answer',
                }
            },
            "required": ["code"],
        },
    },
]


@dataclass
class SessionInfo:
    queue: asyncio.Queue[dict[str, Any]]
    last_activity: float = field(default_factory=time.monotonic)


class Gateway:
    def __init__(self, registry: Registry, host: str = "127.0.0.1") -> None:
        self.registry = registry
        self.host = host
        self.code_mode = CodeMode(registry)
        self._sessions: dict[str, SessionInfo] = {}
        self.start_time: float = time.monotonic()
        self._last_loop_tick: float = time.monotonic()
        self.metrics = MetricsRegistry()
        # pre-register common metrics
        self.metrics.counter(
            "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
        )
        self.metrics.histogram(
            "http_request_duration_seconds", "HTTP request latency", ["path"]
        )
        self.metrics.counter(
            "mcp_tool_calls_total",
            "MCP tool call count by server/tool/status",
            ["server", "tool", "status"],
        )
        self.metrics.histogram(
            "discovery_duration_seconds", "Discovery latency", ["server"]
        )
        self.metrics.counter("sandbox_execute_total", "Sandbox executions", ["status"])
        self.metrics.histogram(
            "sandbox_duration_seconds", "Sandbox duration", ["status"]
        )
        self.metrics.counter(
            "registry_operations_total", "Registry add/remove/update counts", ["op"]
        )
        self.metrics.gauge("gateway_sessions_active", "Current SSE sessions", [])
        registry.ensure()
        try:
            registry._metrics = self.metrics  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            self.code_mode.sandbox._metrics = self.metrics  # type: ignore[attr-defined]
        except Exception:
            pass
        dashboard_routes = get_dashboard_routes(registry)
        self.app = Starlette(
            routes=[
                Route("/health", self._health, methods=["GET"]),
                Route("/ready", handle_ready, methods=["GET"]),
                Route("/live", handle_live, methods=["GET"]),
                Route("/metrics", handle_metrics, methods=["GET"]),
                Route("/mcp", self._mcp_sse, methods=["GET"]),
                Route("/mcp", self._mcp_post, methods=["POST"]),
                Route("/mcp/messages", self._mcp_post, methods=["POST"]),
                *dashboard_routes,
            ]
        )
        # order outer→inner: Correlation→Metrics→Logging→CSP/Security/CSRF
        # Starlette last added = outermost, so add innermost first
        self.app.add_middleware(_CSPMiddleware)
        self.app.add_middleware(_SecurityHeadersMiddleware)
        self.app.add_middleware(_CSRFMiddleware)
        self.app.add_middleware(LoggingMiddleware)
        self.app.add_middleware(MetricsMiddleware, registry=self.metrics)
        self.app.add_middleware(CorrelationMiddleware)
        self.app.state.registry = registry  # type: ignore[attr-defined]
        self.app.state.dashboard_host = host  # type: ignore[attr-defined]
        self.app.state.metrics = self.metrics  # type: ignore[attr-defined]
        self.app.state.gateway = self  # type: ignore[attr-defined]
        self.app.state.start_time = self.start_time  # type: ignore[attr-defined]
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._heartbeat())
        except RuntimeError:
            pass

    def _create_session(self, session_id: str) -> SessionInfo:
        info = SessionInfo(queue=asyncio.Queue())
        self._sessions[session_id] = info
        try:
            self.metrics.set("gateway_sessions_active", float(len(self._sessions)), {})
        except Exception:
            pass
        return info

    def cleanup_expired_sessions(self, max_idle_seconds: float = 300.0) -> int:
        now = time.monotonic()
        expired = [
            sid
            for sid, info in self._sessions.items()
            if now - info.last_activity > max_idle_seconds
        ]
        for sid in expired:
            info = self._sessions.pop(sid)
            info.queue.put_nowait(None)
        if expired:
            try:
                self.metrics.set(
                    "gateway_sessions_active", float(len(self._sessions)), {}
                )
            except Exception:
                pass
        return len(expired)

    async def _handle_post(
        self, body: dict[str, Any], *, session_id: str | None = None
    ) -> dict[str, Any]:
        method = body.get("method")
        req_id = body.get("id")
        params = body.get("params", {})

        if session_id and session_id not in self._sessions:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32001, "message": "Session not found or expired"},
            }

        try:
            result = self._handle_method(method, params)
            response = {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as e:
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -1, "message": str(e)},
            }

        if session_id and session_id in self._sessions:
            info = self._sessions[session_id]
            info.last_activity = time.monotonic()
            await info.queue.put(response)

        return response

    async def _heartbeat(self) -> None:
        while True:
            self._last_loop_tick = time.monotonic()
            await asyncio.sleep(1)

    async def _health(self, request: Request) -> JSONResponse:
        return await handle_health(request)

    async def _mcp_sse(self, request: Request) -> StreamingResponse:
        session_id = str(uuid.uuid4())
        info = self._create_session(session_id)

        async def event_stream():
            try:
                yield f"event: endpoint\ndata: /mcp/messages?session_id={session_id}\n\n"
                while True:
                    msg = await info.queue.get()
                    if msg is None:
                        break
                    yield f"event: message\ndata: {json.dumps(msg)}\n\n"
            finally:
                self._sessions.pop(session_id, None)
                try:
                    self.metrics.set(
                        "gateway_sessions_active", float(len(self._sessions)), {}
                    )
                except Exception:
                    pass

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def _mcp_post(self, request: Request) -> JSONResponse:
        session_id = request.query_params.get("session_id")
        body = await self._read_limited_json(request)
        if isinstance(body, JSONResponse):
            return body
        response = await self._handle_post(body, session_id=session_id)
        return JSONResponse(response)

    async def _read_limited_json(
        self, request: Request
    ) -> dict[str, Any] | JSONResponse:
        clen = request.headers.get("content-length")
        if clen and clen.isdigit() and int(clen) > 1_048_576:
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        body = b""
        async for chunk in request.stream():
            body += chunk
            if len(body) > 1_048_576:
                return JSONResponse({"detail": "payload too large"}, status_code=413)
        try:
            return json.loads(body.decode("utf-8") if body else "{}")
        except Exception:
            return JSONResponse({"detail": "Invalid JSON"}, status_code=400)

    def _handle_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mcp-gway", "version": __version__},
            }
        if method == "notifications/initialized":
            return {}
        if method == "tools/list":
            return {"tools": CODE_MODE_TOOLS}
        if method == "tools/call":
            return self._handle_tool_call(params)
        raise ValueError(f"Unknown method: {method}")

    def _handle_tool_call(self, params: dict[str, Any]) -> dict[str, Any]:
        import re

        name = params.get("name")
        arguments = params.get("arguments", {})

        # Instrumentation helper: sanitize labels
        def _san(v: str) -> str:
            s = re.sub(r"[^A-Za-z0-9_]", "_", v)[:32]
            return s.strip("_") or "_other"

        status = "ok"
        server_label = "gateway"
        tool_label = _san(str(name)) if name else "_other"
        # For executeToolCode we could try to parse server from code, but keep gateway
        try:
            if name == "listToolFiles":
                result = self.code_mode.list_tool_files()
            elif name == "readToolFile":
                result = self.code_mode.read_tool_file(
                    fileName=arguments["fileName"],
                    startLine=arguments.get("startLine"),
                    endLine=arguments.get("endLine"),
                )
            elif name == "getToolDocs":
                # server label from arguments
                try:
                    server_label = _san(str(arguments.get("server", "gateway")))
                    tool_label = _san(str(arguments.get("tool", str(name))))
                except Exception:
                    pass
                result = self.code_mode.get_tool_docs(
                    server=arguments["server"], tool=arguments["tool"]
                )
            elif name == "executeToolCode":
                result = self.code_mode.execute_tool_code(code=arguments["code"])
            else:
                status = "error"
                raise ValueError(f"Unknown tool: {name}")
            # success path
            try:
                self.metrics.inc(
                    "mcp_tool_calls_total",
                    {"server": server_label, "tool": tool_label, "status": status},
                )
            except Exception:
                pass
            return {"content": [{"type": "text", "text": result}]}
        except Exception:
            # record error if not already
            if status != "error":
                status = "error"
                try:
                    self.metrics.inc(
                        "mcp_tool_calls_total",
                        {"server": server_label, "tool": tool_label, "status": status},
                    )
                except Exception:
                    pass
            raise
