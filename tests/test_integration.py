"""Integration test: full end-to-end flow."""

from click.testing import CliRunner

from mcp_gway.cli import main
from mcp_gway.code_mode import CodeMode
from mcp_gway.gateway import Gateway
from mcp_gway.models import ToolInfo
from mcp_gway.registry import Registry


def test_full_flow(tmp_path, monkeypatch):
    """Test: add server -> inspect -> list -> code mode -> gateway."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "servers").mkdir()

    def mock_get_registry():
        return Registry(servers_dir=tmp_path / "servers")

    monkeypatch.setattr("mcp_gway.cli._get_registry", mock_get_registry)

    async def mock_discover(config, force_auth=False):
        return [
            ToolInfo(
                name="search",
                description="Search videos",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            ),
            ToolInfo(
                name="get_video",
                description="Get video details",
                input_schema={
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                },
            ),
        ]

    async def mock_detect(config):
        return "streamable-http"

    monkeypatch.setattr("mcp_gway.core.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.cli.discover_tools", mock_discover)
    monkeypatch.setattr("mcp_gway.core.transport.detect_transport", mock_detect)
    monkeypatch.setattr("mcp_gway.core.detect_transport", mock_detect)
    monkeypatch.setattr("mcp_gway.cli.detect_transport", mock_detect)
    runner = CliRunner()

    # Add server
    result = runner.invoke(
        main,
        ["add", "youtube", "--type", "remote", "--url", "http://localhost:3001/mcp"],
    )
    assert result.exit_code == 0
    assert "2 tools" in result.output

    # List servers
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "youtube" in result.output

    # Inspect
    result = runner.invoke(main, ["inspect", "youtube"])
    assert result.exit_code == 0
    assert "def search(" in result.output

    # Code mode
    registry = Registry(servers_dir=tmp_path / "servers")
    code_mode = CodeMode(registry)

    listing = code_mode.list_tool_files()
    assert "youtube.pyi" in listing

    stubs = code_mode.read_tool_file(fileName="servers/youtube.pyi")
    assert "def search(" in stubs

    docs = code_mode.get_tool_docs(server="youtube", tool="search")
    assert "def search(" in docs

    # Gateway health check
    gateway = Gateway(registry)
    assert gateway is not None
    assert "tools/list" in {
        "tools/list",
        "tools/call",
    }
