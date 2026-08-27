"""Tests for CLI commands (OpenCode-only)."""

import pytest
from click.testing import CliRunner

from mcp_gway.cli import main
from mcp_gway.registry import Registry


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "servers").mkdir()

    def mock_get_registry():
        return Registry(servers_dir=tmp_path / "servers")

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)
    return CliRunner()


def test_list_empty(runner):
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "No servers" in result.output


def test_inspect_server(runner, monkeypatch):
    async def mock_discover_tools(config, force_auth=False):
        from mcp_gway.models import ToolInfo

        return [ToolInfo(name="search", description="Search videos")]

    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover_tools)
    runner.invoke(
        main,
        ["add", "youtube", "--type", "remote", "--url", "http://localhost:3001/mcp"],
    )
    result = runner.invoke(main, ["inspect", "youtube"])
    assert result.exit_code == 0
    assert "search" in result.output


# --- discover_tools signature ---


def test_discover_tools_accepts_force_auth():
    """discover_tools should accept force_auth parameter with default False."""
    import inspect

    from mcp_gway.core import discover_tools

    sig = inspect.signature(discover_tools)
    assert "force_auth" in sig.parameters
    assert sig.parameters["force_auth"].default is False


# --- refresh OAuth logic ---


def test_refresh_server_does_not_trigger_oauth_for_local(tmp_path, monkeypatch):
    """refresh on a local server must never call run_oauth_flow."""
    from mcp_gway.models import MCPServerConfig, ToolInfo

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    registry = Registry(servers_dir=servers_dir)
    config = MCPServerConfig(
        name="gitserver",
        type="local",
        command=["npx", "-y", "mcp-server-git"],
    )
    registry.add(config, [ToolInfo(name="clone", description="Clone a repo")])

    async def mock_discover_tools(cfg, force_auth=False):
        return [ToolInfo(name="clone", description="Clone a repo")]

    oauth_called = {"called": False}

    async def mock_run_oauth_flow(**kwargs):
        oauth_called["called"] = True

    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.oauth.run_oauth_flow", mock_run_oauth_flow)

    runner = CliRunner()
    result = runner.invoke(main, ["refresh", "gitserver"])
    assert result.exit_code == 0
    assert not oauth_called["called"], "OAuth should never run for local servers"


def test_refresh_server_tries_without_auth_first(tmp_path, monkeypatch):
    """refresh on remote server should call discover_tools without auth first."""
    from mcp_gway.models import MCPServerConfig, ToolInfo

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    registry = Registry(servers_dir=servers_dir)
    config = MCPServerConfig(
        name="myhttp",
        type="remote",
        url="http://localhost:9999/mcp",
    )
    registry.add(config, [ToolInfo(name="ping", description="Ping")])

    discover_calls = []

    async def mock_discover_tools(cfg, force_auth=False):
        discover_calls.append(force_auth)
        if not force_auth:
            return []  # Simulate failure without auth
        return [ToolInfo(name="ping", description="Ping")]

    oauth_result = type("FakeClient", (), {})()

    async def mock_run_oauth_flow(**kwargs):
        return oauth_result

    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.oauth.run_oauth_flow", mock_run_oauth_flow)

    runner = CliRunner()
    result = runner.invoke(main, ["refresh", "myhttp"])
    assert result.exit_code == 0
    assert discover_calls[0] is False, "First call should be without auth"
    assert discover_calls[1] is True, "Second call should be with auth"


def test_refresh_server_skips_oauth_when_no_auth_needed(tmp_path, monkeypatch):
    """If first attempt succeeds, OAuth should never be triggered."""
    from mcp_gway.models import MCPServerConfig, ToolInfo

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    registry = Registry(servers_dir=servers_dir)
    config = MCPServerConfig(
        name="public",
        type="remote",
        url="http://localhost:9999/mcp",
    )
    registry.add(config, [ToolInfo(name="ping", description="Ping")])

    discover_calls = []

    async def mock_discover_tools(cfg, force_auth=False):
        discover_calls.append(force_auth)
        return [ToolInfo(name="ping", description="Ping")]

    oauth_called = {"called": False}

    async def mock_run_oauth_flow(**kwargs):
        oauth_called["called"] = True

    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.oauth.run_oauth_flow", mock_run_oauth_flow)

    runner = CliRunner()
    result = runner.invoke(main, ["refresh", "public"])
    assert result.exit_code == 0
    assert len(discover_calls) == 1, "Should only call discover_tools once"
    assert discover_calls[0] is False, "Should try without auth first"
    assert not oauth_called["called"], "OAuth should not be triggered"


# --- OAuth callback port configurable ---


def test_run_oauth_flow_accepts_callback_port():
    """run_oauth_flow should accept callback_port parameter."""
    import inspect

    from mcp_gway.oauth import run_oauth_flow

    sig = inspect.signature(run_oauth_flow)
    assert "callback_port" in sig.parameters
    assert sig.parameters["callback_port"].default == 8989


