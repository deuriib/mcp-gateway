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


def test_streamable_http_requires_connection_string():
    with pytest.raises(ValueError, match="connection_string required"):
        MCPClientConfig(name="myserver", connection_type=ConnectionType.STREAMABLE_HTTP)


def test_streamable_http_valid():
    config = MCPClientConfig(
        name="myserver",
        connection_type=ConnectionType.STREAMABLE_HTTP,
        connection_string="http://localhost:3001/mcp",
    )
    assert config.connection_type == ConnectionType.STREAMABLE_HTTP


# ──────────────────────────────────────────────────────────────────────
# New OpenCode-schema models: MCPServerConfig + OAuthConfig
# ──────────────────────────────────────────────────────────────────────

from mcp_gway.models import MCPServerConfig, OAuthConfig


def test_remote_config_valid():
    config = MCPServerConfig(
        name="youtube",
        type="remote",
        url="https://mcp.example.com/mcp",
    )
    assert config.name == "youtube"
    assert config.type == "remote"
    assert config.url == "https://mcp.example.com/mcp"
    assert config.enabled is True
    assert config.timeout == 5000


def test_local_config_valid():
    config = MCPServerConfig(
        name="myserver",
        type="local",
        command=["npx", "-y", "my-mcp-server"],
    )
    assert config.type == "local"
    assert config.command == ["npx", "-y", "my-mcp-server"]


def test_local_requires_command():
    with pytest.raises(ValueError, match="command.*required"):
        MCPServerConfig(name="myserver", type="local")


def test_remote_requires_url():
    with pytest.raises(ValueError, match="url.*required"):
        MCPServerConfig(name="myserver", type="remote")


def test_remote_with_headers():
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
        headers={"Authorization": "Bearer TOKEN"},
    )
    assert config.headers == {"Authorization": "Bearer TOKEN"}


def test_remote_with_oauth_object():
    cid = "550e8400-e29b-41d4-a716-446655440000"
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
        oauth=OAuthConfig(clientId=cid, clientSecret="secret"),
    )
    assert config.oauth.clientId == cid


def test_remote_with_oauth_false():
    config = MCPServerConfig(
        name="myserver",
        type="remote",
        url="https://mcp.example.com/mcp",
        oauth=False,
    )
    assert config.oauth is False


def test_local_with_environment():
    config = MCPServerConfig(
        name="myserver",
        type="local",
        command=["node", "server.js"],
        environment={"FOO": "bar", "BAZ": "qux"},
    )
    assert config.environment == {"FOO": "bar", "BAZ": "qux"}


def test_local_with_cwd():
    config = MCPServerConfig(
        name="myserver",
        type="local",
        command=["python", "-m", "server"],
        cwd="/path/to/workdir",
    )
    assert config.cwd == "/path/to/workdir"


def test_oauth_client_id_auto_uuid():
    import uuid

    cfg = MCPServerConfig(
        name="s", type="remote", url="https://x", oauth={"clientId": "not-a-uuid"}
    )
    assert cfg.oauth.clientId != "not-a-uuid"
    uuid.UUID(cfg.oauth.clientId)

    cfg2 = MCPServerConfig(
        name="s2", type="remote", url="https://x", oauth={"scope": "openid"}
    )
    assert cfg2.oauth.clientId is not None
    uuid.UUID(cfg2.oauth.clientId)


def test_oauth_client_id_valid_uuid_kept():
    import uuid

    cid = str(uuid.uuid4())
    cfg = MCPServerConfig(
        name="s3", type="remote", url="https://x", oauth=OAuthConfig(clientId=cid)
    )
    assert cfg.oauth.clientId == cid
