---
id: FEAT-006
slug: feat-006-dynamic-local-commands
title: Dynamic Local Commands Plan
status: Approved
created: 2026-09-07
updated: 2026-09-07
spec_ref: ../../specs/feat-006-dynamic-local-commands/spec.md
plan_ref: ./plan.md
adr_refs: ["../../../architecture/adr-009-dynamic-local-commands.md"]
slot_refs: ["plan_FEAT-006"]
branch: feat/006-dynamic-local-commands
commits: ["896b281 feat(policy): add dynamic local allow-list with unrestricted TTL", "7eb8028 fix(dashboard): re-gate local POST PATCH refresh catalog with policy", "e1b5f14 feat(cli): gate local add refresh with policy allow-list"]
tags: [local, plan]
---

# Plan: feat-006-dynamic-local-commands

## Objective
Implement ADR-009 adapted per CISO HARD names; close PATCH bypass; prove with AC-001..AC-012.

## Work Units

### WU-001: Policy core + single syntax rule
- Title: policy allow-list + TTL + syntax/cwd/env
- AC ref: AC-001..AC-005, AC-008, AC-011
- BR/EC: BR-001..BR-004, BR-006..BR-008, BR-011..BR-012
- Status: Done
- Commit: 896b281 `feat(policy): add dynamic local allow-list with unrestricted TTL`

### WU-002: Policy + transport gates
- Title: POST/PATCH/refresh re-gate + which-resolve exec
- AC ref: AC-001..AC-003, AC-007..AC-010
- BR/EC: BR-005..BR-006, BR-008..BR-010, BR-013..BR-014
- Status: Done
- Commit: 7eb8028 `fix(dashboard): re-gate local POST PATCH refresh catalog with policy`

### WU-003: CLI gates without VIA
- Title: CLI add/refresh allow-list + audit
- AC ref: AC-012
- BR/EC: BR-013..BR-014
- Status: Done
- Commit: e1b5f14 `feat(cli): gate local add refresh with policy allow-list`

### WU-004: SBTDD + ADR + AC tests + verify
- Title: specs/plans/ADR-009 + test_policy_local_commands AC-001..AC-012 + full green + ruff
- AC ref: AC-001..AC-012
- BR/EC: BR-015..BR-016
- Status: Done
- Commit: 141171c `docs(feat-006): SBTDD scaffold ADR-009 plus AC-001..AC-012`

## Dependencies
- `Registry` atomic writes; `_discovery_sem` shared; `Gateway(registry, host)` loopback flag.

## Risks & Mitigations
- Existing tests assumed static `npx` open → mitigated by per-test allow-list + `resolve_binary` mock.
- Windows `which` PATHEXT → `shutil.which` handles; tests mock for determinism.
- Marker clock skew → strict `0 <= age <= TTL`, invalid → inactive.

## Traceability
- BR-001 ↔ validate_cmd ↔ AC-011 syntax part ↔ WU-001
- BR-003 ↔ get_allow_list ↔ AC-001..AC-003 ↔ WU-001/WU-002
- BR-004 ↔ is_unrestricted_active ↔ AC-004..AC-005 ↔ WU-001
- BR-005 removed 2026-09-10 (VIA/host gate retired with dashboard); AC-007 host deny retained as historical ↔ WU-002
- BR-009 ↔ PATCH re-gate ↔ AC-009 ↔ WU-002
- BR-010 ↔ refresh re-gate ↔ AC-010 ↔ WU-002
