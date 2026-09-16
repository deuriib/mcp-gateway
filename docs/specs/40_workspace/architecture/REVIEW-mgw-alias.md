# Architecture Review: SPEC-MGW-001

**Reviewer:** vasquez (CTO) with architect input
**Date:** 2026-09-16
**Verdict:** Approved

## Contract Compliance

| Invariant | Status | Notes |
|-----------|--------|-------|
| INV-001 Parity 1:1 | pass | Two scripts → same `main()` (`src/mcp_gway/cli.py:74-76`); test normalizes prog name before diff |
| INV-002 `mcp-gway` canonical | pass | Proposal keeps canonical primary; `mgw` shortcut only |
| INV-003 No new boundary | pass | No endpoint/adapter/payload/port; `pyproject.toml:19-20` packaging only |
| INV-004 Local-first | pass | `127.0.0.1` default + `exit 2` gate unchanged under both names |
| INV-005 Env names untouched | pass | `MCP_GWAY_ALLOW_*` strings absent from diff (AC-004 grep) |
| INV-006 Single version source | pass | Both report `pyproject.toml:3` + `__version__` |

## ADR Required?

- [x] Yes — ADR-013 created (`docs/architecture/adr-013-cli-alias-mgw.md`, accepted)
- [ ] No — change is within existing contracts

Note: ADR-013 records a packaging decision within ARCHITECTURE.md v1, not an invariant break. No runtime contract modified.

## Conditions for Approval

None — proceed to `execute-spec` on approved proposal. Security lens: `barrera` path-cite only (`agents/security/barrera.md`); full `review-security` STRIDE not triggered (no auth/data/external-API/PII boundary). If implementation diff shows any new boundary, halt and route to `barrera` before QA.

## Sign-off

- [x] vasquez (CTO)
