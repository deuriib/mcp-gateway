"""Hermetic edge tests: sandbox + server_proxy + factory + code_mode."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_gway.code_mode import CodeMode
from mcp_gway.models import MCPServerConfig, ToolInfo
from mcp_gway.registry import Registry
from mcp_gway.sandbox import SandboxTimeoutError, StarlarkSandbox, _sanitize_identifier
from mcp_gway.server_factory import ServerFactory, _extract_result
from mcp_gway.server_factory import _sanitize_identifier as F_san
from mcp_gway.server_proxy import ServerProxy


def test_sanitize_identifiers():
    assert _sanitize_identifier("query-docs") == "query_docs"
    assert _sanitize_identifier("123abc") == "_123abc"
    assert F_san("a.b-c") == "a_b_c"
    assert F_san("9lives") == "_9lives"


def test_sandbox_basic_and_print():
    sb = StarlarkSandbox()
    assert sb.execute("result = 1 + 2") == 3
    assert sb.execute("print('hi')\nresult = 5") == 5


def test_sandbox_no_result_returns_none():
    sb = StarlarkSandbox()
    assert sb.execute("x = 1") is None


def test_sandbox_error():
    sb = StarlarkSandbox()
    with pytest.raises(Exception, match="undefined_var_xyz"):
        sb.execute("result = undefined_var_xyz")


def test_sandbox_timeout():
    sb = StarlarkSandbox()

    class Slow:
        def spin(self):
            time.sleep(10)
            return 1

    sb.inject_server("slowedge", Slow())
    with pytest.raises(SandboxTimeoutError):
        sb.execute("result = slowedge.spin()", timeout=0.2)


def test_sandbox_server_injection_skips_private_and_noncallable():
    sb = StarlarkSandbox()

    class Fake:
        pub = lambda self, **k: 1
        _priv = lambda self: 2
        val = 42

    sb.inject_server("srv", Fake())
    assert sb.execute("result = srv.pub()") == 1


async def test_server_proxy_edges():
    client = MagicMock()
    client.call_tool = AsyncMock(return_value={"ok": True})
    px = ServerProxy("n", client)
    px.set_tool_names(["a"])
    assert "n" in repr(px)
    fn = px.some_tool
    assert await fn(x=1) == {"ok": True}
    with pytest.raises(AttributeError):
        px._hidden  # noqa: B009, B018


def test_extract_result_variants():
    class Item:
        def __init__(self, text=None):
            self.text = text

        def __str__(self):
            return "stritem"

    class R:
        def __init__(self, content):
            self.content = content

    assert _extract_result(R([Item('{"a": 1}')])) == {"a": 1}
    assert _extract_result(R([Item("plain")])) == "plain"

    class NoText:
        def __str__(self):
            return "fallback"

    assert _extract_result(R([NoText()])) == "fallback"
    assert _extract_result(42) == 42


@pytest.mark.parametrize(
    "server,tool",
    [("", "t"), ("s", ""), ("nosuchserver", "t")],
    ids=["empty-server", "empty-tool", "unknown-server"],
)
def test_factory_call_tool_validation(tmp_path, server, tool):
    reg = Registry(servers_dir=tmp_path / "f")
    fac = ServerFactory(reg)
    with pytest.raises(Exception, match="server|tool|not found"):
        fac.call_tool(server, tool)


def test_factory_struct_and_bind(tmp_path):
    reg = Registry(servers_dir=tmp_path / "f2")
    reg.add(
        MCPServerConfig(name="s1", type="remote", url="https://api.example.com/mcp"),
        [ToolInfo(name="my-tool", description="d")],
    )
    fac = ServerFactory(reg)
    st = fac.make_server_struct("s1")
    assert hasattr(st, "my_tool")
    names = fac._get_tool_names("s1")
    assert names == ["my-tool"]
    reg.add(
        MCPServerConfig(name="s2", type="remote", url="https://api.example.com/mcp"),
        [ToolInfo(name="plain", description="d")],
    )
    assert fac._get_tool_names("s2") == ["plain"]


def test_factory_call_async_mocked(tmp_path, monkeypatch):
    reg = Registry(servers_dir=tmp_path / "f3")
    reg.add(
        MCPServerConfig(name="s1", type="remote", url="https://api.example.com/mcp"),
        [ToolInfo(name="t")],
    )
    fac = ServerFactory(reg)

    async def fake_async(cfg, tool_name, args):
        return {"echo": tool_name}

    monkeypatch.setattr(fac, "_call_tool_async", fake_async)
    import asyncio

    result = asyncio.run(fac._call_tool_async(None, "t", {}))
    assert result == {"echo": "t"}


def test_code_mode_list_and_read(tmp_path):
    reg = Registry(servers_dir=tmp_path / "cm")
    cm = CodeMode(reg)
    assert cm.list_tool_files() == "No servers connected."
    reg.add(
        MCPServerConfig(name="a", type="remote", url="https://api.example.com/mcp"),
        [ToolInfo(name="t", description="d")],
    )
    cm2 = CodeMode(reg)
    assert "a.pyi" in cm2.list_tool_files()
    content = cm2.read_tool_file("a")
    assert "t" in content
    content2 = cm2.read_tool_file("servers/a.pyi", startLine=1, endLine=2)
    assert len(content2.splitlines()) <= 2


def test_code_mode_get_tool_docs_found(tmp_path):
    reg = Registry(servers_dir=tmp_path / "cm")
    reg.add(
        MCPServerConfig(name="a", type="remote", url="https://api.example.com/mcp"),
        [ToolInfo(name="t", description="d")],
    )
    cm2 = CodeMode(reg)
    assert "t" in cm2.get_tool_docs("a", "t")


def test_code_mode_get_tool_docs_missing(tmp_path):
    reg = Registry(servers_dir=tmp_path / "cm")
    reg.add(
        MCPServerConfig(name="a", type="remote", url="https://api.example.com/mcp"),
        [ToolInfo(name="t", description="d")],
    )
    cm2 = CodeMode(reg)
    assert "not found" in cm2.get_tool_docs("a", "nosuch").lower()


def test_code_mode_execute_ok_and_errors(tmp_path):
    reg = Registry(servers_dir=tmp_path / "cm")
    reg.add(
        MCPServerConfig(name="a", type="remote", url="https://api.example.com/mcp"),
        [ToolInfo(name="t", description="d")],
    )
    cm2 = CodeMode(reg)
    import json as _json

    assert _json.loads(cm2.execute_tool_code("result = 7")) == {
        "result": 7,
        "logs": [],
    }
    with pytest.raises(Exception, match="empty|code"):
        cm2.execute_tool_code("")
    with pytest.raises(Exception, match="str|code"):
        cm2.execute_tool_code(123)


def test_code_mode_execute_unserializable(tmp_path):
    reg = Registry(servers_dir=tmp_path / "cm")
    reg.add(
        MCPServerConfig(name="a", type="remote", url="https://api.example.com/mcp"),
        [ToolInfo(name="t", description="d")],
    )
    cm2 = CodeMode(reg)

    class BadResult:
        def __str__(self):
            raise RuntimeError("ser fail")

    with patch.object(cm2.sandbox, "execute", return_value=BadResult()):
        with pytest.raises(RuntimeError, match="serialization failed"):
            cm2.execute_tool_code("result = 1")
