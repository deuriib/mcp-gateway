"""Tests for CLI commands."""

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


def test_add_http_server(runner, monkeypatch):
    async def mock_discover_tools(config, force_auth=False):
        from mcp_gway.models import ToolInfo

        return [ToolInfo(name="search", description="Search videos")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    result = runner.invoke(
        main, ["add", "youtube", "--type", "http", "--url", "http://localhost:3001/mcp"]
    )
    assert result.exit_code == 0
    assert "youtube" in result.output


def test_inspect_server(runner, monkeypatch):
    async def mock_discover_tools(config, force_auth=False):
        from mcp_gway.models import ToolInfo

        return [ToolInfo(name="search", description="Search videos")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    runner.invoke(
        main, ["add", "youtube", "--type", "http", "--url", "http://localhost:3001/mcp"]
    )
    result = runner.invoke(main, ["inspect", "youtube"])
    assert result.exit_code == 0
    assert "search" in result.output


# --- Bug 1: _discover_tools signature ---


def test_discover_tools_accepts_force_auth():
    """_discover_tools should accept force_auth parameter with default False."""
    import inspect

    from mcp_gway.cli import _discover_tools

    sig = inspect.signature(_discover_tools)
    assert "force_auth" in sig.parameters
    assert sig.parameters["force_auth"].default is False


# --- Bug 1: refresh OAuth logic ---


def test_refresh_server_does_not_trigger_oauth_for_stdio(tmp_path, monkeypatch):
    """refresh on a stdio server must never call run_oauth_flow."""
    from mcp_gway.models import ConnectionType, MCPClientConfig, StdioConfig, ToolInfo

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    # Pre-populate the registry with a stdio server
    registry = Registry(servers_dir=servers_dir)
    config = MCPClientConfig(
        name="gitserver",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["-y", "mcp-server-git"]),
    )
    registry.add(config, [ToolInfo(name="clone", description="Clone a repo")])

    async def mock_discover_tools(cfg, force_auth=False):
        return [ToolInfo(name="clone", description="Clone a repo")]

    oauth_called = {"called": False}

    async def mock_run_oauth_flow(**kwargs):
        oauth_called["called"] = True

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.oauth.run_oauth_flow", mock_run_oauth_flow)

    runner = CliRunner()
    result = runner.invoke(main, ["refresh", "gitserver"])
    assert result.exit_code == 0
    assert not oauth_called["called"], "OAuth should never run for stdio servers"


def test_refresh_server_tries_without_auth_first(tmp_path, monkeypatch):
    """refresh on HTTP server should call _discover_tools without auth first."""
    from mcp_gway.models import ConnectionType, MCPClientConfig, ToolInfo

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    # Pre-populate the registry
    registry = Registry(servers_dir=servers_dir)
    config = MCPClientConfig(
        name="myhttp",
        connection_type=ConnectionType.HTTP,
        connection_string="http://localhost:9999/mcp",
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

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.oauth.run_oauth_flow", mock_run_oauth_flow)

    runner = CliRunner()
    result = runner.invoke(main, ["refresh", "myhttp"])
    assert result.exit_code == 0
    # Should first try without auth, then with auth
    assert discover_calls[0] is False, "First call should be without auth"
    assert discover_calls[1] is True, "Second call should be with auth"


def test_refresh_server_skips_oauth_when_no_auth_needed(tmp_path, monkeypatch):
    """If first attempt succeeds, OAuth should never be triggered."""
    from mcp_gway.models import ConnectionType, MCPClientConfig, ToolInfo

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    registry = Registry(servers_dir=servers_dir)
    config = MCPClientConfig(
        name="public",
        connection_type=ConnectionType.SSE,
        connection_string="http://localhost:9999/sse",
    )
    registry.add(config, [ToolInfo(name="ping", description="Ping")])

    discover_calls = []

    async def mock_discover_tools(cfg, force_auth=False):
        discover_calls.append(force_auth)
        return [ToolInfo(name="ping", description="Ping")]

    oauth_called = {"called": False}

    async def mock_run_oauth_flow(**kwargs):
        oauth_called["called"] = True

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.oauth.run_oauth_flow", mock_run_oauth_flow)

    runner = CliRunner()
    result = runner.invoke(main, ["refresh", "public"])
    assert result.exit_code == 0
    assert len(discover_calls) == 1, "Should only call _discover_tools once"
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
    from click.testing import CliRunner

    from mcp_gway.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["add", "--help"])
    assert "--oauth-port" in result.output


def test_refresh_accepts_oauth_port_option():
    """CLI refresh command should accept --oauth-port option."""
    from click.testing import CliRunner

    from mcp_gway.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["refresh", "--help"])
    assert "--oauth-port" in result.output


# --- FIX 1: --env option and env passthrough ---


