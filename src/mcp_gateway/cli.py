"""CLI commands for MCP Gateway management."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from mcp_gateway.models import ConnectionType, MCPClientConfig, StdioConfig, ToolInfo
from mcp_gateway.registry import Registry


def _get_registry() -> Registry:
    return Registry(servers_dir=Path("servers"))


async def _discover_tools(config: MCPClientConfig) -> list[ToolInfo]:
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
        else:
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            url = config.connection_string
            async with sse_client(url) as (read, write):
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
    "--type", "conn_type", type=click.Choice(["http", "stdio", "sse"]), required=True
)
@click.option("--url", help="Connection URL for http/sse")
@click.option("--command", help="Command for stdio connection")
@click.option("--args", help="JSON array of arguments for stdio", default="[]")
@click.option("--tools", help="Comma-separated tool names (default: all)", default="*")
def add(
    name: str,
    conn_type: str,
    url: str | None,
    command: str | None,
    args: str,
    tools: str,
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
    config = MCPClientConfig(
        name=name,
        connection_type=conn_type,
        connection_string=connection_string,
        stdio_config=stdio_config,
    )
    tool_filter = tools.split(",") if tools != "*" else ["*"]
    config.tools_to_execute = tool_filter
    click.echo(f"Discovering tools from {name}...")
    discovered = asyncio.run(_discover_tools(config))
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
    """Remove an MCP server."""
    registry = _get_registry()
    try:
        registry.remove(name)
        click.echo(f"Removed {name}.")
    except FileNotFoundError:
        click.echo(f"Error: Server '{name}' not found.", err=True)
        sys.exit(1)


@main.command()
@click.argument("name")
@click.option("--tools", help="Comma-separated tool names", required=True)
def update(name: str, tools: str) -> None:
    """Update tools for an existing server."""
    registry = _get_registry()
    tool_list = [ToolInfo(name=t.strip(), description="") for t in tools.split(",")]
    try:
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
    from mcp_gateway.gateway import Gateway

    gateway = Gateway(registry)
    click.echo(f"Starting MCP Gateway on {host}:{port}")
    uvicorn.run(gateway.app, host=host, port=port)


if __name__ == "__main__":
    main()
