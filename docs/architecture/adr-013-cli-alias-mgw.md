# ADR-013: CLI Alias `mgw` as Second Console Script (packaging-only)

**Date:** 2026-09-16
**Deciders:** vasquez (CTO), architect
**Status:** accepted (packaging-only; implements SPEC-MGW-001 within ARCHITECTURE.md v1 invariants)

## Context

SPEC-MGW-001 asks for `mgw` alongside canonical `mcp-gway` with 1:1 parity. Packaging exposes one script (`pyproject.toml:19-20` → `mcp-gway = "mcp_gway.cli:main"`); runtime is one click group (`src/mcp_gway/cli.py:74-76` `def main()`). CLI is the only surface (headless CLI-only, no dashboard/catalog). Proposal `docs/specs/40_workspace/backend/PROPOSED_CHANGES.md` offers two scripts → same `main()`, new parity test, doc callouts, `cli.py` frozen.

## Decision — Option A (adopted): second `project.scripts` entry, same `main()`

- Append `mgw = "mcp_gway.cli:main"` under `[project.scripts]`; no new module, no signature change, no new flags/env.
- Both binaries share dispatch, registry (`servers/*.json` + `*.pyi`), transports (stdio/http/sse), local-first (`127.0.0.1` default; `0.0.0.0` without `MCP_GWAY_ALLOW_REMOTE=1` → exit 2).
- `mcp-gway` stays canonical; `mgw` is shortcut. No ADR for runtime — `docs/specs/10_design/ARCHITECTURE.md` v1 + `API_CONTRACTS.md` v1 already cover it (INV-001..006 hold).
- Tests: `tests/test_cli_alias.py` (help normalized diff + `--version` + `importlib.metadata` entry-point check). Docs: README + AGENTS.md shortcut callouts.

## Alternatives Considered

- Option B — Shell wrapper / symlink `mgw → mcp-gway`: REJECTED. Fragile on Windows + `uv tool install`; logic outside packaging; untestable via entry-point metadata.
- Option C — Rename to `mgw` outright: REJECTED. Breaks compat; violates BRIEF-MGW-001 Out of Scope.
- Option D — Separate `mgw_main()`: REJECTED. Forks dispatch; violates INV-001/INV-002; doubles maintenance.

## Consequences

### Positive

- Daily-driver speed with zero behavior fork; one-line packaging diff, trivial rollback.
- Parity machine-checked (normalized help diff), not eyeballed.

### Negative

- Installer-matrix burden (POSIX + Windows `.exe` + `uv tool`) must be reproed once (AC-002); negligible ongoing cost.

## Supersedes / Superseded By

- Supplements ADR-010 (unified `serve`; alias `mcp` hidden) — same alias philosophy at binary level.
- No invariant break; no prior ADR superseded.
