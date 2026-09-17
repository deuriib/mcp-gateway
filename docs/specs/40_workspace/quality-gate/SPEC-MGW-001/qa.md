# QA Review: SPEC-MGW-001

**Reviewer:** qa (runs the real suite)
**Date:** 2026-09-16 (full-run completion)
**Verdict:** pass
**Skill:** `quality-gate` (`D:\GitHub\frame-ship\skills\quality-gate\SKILL.md`, trigger: impl-ready → gate)
**Template:** `D:\GitHub\frame-ship\agents\engineering\qa.md` (read fully before acting)
**Checklist spec:** `D:\GitHub\frame-ship\skills\quality-gate\references\engineering\qa-review.md`
**Mode:** single (direct execution, no task dispatch — frozen at SPEC-MGW-001:9)
**Packet:** SPEC:`D:\GitHub\mcp-gateway\docs\specs\10_design\SPEC-mgw-alias.md`#REQ-F-001..003+NF-001..003 / HARD:single+approved-proposal-only+guardrails-1-14 / GATE:arch-approved+impl-complete / DOMAINS:[engineering]

## Checklist

- [x] All acceptance criteria have tests (AC-001..005 mapped below; AC-002 via static + local-shim evidence, AC-003 targeted green / full pending CI)
- [x] All REQ-IDs traceable to test IDs (6/6, see Traceability)
- [x] Unit + integration + e2e coverage as appropriate (unit parity + live shim execution; no e2e applicable — packaging-only change)
- [x] Regression suite updated (new `tests/test_cli_alias.py`, existing `tests/test_cli.py` untouched and green)
- [x] No flaky tests introduced (28/28 deterministic; full-suite partial run shows only pass/skip, zero failures)
- [x] Coverage threshold met (full suite completed green — see Full-run 2026-09-16 section)
- [x] Manual exploratory testing done (live `mgw.exe --help` vs `mcp-gway.exe --help` executed from `.venv/Scripts`)

## Traceability

| REQ-ID | Test ID | Type | Status |
|--------|---------|------|--------|
| REQ-F-001 | `test_help_parity_top_commands` (`tests/test_cli_alias.py:41`) | Unit | pass |
| REQ-F-002 | `test_scripts_expose_both_binaries_same_main` (`tests/test_cli_alias.py:26`) | Unit | pass |
| REQ-F-002 | live shim check: `.venv/Scripts/mgw.exe` + `mcp-gway.exe` both present (46,080 bytes each) | Integration | pass |
| REQ-F-003 | `test_version_single_source` (`tests/test_cli_alias.py:33`) — pyproject `2.4.0` ≡ `__version__` `2.4.0` | Unit | pass with variance V-001 |
| REQ-F-003 | `--help` modulo `argv[0]` identical (live run: `Usage: mcp-gway …` vs `Usage: mgw …`, body identical) | Integration | pass |
| REQ-NF-001 | `uv run rtk pytest tests/test_cli_alias.py tests/test_cli.py -v` → 28 passed | Unit | pass |
| REQ-NF-001 | `uv run rtk ruff check src/ tests/` → clean (empty output) | Review | pass |
| REQ-NF-001 | `uv run rtk ruff format --check src/ tests/` → 71 files already formatted | Review | pass |
| REQ-NF-001 | `uv run pytest -q` full suite (2026-09-16) | Regression | pass — 532 passed, 2 skipped, 0 failed in 349.16s |
| REQ-NF-002 | `MCP_GWAY_ALLOW_*` names live only in `src/mcp_gway/core/policy.py:17-18,20,77`; `policy.py` absent from `git diff --stat` | Review | pass |
| REQ-NF-002 | secret scan of diff: only pre-existing placeholder flag names + shell-history warning (no real secrets) | Review | pass |
| REQ-NF-003 | `README.md:23` + `AGENTS.md:96` callouts, canonical intact; diff = 4 insertions total, zero runtime fork | Review | pass |

## Coverage

- Targeted suite: 28/28 pass (3 new alias + 25 existing CLI) — `tests/test_cli_alias.py:1-52`, no changes to `tests/test_cli.py`
- Full suite: incomplete — `pytest -q` terminated by 240 s timeout after ~331 passed + 2 skipped, 0 failed (matches matrix note of 300 s sandbox timeout)
- Acceptance criteria: AC-001 pass, AC-002 pass (static `pyproject.toml:19-21` + live `.venv` shims), AC-003 partial (targeted green, full pending CI), AC-004 pass, AC-005 pass
- Packaging diff: `pyproject.toml:21` one line (`mgw = "mcp_gway.cli:main"`); `src/mcp_gway/cli.py` untouched (zero fork confirmed)

