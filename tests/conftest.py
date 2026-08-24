"""Shared test fixtures."""

import pytest

from mcp_gway.models import ConnectionType, MCPClientConfig, StdioConfig


@pytest.fixture
def http_config() -> MCPClientConfig:
    return MCPClientConfig(
        name="testserver",
        connection_type=ConnectionType.HTTP,
        connection_string="http://localhost:3001/mcp",
    )


@pytest.fixture
def stdio_config() -> MCPClientConfig:
    return MCPClientConfig(
        name="teststdio",
        connection_type=ConnectionType.STDIO,
        stdio_config=StdioConfig(command="echo", args=["hello"]),
    )
