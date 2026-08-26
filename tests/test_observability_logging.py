from __future__ import annotations

import io
import json
import logging

from mcp_gway.observability.logging import (
    JSONFormatter,
    request_id_ctx,
    sanitize_request_id,
    setup_logging,
)


def test_json_formatter_shape() -> None:
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(JSONFormatter())
    lg = logging.getLogger("mcp_gway.test.shape")
    lg.handlers = [h]
    lg.setLevel(logging.INFO)
    lg.propagate = False
    request_id_ctx.set("r-123")
    try:
        lg.info("hello")
        line = buf.getvalue().strip()
        data = json.loads(line)
        assert "timestamp" in data
        assert "level" in data
        assert data["level"] == "INFO"
        assert data["logger"] == "mcp_gway.test.shape"
        assert data["message"] == "hello"
        assert data["request_id"] == "r-123"
        assert data["timestamp"].endswith("Z")
    finally:
        request_id_ctx.set(None)
        lg.handlers = []


def test_json_formatter_uses_extra_request_id_over_context() -> None:
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(JSONFormatter())
    lg = logging.getLogger("mcp_gway.test.extra")
    lg.handlers = [h]
    lg.setLevel(logging.INFO)
    lg.propagate = False
    request_id_ctx.set("ctx-id")
    try:
        lg.info("hello", extra={"request_id": "extra-id"})
        data = json.loads(buf.getvalue().strip())
        assert data["request_id"] == "extra-id"
    finally:
        request_id_ctx.set(None)
        lg.handlers = []


def test_json_formatter_includes_whitelisted_extras() -> None:
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(JSONFormatter())
    lg = logging.getLogger("mcp_gway.test.extras")
    lg.handlers = [h]
    lg.setLevel(logging.INFO)
    lg.propagate = False
    try:
        lg.info(
            "hello",
            extra={
                "method": "GET",
                "path": "/health",
                "status": 200,
                "duration_ms": 42,
            },
        )
        data = json.loads(buf.getvalue().strip())
        assert data["method"] == "GET"
        assert data["path"] == "/health"
        assert data["status"] == 200
        assert data["duration_ms"] == 42
    finally:
        lg.handlers = []


def test_sanitize_truncates_and_strips_crlf() -> None:
    assert "\n" not in sanitize_request_id("a\nb")
    assert "\r" not in sanitize_request_id("a\rb")
    assert len(sanitize_request_id("x" * 5000)) <= 64


def test_sanitize_filters_invalid_chars_and_respects_length() -> None:
    result = sanitize_request_id("a\nb\r\x00" + "x" * 5000)
    assert "\n" not in result
    assert "\r" not in result
    assert "\x00" not in result
    assert len(result) <= 64
    # must be allowed charset
    import re

    assert re.match(r"^[A-Za-z0-9_-]{1,64}$", result)


def test_sanitize_empty_returns_unknown() -> None:
    assert sanitize_request_id("") == "unknown"
    assert sanitize_request_id("---") == "unknown"


def test_setup_logging_idempotent() -> None:
    setup_logging("info")
    setup_logging("info")
    logger = logging.getLogger("mcp_gway")
    count = sum(
        1
        for h in logger.handlers
        if isinstance(getattr(h, "formatter", None), JSONFormatter)
    )
    assert count == 1


def test_json_formatter_valid_json_per_line() -> None:
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(JSONFormatter())
    lg = logging.getLogger("mcp_gway.test.jsonline")
    lg.handlers = [h]
    lg.setLevel(logging.INFO)
    lg.propagate = False
    try:
        lg.info("line1")
        lg.warning("line2")
        lines = [line for line in buf.getvalue().strip().splitlines() if line]
        for line in lines:
            data = json.loads(line)
            assert "timestamp" in data
            assert "level" in data
    finally:
        lg.handlers = []
