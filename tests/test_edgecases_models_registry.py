"""Hermetic edge tests: models SSRF/name/oauth/cmd/cwd/env + registry atomic/traversal."""

from __future__ import annotations

import os

import pytest

from mcp_gway.models import MCPServerConfig, OAuthConfig, ToolInfo
from mcp_gway.registry import Registry


@pytest.mark.parametrize(
    "bad",
    [
        "",
        ".",
        "..",
        "a/b",
        "a\\b",
        "has space",
        "has-hyphen",
        "1abc",
        "a<b",
        "con",
        "COM1",
        "x" * 70,
        "café",
    ],
    ids=[
        "empty",
        "dot",
        "dotdot",
        "slash",
        "backslash",
        "space",
        "hyphen",
        "leading-digit",
        "lt",
        "reserved-con",
        "reserved-com1",
        "too-long",
        "non-ascii",
    ],
)
def test_name_validation_edges(bad):
    with pytest.raises(ValueError, match="name|Name|invalid"):
        MCPServerConfig(name=bad, type="remote", url="https://api.example.com/mcp")


def test_name_validation_ok():
    ok = MCPServerConfig(
        name="good_name_1", type="remote", url="https://api.example.com/mcp"
    )
    assert ok.name == "good_name_1"


@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.1/x",
        "http://192.168.1.1/x",
        "http://0.0.0.0/x",
        "ftp://api.example.com/x",
        "https://[::1]/x",
        "http://169.254.169.254/x",
        "https://api.example.com/m\rc",
        "https://",
    ],
    ids=[
        "private-10",
        "private-192",
        "unspecified",
        "ftp-scheme",
        "loopback-v6",
        "link-local",
        "cr-in-url",
        "no-host",
    ],
)
def test_ssrf_guard_blocks(url):
    with pytest.raises(ValueError, match="url|URL|host|private|loopback|scheme"):
        MCPServerConfig(name="s1", type="remote", url=url)


def test_ssrf_test_bypass_allows_loopback_in_pytest():
    # P0-H1: PYTEST_CURRENT_TEST bypass removed — loopback always blocked
    with pytest.raises(ValueError, match="private|loopback|not allowed|blocked"):
        MCPServerConfig(name="s1", type="remote", url="http://127.0.0.1/x")
    with pytest.raises(ValueError, match="private|loopback|not allowed|blocked"):
        MCPServerConfig(name="s1", type="remote", url="http://localhost/x")


def test_ssrf_guard_allows_public():
    ok = MCPServerConfig(name="s1", type="remote", url="https://api.example.com/mcp")
    assert ok.url.endswith("/mcp")


def test_oauth_validators():
    o = OAuthConfig(clientId="notauuid")
    assert o.clientId is not None and o.clientId != "notauuid"
    o2 = OAuthConfig(clientId=None)
    assert o2.clientId is None
    c = MCPServerConfig(
        name="o1", type="remote", url="https://api.example.com/mcp", oauth=True
    )
    assert c.oauth is not None
    c2 = MCPServerConfig(
        name="o2",
        type="remote",
        url="https://api.example.com/mcp",
        oauth={"scope": "x"},
    )
    assert c2.oauth is not None
    c3 = MCPServerConfig(
        name="o3",
        type="remote",
        url="https://api.example.com/mcp",
        oauth={"clientId": "bad"},
    )
    assert c3.oauth is not None
    c4 = MCPServerConfig(
        name="o4", type="remote", url="https://api.example.com/mcp", oauth=False
    )
    assert c4.oauth is False


