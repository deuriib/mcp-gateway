# RELEASE_NOTES.md — Minimal CLI Alias mgw (SPEC-MGW-001)

**Version:** Unreleased (rides next hybrid release per ADR-007; no tag by hand)
**Date:** 2026-09-16
**Release Manager:** montilla (CEO)
**Specs Included:** SPEC-MGW-001
**Domains-Touched:** [engineering]
**Ship Type:** rollout

## Highlights

Typing `mcp-gway` dozens of times a day is friction. `mgw` is now a full 1:1 shortcut — every command, flag, and help screen works identically under both names, with `mcp-gway` staying canonical. Zero behavior change, zero new dependencies, zero new services.

## Changes

### Features

- `mgw` console script bound to the same `mcp_gway.cli:main` (SPEC-MGW-001, engineering) — `pyproject.toml:21`
- Parity tests: entry-point + help + version single-source (`tests/test_cli_alias.py`)
- Docs: shortcut callouts in README, AGENTS.md, CHANGELOG Unreleased

### Fixes

- None (no bug fixed; purely additive)

### Breaking Changes

- None. Compat is permanent in this SPEC: scripts, runbooks, and OpenCode configs using `mcp-gway` keep working untouched.

## Known Issues

- Full suite takes ~350s wall time — CI jobs need a ≥600s budget (owner vasquez). No failures: 532 passed + 2 skipped, 0 failed.
- No `--version` CLI flag exists (pre-existing; none added by scope freeze) — version parity is proven via single source `pyproject.toml:3` ≡ `__version__`.

## Rollback / Undo

Revert one `pyproject.toml` line (`mgw = ...`), delete `tests/test_cli_alias.py`, revert 4 doc lines (README + AGENTS.md + CHANGELOG). Owner: vasquez via backend. ETA <15 min. No migration, no deploy beyond reinstall. Worst case if unreverted: `mgw: command not found` while `mcp-gway` keeps working — no outage possible.
