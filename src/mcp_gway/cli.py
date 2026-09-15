"""CLI commands for MCP Gateway management."""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import sys
from pathlib import Path

import click

from mcp_gway.core import detect_transport, discover_tools, parse_envs, parse_headers
from mcp_gway.core.client import refresh_server
from mcp_gway.models import MCPServerConfig, OAuthConfig, ToolInfo
from mcp_gway.registry import Registry


def _get_registry() -> Registry:
    return Registry(servers_dir=Path.home() / ".config" / "mcp-gway" / "servers")


# Single source of truth lives in mcp_gway.core.client; re-export here for
# backward compatibility (triple-branch helpers were duplicated).
from mcp_gway.core.client import (
    _get_config_url,
    _is_local_config,
    _is_remote_config,
)


def _get_config_display_type(config: MCPServerConfig) -> str:
    return str(config.type).upper()


@click.group()
def main() -> None:
    """MCP Gateway CLI — manage MCP servers with Code Mode."""


@main.command()
@click.argument("name")
@click.option(
    "--type",
    "conn_type",
    type=click.Choice(["local", "remote"]),
    required=True,
)
@click.option("--url", help="URL for remote")
@click.option(
    "--command",
    help="Command for local (single string, will be split). For local new style, pass like 'npx -y my-mcp'",
)
@click.option("--tools", help="Comma-separated tool names (default: all)", default="*")
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
    tools: str,
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
    headers_dict = parse_headers(list(headers)) if headers else None
    oauth_config = None
    if oauth_client_id or oauth_client_secret or oauth_scope:
        oauth_config = OAuthConfig(
            clientId=oauth_client_id,
            clientSecret=oauth_client_secret,
            scope=oauth_scope,
        )

    env_dict = parse_envs(list(envs)) if envs else None
    environment = env_dict if env_dict else None

    config: MCPServerConfig
    if conn_type == "local":
        if not command:
            click.echo("Error: --command required for local connection", err=True)
            sys.exit(1)
        try:
            cmd_parts = shlex.split(command, posix=sys.platform != "win32")
        except Exception:
            click.echo(
                "Error: invalid --command syntax [reason=invalid_syntax]", err=True
            )
            sys.exit(1)
        from mcp_gway.core.policy import (
            audit_local_action,
            check_cwd,
            check_local_command,
        )

        resolved_cwd: str | None = None
        if cwd:
            try:
                resolved_cwd = check_cwd(cwd)
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)
                sys.exit(1)
        try:
            config = MCPServerConfig(
                name=name,
                type="local",
                command=cmd_parts,
                cwd=resolved_cwd,
                environment=environment,
                timeout=timeout,
                enabled=enabled,
            )
        except Exception as e:
            click.echo(f"Error: invalid local config: {e}", err=True)
            sys.exit(1)
        decision = check_local_command(list(cmd_parts), require_binary=True)
        audit_local_action(
            "cli_add", name, cmd_parts[0] if cmd_parts else None, decision
        )
        if not decision.allowed:
            click.echo(f"Error: {decision.message}", err=True)
            sys.exit(1)
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

    tool_filter = [t.strip() for t in tools.split(",")] if tools != "*" else ["*"]
    config.tools_to_execute = tool_filter
    click.echo(f"Discovering tools from {name}...")
    discovered = asyncio.run(discover_tools(config))

    if (
        not discovered
        and _is_remote_config(config)
        and getattr(config, "oauth", None) is not False
    ):
        from mcp_gway.oauth import run_oauth_flow

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
                oauth_config=config.oauth,
            )
        )
        if client:
            click.echo("Authentication successful.")
            discovered = asyncio.run(discover_tools(config, force_auth=True))

    if tools != "*":
        discovered = [t for t in discovered if t.name in tool_filter]
    if not discovered:
        click.echo("Warning: No tools discovered. Adding server with empty tool list.")
    if conn_type == "local":
        from mcp_gway.core.policy import audit_local_action as _audit2
        from mcp_gway.core.policy import check_local_command as _check2

        _re = _check2(list(cmd_parts), require_binary=True)
        _audit2("cli_add_regate", name, cmd_parts[0] if cmd_parts else None, _re)
        if not _re.allowed:
            click.echo(f"Error: {_re.message}", err=True)
            sys.exit(1)
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
    val = os.environ.get("MCP_GWAY_LOG_LEVEL")
    if val:
        v = val.strip().lower()
        if v in ("trace", "debug", "info", "warning", "warn", "error", "critical"):
            return "warning" if v == "warn" else v
    return "info"


