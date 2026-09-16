# Test / Evidence Matrix: SPEC-MGW-001

**Agent:** backend
**Date:** 2026-09-16
**Domains-Touched:** [engineering]

| REQ-ID | Evidence ID | Description | Type | Status | Commit |
|--------|-------------|-------------|------|--------|--------|
| REQ-F-001 | T-001 | Help parity every top-level cmd via one group (`test_help_parity_top_commands`) | Unit | pass (3/3 alias file; 28/28 with `test_cli.py`) | uncommitted (gate to commit) |
| REQ-F-002 | T-002 | Both scripts same `main()` (`test_scripts_expose_both_binaries_same_main`; RED `KeyError: 'mgw'` → GREEN 3 passed) | Unit | pass | uncommitted |
| REQ-F-003 | T-003 | Version single-source `pyproject` ≡ `__version__` (`test_version_single_source`); CLI `--version` flag N/A — no such flag in `cli.py`, no new flag per approved scope | Unit | pass with variance noted | uncommitted |
| REQ-NF-001 | E-001 | `ruff check` + `ruff format --check` clean; targeted 28 passed; full `pytest -v` timed out 300s sandbox → deferred to `qa` | Review | partial (gate pending) | — |
| REQ-NF-002 | E-002 | No new boundary; `MCP_GWAY_ALLOW_*` untouched (`grep` clean); diff 4 insertions, no secrets | Review | pass | — |
| REQ-NF-003 | E-003 | README + AGENTS.md shortcut callouts, canonical intact | Review | pass | — |

Types per matrix template; REQ-ID trace mandatory — all 6 REQs traced.

## Coverage Summary

- Unit coverage: new file 3/3 pass; `test_cli.py` 25/25 alongside → 28/28 targeted
- Integration coverage: install-repro (AC-002 clean-install shim check) pending gate
- Evidence coverage: 6/6 REQ-IDs linked (1 partial: full-suite run; 1 variance: `--version` flag absent by design)
- Acceptance criteria covered: AC-001 pass, AC-002 partial (static proven, shim repro pending), AC-003 partial (targeted green, full pending), AC-004 pass, AC-005 pass

## Variance Log

- V-001: SPEC AC-003 assumed `mcp-gway --version` flag; `cli.py` has no `--version` option (verified `grep version src/mcp_gway/cli.py` → only banner/health uses). No new flag added (out of approved scope). Covered instead by single-source version assert. Recommend SPEC amendment in gate or `--version` as follow-up proposal.
- V-002: `uv.lock` 2.3.0→2.4.0 auto-sync on `uv run` (pre-existing drift, not authored). Left untouched per non-destructive rule; gate adjudicates (keep sync or revert).
