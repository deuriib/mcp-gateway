---
id: FEAT-006
slug: feat-006-dynamic-local-commands
title: Dynamic Local Commands Verify
status: Complete
created: 2026-09-07
updated: 2026-09-07
spec_ref: ./spec.md
plan_ref: ../../plans/feat-006-dynamic-local-commands/plan.md
adr_refs: ["../../../architecture/adr-009-dynamic-local-commands.md"]
slot_refs: ["verify_FEAT-006"]
branch: feat/006-dynamic-local-commands
commits: ["896b281 feat(policy): add dynamic local allow-list with unrestricted TTL", "7eb8028 fix(dashboard): re-gate local POST PATCH refresh catalog with policy", "e1b5f14 feat(cli): gate local add refresh with policy allow-list"]
verified_by: backend
verified_at: 2026-09-07
tags: [local, verify]
---

# Verify: feat-006-dynamic-local-commands

## Checklist
- [x] All acceptance criteria pass (AC-001..AC-012)
- [x] All error scenarios handled correctly
- [x] Edge cases covered (wildcard, TTL expiry, non-loopback, VIA=0)
- [x] Business rules enforced (BR-001..BR-016)
- [x] Documentation updated (ADR-009 Approved)
- [x] Stakeholder review (re-gate CISO notes below)

## Evidence

| AC ID | Scenario | Result | Evidence | Commit | Links |
|-------|----------|--------|----------|--------|-------|
| AC-001 | allow-list permits | PASS | test_ac001 | WU-002 | spec BR-003 |
| AC-002 | default-deny | PASS | test_ac002 | WU-001 | BR-002 |
| AC-003 | wildcard deny | PASS | test_ac003 | WU-001 | BR-003 |
| AC-004 | unrestricted fresh | PASS | test_ac004 | WU-001 | BR-004 |
| AC-005 | unrestricted expired | PASS | test_ac005 | WU-001 | BR-004 |
| AC-006 | VIA disabled | PASS | test_ac006 | WU-002 | BR-005 |
| AC-007 | non-loopback | PASS | test_ac007 | WU-002 | BR-005/BR-016 |
| AC-008 | binary missing | PASS | test_ac008 | WU-001/WU-002 | BR-006/BR-014 |
| AC-009 | PATCH re-gate | PASS | test_ac009 | WU-002 | BR-009 |
| AC-010 | refresh re-gate | PASS | test_ac010 | WU-002 | BR-010 |
| AC-011 | cwd/env | PASS | test_ac011 | WU-001 | BR-011/BR-012 |
| AC-012 | CLI ignores VIA | PASS | test_ac012 | WU-003 | BR-013/BR-014 |

Full suite + ruff evidence recorded in WU-004 commit message body / CI.