def _serve_stdio(log_level: str | None, registry_dir: str | None) -> None:
    """Serve NDJSON JSON-RPC over stdin/stdout (stdio transport)."""
    resolved_level = _resolve_log_level(log_level)
    from mcp_gway.observability.logging import setup_logging

    setup_logging(resolved_level)
    servers_dir = (
        Path(registry_dir).expanduser()
        if registry_dir
        else Path.home() / ".config" / "mcp-gway" / "servers"
    )
    import logging as _logging

    _logger = _logging.getLogger("mcp_gway.mcp")
    try:
        registry = Registry(servers_dir=servers_dir)
        # NB: mcp_gway.stdio is server-side NDJSON (we serve stdin/stdout);
        # mcp_gway.stdio_transport is client-side (we connect to children).
        # Keep these imports separate — do not merge or rename (import churn).
        from mcp_gway.gateway import Gateway
        from mcp_gway.stdio import run_stdio_async

        gateway = Gateway(registry)
    except Exception as e:
        click.echo(
            f"Error: invalid --registry-dir {servers_dir} [reason={e}]", err=True
        )
        sys.exit(2)
    try:
        names = registry.list()
    except Exception as e:
        _logger.warning("could not list registry %s [reason=%s]", str(servers_dir), e)
        names = []
    try:
        import os as _os

        _pid = _os.getpid()
    except Exception:
        _pid = -1
    _logger.info(
        "mcp mode ready: %d servers from %s (pid=%s, log-level=%s)",
        len(names),
        str(servers_dir),
        _pid,
        resolved_level,
    )
    click.echo(
        f"[mcp] ready: {len(names)} server(s) from {servers_dir} "
        f"(pid={_pid}, log-level={resolved_level}) — "
        "stdout is pure NDJSON, logs go to stderr",
        err=True,
    )
    try:
        code = asyncio.run(run_stdio_async(gateway, sys.stdin, sys.stdout, sys.stderr))
    except KeyboardInterrupt:
        sys.exit(130)
    except (EOFError, BrokenPipeError):
        sys.exit(0)
    sys.exit(code)


def _serve_http(
    host: str, port: int, log_level: str | None, registry_dir: str | None
) -> None:
    """Serve the HTTP/SSE gateway app (http and sse share Gateway.app)."""
    import time

    import uvicorn

    resolved_level = _resolve_log_level(log_level)
    from mcp_gway.observability.logging import setup_logging

    setup_logging(resolved_level)
    _py_level = {
        "trace": logging.DEBUG,
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }.get(resolved_level, logging.INFO)
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
    servers_dir = (
        Path(registry_dir).expanduser()
        if registry_dir
        else Path.home() / ".config" / "mcp-gway" / "servers"
    )
    from mcp_gway import __version__

    if not is_loopback:
        logger = logging.getLogger(__name__)
        logger.warning("server exposed on non-loopback host %s", host)
    t0 = time.monotonic()
    try:
        registry = Registry(servers_dir=servers_dir)
        from mcp_gway.gateway import Gateway

        gateway = Gateway(registry, host=host)
        names = registry.list()
    except Exception as e:
        click.echo(
            f"Error: invalid --registry-dir {servers_dir} [reason={e}]", err=True
        )
        sys.exit(2)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

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
            f"  {_c(f'{glyph_warn} exposed on non-loopback', fg='yellow', bold=True)} {_c(f'-- server reachable at {host}', dim=True)} {_c('(MCP_GWAY_ALLOW_REMOTE=1)', dim=True)}"
        )
    if resolved_level != "info":
        click.echo(f"  {_c('log ' + resolved_level, dim=True)}")
    click.echo(f"  {_c('Press Ctrl+C to stop', dim=True)}")
    click.echo("")

    try:
        uvicorn.run(
            gateway.app,
            host=host,
            port=port,
            log_level=resolved_level,
            access_log=resolved_level in ("trace", "debug", "info"),
        )
    except Exception as e:
        click.echo(f"Error: serve failed to bind {host}:{port} [reason={e}]", err=True)
        sys.exit(1)


