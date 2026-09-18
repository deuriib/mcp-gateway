# PROPOSED_CHANGES — v2.4.0 tag collision (Option C delta)

**Spec refs (reference-only):** `docs/specs/30_delivery/RELEASE_NOTES.md`,
`CHANGELOG.md ## v2.4.0`, git refs `0cdcfe8` (published) .. `6601767` (master),
`.github/workflows/release.yml` ADR-007 hybrid, inspection provenance
(remote annotated tag → `0cdcfe8`, local lightweight tag → `6601767`).
**Execution mode:** `single` (engineering-only, docs + tag hygiene).
**DOMAINS:** `[engineering]`.
**Skills cited:** `frame-ship:propose-changes` (this proposal),
then `frame-ship:execute-spec` → `frame-ship:quality-gate` → `frame-ship:verify-handoff`.
**Date:** 2026-09-18. **Owner:** vasquez (CTO, engineering chain owner).

## Provenance (verified, not assumed)

- Remote `refs/tags/v2.4.0` = annotated tag object `07b3b05…` peeled to
  `0cdcfe8` ("2.4.0", 2026-09-16, semantic-release). Published — untouched.
- Local `refs/tags/v2.4.0` = lightweight (`objecttype=commit`) → `6601767`
  ("chore(release-2.4.0): ship 8 unreleased…", 2026-09-17, Deuri Vasquez).
  Collision: same name, different object, different type.
- `0cdcfe8` is the ancestor of `6601767` via
  `a034e83` (mgw alias) → `2686015` (fix health drift 3→35) →
  `6e159cc` (perf docs) → `d04fc91` → `6601767`.
- At `0cdcfe8`: `pyproject.toml`/`__init__.py` already `2.4.0`;
  `CHANGELOG.md ## Unreleased` holds 6 bullets (cleanup, unified serve,
  hidden-alias deprecation, compat, FEAT-007, retry). No `mgw` line in
  `[project.scripts]`, no consolidated `RELEASE_NOTES.md`
  (only `RELEASE_NOTES-FEAT007.md` exists there).
- Delta `0cdcfe8..6601767` adds: `mgw` shim (`pyproject.toml:21` + tests),
  `fix(health)` drift 3→35, perf audit tooling (docs-only), FEAT-007 evidence
  wording, residual risks, consolidated `RELEASE_NOTES.md` titled v2.4.0
  (2026-09-17) with dangerous rollback (`git tag -d v2.4.0` + push delete).

## Change list (approved targets ONLY)

1. Tag hygiene: `git tag -d v2.4.0` (local lightweight ONLY). No push, no
   remote touch, no delete/re-push of published tag. Verify via
   `git for-each-ref` + `show-ref` + `ls-remote --tags origin`.
2. `CHANGELOG.md`: restore `## v2.4.0 (2026-09-16)` to the 6-bullet automation
   content from `0cdcfe8`; move 09-16/17 delta (mgw feat, health fix, perf
   docs, evidence wording, residual risks) under `## Unreleased` per
   Keep-a-Changelog so semantic-release generates the next version.
3. `docs/specs/30_delivery/RELEASE_NOTES.md`: retitle to pending next version,
   document the collision (remote v2.4.0 stays 2026-09-16 automation; new
   version carries 09-16/17 delta), fix rollback (NEVER `tag -d`/push-delete a
   published tag; published recovery = `git revert` + PyPI yank via
   devops + vasquez; local lightweight removal is local-only, no push).
4. Gate artifacts (this lane): `GATE_REPORT.md` + `HANDOFF.md` under
   `40_workspace/{quality-gate,verify-handoff}/v2.4.0-collision/`.
5. Single conventional commit (see below). No `src/` changes, no version
   bumps by hand (semantic-release owns `pyproject`/`__init__`).

## Conventional commit ruling (default + breaker)

- **Default: `feat` → next version v2.5.0.** Delta ships a user-facing
  binary (`mgw` 1:1 shortcut, `pyproject.toml:21`) that postdates remote
  v2.4.0 — feat-scope under `[tool.semantic_release] minor_tags=[feat]`.
  Shipping it as patch would under-signal minor.
- Breaker that would flip to `fix` → v2.4.1: only if `mgw` were ruled
  docs/alias-without-contract (it is not — new console script + contract).
- Message: `feat(cli): queue post-v2.4.0 delta (mgw + health fix + perf docs)
  after tag-collision reconcile`. Body links REQ→evidence→artifact.

## Risk assessment (blast radius)

- Systems: git refs + 2 markdown files + 3 lane docs. No runtime, no
  endpoint, no migration, no data. `src/` untouched.
- Teams/customers/regulators/revenue: none — docs-only + local ref delete.
  Worst case unreverted: `--tags` push resurrects lightweight and re-collides
  (mitigated by verification step + instruction to never `push --tags`).
- Irreversible actions: NONE in this lane. Remote tag + PyPI untouched.
  `git tag -d` is local-only and recoverable (`git fetch --tags` restores
  remote annotated on demand).
- Rollback: `git revert <this-commit>`; re-create nothing (remote tag never
  deleted).

## Approvers

- Owning domain owner vasquez (engineering) — mandatory, this proposal.
- Gate: `quality-gate` OPEN required; `verify-handoff` HANDOFF required.
- `devops` for PyPI hash confirm at ship (not in this lane — no publish here).

## Commit-granularity waiver (owner-recorded)

`propose-changes`/`quality-gate`/`verify-handoff` each prescribe their own
commit; task constrains ONE conventional commit so semantic-release emits
exactly one next version (each of `chore`/`docs` is in `patch_tags` and would
otherwise trigger stray patch bumps). Vasquez (engineering owner + lane
orchestrator) waives to a single `feat` commit containing proposal + impl +
gate + handoff docs. Auditable here.
