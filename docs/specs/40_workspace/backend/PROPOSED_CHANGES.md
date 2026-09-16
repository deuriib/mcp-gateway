# Proposed Changes: backend

**Spec Reference:** SPEC-MGW-001
**Agent:** backend
**Date:** 2026-09-16
**Execution_Mode:** single (inherited from SPEC-MGW-001; no override)
**Domains-Touched:** [engineering]

## Summary

Add `mgw` as a second console script bound to the same `mcp_gway.cli:main` click group, proving parity with a new `tests/test_cli_alias.py` and documenting the shortcut. One-line packaging change, zero runtime fork, repo otherwise untouched until approval.

## Changes

| Target | Change Type | Description |
|--------|-------------|-------------|
| `pyproject.toml` | file-modify | Under `[project.scripts]` add `mgw = "mcp_gway.cli:main"` alongside `mcp-gway`; no other packaging change |
| `tests/test_cli_alias.py` | file-create | Parity tests: help-output diff (normalized prog name) for every top-level cmd, `--version` match, entry-point metadata check via `importlib.metadata` |
| `README.md` | file-modify | Add `mgw` shortcut examples; keep `mcp-gway` canonical in all primary examples |
| `AGENTS.md` | file-modify | Commands section notes `mgw` alias 1:1; no behavior change |
| `src/mcp_gway/cli.py` | file-modify — NO-OP explicitly | No change required; listed to freeze that `main()` signature stays untouched as proof of zero fork |

Change types per `propose-changes` template: engineering uses `file-*` only.

## Rationale

SPEC-MGW-001 REQ-F-001..003 demand identical behavior with one binding. Two `project.scripts` → same `main()` is the minimal mechanism the build backend (`uv_build`) already supports: no wrapper process, no arg reshaping, no new module, Windows `.exe` shims emitted automatically. New test file is the RED in TDD (fails today because `mgw` entry point missing); GREEN is the one-line `pyproject.toml` addition. Docs edits satisfy REQ-NF-003 without touching runtime.

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| Shell wrapper script / symlink `mgw → mcp-gway` | Fragile across `uv tool install` + Windows; duplicates install logic outside packaging; harder to test via `importlib.metadata` |
| Rename `mcp-gway` to `mgw` outright | Breaks compat; violates BRIEF-MGW-001 Out of Scope (canonical stays) |
| Separate `mgw_main()` function | Forks dispatch; violates INV-001 parity + INV-002 canonical; doubles maintenance for zero gain |

## Approval Required From

- [ ] Owning C-level: vasquez (CTO) — mandatory (engineering)
- [ ] vasquez (CTO, architecture/API impact) — required: confirms packaging-only, ADR explicitly waived, `ARCHITECTURE.md` v1 sufficient
- [ ] barrera (CISO, auth/data/external-API/PII) — conditional: required only if review finds new boundary/payload; not expected (no new endpoint/adapter/port)

> **Rule:** No repository file modifications during proposal phase. For non-code domains, no external sends/filings/launches during proposal phase either. Only this `PROPOSED_CHANGES.md` is produced.

---

# Risk Assessment: SPEC-MGW-001

**Proposer:** backend
**Date:** 2026-09-16
**Domains-Touched:** [engineering]

## Risk Matrix

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R-001 | `mgw` shim missing on some installer (`uv tool install` / Windows `.exe`) | Med | Med | Install repro on POSIX + Windows check in AC-002; rollback = remove one line |
| R-002 | Help diff flakes on prog-name rendering (`click` prog name) | Med | Low | Normalize `argv[0]`/prog in test before diff; assert exit 0 + normalized equality |
| R-003 | Docs drift (examples diverge between names) | Low | Low | Keep `mcp-gway` primary, `mgw` shortcut callout only; doc diff in AC-005 |
| R-004 | Version skew (`__version__` vs `project.version`) surfaces under new name | Low | Low | Single source already (`semantic_release`); test asserts both `--version` equal |

## Blast Radius

- Engineering: packaging only; services/data untouched; failure = `mgw: command not found`, `mcp-gway` keeps working — no outage.
- Finance/legal/marketing/people/revenue/automation: none — no budget, contract, brand launch, team change, pipeline, or runbook capacity impact.
- Regulators: none — no PII store added; help/logs touch no PII.

## Rollback Plan

Revert one line in `pyproject.toml` (`mgw = ...`), delete `tests/test_cli_alias.py` addition, revert doc callouts. Owner: vasquez via backend. ETA: <15 min. No data migration, no prod deploy beyond reinstall.

## Security Considerations

No auth, no data exposure, no input validation change — same `main()` object, same allow-list (`MCP_GWAY_ALLOW_LOCAL_COMMANDS`) + break-glass (`MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL`) names and semantics. Diff must show zero secrets/tokens/creds; grep for `MCP_GWAY_ALLOW_*` proves untouched. barrera confirms conditional lens.

## Domain Considerations

Engineering only. Finance/budget [dauhajre]: none. Legal/IP [subero]: none. Marketing/brand [vera]: internal shortcut, no external announcement. People/change [santana]: minimal (one shortcut + docs). Revenue [montero]: none. Automation/ops [espinoza+vasquez]: no runbook capacity change; install repro only.
