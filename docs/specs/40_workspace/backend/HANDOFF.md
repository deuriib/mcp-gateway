# Handoff: backend → ship-release

**Spec Reference:** SPEC-MGW-001
**Agent:** backend (verified by vasquez gate)
**Date:** 2026-09-16
**Status:** complete
**Domains-Touched:** [engineering]

## Deliverables

| Artifact | Location / Evidence | Status |
|----------|---------------------|--------|
| Packaging alias | `pyproject.toml:21` (`mgw = "mcp_gway.cli:main"`) | done |
| Parity tests | `tests/test_cli_alias.py` (3/3 pass; RD-001/RD-002 applied) | done |
| Docs | `README.md:23`, `AGENTS.md:96`, `CHANGELOG.md` Unreleased `feat(cli)` | done |
| Spec + contracts | `docs/specs/10_design/SPEC-mgw-alias.md`, `ARCHITECTURE.md` v1, `API_CONTRACTS.md` v1, `docs/specs/15_requirements/REQ-mgw-alias.md` | done |
| Proposal + plan + matrix | `docs/specs/40_workspace/backend/PROPOSED_CHANGES.md`, `IMPLEMENTATION_PLAN.md`, `TEST_MATRIX.md` | done |
| ADR + arch review | `docs/architecture/adr-013-cli-alias-mgw.md`, `docs/specs/40_workspace/architecture/REVIEW-mgw-alias.md` | done |
| Gate | `docs/specs/40_workspace/quality-gate/SPEC-MGW-001/` (4 reviews + `GATE_REPORT.md` OPEN) | done |
| Live shims | `.venv/Scripts/mgw.exe` + `mcp-gway.exe`; entry points `['mcp-gway', 'mgw']` | done |

## Definition of Done Checklist

- [x] Acceptance criteria satisfied — AC-001/002/003/004/005 pass (AC-003 via full 532+2 green)
- [x] Tests/evidence linked per REQ-ID — 6/6 in `TEST_MATRIX.md` + `qa.md:24-38`
- [x] Load evidence present — `frame-ship:verify-handoff` + `agents/c-level/vasquez.md`; mode `single`; packet `SPEC:docs/specs/10_design/SPEC-mgw-alias.md#REQ-F-001..003+NF-001..003 / HARD:single+approved-proposal-only+guardrails-1-14 / GATE:OPEN / DOMAINS:[engineering]`
- [x] Domain checks passing — ruff check/format clean; full suite 532 passed + 2 skipped, 0 failed; TODO/FIXME scan clean; `src/` untouched
- [x] Security checks passing — scope says not security-touched (no new boundary; barrera path-cite); diff secret scan clean; `MCP_GWAY_ALLOW_*` untouched
- [x] Documentation updated — README + AGENTS.md + CHANGELOG Unreleased + ADR-013

## Notes (explicit, not silent)

- Coverage threshold: not re-measured in-sandbox; change touches zero `src/` lines so the percentage cannot regress from this diff — CI enforces `fail_under = 80` at ship.
- Type checks: N/A — repo quality contract is `pytest` + `ruff check` + `ruff format --check` per AGENTS.md; no type tooling configured.
- `uv.lock` 2.3.0→2.4.0 sync kept (gate-adjudicated; aligns lock with `pyproject.toml:3`).
- Suite wall time ~350s — CI needs ≥600s budget (owner vasquez).

## Blockers / Open Questions

None. No Cross-domain requests. No waivers invoked anywhere in the chain.

## Next Agent

`ship-release` (montilla owns releases): version/changelog coordination per hybrid workflow (ADR-007) + rollback = revert one `pyproject.toml` line + test file + 4 doc lines (<15 min). Lessons live in this HANDOFF on PASS.
