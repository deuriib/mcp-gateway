# Implementation Plan: SPEC-MGW-001

**Agent:** backend
**Date:** 2026-09-16
**Approved By:** initiator go (proposal) + vasquez arch Approved (`docs/specs/40_workspace/architecture/REVIEW-mgw-alias.md`)
**Domains-Touched:** [engineering]

## Steps

| Step | Description | Target / Files | Evidence Location | Est. Effort |
|------|-------------|----------------|-------------------|-------------|
| 1 RED | Failing parity test first (entry-point + help + version single-source) | `tests/test_cli_alias.py` (create) | `uv run rtk pytest tests/test_cli_alias.py -v` → 2 passed, 1 failed (`KeyError: 'mgw'`) | 0.5h |
| 2 GREEN | Second console script, same `main()` | `pyproject.toml` (+1 line under `[project.scripts]`) | same command → 3 passed | 5 min |
| 3 Docs | Shortcut callouts, canonical intact | `README.md` (+2), `AGENTS.md` (+1) | `git diff` file:line | 10 min |
| 4 Checks | Lint/format + targeted tests + diff hygiene | n/a (gate) | `ruff check` + `ruff format --check` clean; 28 passed (`test_cli_alias` + `test_cli`); no env-name touch | 15 min |

## Order of Operations

RED before GREEN (TDD law — no production change without its failing test); packaging before docs (docs describe shipped behavior); checks last (gate on final tree). `cli.py` frozen by design — listed NO-OP in proposal, untouched in diff.

## Rollback Points

Any step: delete `tests/test_cli_alias.py`, drop the one `pyproject.toml` line, revert 3 doc lines. No migration, no deploy beyond reinstall. (`uv.lock` auto-sync 2.3.0→2.4.0 noted as incidental, left for gate to adjudicate; backend does not checkout-restore per non-destructive rule.)

## Quality Gates

- [x] Engineering: Lint / Tests (targeted) passing — full suite timed out at 300s in sandbox, deferred to `qa` in quality-gate
- [ ] Finance: n/a (no budget/controls impact)
- [ ] Legal: n/a
- [ ] Marketing: n/a (internal, no announcement)
- [ ] People: n/a (shortcut + docs only)
- [ ] Revenue: n/a
- [ ] Automation/ops: install repro (AC-002 POSIX/Windows) deferred to gate — `importlib`-level proven via `pyproject.toml` scripts assert; shim presence needs clean-install check