def test_add_accepts_oauth_port_option():
    """CLI add command should accept --oauth-port option."""
    runner = CliRunner()
    result = runner.invoke(main, ["add", "--help"])
    assert "--oauth-port" in result.output


def test_refresh_accepts_oauth_port_option():
    """CLI refresh command should accept --oauth-port option."""
    runner = CliRunner()
    result = runner.invoke(main, ["refresh", "--help"])
    assert "--oauth-port" in result.output


# --- list command shows correct connection type ---


def test_list_shows_correct_type_for_new_format(tmp_path, monkeypatch):
    """list should show correct connection type from JSON config, not default HTTP."""
    from mcp_gway.models import MCPServerConfig, ToolInfo

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    registry = Registry(servers_dir=servers_dir)
    config = MCPServerConfig(
        name="gitserver",
        type="local",
        command=["npx", "-y", "mcp-server-git"],
    )
    registry.add(config, [ToolInfo(name="clone", description="Clone a repo")])

    runner = CliRunner()
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "LOCAL" in result.output
    assert "REMOTE" not in result.output


# --- refresh resilience ---


def test_refresh_continues_after_server_error(tmp_path, monkeypatch):
    """refresh should continue to next server if one fails."""
    from mcp_gway.models import MCPServerConfig, ToolInfo

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    registry = Registry(servers_dir=servers_dir)
    for name in ("server_a", "server_b"):
        config = MCPServerConfig(
            name=name,
            type="remote",
            url=f"http://localhost:9999/{name}",
        )
        registry.add(config, [ToolInfo(name="ping", description="Ping")])

    call_count = {"n": 0}

    async def mock_discover(cfg, force_auth=False):
        call_count["n"] += 1
        if cfg.name == "server_a":
            raise RuntimeError("Connection refused")
        return [ToolInfo(name="ping", description="Ping")]

    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover)

    runner = CliRunner()
    result = runner.invoke(main, ["refresh"])
    assert result.exit_code == 0
    assert "Error refreshing server_a" in result.output
    assert "Refreshed server_b" in result.output
    assert call_count["n"] == 2, "Both servers should be attempted"


# --- OpenCode-style CLI options ---


def test_add_remote_type(runner, monkeypatch):
    async def mock_discover_tools(config, force_auth=False):
        from mcp_gway.models import ToolInfo

        return [ToolInfo(name="search", description="Search videos")]

    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover_tools)
    result = runner.invoke(
        main,
        ["add", "myserver", "--type", "remote", "--url", "https://mcp.example.com/mcp"],
    )
    assert result.exit_code == 0, result.output
    assert "myserver" in result.output


def test_add_local_type(runner, monkeypatch):
    async def mock_discover_tools(config, force_auth=False):
        from mcp_gway.models import ToolInfo

        return [ToolInfo(name="ping", description="Ping")]

    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover_tools)
    result = runner.invoke(
        main, ["add", "myserver", "--type", "local", "--command", "npx -y my-mcp"]
    )
    assert result.exit_code == 0, result.output


def test_add_with_header_option(runner, monkeypatch):
    async def mock_discover_tools(config, force_auth=False):
        from mcp_gway.models import ToolInfo

        return [ToolInfo(name="search", description="Search")]

    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover_tools)
    result = runner.invoke(
        main,
        [
            "add",
            "myserver",
            "--type",
            "remote",
            "--url",
            "https://mcp.example.com/mcp",
            "--header",
            "Authorization=Bearer TOKEN",
        ],
    )
    assert result.exit_code == 0, result.output


def test_add_with_timeout_option(runner, monkeypatch):
    async def mock_discover_tools(config, force_auth=False):
        from mcp_gway.models import ToolInfo

        return [ToolInfo(name="search", description="Search")]

    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover_tools)
    result = runner.invoke(
        main,
        [
            "add",
            "myserver",
            "--type",
            "remote",
            "--url",
            "https://mcp.example.com/mcp",
            "--timeout",
            "10000",
        ],
    )
    assert result.exit_code == 0, result.output


def test_list_shows_remote_type(tmp_path, monkeypatch):
    from mcp_gway.models import MCPServerConfig, ToolInfo

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    registry = Registry(servers_dir=servers_dir)
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
    )
    registry.add(config, [ToolInfo(name="search", description="Search")])

    runner = CliRunner()
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "REMOTE" in result.output


def test_list_shows_local_type(tmp_path, monkeypatch):
    from mcp_gway.models import MCPServerConfig, ToolInfo

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    registry = Registry(servers_dir=servers_dir)
    config = MCPServerConfig(
        name="myserver",
        type="local",
        command=["npx", "-y", "my-mcp"],
    )
    registry.add(config, [ToolInfo(name="ping", description="Ping")])

    runner = CliRunner()
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "LOCAL" in result.output


