"""FEAT-006 AC-001..AC-012 — dynamic local commands (TestClient, mock discover)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_gway.gateway import Gateway
from mcp_gway.registry import Registry


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    return Registry(servers_dir=tmp_path / "servers")


@pytest.fixture
def gateway(registry: Registry) -> Gateway:
    return Gateway(registry)


def _mock_discover(monkeypatch) -> None:
    async def _mock(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.core.discover_tools", _mock)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", _mock)


def _allow(monkeypatch, tmp_path, binaries: str) -> None:
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", binaries)
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "1")
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    mapping = {
        b.strip(): f"/usr/bin/{b.strip()}" for b in binaries.split(",") if b.strip()
    }

    def _which(basename: str) -> str | None:
        return mapping.get(basename)

    monkeypatch.setattr("mcp_gway.core.policy.resolve_binary", _which)
    monkeypatch.setattr("mcp_gway.core.policy.check_cwd", lambda cwd: str(tmp_path))


async def _post_local(
    client: AsyncClient, name: str, command: list[str], tmp_path: Path
) -> object:
    return await client.post(
        "/api/servers",
        json={"name": name, "type": "local", "command": command, "cwd": str(tmp_path)},
    )


@pytest.mark.asyncio
async def test_ac001_allow_list_permits(
    gateway, registry, monkeypatch, tmp_path
) -> None:
    _mock_discover(monkeypatch)
    _allow(monkeypatch, tmp_path, "mybin")
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await _post_local(client, "a", ["mybin"], tmp_path)
        assert resp.status_code == 201


@pytest.mark.asyncio
async def test_ac002_default_deny(gateway, monkeypatch, tmp_path) -> None:
    _mock_discover(monkeypatch)
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "")
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await _post_local(client, "b", ["otherbin"], tmp_path)
        assert resp.status_code == 403
        assert resp.json()["reason_code"] == "not_allowlisted"


@pytest.mark.asyncio
async def test_ac003_wildcard_denied(gateway, monkeypatch, tmp_path) -> None:
    _mock_discover(monkeypatch)
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "*")
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    monkeypatch.setattr(
        "mcp_gway.core.policy.resolve_binary", lambda b: "/usr/bin/mybin"
    )
    monkeypatch.setattr("mcp_gway.core.policy.check_cwd", lambda cwd: str(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await _post_local(client, "c", ["mybin"], tmp_path)
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ac004_unrestricted_fresh(
    gateway, registry, monkeypatch, tmp_path
) -> None:
    _mock_discover(monkeypatch)
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "")
    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    monkeypatch.setattr(
        "mcp_gway.core.policy.marker_path", lambda: tmp_path / ".local_unrestricted"
    )
    (tmp_path / ".local_unrestricted").write_text(str(int(time.time())))
    monkeypatch.setattr("mcp_gway.core.policy.resolve_binary", lambda b: "/bin/x")
    monkeypatch.setattr("mcp_gway.core.policy.check_cwd", lambda cwd: str(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await _post_local(client, "d", ["freshbin"], tmp_path)
        assert resp.status_code == 201


@pytest.mark.asyncio
async def test_ac005_unrestricted_expired(gateway, monkeypatch, tmp_path) -> None:
    _mock_discover(monkeypatch)
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "")
    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    monkeypatch.setattr(
        "mcp_gway.core.policy.marker_path", lambda: tmp_path / ".local_unrestricted"
    )
    (tmp_path / ".local_unrestricted").write_text(str(int(time.time()) - 73 * 3600))
    monkeypatch.setattr("mcp_gway.core.policy.check_cwd", lambda cwd: str(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await _post_local(client, "e", ["freshbin"], tmp_path)
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ac006_via_disabled(gateway, monkeypatch, tmp_path) -> None:
    _mock_discover(monkeypatch)
    _allow(monkeypatch, tmp_path, "mybin")
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "0")
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await _post_local(client, "f", ["mybin"], tmp_path)
        assert resp.status_code == 403
        assert resp.json()["reason_code"] == "via_dashboard_disabled"


@pytest.mark.asyncio
async def test_ac007_non_loopback(registry, monkeypatch, tmp_path) -> None:
    _mock_discover(monkeypatch)
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "mybin")
    monkeypatch.setattr(
        "mcp_gway.core.policy.resolve_binary", lambda b: "/usr/bin/mybin"
    )
    monkeypatch.setattr("mcp_gway.core.policy.check_cwd", lambda cwd: str(tmp_path))
    exposed = Gateway(registry, host="0.0.0.0")
    async with AsyncClient(
        transport=ASGITransport(app=exposed.app), base_url="http://test"
    ) as client:
        resp = await _post_local(client, "g", ["mybin"], tmp_path)
        assert resp.status_code == 403
        assert resp.json()["reason_code"] == "non_loopback_denied"


@pytest.mark.asyncio
async def test_ac008_binary_missing(gateway, monkeypatch, tmp_path) -> None:
    _mock_discover(monkeypatch)
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "mybin")
    monkeypatch.setattr("mcp_gway.core.policy.resolve_binary", lambda b: None)
    monkeypatch.setattr("mcp_gway.core.policy.check_cwd", lambda cwd: str(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await _post_local(client, "h", ["mybin"], tmp_path)
        assert resp.status_code == 403
        body = resp.json()
        assert body["reason_code"] == "binary_not_found"
        assert "binary not found in PATH" in body["detail"]


@pytest.mark.asyncio
async def test_ac009_patch_regate(gateway, registry, monkeypatch, tmp_path) -> None:
    _mock_discover(monkeypatch)
    _allow(monkeypatch, tmp_path, "mybin")
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await _post_local(client, "srv", ["mybin"], tmp_path)
        assert resp.status_code == 201
        resp2 = await client.patch(
            "/api/servers/srv", json={"command": ["evilbin"], "_from_edit": True}
        )
        assert resp2.status_code == 403
        cfg = registry.get_config("srv")
        assert cfg.command == ["mybin"]


@pytest.mark.asyncio
async def test_ac010_refresh_regate(gateway, monkeypatch, tmp_path) -> None:
    _mock_discover(monkeypatch)
    _allow(monkeypatch, tmp_path, "mybin")
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await _post_local(client, "srv2", ["mybin"], tmp_path)
        assert resp.status_code == 201
        monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "otherbin")
        resp2 = await client.post("/api/servers/srv2/refresh")
        assert resp2.status_code == 403


@pytest.mark.asyncio
async def test_ac011_cwd_env(gateway, monkeypatch, tmp_path) -> None:
    _mock_discover(monkeypatch)
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "mybin")
    monkeypatch.setattr(
        "mcp_gway.core.policy.resolve_binary", lambda b: "/usr/bin/mybin"
    )
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        r1 = await client.post(
            "/api/servers",
            json={
                "name": "cwd1",
                "type": "local",
                "command": ["mybin"],
                "cwd": "relative/path",
            },
        )
        assert r1.status_code == 400
        r2 = await client.post(
            "/api/servers",
            json={
                "name": "env1",
                "type": "local",
                "command": ["mybin"],
                "environment": {"PATH": "x"},
            },
        )
        assert r2.status_code == 400
        r3 = await client.post(
            "/api/servers",
            json={
                "name": "env2",
                "type": "local",
                "command": ["mybin"],
                "environment": {"DYLD_FOO": "x"},
            },
        )
        assert r3.status_code == 400


def test_ac012_cli_ignores_via(monkeypatch, tmp_path) -> None:
    from click.testing import CliRunner

    from mcp_gway.cli import main

    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "0")
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "mybin")
    monkeypatch.setattr(
        "mcp_gway.core.policy.resolve_binary", lambda b: "/usr/bin/mybin"
    )

    async def _mock(config, force_auth=False):  # noqa: ARG001
        from mcp_gway.models import ToolInfo

        return [ToolInfo(name="ping", description="")]

    monkeypatch.setattr("mcp_gway.cli.discover_tools", _mock)
    monkeypatch.setattr("mcp_gway.core.discover_tools", _mock)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            main, ["add", "clibin", "--type", "local", "--command", "mybin"]
        )
        assert result.exit_code == 0, result.output
