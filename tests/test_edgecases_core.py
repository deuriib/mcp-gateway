"""Hermetic edge tests: core parsing/install/client/transport + shim."""

from __future__ import annotations

import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_gway.core import client as C
from mcp_gway.core import install as I
from mcp_gway.core import parsing as P
from mcp_gway.core import transport as T
from mcp_gway.models import MCPServerConfig, ToolInfo
from mcp_gway.registry import Registry


def test_parse_headers_envs_edges():
    assert P.parse_headers([]) == {}
    assert P.parse_headers(["  =x", "K = V ", "A=B=C"]) == {"K": "V", "A": "B=C"}
    assert P.parse_headers(["NOEQUALS"]) == {"NOEQUALS": ""}
    assert P.parse_envs(["", "  ", "K="]) == {"K": ""}
    assert P.parse_envs(["K = V"]) == {"K": "V"}


async def test_transport_shim_warns_and_delegates(monkeypatch):
    import mcp_gway.transport as SH

    cfg = MCPServerConfig(
        name="shimx", type="remote", url="https://api.example.com/mcp"
    )
    monkeypatch.setattr(SH, "_core_try_http", AsyncMock(return_value=True))
    monkeypatch.setattr(SH, "_core_try_sse", AsyncMock(return_value=True))
    monkeypatch.setattr(SH, "_core_try_streamable_http", AsyncMock(return_value=True))
    monkeypatch.setattr(SH, "_core_detect_transport", AsyncMock(return_value="sse"))
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert await SH.detect_transport(cfg) == "sse"
        assert await SH._try_http("https://api.example.com/mcp") is True
        assert await SH._try_sse("https://api.example.com/mcp") is True
        assert await SH._try_streamable_http("https://api.example.com/mcp") is True
        dep = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(dep) == 4


async def test_core_transport_detect_order(monkeypatch):
    cfg = MCPServerConfig(name="trx", type="remote", url="https://api.example.com/mcp")
    monkeypatch.setattr(T, "_try_streamable_http", AsyncMock(return_value=True))
    assert await T.detect_transport(cfg) == "streamable-http"
    monkeypatch.setattr(T, "_try_streamable_http", AsyncMock(return_value=False))
    monkeypatch.setattr(T, "_try_sse", AsyncMock(return_value=True))
    assert await T.detect_transport(cfg) == "sse"
    monkeypatch.setattr(T, "_try_sse", AsyncMock(return_value=False))
    monkeypatch.setattr(T, "_try_http", AsyncMock(return_value=True))
    assert await T.detect_transport(cfg) == "http"
    monkeypatch.setattr(T, "_try_http", AsyncMock(return_value=False))
    with pytest.raises(ConnectionError):
        await T.detect_transport(cfg)
    bad = MCPServerConfig.__new__(MCPServerConfig)
    object.__setattr__(bad, "url", None)
    object.__setattr__(bad, "timeout", 5000)
    object.__setattr__(bad, "headers", None)
    with pytest.raises(ValueError, match="url"):
        await T.detect_transport(bad)


async def test_core_transport_try_helpers_swallow(monkeypatch):
    import mcp.client.sse as _sse
    import mcp.client.streamable_http as _sh

    monkeypatch.setattr(
        _sh, "streamable_http_client", MagicMock(side_effect=RuntimeError("down"))
    )
    monkeypatch.setattr(_sse, "sse_client", MagicMock(side_effect=RuntimeError("down")))
    import httpx2 as _h2

    class _BoomClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            raise RuntimeError("down")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(_h2, "AsyncClient", _BoomClient)
    assert await T._try_streamable_http("https://api.example.com/mcp") is False
    assert await T._try_sse("https://api.example.com/mcp") is False
    assert await T._try_http("https://api.example.com/mcp") is False


