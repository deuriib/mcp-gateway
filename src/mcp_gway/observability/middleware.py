from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from mcp_gway.observability.logging import request_id_ctx, sanitize_request_id
from mcp_gway.observability.metrics import MetricsRegistry

logger = logging.getLogger(__name__)


def _get_request_id(request: Request) -> str:
    raw = request.headers.get("X-Request-ID") or request.headers.get("x-request-id")
    if not raw:
        raw = request.headers.get("X-Correlation-ID") or request.headers.get(
            "x-correlation-id"
        )
    if raw:
        sanitized = sanitize_request_id(raw)
        if sanitized != "unknown":
            return sanitized
    return uuid.uuid4().hex


def path_template(path: str) -> str:
    if path.startswith("/api/servers/"):
        # /api/servers, /api/servers/{name}, /api/servers/{name}/refresh etc
        # Normalize to /api/servers or /api/servers/{name} or /api/servers/{name}/refresh etc but bound cardinality
        # For metrics we want to template the name segment
        # Patterns: /api/servers/{name}, /api/servers/{name}/refresh, /api/servers/{name}/reveal, /api/servers/{name}/oauth/start, /api/servers/{name}/oauth/status
        # Also /dashboard/servers/{name}
        # Simple: if path == /api/servers -> keep, if path starts with /api/servers/<something> -> map first segment after to {name}
        remainder = path[len("/api/servers/") :]
        if not remainder:
            return "/api/servers"
        parts = remainder.split("/")
        # parts[0] is name
        if len(parts) == 1:
            return "/api/servers/{name}"
        # more segments
        suffix = "/".join(parts[1:])
        # keep suffix literal but with name templated
        # e.g., refresh, reveal, oauth/start
        # For oauth we need to bound: /api/servers/{name}/oauth/start -> keep as is with {name}
        return f"/api/servers/{{name}}/{suffix}"
    if path.startswith("/dashboard/servers/"):
        remainder = path[len("/dashboard/servers/") :]
        if not remainder:
            return "/dashboard/servers"
        parts = remainder.split("/")
        if len(parts) == 1:
            return "/dashboard/servers/{name}"
        return f"/dashboard/servers/{{name}}/{'/'.join(parts[1:])}"
    if path.startswith("/mcp"):
        # keep as /mcp or /mcp/messages
        if path.startswith("/mcp/messages"):
            return "/mcp/messages"
        return "/mcp"
    return path


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        rid = _get_request_id(request)
        token = request_id_ctx.set(rid)
        request.state.request_id = rid  # type: ignore[attr-defined]
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            request_id_ctx.reset(token)


class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, registry: MetricsRegistry) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.registry = registry
        # ensure metrics exist
        self.registry.counter(
            "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
        )
        self.registry.histogram(
            "http_request_duration_seconds", "HTTP request latency", ["path"]
        )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration = time.perf_counter() - start
            status = str(response.status_code) if response is not None else "500"
            method = request.method
            tmpl = path_template(request.url.path)
            # sanitize method? keep as is
            try:
                self.registry.inc(
                    "http_requests_total",
                    {"method": method, "path": tmpl, "status": status},
                )
                self.registry.observe(
                    "http_request_duration_seconds", duration, {"path": tmpl}
                )
            except Exception:
                # never break request
                pass


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        rid = getattr(request.state, "request_id", None) or request_id_ctx.get() or "-"
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        # Use logger with extra fields for JSONFormatter
        extra = {
            "request_id": rid,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        }
        # Log at INFO, but avoid logging health probes too verbosely? We log all
        logger.info("request completed", extra=extra)
        return response


_SANITIZE_LABEL_RE = re.compile(r"[^A-Za-z0-9_]")


def sanitize_label(value: str) -> str:
    s = _SANITIZE_LABEL_RE.sub("_", value)[:32]
    return s.strip("_") or "_other"
