"""FEAT-006 harden loop — marker 644, strip-env, TOCTOU, cwd-canonical, audit ***, no persist on deny."""

from __future__ import annotations

import os
import stat
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


def test_marker_wrong_mode_denied(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy

    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    marker = tmp_path / ".local_unrestricted"
    marker.write_text(str(int(time.time())))
    monkeypatch.setattr(policy, "marker_path", lambda: marker)

    class _FakeStat:
        st_mode = stat.S_IFREG | 0o644

    monkeypatch.setattr(Path, "stat", lambda self: _FakeStat())
    monkeypatch.setattr(os, "name", "posix")
    assert policy.is_unrestricted_active() is False


def test_marker_read_capped_no_crash(monkeypatch, tmp_path: Path) -> None:
    from mcp_gway.core import policy

    monkeypatch.setenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", "1")
    marker = tmp_path / ".local_unrestricted"
    marker.write_text("not-a-number-" + "x" * 5000)
    monkeypatch.setattr(policy, "marker_path", lambda: marker)
    assert policy.is_unrestricted_active() is False


def test_strip_env_and_allow_list_case_insensitive(monkeypatch) -> None:
    from mcp_gway.core.parsing import parse_envs, parse_headers
    from mcp_gway.core.policy import check_basename_allowed, get_allow_list

    assert parse_envs([" PATH = x "]) == {"PATH": "x"}
    assert parse_headers([" Authorization = Bearer t "]) == {
        "Authorization": "Bearer t"
    }
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "MyBin, mybin , MYBIN")
    assert get_allow_list() == {"mybin"}
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "1")
    monkeypatch.setattr(
        "mcp_gway.core.policy.is_unrestricted_active", lambda now=None: False
    )
    monkeypatch.setattr(
        "mcp_gway.core.policy.resolve_binary", lambda b: "/usr/bin/mybin"
    )
    d = check_basename_allowed("MYBIN", via_dashboard=False, host_loopback=True)
    assert d.allowed is True
    assert d.reason_code == "allow_list"


@pytest.mark.asyncio
async def test_toctou_regate_no_persist(
    gateway, registry, monkeypatch, tmp_path
) -> None:
    from mcp_gway.dashboard import api as dapi

    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "mybin")
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "1")
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    monkeypatch.setattr(
        "mcp_gway.core.policy.resolve_binary", lambda b: "/usr/bin/mybin"
    )
    monkeypatch.setattr("mcp_gway.core.policy.check_cwd", lambda cwd: str(tmp_path))

    async def _flipping(config, force_auth=False):  # noqa: ARG001
        monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "otherbin")
        return []

    monkeypatch.setattr("mcp_gway.core.discover_tools", _flipping)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", _flipping)

    async def _acq(config):  # noqa: ARG001
        monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "otherbin")
        return []

    monkeypatch.setattr(dapi, "_acquire_and_discover", _acq)
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/servers",
            json={"name": "toctou", "type": "local", "command": ["mybin"]},
        )
        assert resp.status_code == 403
    assert not (registry.servers_dir / "toctou.json").exists()


@pytest.mark.asyncio
async def test_second_filenotfound_maps_binary_not_found(
    gateway, registry, monkeypatch, tmp_path
) -> None:
    from mcp_gway.dashboard import api as dapi

    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "mybin")
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "1")
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    monkeypatch.setattr(
        "mcp_gway.core.policy.resolve_binary", lambda b: "/usr/bin/mybin"
    )
    monkeypatch.setattr("mcp_gway.core.policy.check_cwd", lambda cwd: str(tmp_path))

    async def _boom(config):  # noqa: ARG001
        raise FileNotFoundError(
            "binary not found in PATH: mybin [reason=binary_not_found]"
        )

    monkeypatch.setattr(dapi, "_acquire_and_discover", _boom)
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/servers",
            json={"name": "fnf", "type": "local", "command": ["mybin"]},
        )
        assert resp.status_code == 403
        assert resp.json()["reason_code"] == "binary_not_found"
    assert not (registry.servers_dir / "fnf.json").exists()


@pytest.mark.asyncio
async def test_cwd_canonical_persisted(
    gateway, registry, monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "mybin")
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "1")
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    monkeypatch.setattr(
        "mcp_gway.core.policy.resolve_binary", lambda b: "/usr/bin/mybin"
    )

    async def _mock(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.core.discover_tools", _mock)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", _mock)
    sub = tmp_path / "sub"
    sub.mkdir()
    messy = str(sub / ".." / "sub")
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/servers",
            json={"name": "cwdc", "type": "local", "command": ["mybin"], "cwd": messy},
        )
        assert resp.status_code == 201
    cfg = registry.get_config("cwdc")
    assert cfg.cwd == str(sub.resolve())


@pytest.mark.asyncio
async def test_audit_masked_and_no_json_on_deny(
    gateway, registry, monkeypatch, tmp_path, caplog
) -> None:
    import logging

    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "mybin")
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "1")
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    monkeypatch.setattr(
        "mcp_gway.core.policy.resolve_binary", lambda b: "/usr/bin/mybin"
    )
    monkeypatch.setattr("mcp_gway.core.policy.check_cwd", lambda cwd: str(tmp_path))

    async def _mock(config, force_auth=False):  # noqa: ARG001
        return []

    monkeypatch.setattr("mcp_gway.core.discover_tools", _mock)
    monkeypatch.setattr("mcp_gway.core.client.discover_tools", _mock)
    async with AsyncClient(
        transport=ASGITransport(app=gateway.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/servers",
            json={
                "name": "sec",
                "type": "local",
                "command": ["mybin"],
                "environment": {"MY_SECRET": "supersecret123"},
            },
        )
        assert resp.status_code == 201
        with caplog.at_level(logging.INFO):
            denied = await client.post(
                "/api/servers",
                json={"name": "denyj", "type": "local", "command": ["evilbin"]},
            )
        assert denied.status_code == 403
        listed = await client.get("/api/servers")
        assert listed.status_code == 200
        body = listed.text
        assert "***" in body
        assert "supersecret123" not in body
    assert not (registry.servers_dir / "denyj.json").exists()
    for rec in caplog.records:
        assert "supersecret123" not in rec.getMessage()