def test_install_is_duplicate(tmp_path):
    reg = Registry(servers_dir=tmp_path / "srv")
    cfg = MCPServerConfig(name="dup1", type="remote", url="https://api.example.com/mcp")
    assert I.is_duplicate(reg, cfg) is False
    reg.add(cfg, [])
    assert I.is_duplicate(reg, cfg) is True
    bad = MCPServerConfig.__new__(MCPServerConfig)
    object.__setattr__(bad, "name", "../evil")
    with pytest.raises(ValueError, match="invalid request"):
        I.is_duplicate(reg, bad)


async def test_install_maybe_detect_skips(monkeypatch):
    local = MCPServerConfig(name="loc1", type="local", command=["npx", "x"])
    await I._maybe_detect_transport(local)
    remote = MCPServerConfig(
        name="rem1",
        type="remote",
        url="https://api.example.com/mcp",
        resolved_transport="sse",
    )
    await I._maybe_detect_transport(remote)
    remote2 = MCPServerConfig(
        name="rem2", type="remote", url="https://api.example.com/mcp"
    )
    with patch(
        "mcp_gway.core.detect_transport", AsyncMock(return_value="http")
    ) as detect:
        await I._maybe_detect_transport(remote2)
        assert remote2.resolved_transport == "http"
        assert detect.await_count == 1
    remote3 = MCPServerConfig(
        name="rem3", type="remote", url="https://api.example.com/mcp"
    )
    with patch("mcp_gway.core.detect_transport", side_effect=RuntimeError("down")):
        await I._maybe_detect_transport(remote3)


async def test_install_acquire_saturated_and_error_paths(monkeypatch):
    cfg = MCPServerConfig(name="d1", type="remote", url="https://api.example.com/mcp")
    monkeypatch.setattr(I, "_maybe_detect_transport", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "mcp_gway.core.discover_tools",
        AsyncMock(return_value=[ToolInfo(name="t", description="d")]),
    )
    out = await I._acquire_and_discover(cfg)
    assert len(out) == 1
    monkeypatch.setattr("mcp_gway.core.discover_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "mcp_gway.oauth.get_authenticated_client", AsyncMock(return_value=None)
    )
    out2 = await I._acquire_and_discover(cfg)
    assert out2 == []
    with patch.object(I._discovery_sem, "acquire", side_effect=TimeoutError("t")):
        with pytest.raises(ConnectionError, match="saturated"):
            await I._acquire_and_discover(cfg)

    async def boom(c, force_auth=False):
        raise RuntimeError("x")

    monkeypatch.setattr("mcp_gway.core.discover_tools", boom)
    assert await I._acquire_and_discover(cfg) == []


async def test_install_discover_and_persist_local_gate(tmp_path, monkeypatch):
    reg = Registry(servers_dir=tmp_path / "srv2")
    monkeypatch.setattr(I, "_acquire_and_discover", AsyncMock(return_value=[]))
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "npx")
    with patch("mcp_gway.core.policy.resolve_binary", return_value="/usr/bin/npx"):
        cfg = MCPServerConfig(name="ll1", type="local", command=["npx", "y"])
        out = await I.discover_and_persist(reg, cfg)
        assert out == []
    # Setting env to a value that does NOT include npx causes denial
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "otherbin")
    cfg2 = MCPServerConfig(name="ll2", type="local", command=["npx", "y"])
    with pytest.raises(PermissionError, match="reason=not_allowlisted"):
        await I.discover_and_persist(reg, cfg2)
    # Use an allowed binary for the subsequent error-path tests
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "npx")
    cfg2_ok = MCPServerConfig(name="ll2", type="local", command=["npx", "y"])
    monkeypatch.setattr(
        I,
        "_acquire_and_discover",
        AsyncMock(side_effect=ConnectionError("discovery saturated")),
    )
    with pytest.raises(ConnectionError, match="saturated"):
        await I.discover_and_persist(reg, cfg2_ok)
    monkeypatch.setattr(
        I, "_acquire_and_discover", AsyncMock(side_effect=FileNotFoundError("nf"))
    )
    with pytest.raises(FileNotFoundError, match="nf"):
        await I.discover_and_persist(reg, cfg2_ok)
    monkeypatch.setattr(
        I, "_acquire_and_discover", AsyncMock(side_effect=RuntimeError("other"))
    )
    cfg3 = MCPServerConfig(name="rr1", type="remote", url="https://api.example.com/mcp")
    out3 = await I.discover_and_persist(reg, cfg3)
    assert out3 == []


