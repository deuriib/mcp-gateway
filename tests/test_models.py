"""Tests for MCP client config models."""

import pytest

from mcp_gway.models import ConnectionType, MCPClientConfig, StdioConfig


def test_http_config_valid():
    config = MCPClientConfig(
        name="youtube",
        connection_type=ConnectionType.HTTP,
        connection_string="http://localhost:3001/mcp",
    )
    assert config.name == "youtube"
    assert config.connection_type == ConnectionType.HTTP
    assert config.is_code_mode_client is True


def test_stdio_config_valid():
    config = MCPClientConfig(
        name="filesystem",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(
            command="npx", args=["-y", "@anthropic/mcp-filesystem"]
        ),
    )
    assert config.stdio_config.command == "npx"


def test_name_rejects_hyphens():
    with pytest.raises(ValueError, match="hyphens"):
        MCPClientConfig(
            name="my-tools",
            connection_type=ConnectionType.HTTP,
            connection_string="http://localhost:3001/mcp",
        )


def test_name_rejects_leading_digit():
    with pytest.raises(ValueError, match="number"):
        MCPClientConfig(
            name="123tools",
            connection_type=ConnectionType.HTTP,
            connection_string="http://localhost:3001/mcp",
        )


def test_name_rejects_non_ascii():
    with pytest.raises(ValueError, match="ASCII"):
        MCPClientConfig(
            name="datös",
            connection_type=ConnectionType.HTTP,
            connection_string="http://localhost:3001/mcp",
        )


def test_http_requires_connection_string():
    with pytest.raises(ValueError, match="connection_string required"):
        MCPClientConfig(name="youtube", connection_type=ConnectionType.HTTP)


def test_stdio_requires_stdio_config():
    with pytest.raises(ValueError, match="stdio_config required"):
        MCPClientConfig(name="filesystem", connection_type=ConnectionType.STDIO)
