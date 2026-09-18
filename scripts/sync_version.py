from __future__ import annotations

"""Sync owned version markers from pyproject.toml without fighting semantic-release.

Single source of truth stays ``pyproject.toml:project.version`` (read-only).
Semantic-release owns ``pyproject.toml`` + ``src/mcp_gway/__init__.py`` +
``CHANGELOG.md`` — this script never writes those files.

Owned refs (closed allow-list):
- ``.opencode/plugins/mcp-gateway.ts`` — ``const MARKER = "MCP-GWAY vX.Y.Z"``
- ``.opencode/INSTALL.md`` — ``MCP-GWAY vX.Y.Z`` tokens
- ``docs/specs/40_workspace/engineering/PROPOSED_CHANGES-version-sync.md``
  — ``MCP-GWAY vX.Y.Z`` marker, if present (idempotent no-op otherwise)
"""

import argparse
import difflib
import re
import sys
from pathlib import Path

MARKER_RE = re.compile(r"MCP-GWAY v\d+\.\d+\.\d+(?:[-.+][0-9A-Za-z-.+]*)?")
TS_MARKER_RE = re.compile(
    r'const MARKER = "MCP-GWAY v\d+\.\d+\.\d+(?:[-.+][0-9A-Za-z-.+]*)?";'
)
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-.+][0-9A-Za-z-.+]*)?$")

OWNED_TARGETS: tuple[str, ...] = (
    ".opencode/plugins/mcp-gateway.ts",
    ".opencode/INSTALL.md",
    "docs/specs/40_workspace/engineering/PROPOSED_CHANGES-version-sync.md",
    "README.md",
    "AGENTS.md",
)


def normalize_version(raw: str) -> str:
    """Canonicalize a version string to bare ``X.Y.Z`` (strip leading ``v``)."""
    cleaned = raw.strip().removeprefix("v").removeprefix("V")
    if not VERSION_RE.match(cleaned):
        raise ValueError(f"invalid version {raw!r}: expected semver X.Y.Z")
    return cleaned


def read_version_from_pyproject(root: Path) -> str:
    """Read ``project.version`` from ``pyproject.toml`` (read-only input)."""
    import tomllib

    pyproject = root / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    version = data["project"]["version"]
    return normalize_version(str(version))


def sync_text(path: str, text: str, version: str) -> str:
    """Return synced text for an owned target; no-op when marker absent."""
    if path.endswith(".opencode/plugins/mcp-gateway.ts"):
        replacement = f'const MARKER = "MCP-GWAY v{version}";'
        synced, count = TS_MARKER_RE.subn(replacement, text)
        if count == 0:
            return text
        return synced
    synced, _ = MARKER_RE.subn(f"MCP-GWAY v{version}", text)
    return synced


def collect_drifts(root: Path, version: str) -> list[tuple[Path, str, str]]:
    """Collect ``(path, original, synced)`` triples for owned targets with drift."""
    drifts: list[tuple[Path, str, str]] = []
    for rel in OWNED_TARGETS:
        target = root / rel
        if not target.is_file():
            continue
        original = target.read_text(encoding="utf-8")
        synced = sync_text(rel, original, version)
        if synced != original:
            drifts.append((target, original, synced))
    return drifts


def print_drift_diff(path: Path, original: str, synced: str) -> None:
    """Print a unified diff for one drifted file to stdout."""
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        synced.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    sys.stdout.writelines(diff)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI args for the version-sync script."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default=None,
        help="Explicit version (default: read pyproject.toml)",
    )
    parser.add_argument("--root", default=".", help="Repo root (default: cwd)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Dry-run: exit 2 with diff on drift (default)",
    )
    mode.add_argument("--write", action="store_true", help="Apply sync to owned refs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point: check (default) or write owned version markers."""
    args = parse_args(argv)
    root = Path(args.root).resolve()
    try:
        version = (
            normalize_version(args.version)
            if args.version
            else read_version_from_pyproject(root)
        )
    except (ValueError, FileNotFoundError, KeyError) as exc:
        print(f"error: cannot resolve version: {exc}", file=sys.stderr)
        return 2
    drifts = collect_drifts(root, version)
    if args.write:
        for target, _, synced in drifts:
            target.write_text(synced, encoding="utf-8")
            print(f"synced {target} -> {version}")
        if not drifts:
            print(f"version-sync: clean at {version} (no writes needed)")
        return 0
    if drifts:
        print(f"version-sync: DRIFT at {version} ({len(drifts)} file(s))")
        for target, original, synced in drifts:
            print_drift_diff(target, original, synced)
        print(
            "hint: run `python scripts/sync_version.py --write` to fix", file=sys.stderr
        )
        return 2
    print(f"version-sync: clean at {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
