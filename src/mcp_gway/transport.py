"""Transport shim — re-exports core transport detection.

Deprecated: use ``mcp_gway.core.transport`` directly. This shim is kept
for backward compatibility and will be removed in a future major version.
"""

from __future__ import annotations

import warnings as _warnings

from mcp_gway.core.transport import (
    _try_http as _core_try_http,
)
from mcp_gway.core.transport import (
    _try_sse as _core_try_sse,
)
from mcp_gway.core.transport import (
    _try_streamable_http as _core_try_streamable_http,
)
from mcp_gway.core.transport import (
    detect_transport as _core_detect_transport,
)


def _warn() -> None:
    _warnings.warn(
        "mcp_gway.transport is deprecated, use mcp_gway.core.transport",
        DeprecationWarning,
        stacklevel=3,
    )


async def _try_http(
    url: str, timeout: int = 5000, headers: dict[str, str] | None = None
) -> bool:  # type: ignore[no-untyped-def]
    _warn()
    return await _core_try_http(url, timeout, headers)


async def _try_sse(
    url: str, timeout: int = 5000, headers: dict[str, str] | None = None
) -> bool:  # type: ignore[no-untyped-def]
    _warn()
    return await _core_try_sse(url, timeout, headers)


async def _try_streamable_http(
    url: str, timeout: int = 5000, headers: dict[str, str] | None = None
) -> bool:  # type: ignore[no-untyped-def]
    _warn()
    return await _core_try_streamable_http(url, timeout, headers)


async def detect_transport(config):  # type: ignore[no-untyped-def]
    _warn()
    return await _core_detect_transport(config)


__all__ = ["_try_http", "_try_sse", "_try_streamable_http", "detect_transport"]
