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
        return None

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
        return None

    monkeypatch.setattr("mcp_gway.cli._discover_tools", mock_discover_tools)
    monkeypatch.setattr("mcp_gway.oauth.run_oauth_flow", mock_run_oauth_flow)

    runner = CliRunner()
    result = runner.invoke(main, ["refresh", "public"])
    assert result.exit_code == 0
    assert len(discover_calls) == 1, "Should only call _discover_tools once"
    assert discover_calls[0] is False, "Should try without auth first"
    assert not oauth_called["called"], "OAuth should not be triggered"
