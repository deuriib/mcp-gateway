"""Core client helpers — transport creation and tool discovery (OpenCode-only)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import click

from mcp_gway.models import MCPServerConfig, OAuthConfig, ToolInfo, _validate_name_value

logger = logging.getLogger(__name__)


def _default_on_noise(count: int) -> None:
    click.echo(f"Warning: {count} non-JSON messages received from server", err=True)


def _is_local_config(config: MCPServerConfig) -> bool:
    return config.type == "local"


def _is_remote_config(config: MCPServerConfig) -> bool:
    return config.type == "remote"


def _get_config_url(config: MCPServerConfig) -> str | None:
    return config.url


@asynccontextmanager
async def _create_local_transport(
    config: MCPServerConfig,
) -> AsyncIterator[tuple[object, object]]:
    from mcp import StdioServerParameters

    from mcp_gway.core.policy import (
        audit_local_action,
        check_cwd,
        check_environment,
        check_local_command,
    )
    from mcp_gway.stdio_transport import (
        filtered_stdio_client,
        resolve_windows_command,
    )

    cmd_list: list[str] | None = getattr(config, "command", None)
    if not cmd_list:
        raise ValueError("command required for local")
    decision = check_local_command(list(cmd_list), require_binary=True)
    audit_local_action("spawn", config.name, cmd_list[0], decision)
    if not decision.allowed:
        if decision.reason_code == "binary_not_found":
            raise FileNotFoundError(decision.message)
        raise PermissionError(decision.message)
    command = cmd_list[0]
    args = cmd_list[1:] if len(cmd_list) > 1 else []
    resolved = resolve_windows_command(command)
    env_dict = check_environment(getattr(config, "environment", None))
    raw_cwd = getattr(config, "cwd", None)
    cwd = check_cwd(raw_cwd) if raw_cwd else None
    try:
        params = StdioServerParameters(
            command=resolved,
            args=args,
            env=env_dict,
            cwd=cwd,
        )
    except TypeError:
        params = StdioServerParameters(
            command=resolved,
            args=args,
            env=env_dict,
        )
    async with filtered_stdio_client(server=params, on_noise=_default_on_noise) as (
        read,
        write,
    ):
        yield read, write


async def _require_authenticated_client(server_name: str) -> object:
    """Fail-closed auth: never return None when force_auth is set.

    Raises PermissionError when no tokens exist so callers can never pass
    None into the SDK (which would silently downgrade to anonymous).
    """
    from mcp_gway.oauth import get_authenticated_client

    http_client = await get_authenticated_client(server_name)
    if http_client is None:
        raise PermissionError(
            "oauth authentication required but no tokens found [reason=auth_required]"
        )
    return http_client


@asynccontextmanager
async def _create_remote_transport(
    config: MCPServerConfig, *, force_auth: bool = False
) -> AsyncIterator[tuple[object, object]]:
    """Remote transport via the SSRF port: https-only + async gate + pin + 8s/no-redirect httpx."""
    from urllib.parse import urlparse as _up

    from mcp_gway.models import (
        SSRF_TIMEOUT,
        _aresolve_host_ips,
        _ensure_resolved_ips,
        _normalize_host,
        _pinned_dns,
        _require_https,
        avalidate_url_ssrf,
    )

    url = config.url
    if not url:
        raise ValueError("url required for remote config")
    _require_https(url)
    await avalidate_url_ssrf(url)
    host = _normalize_host(_up(url).hostname or "")
    ips = await _aresolve_host_ips(host, use_cache=False)
    _ensure_resolved_ips(ips)
    resolved_transport = getattr(config, "resolved_transport", None)
    headers = getattr(config, "headers", None)
    if resolved_transport == "streamable-http":
        from mcp.client.streamable_http import streamable_http_client

        if force_auth:
            http_client = await _require_authenticated_client(config.name)
            try:
                async with _pinned_dns(host, ips):
                    async with streamable_http_client(url, http_client=http_client) as (
                        read,
                        write,
                    ):
                        yield read, write
            finally:
                if http_client is not None:
                    try:
                        await http_client.aclose()
                    except Exception:
                        # WHY broad: transport teardown must not mask the
                        # session error; close failures are best-effort.
                        pass
        elif headers:
            import httpx2

            async with httpx2.AsyncClient(
                headers=headers, timeout=SSRF_TIMEOUT, follow_redirects=False
            ) as hc:
                async with _pinned_dns(host, ips):
                    async with streamable_http_client(url, http_client=hc) as (
                        read,
                        write,
                    ):
                        yield read, write
        else:
            import httpx2

            async with httpx2.AsyncClient(
                timeout=SSRF_TIMEOUT, follow_redirects=False
            ) as hc:
                async with _pinned_dns(host, ips):
                    async with streamable_http_client(url, http_client=hc) as (
                        read,
                        write,
                    ):
                        yield read, write
    elif resolved_transport == "http":
        import httpx2
        from mcp.client.sse import sse_client

        def _factory(
            headers: object = None, timeout: object = None, auth: object = None
        ) -> object:
            return httpx2.AsyncClient(
                headers=headers,  # type: ignore[arg-type]
                timeout=SSRF_TIMEOUT,
                follow_redirects=False,
                auth=auth,  # type: ignore[arg-type]
            )

        sse_headers = None
        http_client = None
        if force_auth:
            http_client = await _require_authenticated_client(config.name)
            sse_headers = http_client.headers
            try:
                async with _pinned_dns(host, ips):
                    async with sse_client(
                        url, headers=sse_headers, httpx_client_factory=_factory
                    ) as (
                        read,
                        write,
                    ):
                        yield read, write
            finally:
                if http_client is not None:
                    try:
                        await http_client.aclose()
                    except Exception:
                        # WHY broad: same teardown rationale as above.
                        pass
        else:
            if headers:
                sse_headers = headers
            async with _pinned_dns(host, ips):
                async with sse_client(
                    url, headers=sse_headers, httpx_client_factory=_factory
                ) as (
                    read,
                    write,
                ):
                    yield read, write
    else:
        import httpx2
        from mcp.client.sse import sse_client

        def _factory_default(
            headers: object = None, timeout: object = None, auth: object = None
        ) -> object:
            return httpx2.AsyncClient(
                headers=headers,  # type: ignore[arg-type]
                timeout=SSRF_TIMEOUT,
                follow_redirects=False,
                auth=auth,  # type: ignore[arg-type]
            )

        sse_headers = None
        http_client = None
        if force_auth:
            http_client = await _require_authenticated_client(config.name)
            sse_headers = http_client.headers
            try:
                async with _pinned_dns(host, ips):
                    async with sse_client(
                        url, headers=sse_headers, httpx_client_factory=_factory_default
                    ) as (
                        read,
                        write,
                    ):
                        yield read, write
            finally:
                if http_client is not None:
                    try:
                        await http_client.aclose()
                    except Exception:
                        # WHY broad: same teardown rationale as above.
                        pass
        else:
            if headers:
                sse_headers = headers
            async with _pinned_dns(host, ips):
                async with sse_client(
                    url, headers=sse_headers, httpx_client_factory=_factory_default
                ) as (
                    read,
                    write,
                ):
                    yield read, write


@asynccontextmanager
async def create_client_transport(
    config: MCPServerConfig, *, force_auth: bool = False
) -> AsyncIterator[tuple[object, object]]:
    _validate_name_value(config.name)
    if _is_local_config(config):
        async with _create_local_transport(config) as (read, write):
            yield read, write
    else:
        async with _create_remote_transport(config, force_auth=force_auth) as (
            read,
            write,
        ):
            yield read, write


async def discover_tools(
    config: MCPServerConfig, *, force_auth: bool = False
) -> list[ToolInfo]:
    try:
        from mcp import ClientSession

        raw_timeout = getattr(config, "timeout", 5000)
        if raw_timeout is None or raw_timeout <= 0:
            timeout_sec = 5
        else:
            timeout_sec = raw_timeout / 1000
        async with asyncio.timeout(timeout_sec):
            async with create_client_transport(config, force_auth=force_auth) as (
                read,
                write,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [
                        ToolInfo(
                            name=t.name,
                            description=t.description or "",
                            input_schema=t.input_schema,
                        )
                        for t in result.tools
                    ]
    except Exception as e:
        logger.debug("Could not connect to server: %s", e)
        return []


async def refresh_server(
    cfg: MCPServerConfig,
    srv_name: str,
    force_auth: bool,
    oauth_port: int = 8989,
) -> list[ToolInfo]:
    discovered = await discover_tools(cfg, force_auth=False)

    needs_auth = (force_auth or _is_remote_config(cfg)) and getattr(
        cfg, "oauth", None
    ) is not False
    if not discovered and needs_auth:
        from mcp_gway.oauth import run_oauth_flow

        server_url = _get_config_url(cfg) or ""
        client_metadata = None
        if isinstance(getattr(cfg, "oauth", None), OAuthConfig):
            try:
                from mcp.shared.auth import OAuthClientMetadata

                client_metadata = OAuthClientMetadata(
                    scope=cfg.oauth.scope,  # type: ignore[union-attr]
                    redirect_uris=[f"http://127.0.0.1:{oauth_port}/callback"],
                )
            except Exception:
                client_metadata = None
        client = await run_oauth_flow(
            server_url=server_url,
            server_name=srv_name,
            client_metadata=client_metadata,
            output_callback=click.echo,
            callback_port=oauth_port,
            oauth_config=getattr(cfg, "oauth", None),
        )
        if client:
            try:
                await client.aclose()
            except Exception:
                pass
            click.echo("Authentication successful. Discovering tools...")
            discovered = await discover_tools(cfg, force_auth=True)
        else:
            click.echo("Authentication failed.")

    return discovered
