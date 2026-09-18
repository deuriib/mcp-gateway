# HANDOFF — version-sync sub-lane (vasquez, CTO)

**Skill:** `frame-ship:verify-handoff` (single-mode, gate OPEN).
**SPEC:** `docs/specs/40_workspace/engineering/PROPOSED_CHANGES-version-sync.md` (VS-001..VS-004).
**HARD:** execution_mode=single.
**GATE:** OPEN per `docs/specs/40_workspace/quality-gate/version-sync/GATE_REPORT.md` (4/4 ✅: readability + risk + refuter + qa).
**DOMAINS:** [engineering].
**Date:** 2026-09-18. **Owner:** vasquez (CTO, engineering chain owner).

## Deliverables (with evidence links)

- `scripts/sync_version.py` (new, untracked) — stdlib-only sync script; `--check` clean at 2.5.0 exit 0, `--version 9.9.9` drift exit 2, `v`-prefix/bad-input semantics proven; ruff check + format clean.
- `.github/workflows/test.yml` (modified, +3) — additive `Verify version sync` step after Lint, before tests; `release.yml` diff empty.
- `docs/specs/40_workspace/quality-gate/version-sync/` (new: 4 reviewer files + GATE_REPORT.md) — min wave consolidated in place.
- Plugin lane carried, not re-gated: `quality-gate/opencode-plugin/GATE_REPORT.md` stays OPEN.

## Definition of Done

- [x] `qa` verdict green (min-wave subset: script checks + ruff + `pytest tests/test_cli.py` 25 passed; full 255-suite + YAML parse are CI arbiters via the new check step).
- [x] ADR: explicitly waived — isolated dev-tooling, no `src/` contract change (proposal § Approval + VS-004; no architecture impact).
- [x] Docs named in acceptance touched: proposal lane doc + `test.yml` step + gate report (historical docs frozen by design, OUT list honored).
- [x] Review wave passed, no Critical/High findings (risk ✅, refuter 7/8 + 1 carried residual, readability ✅).

## Lessons (capture on PASS)

- Closed allow-list (`OWNED_TARGETS`) + read-only single source is what kept this lane safe: the 9.9.9 drift test proves blast radius is exactly 2 files.
- `yaml` module absent in local sandbox python — Select-String line verification + CI parse is the fallback pattern for workflow edits.
- `package.json` version deliberately OUT of scope; surface as intent-owner question, never auto-sync.

## Next

Route to `frame-ship:ship-release` with SPEC/HARD/GATE/DOMAINS intact. Commit suggestion: `docs(gate-handoff-version-sync): OPEN min-wave + handoff (script + test.yml check)`.

## Path cites

`frame-ship:using-frame-ship` → `frame-ship:quality-gate` → `frame-ship:verify-handoff` (this stage) → next `frame-ship:ship-release`.