def test_add_remote_auto_detects_transport(runner, monkeypatch):
    """add --type remote should call detect_transport and store result."""
    from mcp_gway.models import ToolInfo

    async def mock_discover_tools(config, force_auth=False):
        assert config.resolved_transport == "streamable-http"
        return [ToolInfo(name="search", description="Search")]

    async def mock_detect_transport(config):
        return "streamable-http"

    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.cli.detect_transport", mock_detect_transport)
    monkeypatch.setattr("mcp_gway.core.detect_transport", mock_detect_transport)
    monkeypatch.setattr(
        "mcp_gway.core.transport.detect_transport", mock_detect_transport
    )
    result = runner.invoke(
        main,
        ["add", "myserver", "--type", "remote", "--url", "https://mcp.example.com/mcp"],
    )
    assert result.exit_code == 0
    assert "myserver" in result.output


def test_add_remote_detect_failure_still_adds(runner, monkeypatch):
    """If detect_transport fails, add should still succeed with empty transport."""
    from mcp_gway.models import ToolInfo

    async def mock_discover_tools(config, force_auth=False):
        assert (
            config.resolved_transport is None
            or config.resolved_transport == "streamable-http"
        )
        return [ToolInfo(name="search", description="Search")]

    async def mock_detect_transport(config):
        raise ConnectionError("All transports failed for https://...")

    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.cli.detect_transport", mock_detect_transport)
    monkeypatch.setattr("mcp_gway.core.detect_transport", mock_detect_transport)
    monkeypatch.setattr(
        "mcp_gway.core.transport.detect_transport", mock_detect_transport
    )
    result = runner.invoke(
        main,
        ["add", "myserver", "--type", "remote", "--url", "https://mcp.example.com/mcp"],
    )
    assert result.exit_code == 0


def test_add_rejects_legacy_type_http(runner):
    result = runner.invoke(
        main, ["add", "myserver", "--type", "http", "--url", "https://example.com"]
    )
    assert result.exit_code != 0
    assert "Invalid value" in result.output or "is not one of" in result.output


def test_add_rejects_legacy_type_stdio(runner):
    result = runner.invoke(
        main, ["add", "myserver", "--type", "stdio", "--command", "node server.js"]
    )
    assert result.exit_code != 0


def test_add_rejects_legacy_args_option(runner):
    result = runner.invoke(
        main,
        [
            "add",
            "myserver",
            "--type",
            "local",
            "--command",
            "node",
            "--args",
            '["server.js"]',
        ],
    )
    assert result.exit_code != 0
    assert "No such option" in result.output


def test_add_rejects_legacy_docs_url_option(runner):
    result = runner.invoke(
        main,
        [
            "add",
            "myserver",
            "--type",
            "remote",
            "--url",
            "https://example.com",
            "--docs-url",
            "https://docs.example.com",
        ],
    )
    assert result.exit_code != 0
    assert "No such option" in result.output


def test_add_local_with_env_stores_environment(tmp_path, monkeypatch):
    """add --env should populate environment dict in stored config."""
    from mcp_gway.models import ToolInfo
    from mcp_gway.registry import Registry

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    async def mock_discover_tools(config, force_auth=False):
        return [ToolInfo(name="ping", description="Ping")]

    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover_tools)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "add",
            "myserver",
            "--type",
            "local",
            "--command",
            "node server.js",
            "--env",
            "FOO=bar",
            "--env",
            "BAZ=qux",
        ],
    )
    assert result.exit_code == 0, result.output

    registry = Registry(servers_dir=servers_dir)
    config = registry.get_config("myserver")
    assert config.environment == {"FOO": "bar", "BAZ": "qux"}


def test_create_client_transport_local_env(tmp_path, monkeypatch):
    """create_client_transport should handle environment for local config."""
    import asyncio

    from mcp_gway.models import MCPServerConfig

    config = MCPServerConfig(
        name="envtest",
        type="local",
        command=["npx", "hello"],
        environment={"FOO": "bar", "BAZ": "qux"},
    )

    captured_params = {}

    def mock_filtered_stdio_client(*, server=None, read_stream=None, on_noise=None):
        from contextlib import asynccontextmanager

        class _FakeStream:
            def __init__(self, items):
                self._items = iter(items)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration

        captured_params["env"] = server.env if server else None

        @asynccontextmanager
        async def _fake():
            msg = {"jsonrpc": "2.0", "id": 1, "result": {}}
            from mcp_gway.stdio_transport import _FilteredReadStream

            stream = _FilteredReadStream(_FakeStream([msg]), on_noise)
            yield stream, None

        return _fake()

    monkeypatch.setattr(
        "mcp_gway.stdio_transport.filtered_stdio_client",
        mock_filtered_stdio_client,
    )
    monkeypatch.setattr(
        "mcp_gway.stdio_transport.resolve_windows_command", lambda cmd: cmd
    )

    async def run_test():
        from mcp_gway.core import create_client_transport

        async with create_client_transport(config) as (_read, _write):
            pass

    asyncio.run(run_test())
    assert captured_params["env"] == {"FOO": "bar", "BAZ": "qux"}
