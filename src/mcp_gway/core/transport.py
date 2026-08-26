"""Transport auto-detection for remote MCP servers (OpenCode-only)."""

from __future__ import annotations

import asyncio
from typing import Literal

from mcp_gway.models import MCPServerConfig


async def _try_streamable_http(
    url: str, timeout: int = 5000, headers: dict[str, str] | None = None
) -> bool:
    try:
        from mcp.client.streamable_http import streamable_http_client

        async with asyncio.timeout(timeout / 1000):
            if headers:
                import httpx

                async with httpx.AsyncClient(headers=headers) as hc:
                    async with streamable_http_client(url, http_client=hc) as (
                        read,
                        write,
                    ):
                        return True
            else:
                async with streamable_http_client(url) as (read, write):  # noqa: RUF059
                    return True
    except Exception:
        return False


async def _try_sse(
    url: str, timeout: int = 5000, headers: dict[str, str] | None = None
) -> bool:
    try:
        from mcp.client.sse import sse_client

        async with asyncio.timeout(timeout / 1000):
            async with sse_client(url, headers=headers) as (read, write):  # noqa: RUF059
                return True
    except Exception:
        return False


async def _try_http(
    url: str, timeout: int = 5000, headers: dict[str, str] | None = None
) -> bool:
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout / 1000, headers=headers) as client:
            response = await client.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )
            return response.status_code == 200
    except Exception:
        return False


async def detect_transport(
    config: MCPServerConfig,
) -> Literal["streamable-http", "sse", "http"]:
    url = config.url
    timeout = config.timeout
    headers = getattr(config, "headers", None)
    if not url:
        raise ValueError("url required for remote config")
    if await _try_streamable_http(url, timeout, headers=headers):
        return "streamable-http"
    if await _try_sse(url, timeout, headers=headers):
        return "sse"
    if await _try_http(url, timeout, headers=headers):
        return "http"
    raise ConnectionError(f"All transports failed for {url}")


__all__ = ["detect_transport"]
