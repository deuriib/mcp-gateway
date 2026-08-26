from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

_SAN_RE = re.compile(r"[^A-Za-z0-9_-]")


def sanitize_request_id(value: str) -> str:
    s = _SAN_RE.sub("-", value.strip())[:64]
    s = s.strip("-")
    return s if s else "unknown"


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rid = getattr(record, "request_id", None)
        if rid is None:
            rid = request_id_ctx.get()
        timestamp = (
            datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )
        payload: dict[str, object] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": rid,
        }
        for key in ("method", "path", "status", "duration_ms", "server", "tool"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def _level_from_str(level: str) -> int:
    mapping = {
        "trace": logging.DEBUG,
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "warn": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    return mapping.get(level.strip().lower(), logging.INFO)


def setup_logging(level: str) -> None:
    py_level = _level_from_str(level)
    logger = logging.getLogger("mcp_gway")
    logger.setLevel(py_level)
    has_json = any(
        isinstance(getattr(h, "formatter", None), JSONFormatter)
        for h in logger.handlers
    )
    if has_json:
        for handler in logger.handlers:
            handler.setLevel(py_level)
        return
    handler = logging.StreamHandler()
    handler.setLevel(py_level)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    if not logger.handlers:
        return
    # Ensure uvicorn loggers also use level but not formatter
    for name in ("uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.setLevel(py_level)
