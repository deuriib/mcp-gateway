"""CLI commands for MCP Gateway management."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from mcp_gway.models import ConnectionType, MCPClientConfig, StdioConfig, ToolInfo
from mcp_gway.registry import Registry


def _get_registry() -> Registry:
    return Registry(servers_dir=Path.home() / ".config" / "mcp-gway" / "servers")


async def _discover_tools(
    config: MCPClientConfig, *, force_auth: bool = False
) -> list[ToolInfo]:
    """Connect to MCP server and discover available tools."""
    try:
        if config.connection_type == ConnectionType.STDIO:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=config.stdio_config.command, args=config.stdio_config.args
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [
                        ToolInfo(
                            name=t.name,
                            description=t.description or "",
                            input_schema=t.inputSchema
                            if hasattr(t, "inputSchema")
                            else {},
                        )
                        for t in result.tools
                    ]
        elif config.connection_type == ConnectionType.STREAMABLE_HTTP:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client

            url = config.connection_string

            # Only get authenticated client when force_auth is True
            http_client = None
            if force_auth:
                from mcp_gway.oauth import get_authenticated_client

                http_client = await get_authenticated_client(config.name)
            async with streamable_http_client(url, http_client=http_client) as (
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
                            input_schema=t.inputSchema
                            if hasattr(t, "inputSchema")
                            else {},
                        )
                        for t in result.tools
                    ]
        else:
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            url = config.connection_string

            # Only get authenticated client when force_auth is True
            headers = None
            if force_auth:
                from mcp_gway.oauth import get_authenticated_client

                http_client = await get_authenticated_client(config.name)
                headers = http_client.headers if http_client else None
            async with sse_client(url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [
                        ToolInfo(
                            name=t.name,
                            description=t.description or "",
                            input_schema=t.inputSchema
                            if hasattr(t, "inputSchema")
                            else {},
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
    type=click.Choice(["http", "stdio", "sse", "streamable-http"]),
    required=True,
)
@click.option("--url", help="Connection URL for http/sse")
@click.option("--command", help="Command for stdio connection")
@click.option("--args", help="JSON array of arguments for stdio", default="[]")
@click.option("--tools", help="Comma-separated tool names (default: all)", default="*")
@click.option("--docs-url", help="Documentation URL for the server", default=None)
def add(
    name: str,
    conn_type: str,
    url: str | None,
    command: str | None,
    args: str,
    tools: str,
    docs_url: str | None,
) -> None:
    """Add an MCP server and generate its .pyi stub."""
    stdio_config = None
    connection_string = url
    if conn_type == "stdio":
        if not command:
            click.echo("Error: --command required for stdio connection", err=True)
            sys.exit(1)
        stdio_config = StdioConfig(command=command, args=json.loads(args))
        connection_string = command
    elif conn_type in ("http", "sse", "streamable-http"):
        if not url:
            click.echo(f"Error: --url required for {conn_type} connection", err=True)
            sys.exit(1)
    config = MCPClientConfig(
        name=name,
        connection_type=conn_type,
        connection_string=connection_string,
        stdio_config=stdio_config,
        docs_url=docs_url,
    )
    tool_filter = tools.split(",") if tools != "*" else ["*"]
    config.tools_to_execute = tool_filter
    click.echo(f"Discovering tools from {name}...")
    discovered = asyncio.run(_discover_tools(config))

    # Auto-auth: if no tools and server type supports OAuth, try authentication
    if not discovered and config.connection_type in (
        ConnectionType.HTTP,
        ConnectionType.SSE,
        ConnectionType.STREAMABLE_HTTP,
    ):
        from mcp_gway.oauth import run_oauth_flow

        click.echo("Connection failed. Trying OAuth authentication...")
        client = asyncio.run(
            run_oauth_flow(
                server_url=config.connection_string,
                server_name=name,
                output_callback=click.echo,
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
        # Clean up OAuth tokens
        from pathlib import Path

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
            config.docs_url = docs_url
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
        conn_type = "http"
        for line in content.splitlines():
            if line.startswith("# connection_type:"):
                conn_type = line.split(":", 1)[1].strip()
                break
        click.echo(f"{name:<20} {conn_type.upper():<10} {tool_count:<8}")


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


@main.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8080, type=int, help="Bind port")
def serve(host: str, port: int) -> None:
    """Start the gateway server."""
    import uvicorn

    registry = _get_registry()
    from mcp_gway.gateway import Gateway

    gateway = Gateway(registry)
    click.echo(f"Starting MCP Gateway on {host}:{port}")
    uvicorn.run(gateway.app, host=host, port=port)


@main.command()
@click.argument("name", required=False)
@click.option("--auth", is_flag=True, help="Force OAuth authentication flow")
def refresh(name: str | None, auth: bool) -> None:
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

        click.echo(f"\n--- {server_name} ({config.connection_type.value}) ---")

        async def _refresh_server(
            cfg: MCPClientConfig, srv_name: str
        ) -> list[ToolInfo]:
            # Step 1: Try connecting without auth
            discovered = await _discover_tools(cfg, force_auth=False)

            # Step 2: If empty and auth is needed, try OAuth flow
            needs_auth = auth or cfg.connection_type in (
                ConnectionType.HTTP,
                ConnectionType.SSE,
                ConnectionType.STREAMABLE_HTTP,
            )
            if not discovered and needs_auth:
                from mcp_gway.oauth import run_oauth_flow

                if auth:
                    click.echo("Running OAuth authentication flow...")
                else:
                    click.echo("Connection failed. Trying OAuth authentication...")

                client = await run_oauth_flow(
                    server_url=cfg.connection_string,
                    server_name=srv_name,
                    output_callback=click.echo,
                )
                if client:
                    click.echo("Authentication successful. Discovering tools...")
                    discovered = await _discover_tools(cfg, force_auth=True)
                else:
                    click.echo("Authentication failed.")

            return discovered

        discovered = asyncio.run(_refresh_server(config, server_name))

        if not discovered:
            click.echo(f"Warning: No tools discovered for {server_name}.")
            click.echo(f"Try: mcp-gway refresh {server_name} --auth")
            continue

        # Update the registry with new tools
        registry.update(server_name, discovered)
        click.echo(f"Refreshed {server_name} with {len(discovered)} tools.")

    if len(names) > 1:
        click.echo(f"\nDone. Refreshed {len(names)} servers.")


if __name__ == "__main__":
    main()