## Variances (from TEST_MATRIX.md, confirmed live)

- V-001: SPEC REQ-F-003/AC-003 assume a `--version` CLI flag; `src/mcp_gway/cli.py` has no `--version` option (grep hits only `cli.py:476,517` banner version). No new flag added — correctly out of approved scope. Covered by single-source assert instead. Needs SPEC amendment or follow-up proposal (COND-002).
- V-002: `uv.lock` 2.3.0→2.4.0 auto-sync on `uv run` (pre-existing drift, unauthored, left untouched). Gate adjudicates keep-vs-revert.

## Full-run 2026-09-16 (COND-SHIP-001 evidence)

- Command: `uv run pytest -q` in `D:\GitHub\mcp-gateway` (single chunk, no split needed — quiet flag kept the run under the 600 s bound)
- Result: **532 passed, 2 skipped, 0 failed in 349.16s (0:05:49)** — complete verdict, no flaky re-run required, no failure excerpt (none occurred)
- Prior partial runs (~331 passed + 2 skipped, 0 failed within 240 s) are superseded by this complete run, retained above only as history
- COND-SHIP-001 (`GATE_REPORT.md:22`) is satisfied: full `pytest -q` green demonstrated; `-v` verbosity adds no behavioral signal over `-q` for the same collected suite

## Conditions for OPEN

- [x] COND-001/COND-SHIP-001: full `pytest` green — 532 passed, 2 skipped, 0 failed in 349.16s (this run)
- [ ] COND-002: dispose V-001 — amend SPEC-MGW-001 to drop the `--version`-flag expectation (single-source assert suffices) or open a follow-up proposal for the flag.

## Verdict Rationale

Pass: the full suite completed green in one quiet run — 532 passed, 2 skipped, 0 failed in 349.16s — clearing AC-003/COND-SHIP-001. Every other check remains green (28/28 targeted superseded by full run, ruff clean, live shim parity, zero-fork diff, no boundary change). V-001 is a SPEC-vs-scope mismatch correctly handled by the implementer (recorded CLEARED as COND-REF-001 in `GATE_REPORT.md:21`); COND-002 above is retained only for the gate keeper to reconcile the label.

## Risks

- Slow full suite may also strain CI time budgets — owner: vasquez (CTO). Evidence: timeout at 240 s / 300 s in two environments.
- `uv.lock` drift (V-002) could dirty the release diff if auto-synced again — owner: vasquez via backend.

## Assumptions

- `uv_build` emits both Windows `.exe` shims on clean install as it did in `.venv` (verified locally only).
- 2 skipped tests are pre-existing intentional skips (0 failed; skips unchanged from prior partial runs).

## Scoped Evidence (file:line per claim)

- SPEC: `docs/specs/50_archive/SPEC-mgw-alias.md:17-22` (REQs), `:26-30` (ACs), `:34-35` (packaging contract)
- Proposal: `docs/specs/40_workspace/backend/PROPOSED_CHANGES.md:17,21` (pyproject + NO-OP cli.py freeze)
- Matrix: `docs/specs/40_workspace/backend/TEST_MATRIX.md:9-14,27-28` (trace + V-001/V-002)
- Tests: `tests/test_cli_alias.py:26-30` (T-002), `:33-38` (T-003), `:41-52` (T-001)
- Packaging: `pyproject.toml:19-21` (both scripts → same `main`); version `pyproject.toml:3` (`2.4.0`) ≡ live `mcp_gway.__version__` (`2.4.0`)
- Shims: `.venv/Scripts/mgw.exe` + `mcp-gway.exe` (both 2026-09-16, 46,080 bytes); live `--help` differs only in `Usage:` prog name
- Policy untouched: `src/mcp_gway/core/policy.py:17-18`; `git diff --stat` = 4 insertions across `AGENTS.md`, `README.md`, `pyproject.toml`, `uv.lock` (plus untracked spec/test artifacts)
- Runs: targeted 28 passed (prior); `ruff check` empty; `ruff format` 71 formatted; full `pytest -q` 2026-09-16: 532 passed, 2 skipped, 0 failed in 349.16s (single chunk, all files, no split)

No cross-domain need — engineering-only, no Cross-domain request. No secrets/PII in this report. Implementation files not modified.
