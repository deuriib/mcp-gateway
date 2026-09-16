"""Parity tests for `mgw` alias (SPEC-MGW-001).

Both console scripts (`mcp-gway` canonical + `mgw` shortcut) bind to the
same `mcp_gway.cli:main` click group. No runtime fork: parity is proven by
single-source entry points + identical help dispatch.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from click.testing import CliRunner

from mcp_gway import __version__
from mcp_gway.cli import main


def _project_scripts() -> dict[str, str]:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    return dict(data["project"]["scripts"])


def test_scripts_expose_both_binaries_same_main():
    """REQ-F-002: install exposes `mcp-gway` + `mgw` on the same object."""
    scripts = _project_scripts()
    assert scripts["mcp-gway"] == "mcp_gway.cli:main"
    assert scripts["mgw"] == "mcp_gway.cli:main"


def test_version_single_source():
    """REQ-F-003 (version subset): single source, no flag added in this SPEC."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject.open("rb") as fh:
        expected = tomllib.load(fh)["project"]["version"]
    assert __version__ == expected


def test_help_parity_top_commands():
    """REQ-F-001: every top-level command helps cleanly via the one group."""
    runner = CliRunner()
    root_help = runner.invoke(main, ["--help"])
    assert root_help.exit_code == 0
    assert "Usage" in root_help.output
    for cmd in sorted(main.commands):
        result = runner.invoke(main, [cmd, "--help"])
        assert result.exit_code == 0, cmd
        assert "Usage" in result.output, cmd
        # WHY repeat, not cross-binary diff: both scripts bind the same
        # `main` object, so parity is determinism of one group; the
        # entry-point assert above guards against a future fork.
        repeat = runner.invoke(main, [cmd, "--help"])
        assert repeat.output == result.output, cmd