def test_command_cwd_env_validators(monkeypatch):
    monkeypatch.setenv("MCP_GWAY_ALLOW_LOCAL_COMMANDS", "npx")
    with pytest.raises(ValueError, match="path|basename|command"):
        MCPServerConfig(name="c1", type="local", command=["/bin/npx"])
    with pytest.raises(ValueError, match="invalid|token|command"):
        MCPServerConfig(name="c1", type="local", command=["npx", "a;b"])
    with pytest.raises(ValueError, match="cwd|absolute|directory"):
        MCPServerConfig(name="c1", type="local", cwd="relative")
    with pytest.raises(ValueError, match="environment|denied|PATH"):
        MCPServerConfig(
            name="c1", type="local", command=["npx"], environment={"PATH": "x"}
        )
    with pytest.raises(ValueError, match="command|local"):
        MCPServerConfig(name="c1", type="local")
    with pytest.raises(ValueError, match="url|remote"):
        MCPServerConfig(name="c1", type="remote")


def test_registry_crud_and_traversal(tmp_path):
    reg = Registry(servers_dir=tmp_path / "r")
    cfg = MCPServerConfig(name="a1", type="remote", url="https://api.example.com/mcp")
    reg.add(
        cfg,
        [
            ToolInfo(
                name="my-tool",
                description="d",
                input_schema={
                    "properties": {"x-h": {"type": "string"}},
                    "required": ["x-h"],
                },
            )
        ],
    )
    assert "a1" in reg.list()
    assert "my_tool" in reg.read_pyi("a1")
    assert reg.get_pyi_tools("a1")[0].name == "my_tool"
    assert "my_tool" in reg.get_tool_docs("a1", "my-tool")
    assert "not found" in reg.get_tool_docs("a1", "nosuchtool")
    reg.update("a1", [ToolInfo(name="t2")])
    assert "t2" in reg.read_pyi("a1")
    reg.patch_enabled("a1", False)
    assert reg.get_config("a1").enabled is False
    assert reg.list_enabled() == []
    reg.patch_enabled("a1", True)
    for bad in ["../evil", "a/b", "", "."]:
        with pytest.raises(ValueError, match="Name|path|Invalid"):
            reg._safe_path(bad, ".json")
    with pytest.raises(FileNotFoundError, match="not found"):
        reg.read_pyi("nosuch")
    with pytest.raises(FileNotFoundError, match="not found"):
        reg.get_config("nosuch")
    with pytest.raises(FileNotFoundError, match="not found"):
        reg.remove("nosuch")
    reg.remove("a1")
    assert reg.list() == []


def test_registry_symlink_refusal(tmp_path):
    if os.name == "nt":
        pytest.skip("posix symlink semantics")
    reg = Registry(servers_dir=tmp_path / "r2")
    cfg = MCPServerConfig(name="s1", type="remote", url="https://api.example.com/mcp")
    reg.add(cfg, [])
    target = tmp_path / "evil.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "r2" / "s1.json"
    link.unlink()
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("no symlink perm")
    with pytest.raises(ValueError, match="symlink"):
        reg._atomic_write_text(link, "x")


def test_registry_pyi_signature_edges(tmp_path):
    reg = Registry(servers_dir=tmp_path / "r3")
    cfg = MCPServerConfig(name="g1", type="remote", url="https://api.example.com/mcp")
    tools = [
        ToolInfo(
            name="123bad-name!",
            description="line1\nline2",
            input_schema={
                "properties": {"p1": {"type": "weird"}, "9x": {"type": "integer"}},
                "required": ["p1"],
            },
        )
    ]
    reg.add(cfg, tools)
    content = reg.read_pyi("g1")
    assert "_123bad_name_" in content
    assert reg._json_type_to_python("unknown") == "Any"
    assert reg._json_type_to_python("string") == "str"


def test_registry_get_config_pyi_only_and_list_enabled_fallback(tmp_path):
    reg = Registry(servers_dir=tmp_path / "r4")
    (tmp_path / "r4").mkdir(parents=True, exist_ok=True)
    (tmp_path / "r4" / "lonely.pyi").write_text(
        "def foo() -> dict:\n    ...\n", encoding="utf-8"
    )
    with pytest.raises(FileNotFoundError, match="not found"):
        reg.get_config("lonely")
    assert "lonely" in reg.list_enabled()
