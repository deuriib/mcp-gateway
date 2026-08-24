"""Tests for CLI commands."""

import pytest
from click.testing import CliRunner

from mcp_gateway.cli import main


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "servers").mkdir()
    return CliRunner()


def test_list_empty(runner):
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "No servers" in result.output


def test_add_http_server(runner, monkeypatch):
    async def mock_discover_tools(config):
        from mcp_gateway.models import ToolInfo

        return [ToolInfo(name="search", description="Search videos")]

    monkeypatch.setattr("mcp_gateway.cli._discover_tools", mock_discover_tools)
    result = runner.invoke(
        main, ["add", "youtube", "--type", "http", "--url", "http://localhost:3001/mcp"]
    )
    assert result.exit_code == 0
    assert "youtube" in result.output


def test_inspect_server(runner, monkeypatch):
    async def mock_discover_tools(config):
        from mcp_gateway.models import ToolInfo

        return [ToolInfo(name="search", description="Search videos")]

    monkeypatch.setattr("mcp_gateway.cli._discover_tools", mock_discover_tools)
    runner.invoke(
        main, ["add", "youtube", "--type", "http", "--url", "http://localhost:3001/mcp"]
    )
    result = runner.invoke(main, ["inspect", "youtube"])
    assert result.exit_code == 0
    assert "search" in result.output
