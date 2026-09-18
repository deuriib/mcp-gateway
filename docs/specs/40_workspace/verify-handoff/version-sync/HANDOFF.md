# HANDOFF — version-sync sub-lane (vasquez, CTO)

**Skill:** `frame-ship:verify-handoff` (single-mode, gate OPEN).
**SPEC:** `docs/specs/40_workspace/engineering/PROPOSED_CHANGES-version-sync.md` (VS-001..VS-004).
**HARD:** execution_mode=single.
**GATE:** OPEN per `docs/specs/40_workspace/quality-gate/version-sync/GATE_REPORT.md` (4/4 ✅: readability + risk + refuter + qa).
**DOMAINS:** [engineering].
**Date:** 2026-09-18. **Owner:** vasquez (CTO, engineering chain owner).

## Deliverables (with evidence links)

- `scripts/sync_version.py` (modified, +16/−1) — stdlib-only sync script + `package.json` JSON branch (`json.loads`, no-op on match/invalid/non-dict, `json.dumps(indent=2)+"\n"`); `OWNED_TARGETS` now plugin/INSTALL/`package.json`/README/AGENTS (lane-doc dropped from automation); `--check` clean at 2.5.0 exit 0, `--version 9.9.9` drift 3 files exit 2, `v`-prefix/bad-input semantics proven; ruff check + format clean.
- `.github/workflows/release.yml` (modified, +4) — `Verify version sync` step after Build, before Publish (gated `push || released`), moved here from `test.yml` by intent-owner hand-edit.
- `.github/workflows/test.yml` (modified, −3) — check step removed (Lint → Run tests directly).
- `package.json` (unmodified, 2.5.0) — sync-target status: **in-script** (owned JSON path, clean no-op proven), not manual; `pyproject.toml` 2.5.0 + `__init__.__version__` 2.5.0 all in sync.
- `docs/specs/40_workspace/engineering/PROPOSED_CHANGES-version-sync.md` (delta-updated) — records HARD-1 inversion (user hand-edited tree first, spec follows tree), `package.json` in-script status, hook move, `OWNED_TARGETS` swap, stale docstring line.
- `docs/specs/40_workspace/quality-gate/version-sync/` (delta re-gated: 4 reviewer files + GATE_REPORT.md) — min wave re-run on the hand-edit, OPEN.
- Plugin lane carried, not re-gated: `quality-gate/opencode-plugin/GATE_REPORT.md` stays OPEN.

## Definition of Done

- [x] `qa` verdict green (delta re-run: script checks + ruff + `pytest tests/test_cli.py` 25 passed; full 255-suite + YAML parse are CI arbiters).
- [x] ADR: explicitly waived — isolated dev-tooling, no `src/` contract change (proposal § Approval + VS-004; no architecture impact).
- [x] Docs named in acceptance touched: proposal lane doc (delta-updated to tree truth) + `release.yml`/`test.yml` + gate report + this handoff (historical docs frozen by design, OUT list honored).
- [x] Review wave passed, no Critical/High findings (risk ✅, refuter 7/8 + 1 carried residual, readability ✅ with one stale-docstring info).

## Lessons (capture on PASS)

- Closed allow-list (`OWNED_TARGETS`) + read-only single source is what kept this lane safe: the 9.9.9 drift test proves blast radius is exactly 3 files (plugin + INSTALL + package.json).
- `yaml` module absent in local sandbox python — file-read line verification + CI parse is the fallback pattern for workflow edits.
- HARD-1 inversion lesson: intent-owner hand-edited the tree mid-lane (`release.yml`/`test.yml`/`sync_version.py`); recovery is spec-follows-tree with the inversion recorded explicitly in the proposal — never silently rewrite the tree to match stale docs.
- `package.json` is now **in-script** (JSON no-op path), not OUT — the prior "OUT + follow-up question" residual is closed by the hand-edit; round-trip stability verified at 2.5.0.
- Hook placement lesson: drift gate at publish time (`release.yml`, gated `push || released`) instead of test time — blocks bad publish loudly without gating every `Tests` run.

## Next

Route to `frame-ship:ship-release` with SPEC/HARD/GATE/DOMAINS intact. Commit suggestion: `docs(gate-handoff-version-sync): OPEN min-wave + handoff (script + test.yml check)` → SUPERSEDED by delta: ship the hand-edit as `ci(release): move version-sync check test→release + package.json JSON sync` + docs delta.

## Path cites

`frame-ship:using-frame-ship` → `frame-ship:quality-gate` → `frame-ship:verify-handoff` (this stage) → next `frame-ship:ship-release`.