def test_add_stdio_with_env(tmp_path, monkeypatch):
    """add --env KEY=VALUE should populate StdioConfig.envs in stored config."""
    from mcp_gway.models import ToolInfo
    from mcp_gway.registry import Registry

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    async def mock_discover_tools(config, force_auth=False):
        return [ToolInfo(name="ping", description="Ping")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "add",
            "myserver",
            "--type",
            "stdio",
            "--command",
            "node",
            "--env",
            "FOO=bar",
            "--env",
            "BAZ=qux",
        ],
    )
    assert result.exit_code == 0, result.output

    registry = Registry(servers_dir=servers_dir)
    config = registry.get_config("myserver")
    assert config.stdio_config is not None
    assert config.stdio_config.envs == ["FOO=bar", "BAZ=qux"]


def test_create_client_transport_passes_env(tmp_path, monkeypatch):
    """_create_client_transport should parse envs into a dict for StdioServerParameters."""
    import asyncio

    from mcp_gway.models import ConnectionType, MCPClientConfig, StdioConfig

    config = MCPClientConfig(
        name="envtest",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(
            command="echo",
            args=["hello"],
            envs=["FOO=bar", "BAZ=qux"],
        ),
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
        from mcp_gway.cli import _create_client_transport

        async with _create_client_transport(config) as (_read, _write):
            pass

    asyncio.run(run_test())
    assert captured_params["env"] == {"FOO": "bar", "BAZ": "qux"}


def test_create_client_transport_passes_on_noise(tmp_path, monkeypatch):
    """_create_client_transport should pass on_noise callback to filtered_stdio_client."""
    import asyncio

    from mcp_gway.models import ConnectionType, MCPClientConfig, StdioConfig

    config = MCPClientConfig(
        name="noisetest",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(command="echo", args=["hello"]),
    )

    captured_on_noise: dict[str, object] = {}

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

        captured_on_noise["callback"] = on_noise

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
        from mcp_gway.cli import _create_client_transport

        async with _create_client_transport(config) as (_read, _write):
            pass

    asyncio.run(run_test())
    assert captured_on_noise["callback"] is not None, (
        "on_noise callback should be passed to filtered_stdio_client"
    )


# --- list command shows correct connection type ---


def test_list_shows_correct_type_for_new_format(tmp_path, monkeypatch):
    """list should show correct connection type from JSON config, not default HTTP."""
    from mcp_gway.models import ConnectionType, MCPClientConfig, StdioConfig, ToolInfo

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    registry = Registry(servers_dir=servers_dir)
    config = MCPClientConfig(
        name="gitserver",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["-y", "mcp-server-git"]),
    )
    registry.add(config, [ToolInfo(name="clone", description="Clone a repo")])

    from click.testing import CliRunner

    from mcp_gway.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "STDIO" in result.output or "LOCAL" in result.output
    assert "HTTP" not in result.output


# --- refresh resilience ---


def test_refresh_continues_after_server_error(tmp_path, monkeypatch):
    """refresh should continue to next server if one fails."""
    from mcp_gway.models import ConnectionType, MCPClientConfig, ToolInfo

    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()

    def mock_get_registry():
        return Registry(servers_dir=servers_dir)

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    registry = Registry(servers_dir=servers_dir)
    # Add two servers
    for name in ("server_a", "server_b"):
        config = MCPClientConfig(
            name=name,
            connection_type=ConnectionType.HTTP,
            connection_string=f"http://localhost:9999/{name}",
        )
        registry.add(config, [ToolInfo(name="ping", description="Ping")])

    call_count = {"n": 0}

    async def mock_discover(cfg, force_auth=False):
        call_count["n"] += 1
        if cfg.name == "server_a":
            raise RuntimeError("Connection refused")
        return [ToolInfo(name="ping", description="Ping")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover)

    from click.testing import CliRunner

    from mcp_gway.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["refresh"])
    assert result.exit_code == 0
    assert "Error refreshing server_a" in result.output
    assert "Refreshed server_b" in result.output
    assert call_count["n"] == 2, "Both servers should be attempted"


# --- Task 4: OpenCode-style CLI options ---


def test_add_remote_type(runner, monkeypatch):
    async def mock_discover_tools(config, force_auth=False):
        from mcp_gway.models import ToolInfo

        return [ToolInfo(name="search", description="Search videos")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
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

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    result = runner.invoke(
        main, ["add", "myserver", "--type", "local", "--command", "npx -y my-mcp"]
    )
    assert result.exit_code == 0, result.output


def test_add_with_header_option(runner, monkeypatch):
    async def mock_discover_tools(config, force_auth=False):
        from mcp_gway.models import ToolInfo

        return [ToolInfo(name="search", description="Search")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
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

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
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


def test_add_backward_compat_stdio(runner, monkeypatch):
    async def mock_discover_tools(config, force_auth=False):
        from mcp_gway.models import ToolInfo

        return [ToolInfo(name="ping", description="Ping")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    result = runner.invoke(
        main,
        [
            "add",
            "myserver",
            "--type",
            "stdio",
            "--command",
            "node",
            "--args",
            '["server.js"]',
        ],
    )
    assert result.exit_code == 0, result.output


def test_add_backward_compat_sse(runner, monkeypatch):
    async def mock_discover_tools(config, force_auth=False):
        from mcp_gway.models import ToolInfo

        return [ToolInfo(name="ping", description="Ping")]

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    result = runner.invoke(
        main, ["add", "myserver", "--type", "sse", "--url", "https://example.com/sse"]
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
