"""CLI commands for MCP Gateway management."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import click

from mcp_gway.models import (
    ConnectionType,
    MCPClientConfig,
    MCPServerConfig,
    OAuthConfig,
    ToolInfo,
)
from mcp_gway.registry import Registry


def _get_registry() -> Registry:
    return Registry(servers_dir=Path.home() / ".config" / "mcp-gway" / "servers")


def _parse_envs(envs: list[str]) -> dict[str, str]:
    """Parse KEY=VALUE env strings into a dict."""
    result: dict[str, str] = {}
    for item in envs:
        key, _, value = item.partition("=")
        result[key] = value
    return result


def _parse_headers(headers: list[str]) -> dict[str, str]:
    """Parse KEY=VALUE header strings into a dict."""
    result: dict[str, str] = {}
    for item in headers:
        key, _, value = item.partition("=")
        result[key.strip()] = value.strip()
    return result


def _default_on_noise(count: int) -> None:
    """Log a warning when noise is detected in the server output."""
    click.echo(f"Warning: {count} non-JSON messages received from server", err=True)


def _is_local_config(config: MCPClientConfig | MCPServerConfig) -> bool:
    t = getattr(config, "type", None)
    if t is not None:
        return t == "local"
    ct = getattr(config, "connection_type", None)
    return ct == ConnectionType.STDIO


def _is_remote_config(config: MCPClientConfig | MCPServerConfig) -> bool:
    t = getattr(config, "type", None)
    if t is not None:
        return t == "remote"
    ct = getattr(config, "connection_type", None)
    return ct in (
        ConnectionType.HTTP,
        ConnectionType.SSE,
        ConnectionType.STREAMABLE_HTTP,
    )


def _get_config_url(config: MCPClientConfig | MCPServerConfig) -> str | None:
    url = getattr(config, "url", None)
    if url is not None:
        return url
    return getattr(config, "connection_string", None)


def _get_config_display_type(config: MCPClientConfig | MCPServerConfig) -> str:
    t = getattr(config, "type", None)
    if t is not None:
        return str(t).upper()
    ct = getattr(config, "connection_type", None)
    if ct is not None:
        try:
            return str(ct.value).upper()  # type: ignore[union-attr]
        except Exception:
            return str(ct).upper()
    return "HTTP"


@asynccontextmanager
async def _create_client_transport(
    config: MCPClientConfig | MCPServerConfig, *, force_auth: bool = False
) -> AsyncIterator[tuple[object, object]]:
    """Create the appropriate MCP client transport for a connection type."""
    config_type = getattr(config, "type", None)
    if config_type is not None:
        if config_type == "local":
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
            async with filtered_stdio_client(
                server=params, on_noise=_default_on_noise
            ) as (
                read,
                write,
            ):
                yield read, write
        else:
            url = getattr(config, "url", None) or getattr(
                config, "connection_string", None
            )
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
    else:
        if config.connection_type == ConnectionType.STDIO:
            from mcp import StdioServerParameters

            from mcp_gway.stdio_transport import (
                filtered_stdio_client,
                resolve_windows_command,
            )

            resolved = resolve_windows_command(config.stdio_config.command)
            env_dict = (
                _parse_envs(config.stdio_config.envs)
                if config.stdio_config.envs
                else None
            )
            params = StdioServerParameters(
                command=resolved,
                args=config.stdio_config.args,
                env=env_dict,
            )
            async with filtered_stdio_client(
                server=params, on_noise=_default_on_noise
            ) as (
                read,
                write,
            ):
                yield read, write
        elif config.connection_type == ConnectionType.STREAMABLE_HTTP:
            from mcp.client.streamable_http import streamable_http_client

            if force_auth:
                from mcp_gway.oauth import get_authenticated_client

                http_client = await get_authenticated_client(config.name)
                async with streamable_http_client(
                    config.connection_string, http_client=http_client
                ) as (read, write):
                    yield read, write
            else:
                headers = getattr(config, "headers", None)
                if headers:
                    import httpx

                    async with httpx.AsyncClient(headers=headers) as hc:
                        async with streamable_http_client(
                            config.connection_string, http_client=hc
                        ) as (read, write):
                            yield read, write
                else:
                    async with streamable_http_client(config.connection_string) as (
                        read,
                        write,
                    ):
                        yield read, write
        else:
            from mcp.client.sse import sse_client

            headers = None
            if force_auth:
                from mcp_gway.oauth import get_authenticated_client

                http_client = await get_authenticated_client(config.name)
                headers = http_client.headers if http_client else None
            else:
                headers = getattr(config, "headers", None)
            async with sse_client(config.connection_string, headers=headers) as (
                read,
                write,
            ):
                yield read, write


async def _discover_tools(
    config: MCPClientConfig | MCPServerConfig, *, force_auth: bool = False
) -> list[ToolInfo]:
    """Connect to MCP server and discover available tools."""
    try:
        from mcp import ClientSession

        raw_timeout = getattr(config, "timeout", 5000)
        if raw_timeout is None or raw_timeout <= 0:
            timeout_sec = 5
        else:
            timeout_sec = raw_timeout / 1000
        async with _create_client_transport(config, force_auth=force_auth) as (
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
        click.echo(f"Warning: Could not connect to server: {e}", err=True)
        return []


@click.group()
def main() -> None:
    """MCP Gateway CLI — manage MCP servers with Code Mode."""


@main.command()
@click.argument("name")
@click.option(
    "--type",
    "conn_type",
    type=click.Choice(["local", "remote", "http", "stdio", "sse", "streamable-http"]),
    required=True,
)
@click.option("--url", help="URL for remote")
@click.option(
    "--command",
    help="Command for local (single string, will be split). For local new style, pass like 'npx -y my-mcp'",
)
@click.option("--args", help="JSON array of extra args", default="[]")
@click.option("--tools", help="Comma-separated tool names (default: all)", default="*")
@click.option("--docs-url", help="Documentation URL for the server", default=None)
@click.option(
    "--env", "envs", multiple=True, help="Environment variable KEY=VALUE (repeatable)"
)
@click.option(
    "--header",
    "headers",
    multiple=True,
    help="Header KEY=VALUE for remote (repeatable)",
)
@click.option("--oauth-client-id", default=None, help="OAuth client ID")
@click.option("--oauth-client-secret", default=None, help="OAuth client secret")
@click.option("--oauth-scope", default=None, help="OAuth scope")
@click.option("--timeout", type=int, default=5000, help="Timeout ms")
@click.option("--enabled/--no-enabled", default=True, help="Enable or disable server")
@click.option(
    "--oauth-port",
    type=int,
    default=8989,
    help="Local port for OAuth callback",
)
@click.option("--cwd", default=None, help="Working directory for local server")
def add(
    name: str,
    conn_type: str,
    url: str | None,
    command: str | None,
    args: str,
    tools: str,
    docs_url: str | None,
    oauth_port: int,
    envs: tuple[str, ...],
    headers: tuple[str, ...],
    oauth_client_id: str | None,
    oauth_client_secret: str | None,
    oauth_scope: str | None,
    timeout: int,
    enabled: bool,
    cwd: str | None,
) -> None:
    """Add an MCP server and generate its .pyi stub."""
    _ = docs_url  # deprecated, kept for backward compat
    headers_dict = _parse_headers(list(headers)) if headers else None
    oauth_config = None
    if oauth_client_id or oauth_client_secret or oauth_scope:
        oauth_config = OAuthConfig(
            clientId=oauth_client_id,
            clientSecret=oauth_client_secret,
            scope=oauth_scope,
        )

    env_dict = _parse_envs(list(envs)) if envs else None
    environment = env_dict if env_dict else None

    config: MCPServerConfig
    if conn_type in ("http", "sse", "streamable-http"):
        if not url:
            click.echo(f"Error: --url required for {conn_type} connection", err=True)
            sys.exit(1)
        config = MCPServerConfig(
            name=name,
            type="remote",
            url=url,
            headers=headers_dict,
            oauth=oauth_config,
            timeout=timeout,
            enabled=enabled,
            resolved_transport=conn_type,  # type: ignore[arg-type]
        )
    elif conn_type == "stdio":
        if not command:
            click.echo("Error: --command required for stdio connection", err=True)
            sys.exit(1)
        try:
            extra = json.loads(args) if args else []
            if not isinstance(extra, list):
                extra = []
        except Exception:
            extra = []
        cmd_parts = [command] + extra if extra else [command]
        config = MCPServerConfig(
            name=name,
            type="local",
            command=cmd_parts,
            environment=environment,
            timeout=timeout,
            enabled=enabled,
        )
    elif conn_type == "local":
        if not command:
            click.echo("Error: --command required for local connection", err=True)
            sys.exit(1)
        cmd_parts = shlex.split(command, posix=sys.platform != "win32")
        if args and args != "[]":
            try:
                extra = json.loads(args)
                if isinstance(extra, list) and extra:
                    cmd_parts.extend(extra)
            except Exception:
                extra = []
        config = MCPServerConfig(
            name=name,
            type="local",
            command=cmd_parts,
            cwd=cwd,
            environment=environment,
            timeout=timeout,
            enabled=enabled,
        )
    elif conn_type == "remote":
        if not url:
            click.echo(f"Error: --url required for {conn_type} connection", err=True)
            sys.exit(1)
        config = MCPServerConfig(
            name=name,
            type="remote",
            url=url,
            headers=headers_dict,
            oauth=oauth_config,
            timeout=timeout,
            enabled=enabled,
        )
        try:
            from mcp_gway.transport import detect_transport

            try:
                detected = asyncio.run(
                    asyncio.wait_for(
                        detect_transport(config), timeout=timeout / 1000 + 2
                    )
                )
                config.resolved_transport = detected  # type: ignore[assignment]
            except Exception as e:
                click.echo(f"Warning: transport detection failed: {e}", err=True)
        except Exception as e:
            click.echo(f"Warning: transport detection failed: {e}", err=True)
    else:
        click.echo(f"Error: Unknown connection type {conn_type}", err=True)
        sys.exit(1)

    tool_filter = tools.split(",") if tools != "*" else ["*"]
    click.echo(f"Discovering tools from {name}...")
    discovered = asyncio.run(_discover_tools(config))

    if (
        not discovered
        and _is_remote_config(config)
        and getattr(config, "oauth", None) is not False
    ):
        from mcp_gway.oauth import run_oauth_flow

        click.echo("Connection failed. Trying OAuth authentication...")
        server_url = _get_config_url(config) or ""
        client_metadata = None
        if isinstance(config.oauth, OAuthConfig):
            try:
                from mcp.shared.auth import OAuthClientMetadata

                client_metadata = OAuthClientMetadata(
                    scope=config.oauth.scope,
                    redirect_uris=[f"http://127.0.0.1:{oauth_port}/callback"],
                )
            except Exception:
                client_metadata = None
        client = asyncio.run(
            run_oauth_flow(
                server_url=server_url,
                server_name=name,
                client_metadata=client_metadata,
                output_callback=click.echo,
                callback_port=oauth_port,
            )
        )
        if client:
            click.echo("Authentication successful. Discovering tools...")
            discovered = asyncio.run(_discover_tools(config, force_auth=True))

    if tools != "*":
        discovered = [t for t in discovered if t.name in tool_filter]
    if not discovered:
        click.echo("Warning: No tools discovered. Adding server with empty tool list.")
    registry = _get_registry()
    registry.add(config, discovered)
    click.echo(f"Added {name} with {len(discovered)} tools.")


@main.command()
@click.argument("name")
def remove(name: str) -> None:
    """Remove an MCP server and its stored tokens."""
    registry = _get_registry()
    try:
        registry.remove(name)
        tokens_dir = Path.home() / ".config" / "mcp-gway" / "tokens"
        for suffix in ("", "_client"):
            token_file = tokens_dir / f"{name}{suffix}.json"
            if token_file.exists():
                token_file.unlink()
        click.echo(f"Removed {name}.")
    except FileNotFoundError:
        click.echo(f"Error: Server '{name}' not found.", err=True)
        sys.exit(1)


@main.command()
@click.argument("name")
@click.option("--tools", help="Comma-separated tool names", required=True)
@click.option("--docs-url", help="Documentation URL for the server", default=None)
def update(name: str, tools: str, docs_url: str | None) -> None:
    """Update tools for an existing server."""
    registry = _get_registry()
    tool_list = [ToolInfo(name=t.strip(), description="") for t in tools.split(",")]
    try:
        if docs_url:
            config = registry.get_config(name)
            config.docs_url = docs_url  # type: ignore[attr-defined]
            registry.add(config, tool_list)
        else:
            registry.update(name, tool_list)
        click.echo(f"Updated {name} with {len(tool_list)} tools.")
    except FileNotFoundError:
        click.echo(f"Error: Server '{name}' not found.", err=True)
        sys.exit(1)


@main.command(name="list")
def list_servers() -> None:
    """List all connected MCP servers."""
    registry = _get_registry()
    names = registry.list()
    if not names:
        click.echo("No servers connected.")
        return
    click.echo(f"{'Name':<20} {'Type':<10} {'Tools':<8}")
    click.echo("-" * 38)
    for name in names:
        content = registry.read_pyi(name)
        tool_count = content.count("def ")
        try:
            config = registry.get_config(name)
            conn_type = _get_config_display_type(config)
            enabled = getattr(config, "enabled", True)
        except Exception:
            conn_type = "http"
            enabled = True
        suffix = " (disabled)" if not enabled else ""
        click.echo(f"{name:<20} {conn_type.upper():<10} {tool_count:<8}{suffix}")


@main.command()
@click.argument("name")
def inspect(name: str) -> None:
    """Show tool signatures for a server."""
    registry = _get_registry()
    try:
        content = registry.read_pyi(name)
        click.echo(content)
    except FileNotFoundError:
        click.echo(f"Error: Server '{name}' not found.", err=True)
        sys.exit(1)


def _resolve_log_level(explicit: str | None) -> str:
    if explicit:
        return explicit.lower()
    for key in ("MCP_GWAY_LOG_LEVEL", "LOG_LEVEL"):
        val = os.environ.get(key)
        if val:
            v = val.strip().lower()
            if v in ("trace", "debug", "info", "warning", "warn", "error", "critical"):
                return "warning" if v == "warn" else v
    env = (
        (
            os.environ.get("MCP_GWAY_ENV")
            or os.environ.get("ENV")
            or os.environ.get("ENVIRONMENT")
            or os.environ.get("APP_ENV")
            or ""
        )
        .strip()
        .lower()
    )
    if env in ("production", "prod", "prd", "prodution"):
        return "warning"
    if env in ("staging", "stage", "stg"):
        return "info"
    if env in ("test", "testing"):
        return "warning"
    if env in ("development", "dev", "local", "develop"):
        if os.environ.get("DEBUG", "").lower() in ("1", "true", "yes"):
            return "debug"
        return "info"
    if os.environ.get("DEBUG", "").lower() in ("1", "true", "yes"):
        return "debug"
    return "info"


@main.command()
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8080, type=int, help="Bind port")
@click.option(
    "--log-level",
    type=click.Choice(
        ["trace", "debug", "info", "warning", "error", "critical"], case_sensitive=False
    ),
    default=None,
    help="Log level (overrides MCP_GWAY_LOG_LEVEL/LOG_LEVEL and MCP_GWAY_ENV)",
)
def serve(host: str, port: int, log_level: str | None) -> None:
    """Start the gateway server."""
    import time

    import uvicorn

    resolved_level = _resolve_log_level(log_level)
    _py_level = {
        "trace": logging.DEBUG,
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }.get(resolved_level, logging.INFO)
    logging.getLogger("mcp_gway").setLevel(_py_level)
    logging.getLogger("uvicorn.error").setLevel(_py_level)
    logging.getLogger("uvicorn.access").setLevel(_py_level)

    allowed_remote = os.environ.get("MCP_GWAY_ALLOW_REMOTE") == "1"
    is_loopback = host in ("127.0.0.1", "::1", "localhost")
    if not is_loopback and not allowed_remote:
        click.echo(
            f"Error: binding to non-loopback host '{host}' requires MCP_GWAY_ALLOW_REMOTE=1",
            err=True,
        )
        sys.exit(2)
    registry = _get_registry()
    from mcp_gway import __version__
    from mcp_gway.gateway import Gateway

    if not is_loopback:
        logger = logging.getLogger(__name__)
        logger.warning("dashboard exposed on non-loopback host %s", host)
    t0 = time.monotonic()
    gateway = Gateway(registry, host=host)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    names = registry.list()
    n = len(names)
    if n == 0:
        server_line = "no servers yet — add one with `mcp-gway add`"
    elif n == 1:
        server_line = "1 server aggregated"
    else:
        server_line = f"{n} servers aggregated"

    base_url = f"http://{host}:{port}"
    is_tty = sys.stdout.isatty()

    def _c(text: str, **kwargs: object) -> str:
        return click.style(text, **kwargs) if is_tty else text  # type: ignore[arg-type]

    glyph_tri = ">" if sys.platform == "win32" else "▲"
    glyph_arr = "->" if sys.platform == "win32" else "→"
    glyph_warn = "!" if sys.platform == "win32" else "⚠"

    click.echo("")
    click.echo(
        f"{_c(glyph_tri, fg='cyan', bold=True)} {_c('MCP Gateway', bold=True)} {_c(f'v{__version__}', fg='cyan')}  {_c('·', dim=True)} {_c('ready in', dim=True)} {_c(f'{elapsed_ms}ms', fg='green')}"
    )
    click.echo(
        f"  {_c('Listening on', dim=True)} {_c(base_url, fg='cyan', underline=True)}  {_c('·', dim=True)} {server_line}"
    )
    label_w = 9
    click.echo(
        f"  {_c('Dashboard'.ljust(label_w), dim=True)} {_c(glyph_arr, dim=True)} {_c(f'{base_url}/dashboard', fg='cyan')}"
    )
    click.echo(
        f"  {_c('MCP'.ljust(label_w), dim=True)} {_c(glyph_arr, dim=True)} {_c(f'{base_url}/mcp', fg='cyan')}"
    )
    click.echo(
        f"  {_c('Health'.ljust(label_w), dim=True)} {_c(glyph_arr, dim=True)} {_c(f'{base_url}/health', fg='cyan')}"
    )
    click.echo(
        f"  {_c('Code Mode', fg='green')} {_c('·', dim=True)} local-first {_c('·', dim=True)} CSP enabled"
    )
    if not is_loopback:
        click.echo(
            f"  {_c(f'{glyph_warn} exposed on non-loopback', fg='yellow', bold=True)} {_c(f'-- dashboard reachable at {host}', dim=True)} {_c('(MCP_GWAY_ALLOW_REMOTE=1)', dim=True)}"
        )
    env_hint = (
        os.environ.get("MCP_GWAY_ENV")
        or os.environ.get("ENV")
        or os.environ.get("ENVIRONMENT")
        or os.environ.get("APP_ENV")
        or ""
    ).strip()
    if env_hint or resolved_level != "info":
        parts = []
        if env_hint:
            parts.append(f"env {env_hint.lower()}")
        if resolved_level != "info":
            parts.append(f"log {resolved_level}")
        if parts:
            click.echo(f"  {_c(' · '.join(parts), dim=True)}")
    click.echo(f"  {_c('Press Ctrl+C to stop', dim=True)}")
    click.echo("")

    uvicorn.run(
        gateway.app,
        host=host,
        port=port,
        log_level=resolved_level,
        access_log=resolved_level in ("trace", "debug", "info"),
    )


async def _refresh_server(
    cfg: MCPClientConfig | MCPServerConfig,
    srv_name: str,
    force_auth: bool,
    oauth_port: int = 8989,
) -> list[ToolInfo]:
    """Refresh a single server: try without auth, then with OAuth if needed."""
    discovered = await _discover_tools(cfg, force_auth=False)

    needs_auth = (force_auth or _is_remote_config(cfg)) and getattr(
        cfg, "oauth", None
    ) is not False
    if not discovered and needs_auth:
        from mcp_gway.oauth import run_oauth_flow

        if force_auth:
            click.echo("Running OAuth authentication flow...")
        else:
            click.echo("Connection failed. Trying OAuth authentication...")

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
        )
        if client:
            click.echo("Authentication successful. Discovering tools...")
            discovered = await _discover_tools(cfg, force_auth=True)
        else:
            click.echo("Authentication failed.")

    return discovered


@main.command()
@click.argument("name", required=False)
@click.option("--auth", is_flag=True, help="Force OAuth authentication flow")
@click.option(
    "--oauth-port",
    type=int,
    default=8989,
    help="Local port for OAuth callback",
)
def refresh(name: str | None, auth: bool, oauth_port: int) -> None:
    """Refresh server connections and re-discover tools.

    If NAME is provided, refreshes only that server.
    If no NAME is provided, refreshes all servers.

    If the server requires OAuth and has no valid token, triggers authentication.
    Use --auth to force re-authentication even if tokens exist.
    """
    registry = _get_registry()

    if name:
        names = [name]
    else:
        names = registry.list()
        if not names:
            click.echo("No servers connected.")
            return
        click.echo(f"Refreshing {len(names)} servers...")

    for server_name in names:
        try:
            config = registry.get_config(server_name)
        except FileNotFoundError:
            click.echo(
                f"Warning: Server '{server_name}' not found, skipping.", err=True
            )
            continue

        if not getattr(config, "enabled", True):
            click.echo(f"Skipping {server_name} (disabled)")
            continue

        display_type = _get_config_display_type(config)
        click.echo(f"\n--- {server_name} ({display_type}) ---")

        try:
            discovered = asyncio.run(
                _refresh_server(config, server_name, auth, oauth_port)
            )
        except Exception as e:
            click.echo(f"Error refreshing {server_name}: {e}", err=True)
            continue

        if not discovered:
            click.echo(f"Warning: No tools discovered for {server_name}.")
            click.echo(f"Try: mcp-gway refresh {server_name} --auth")
            continue

        registry.update(server_name, discovered)
        click.echo(f"Refreshed {server_name} with {len(discovered)} tools.")

    if len(names) > 1:
        click.echo(f"\nDone. Refreshed {len(names)} servers.")


if __name__ == "__main__":
    main()