@main.command()
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http", "sse"]),
    default="stdio",
    show_default=True,
    help="Transport to serve (stdio default; http and sse share the same app)",
)
@click.option("--host", default="127.0.0.1", help="Bind host (http|sse only)")
@click.option(
    "--port",
    default=8080,
    type=click.IntRange(1, 65535),
    help="Bind port (http|sse only)",
)
@click.option(
    "--log-level",
    type=click.Choice(
        ["trace", "debug", "info", "warning", "error", "critical"], case_sensitive=False
    ),
    default=None,
    help="Log level (overrides MCP_GWAY_LOG_LEVEL; default info)",
)
@click.option(
    "--registry-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    default=None,
    help="Registry servers directory (default ~/.config/mcp-gway/servers)",
)
@click.pass_context
def serve(
    ctx: click.Context,
    transport: str,
    host: str,
    port: int,
    log_level: str | None,
    registry_dir: str | None,
) -> None:
    """Start the gateway server (default stdio; --host/--port only with http|sse)."""
    # WHY: fail hard on transport×options mismatch, never silently ignore (ADR-010).
    if transport == "stdio":
        for _opt in ("host", "port"):
            _src = ctx.get_parameter_source(_opt)
            if _src is not None and _src != click.core.ParameterSource.DEFAULT:
                click.echo(
                    "Error: --host/--port only apply to --transport http|sse",
                    err=True,
                )
                sys.exit(2)
        _serve_stdio(log_level, registry_dir)
    elif transport in ("http", "sse"):
        _serve_http(host, port, log_level, registry_dir)
    else:
        raise click.BadParameter(f"unknown transport '{transport}'")


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

        if _is_local_config(config):
            from mcp_gway.core.policy import audit_local_action, check_local_command

            decision = check_local_command(
                list(config.command or []), require_binary=True
            )
            audit_local_action(
                "cli_refresh",
                server_name,
                (config.command or [None])[0],
                decision,
            )
            if not decision.allowed:
                click.echo(
                    f"Error refreshing {server_name}: {decision.message}", err=True
                )
                continue

        try:
            discovered = asyncio.run(
                refresh_server(config, server_name, auth, oauth_port)
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


@main.group(name="local-unrestricted")
def local_unrestricted() -> None:
    """Manage break-glass unrestricted marker (explicit only)."""


@local_unrestricted.command(name="enable")
def local_unrestricted_enable() -> None:
    """Create break-glass marker (72h TTL, 0o600 on posix)."""
    from mcp_gway.core.policy import (
        UNRESTRICTED_ENV,
        UNRESTRICTED_TTL_SECONDS,
        create_unrestricted_marker,
        unrestricted_status,
    )

    path = create_unrestricted_marker()
    status = unrestricted_status()
    ttl_hours = UNRESTRICTED_TTL_SECONDS // 3600
    click.echo(
        f"Break-glass marker created: {path} (TTL {ttl_hours}h, 0o600 on posix)."
    )
    if os.environ.get(UNRESTRICTED_ENV) != "1":
        click.echo(
            f"Note: {UNRESTRICTED_ENV}!=1, still inactive. "
            f'$env:{UNRESTRICTED_ENV}="1" to activate.',
        )
    elif not status.active:
        click.echo(f"Note: marker state={status.state}, still inactive.")
    else:
        click.echo(f"Active for {ttl_hours}h. Run `mcp-gway refresh` to retry locals.")


@local_unrestricted.command(name="disable")
def local_unrestricted_disable() -> None:
    """Remove break-glass marker (explicit only)."""
    from mcp_gway.core.policy import UNRESTRICTED_ENV, remove_unrestricted_marker

    try:
        removed = remove_unrestricted_marker()
    except OSError as e:
        click.echo(f"Error: break-glass marker remove failed: {e}", err=True)
        raise click.ClickException("break-glass marker remove failed") from e
    if removed:
        click.echo("Break-glass marker removed.")
    else:
        click.echo("Break-glass marker not present.")
    click.echo(
        f"Also run Remove-Item Env:\\{UNRESTRICTED_ENV} "
        f"to unset $env:{UNRESTRICTED_ENV}."
    )


@local_unrestricted.command(name="status")
def local_unrestricted_status() -> None:
    """Show break-glass env + marker state without side effects."""
    from mcp_gway.core.policy import (
        UNRESTRICTED_ENV,
        UNRESTRICTED_TTL_SECONDS,
        marker_path,
        unrestricted_status,
    )

    status = unrestricted_status()
    env_set = os.environ.get(UNRESTRICTED_ENV) == "1"
    click.echo(f"env {UNRESTRICTED_ENV}={'1' if env_set else 'unset'}")
    click.echo(f"marker {marker_path()} exists={status.marker_exists}")
    click.echo(f"state={status.state} active={status.active}")
    if status.age_seconds is not None:
        click.echo(
            f"age_seconds={int(status.age_seconds)} ttl={UNRESTRICTED_TTL_SECONDS}"
        )
    if status.expires_in_seconds is not None:
        click.echo(f"expires_in_seconds={int(status.expires_in_seconds)}")


@main.command(name="mcp", hidden=True)
@click.option(
    "--log-level",
    type=click.Choice(
        ["trace", "debug", "info", "warning", "error", "critical"], case_sensitive=False
    ),
    default=None,
    help="Log level (overrides MCP_GWAY_LOG_LEVEL; default info)",
)
@click.option(
    "--registry-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=str),
    default=None,
    help="Registry servers directory (default ~/.config/mcp-gway/servers)",
)
def mcp_cmd(log_level: str | None, registry_dir: str | None) -> None:
    """Deprecated alias for serve --transport stdio."""
    click.echo("[mcp] deprecated, use serve --transport stdio", err=True)
    _serve_stdio(log_level, registry_dir)


if __name__ == "__main__":
    main()
