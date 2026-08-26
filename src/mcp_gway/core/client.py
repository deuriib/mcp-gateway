"""Core client helpers — transport creation and tool discovery (OpenCode-only)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import click

from mcp_gway.models import MCPServerConfig, OAuthConfig, ToolInfo

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
async def create_client_transport(
    config: MCPServerConfig, *, force_auth: bool = False
) -> AsyncIterator[tuple[object, object]]:
    if config.type == "local":
        from mcp import StdioServerParameters

        from mcp_gway.stdio_transport import (
            filtered_stdio_client,
            resolve_windows_command,
        )

        cmd_list: list[str] | None = getattr(config, "command", None)
        if not cmd_list:
            raise ValueError("command required for local")
        command = cmd_list[0]
        args = cmd_list[1:] if len(cmd_list) > 1 else []
        resolved = resolve_windows_command(command)
        env_dict = getattr(config, "environment", None)
        cwd = getattr(config, "cwd", None)
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
    else:
        url = config.url
        if not url:
            raise ValueError("url required for remote config")
        resolved_transport = getattr(config, "resolved_transport", None)
        headers = getattr(config, "headers", None)
        if resolved_transport == "streamable-http":
            from mcp.client.streamable_http import streamable_http_client

            if force_auth:
                from mcp_gway.oauth import get_authenticated_client

                http_client = await get_authenticated_client(config.name)
                async with streamable_http_client(url, http_client=http_client) as (
                    read,
                    write,
                ):
                    yield read, write
            elif headers:
                import httpx

                async with httpx.AsyncClient(headers=headers) as hc:
                    async with streamable_http_client(url, http_client=hc) as (
                        read,
                        write,
                    ):
                        yield read, write
            else:
                async with streamable_http_client(url) as (
                    read,
                    write,
                ):
                    yield read, write
        elif resolved_transport == "http":
            from mcp.client.sse import sse_client

            sse_headers = None
            if force_auth:
                from mcp_gway.oauth import get_authenticated_client

                http_client = await get_authenticated_client(config.name)
                sse_headers = http_client.headers if http_client else None
            elif headers:
                sse_headers = headers
            async with sse_client(url, headers=sse_headers) as (
                read,
                write,
            ):
                yield read, write
        else:
            from mcp.client.sse import sse_client

            sse_headers = None
            if force_auth:
                from mcp_gway.oauth import get_authenticated_client

                http_client = await get_authenticated_client(config.name)
                sse_headers = http_client.headers if http_client else None
            elif headers:
                sse_headers = headers
            async with sse_client(url, headers=sse_headers) as (
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
        async with create_client_transport(config, force_auth=force_auth) as (
            read,
            write,
        ):
            async with ClientSession(read, write) as session:
                async with asyncio.timeout(timeout_sec):
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
            click.echo("Authentication successful. Discovering tools...")
            discovered = await discover_tools(cfg, force_auth=True)
        else:
            click.echo("Authentication failed.")

    return discovered
