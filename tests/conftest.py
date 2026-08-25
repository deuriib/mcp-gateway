"""Shared test fixtures."""

import pytest

from mcp_gway.models import (
    ConnectionType,
    MCPClientConfig,
    MCPServerConfig,
)


@pytest.fixture
def http_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="testserver",
        type="remote",
        url="http://localhost:3001/mcp",
    )


@pytest.fixture
def stdio_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="teststdio",
        type="local",
        command=["echo", "hello"],
    )


@pytest.fixture
def legacy_http_config() -> MCPClientConfig:
    return MCPClientConfig(
        name="testserver",
        connection_type=ConnectionType.HTTP,
        connection_string="http://localhost:3001/mcp",
    )
