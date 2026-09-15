"""Transport auto-detection for remote MCP servers (OpenCode-only)."""

from __future__ import annotations

import asyncio
from typing import Literal
from urllib.parse import urlparse as _urlparse

from mcp_gway.models import SSRF_TIMEOUT, MCPServerConfig


async def _ssrf_gate(url: str) -> str | None:
    """Async SSRF gate shared by all probes: https-only + bounded DNS validate.

    Returns normalized (punycode, lowercase) host on pass, None on fail-closed
    block (probe returns False instead of raising; detect_transport raises
    only after all fail). Normalization matters for IDN: pinning and DNS must
    use the ASCII form, never raw unicode.
    """
    from mcp_gway.models import _validate_url_structure, avalidate_url_ssrf

    try:
        if _urlparse(url).scheme != "https":
            return None
        _parsed, host = _validate_url_structure(url)
        await avalidate_url_ssrf(url)
    except ValueError:
        # WHY narrow: only SSRF gate rejections map to probe-miss; transport
        # errors below are handled per-probe. Anything else would be a bug.
        return None
    return host


async def _try_streamable_http(
    url: str, timeout: int = 5000, headers: dict[str, str] | None = None
) -> bool:
    host = await _ssrf_gate(url)
    if host is None:
        return False
    try:
        from mcp.client.streamable_http import streamable_http_client

        from mcp_gway.models import (
            _aresolve_host_ips,
            _ensure_resolved_ips,
            _pinned_dns,
        )

        ips = await _aresolve_host_ips(host, use_cache=False)
        try:
            _ensure_resolved_ips(ips)
        except ValueError:
            return False
        async with asyncio.timeout(timeout / 1000):
            # Single outer pin only: the headerless branch previously nested a
            # second _pinned_dns inside the outer one, deadlocking on the
            # non-reentrant pin lock. One outer pin covers both branches.
            async with _pinned_dns(host, ips):
                import httpx2

                if headers:
                    async with httpx2.AsyncClient(
                        headers=headers,
                        timeout=SSRF_TIMEOUT,
                        follow_redirects=False,
                    ) as hc:
                        async with streamable_http_client(url, http_client=hc) as (
                            _read,
                            _write,
                        ):
                            return True
                else:
                    async with httpx2.AsyncClient(
                        timeout=SSRF_TIMEOUT, follow_redirects=False
                    ) as hc:
                        async with streamable_http_client(url, http_client=hc) as (
                            _read,
                            _write,
                        ):
                            return True
    except Exception:
        # WHY broad: detection probes must never raise; any transport/auth/TLS
        # failure is a probe-miss (False). Fail-closed gating already happened
        # in _ssrf_gate above.
        return False


async def _try_sse(
    url: str, timeout: int = 5000, headers: dict[str, str] | None = None
) -> bool:
    host = await _ssrf_gate(url)
    if host is None:
        return False
    try:
        from mcp.client.sse import sse_client

        from mcp_gway.models import (
            _aresolve_host_ips,
            _ensure_resolved_ips,
            _pinned_dns,
        )

        ips = await _aresolve_host_ips(host, use_cache=False)
        try:
            _ensure_resolved_ips(ips)
        except ValueError:
            return False
        import httpx2

        def _factory(
            headers: object = None, timeout: object = None, auth: object = None
        ) -> object:
            # WHY closure: SDK builds its own httpx client per connection; the
            # factory forces the SSRF-port settings (8s, no redirects) on it.
            return httpx2.AsyncClient(
                headers=headers,  # type: ignore[arg-type]
                timeout=SSRF_TIMEOUT,
                follow_redirects=False,
                auth=auth,  # type: ignore[arg-type]
            )

        async with asyncio.timeout(timeout / 1000):
            async with _pinned_dns(host, ips):
                async with sse_client(
                    url, headers=headers, httpx_client_factory=_factory
                ) as (read, write):  # noqa: RUF059
                    return True
    except Exception:
        # WHY broad: same probe-must-not-raise rationale as above.
        return False


async def _try_http(
    url: str, timeout: int = 5000, headers: dict[str, str] | None = None
) -> bool:
    host = await _ssrf_gate(url)
    if host is None:
        return False
    try:
        from mcp_gway.models import ssrf_post

        response = await ssrf_post(
            url,
            headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        return response.status_code == 200
    except Exception:
        # WHY broad: probe-must-not-raise; SSRF gate already enforced inside
        # ssrf_post (https-only, pin, max-3, 1MB, no auto-redirects).
        return False


async def detect_transport(
    config: MCPServerConfig,
) -> Literal["streamable-http", "sse", "http"]:
    from mcp_gway.models import avalidate_url_ssrf

    url = config.url
    timeout = config.timeout
    headers = getattr(config, "headers", None)
    if not url:
        raise ValueError("url required for remote config")
    if _urlparse(url).scheme != "https":
        raise ValueError("ssrf: https-only [reason=https_only]")
    await avalidate_url_ssrf(url)
    if await _try_streamable_http(url, timeout, headers=headers):
        return "streamable-http"
    if await _try_sse(url, timeout, headers=headers):
        return "sse"
    if await _try_http(url, timeout, headers=headers):
        return "http"
    raise ConnectionError(f"All transports failed for {url}")


__all__ = ["detect_transport"]
