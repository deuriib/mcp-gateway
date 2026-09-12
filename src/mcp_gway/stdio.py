"""Server-side NDJSON transport for `mcp-gway serve --transport stdio` (stdin/stdout).

This module is the **server side**: it reads JSON-RPC 2.0 requests as NDJSON
from stdin and writes one JSON response per line to stdout. Invoked as
``mcp-gway serve --transport stdio`` (default) and usable as an OpenCode
``type: local`` server with ``command: [mcp-gway, serve, --transport, stdio]``.
``mcp-gway mcp`` remains as a deprecated hidden alias.

Contrast with :mod:`mcp_gway.stdio_transport` which is the **client side**:
``filtered_stdio_client`` connects *to* child MCP servers and filters noise
from their stdout. Do not confuse the two — this file never spawns children
and never opens sockets.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, TextIO

# 1 MiB per-line cap: stdin here is a local trust-boundary (same user /
# parent process, not remote network). Reads are bounded incrementally
# (never an unbounded readline) and whole-line length is re-checked in
# handle_line before json.loads.
MAX_LINE_BYTES = 1_048_576

_READ_CHUNK = 8_192


def _error(code: int, message: str, req_id: Any = None) -> str:
    return json.dumps(
        {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}},
        ensure_ascii=False,
    )


class StdioAdapter:
    """Adapt Gateway JSON-RPC handlers to NDJSON over stdio."""

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    async def handle_line(self, raw: str | bytes) -> str | None:
        """Process one NDJSON line, returning a JSON line or None."""
        if isinstance(raw, bytes):
            if len(raw) > MAX_LINE_BYTES:
                return _error(-32700, "Parse error")
            try:
                text = raw.decode("utf-8")
            except Exception:
                return _error(-32700, "Parse error")
        else:
            if len(raw.encode("utf-8", errors="ignore")) > MAX_LINE_BYTES:
                return _error(-32700, "Parse error")
            text = raw
        if not text.strip():
            return None
        try:
            body = json.loads(text)
        except Exception:
            return _error(-32700, "Parse error")
        if isinstance(body, list):
            return _error(-32600, "Invalid Request")
        if not isinstance(body, dict):
            return _error(-32600, "Invalid Request")
        method = body.get("method")
        has_id = "id" in body
        req_id = body.get("id")
        if not isinstance(method, str):
            if not has_id:
                return None
            return _error(-32600, "Invalid Request", req_id)
        if not has_id:
            if method.startswith("notifications/"):
                try:
                    self._gateway._handle_method(
                        method,
                        body.get("params", {})
                        if isinstance(body.get("params", {}), dict)
                        else {},
                    )
                except Exception:
                    pass
            return None
        params = body.get("params", {})
        if not isinstance(params, dict):
            return _error(-32602, "Invalid params", req_id)
        response = await self._gateway._handle_post(body, session_id=None)
        if not isinstance(response, dict):
            return _error(-32603, "Internal error", req_id)
        response.setdefault("jsonrpc", "2.0")
        response.setdefault("id", req_id)
        return json.dumps(response, ensure_ascii=False)


class _CappedLineReader:
    """Bounded NDJSON line reader using ``readline`` framing.

    Uses ``stdin.readline(limit)`` so one call returns at most one
    ``\\n``-terminated line and returns promptly after the newline —
    never blocking for more bytes than the current line holds. If the
    line exceeds ``MAX_LINE_BYTES``, the remainder is discarded in
    bounded chunks and the call reports ``overlong=True`` so the caller
    can emit ``-32700`` without OOM. Extra bytes are never buffered
    beyond the current line, preserving framing.
    """

    def __init__(self, stdin: Any) -> None:
        self._stdin = stdin
        try:
            probe = stdin.read(0)
            self._binary = isinstance(probe, (bytes, bytearray))
        except Exception:
            self._binary = False

    def _byte_len(self, data: Any) -> int:
        if isinstance(data, (bytes, bytearray)):
            return len(data)
        return len(data.encode("utf-8", errors="ignore"))

    def _readline(self, limit: int) -> Any:
        readline = getattr(self._stdin, "readline", None)
        if callable(readline):
            return readline(limit)
        data = self._stdin.read(limit)
        if not isinstance(data, (str, bytes, bytearray)):
            raise TypeError(f"unexpected read type: {type(data).__name__}")
        return data

    def readline_capped(self) -> tuple[Any | None, bool, bool]:
        """Return ``(line, overlong, eof)``.

        ``line`` is ``str``/``bytes`` (with trailing newline when present),
        ``overlong`` means the line exceeded ``MAX_LINE_BYTES`` and was
        discarded, ``eof`` with ``line is None`` means clean EOF.
        """
        nl: Any = b"\n" if self._binary else "\n"
        try:
            line = self._readline(MAX_LINE_BYTES + 2)
        except TypeError:
            return None, False, True
        except Exception:
            return None, False, True
        if line == "" or line == b"":
            return None, False, True
        if not isinstance(line, (str, bytes, bytearray)):
            return None, False, True
        if line.endswith(nl):
            if self._byte_len(line) > MAX_LINE_BYTES:
                return None, True, False
            return line, False, False
        if self._byte_len(line) <= MAX_LINE_BYTES:
            return line, False, False
        try:
            while True:
                try:
                    nxt = self._readline(MAX_LINE_BYTES + 2)
                except Exception:
                    break
                if nxt == "" or nxt == b"":
                    break
                if not isinstance(nxt, (str, bytes, bytearray)):
                    break
                if nxt.endswith(nl):
                    break
        except Exception:
            pass
        return None, True, False


async def run_stdio_async(
    gateway: Any,
    stdin: TextIO | Any,
    stdout: TextIO | Any,
    stderr: TextIO | Any = sys.stderr,
) -> int:
    """Run NDJSON loop until EOF, returning exit code 0.

    Contract: only JSON-RPC lines are written to ``stdout`` (one JSON
    object per line). All human/operator logs go to ``stderr`` or the
    ``mcp_gway`` logger (configured to stderr). Never opens sockets.
    """
    logger = logging.getLogger("mcp_gway.stdio")
    reader = _CappedLineReader(stdin)
    adapter = StdioAdapter(gateway)
    while True:
        try:
            line, overlong, eof = reader.readline_capped()
        except Exception:
            logger.debug("readline_capped failed", exc_info=True)
            break
        if eof and line is None:
            break
        if overlong:
            out: str | None = _error(-32700, "Parse error")
        elif line is None:
            break
        else:
            try:
                out = await adapter.handle_line(line)
            except Exception:
                logger.debug("handle_line failed", exc_info=True)
                try:
                    body = json.loads(line)
                except Exception:
                    continue
                if isinstance(body, dict) and body.get("id") is not None:
                    try:
                        stdout.write(
                            _error(-32603, "Internal error", body.get("id")) + "\n"
                        )
                        stdout.flush()
                    except BrokenPipeError:
                        try:
                            print("stdio broken pipe, exiting 0", file=stderr)
                        except Exception:
                            pass
                        return 0
                    except Exception:
                        logger.debug("stdout write failed", exc_info=True)
                continue
        if out is not None:
            try:
                stdout.write(out + "\n")
                stdout.flush()
            except BrokenPipeError:
                try:
                    print("stdio broken pipe, exiting 0", file=stderr)
                except Exception:
                    pass
                return 0
            except Exception:
                logger.debug("stdout write failed", exc_info=True)
    return 0
