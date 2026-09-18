# HANDOFF — v2.4.0 tag-collision reconcile (Option C delta)

**Skill:** `frame-ship:verify-handoff`. **Gate:** CONDITIONAL OPEN (see
`../quality-gate/v2.4.0-collision/GATE_REPORT.md`).
**DOMAINS:** `[engineering]`. **Owner:** vasquez. **Date:** 2026-09-18.
**Next agent:** ship-release (via orchestrator; `devops` PyPI hash confirm at publish).

## Deliverables + evidence links

1. Tag hygiene — local lightweight `v2.4.0` (→ `6601767`) deleted via
   `git tag -d v2.4.0`; verified absent (`for-each-ref` empty, `show-ref` clean);
   remote annotated (`07b3b05…` → `0cdcfe8`) untouched (`ls-remote` proof).
2. `CHANGELOG.md` — `## v2.4.0 (2026-09-16)` restored to 6-bullet automation
   content (+ provenance `note`); 09-16/17 delta (mgw feat, `/ready` fix, perf
   docs, collision docs, FEAT-007 evidence) under `## Unreleased`;
   residual risks ride Unreleased. Keep-a-Changelog order preserved.
3. `docs/specs/30_delivery/RELEASE_NOTES.md` — retitled to pending next version,
   collision provenance box, rollback corrected (NEVER tag-d/push-delete
   published tag; recovery = revert + yank via devops + vasquez).
4. Lane docs — `PROPOSED_CHANGES-v240-collision.md`, this `GATE_REPORT.md`,
   this `HANDOFF.md` (all under `40_workspace/`).
5. Single trigger commit (pending at handoff time, message below) — `feat`
   scope → semantic-release emits **v2.5.0**.

Trigger commit: `feat(cli): queue post-v2.4.0 delta after tag-collision reconcile`.

## DoD checklist

- [x] Proposal before code (proposal file written before edits; single-commit
      waiver recorded, owner-signed).
- [x] Scope respected (approved targets only; zero `src/`, zero version bumps).
- [x] Remote tag + PyPI untouched (proof above). No force, no remote delete.
- [x] Keep-a-Changelog (Unreleased carries pending; dated entry matches automation).
- [x] Rollback text corrected (no published-tag deletion advice anywhere).
- [x] `ruff check` + `format --check` clean.
- [x] Scoped pytest recorded (27+6+11 passed; 1 pre-existing fail stash-proven,
      owned follow-up, not this lane's regression).
- [x] Gate CONDITIONAL OPEN, no Critical/High, refuter run before qa.
- [ ] Follow-up (not blocking this lane): update
      `test_ready_not_ready_and_loop_blocked` to the 35s drift contract
      (owner vasquez); `devops` PyPI hash confirm at next publish; never
      `push --tags` until next version tag exists.

## Risks + assumptions

- Risk (Low): `push --tags` resurrects collision — mitigated by verification +
  written instruction. Owner: vasquez.
- Risk (Low, pre-existing): edge test vs 35s threshold mismatch — owned
  follow-up, documented, no silent PASS (CONDITIONAL, not clean-green claim).
- Assumption: feat-scope → v2.5.0 (mgw binary is user-facing). Breaker noted
  in proposal. Assumption: single-commit waiver avoids stray patch bumps
  (`chore`/`docs` ∈ `patch_tags`).

## Lesson capture

- Lightweight local tags sharing an automation version number collide silently
  until `ls-remote` comparison; future release lanes must verify
  `for-each-ref` vs `ls-remote` BEFORE creating any local `v*` tag, and must
  never hand-tag a version number owned by semantic-release.
- Edge tests that pin timing thresholds must be updated in the same commit as
  the threshold change (the 3→35 drift fix left a 10s-drift test red on master).
- One-conventional-commit lanes need an explicit granularity waiver up front,
  or the gate's own doc commits trigger unwanted patch releases.