def test_client_default_on_noise(capsys):
    C._default_on_noise(3)
    assert "3" in capsys.readouterr().err


async def test_client_local_transport_denied(monkeypatch):
    # Setting env to a value that does NOT include the binary causes denial
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "otherbin")
    monkeypatch.delenv("MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL", raising=False)
    cfg = MCPServerConfig(name="deny1", type="local", command=["npx", "x"])

    async def go():
        async with C.create_client_transport(cfg):
            pass

    with pytest.raises(PermissionError, match="reason="):
        await go()


async def test_client_local_transport_binary_not_found(monkeypatch):
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "npx")
    monkeypatch.setattr("mcp_gway.core.policy.resolve_binary", lambda b: None)
    cfg = MCPServerConfig(name="nbin", type="local", command=["npx", "x"])

    async def go():
        async with C.create_client_transport(cfg):
            pass

    with pytest.raises(FileNotFoundError, match="reason=binary_not_found"):
        await go()


async def test_client_remote_branches(monkeypatch):
    async def go(cfg, force_auth=False):
        with patch("mcp.client.sse.sse_client") as sc:
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
            cm.__aexit__ = AsyncMock(return_value=False)
            sc.return_value = cm
            async with C.create_client_transport(cfg, force_auth=force_auth):
                pass

    cfg = MCPServerConfig(
        name="r1",
        type="remote",
        url="https://api.example.com/mcp",
        resolved_transport="http",
    )
    await go(cfg)

    async def go_auth():
        with (
            patch("mcp.client.sse.sse_client") as sc,
            patch(
                "mcp_gway.oauth.get_authenticated_client", AsyncMock(return_value=None)
            ),
        ):
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
            cm.__aexit__ = AsyncMock(return_value=False)
            sc.return_value = cm
            # Wave-4 fail-closed: force_auth with no tokens must raise, never
            # pass None to the SDK (silent anonymous downgrade).
            with pytest.raises((PermissionError, ValueError), match="auth|token|login"):
                async with C.create_client_transport(cfg, force_auth=True):
                    pass

    await go_auth()
    bad = MCPServerConfig.__new__(MCPServerConfig)
    object.__setattr__(bad, "name", "badu")
    object.__setattr__(bad, "type", "remote")
    object.__setattr__(bad, "url", None)
    object.__setattr__(bad, "resolved_transport", None)
    object.__setattr__(bad, "headers", None)

    async def go_bad():
        async with C.create_client_transport(bad):
            pass

    with pytest.raises(ValueError, match="url"):
        await go_bad()


async def test_client_discover_tools_timeout_and_error(monkeypatch):
    cfg = MCPServerConfig(
        name="d2", type="remote", url="https://api.example.com/mcp", timeout=0
    )
    monkeypatch.setattr(C, "create_client_transport", None)
    assert await C.discover_tools(cfg) == []


async def test_client_refresh_server_oauth_path(monkeypatch):
    cfg = MCPServerConfig(
        name="rf1", type="remote", url="https://api.example.com/mcp", oauth=True
    )
    monkeypatch.setattr(
        C, "discover_tools", AsyncMock(side_effect=[[], [ToolInfo(name="t")]])
    )
    fake_client = MagicMock()
    fake_client.aclose = AsyncMock()
    monkeypatch.setattr(
        "mcp_gway.oauth.run_oauth_flow", AsyncMock(return_value=fake_client)
    )
    out = await C.refresh_server(cfg, "rf1", False, 8989)
    assert len(out) == 1
    monkeypatch.setattr("mcp_gway.oauth.run_oauth_flow", AsyncMock(return_value=None))
    monkeypatch.setattr(C, "discover_tools", AsyncMock(return_value=[]))
    out2 = await C.refresh_server(cfg, "rf1", True, 8989)
    assert out2 == []
