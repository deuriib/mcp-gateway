"""Transport shim — re-exports core transport detection."""

from __future__ import annotations

from mcp_gway.core.transport import (
    _try_http,
    _try_sse,
    _try_streamable_http,
    detect_transport,
)

__all__ = ["_try_http", "_try_sse", "_try_streamable_http", "detect_transport"]
