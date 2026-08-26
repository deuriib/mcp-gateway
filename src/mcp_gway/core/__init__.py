"""Core package — single source of truth for transport/discovery (OpenCode-only)."""

from __future__ import annotations

from mcp_gway.core.client import (
    create_client_transport,
    discover_tools,
    refresh_server,
)
from mcp_gway.core.parsing import parse_envs, parse_headers
from mcp_gway.core.transport import detect_transport

__all__ = [
    "create_client_transport",
    "detect_transport",
    "discover_tools",
    "parse_envs",
    "parse_headers",
    "refresh_server",
]
