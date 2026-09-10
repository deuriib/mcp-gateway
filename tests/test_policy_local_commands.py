"""FEAT-006 policy — local command gating (CLI + unit policy)."""

from __future__ import annotations

import pytest

from mcp_gway.core.policy import check_environment, check_local_command


def test_local_command_requires_binary():
    decision = check_local_command(
        ["definitely-not-a-real-binary-xyz"], require_binary=True
    )
    assert decision.allowed is False
    assert decision.reason_code in ("binary_not_found", "not_allowlisted")


def test_ac012_cli_add_local(monkeypatch, tmp_path) -> None:
    from click.testing import CliRunner

    from mcp_gway.cli import main

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


@pytest.mark.parametrize(
    "var",
    [
        "PATH",
        "NODE_PATH",
        "NODE_EXTRA_CA_CERTS",
        "NODE_TLS_REJECT_UNAUTHORIZED",
        "NPM_CONFIG_FOO",
        "BUN_FOO",
        "UV_FOO",
        "DYLD_FOO",
    ],
)
def test_env_denylist_exact_and_prefixes_denied(var) -> None:
    with pytest.raises(ValueError, match=r"denied_env"):
        check_environment({var: "x"})


@pytest.mark.parametrize("var", ["path", "node_path", "npm_config_foo"])
def test_env_denylist_case_insensitive(var) -> None:
    with pytest.raises(ValueError, match=r"denied_env"):
        check_environment({var: "x"})


def test_env_node_env_allowed() -> None:
    assert check_environment({"NODE_ENV": "production"}) == {"NODE_ENV": "production"}
