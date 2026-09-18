# GATE_REPORT — v2.4.0 tag-collision reconcile (Option C delta)

**Skill:** `frame-ship:quality-gate` (single-mode min gate).
**Spec refs (reference-only):** `40_workspace/engineering/PROPOSED_CHANGES-v240-collision.md`,
`CHANGELOG.md`, `docs/specs/30_delivery/RELEASE_NOTES.md`,
git `0cdcfe8`..`6601767`, `.github/workflows/release.yml` (ADR-007 hybrid).
**DOMAINS:** `[engineering]`. **Mode:** `single`.
**Owner/gate keeper:** vasquez (CTO, engineering). **Date:** 2026-09-18.

## Verdicts

| Reviewer | Verdict | Summary |
|---|---|---|
| review-readability | ✅ PASS | CHANGELOG keeps Keep-a-Changelog order (Unreleased on top, dated versions below); v2.4.0 entry restored to 6-bullet automation text + provenance `note`; delta rides Unreleased with typed bullets. RELEASE_NOTES retitled to pending, collision box at top, per-item detail still by reference. No duplicated sections; orphan bullet fragment removed. |
| review-risk | ✅ PASS | No secrets/tokens/creds in diff (docs + ref delete only). No new endpoints/adapters/boundaries/payloads — no new trust boundary. Least privilege intact: local-only `tag -d`, no remote write, no force, explicit `push --tags` warning. Blast radius: 2 markdown files + lane docs. Residual risk stated (re-collision on `push --tags`) with mitigation (verification + instruction). No Critical/High. |
| review-refuter | ✅ PASS (adversarial) | Challenged: (1) "Should next be v2.4.1 not v2.5.0?" — REFUTED: delta ships user-facing `mgw` binary postdating remote v2.4.0; `minor_tags=[feat]` → minor. Patch would under-signal. (2) "Should we fix the failing edge test here to claim green?" — REFUTED: out of approved scope (docs + tag hygiene only); fix rides follow-up (see qa). (3) "Should CHANGELOG keep 2026-09-17 v2.4.0 entry?" — REFUTED: that entry describes unreleased delta under a published version number; collision documented instead. Finding without proof = refuted; all claims above carry diff/scan/log proof in evidence. |
| qa (real suite) | ⚠️ CONDITIONAL PASS | `ruff check` clean; `ruff format --check` 71 files clean. Scoped pytest: 27 passed (alias+probes+serve_unified) · 6 passed (edgecases-observability minus 1) · 11 passed (obsfeat007 core ACs). ONE pre-existing failure: `test_ready_not_ready_and_loop_blocked` (expects 503 at 10s drift; code threshold is 35s since `2686015`) — fails identically on clean HEAD (stash-proven, not caused by this docs-only delta). No `src/` touched here, so no new coverage owed. Condition: follow-up updates that edge test to the 35s contract (owner vasquez). |
| review-data | N/A | No schema/lineage/PII-store impact. No PII in diff. |

## Gate: CONDITIONAL OPEN

No ❌. Single ⚠️ (qa, pre-existing, owned, with path out) → gate CONDITIONAL OPEN
per `quality-gate` §4 (conditions must clear before ship of the *follow-up*;
this lane's docs-only delta is itself shippable as the trigger commit).
Handoff to `frame-ship:verify-handoff` permitted. Waiver: commit-granularity
(single `feat` commit for proposal+impl+gate+handoff) recorded in proposal;
no verdict overridden.

## Evidence (scoped, allowlisted)

- `git for-each-ref refs/tags/v2.4.0` → empty (local deleted); `git show-ref` → no local `v2.4.0`; `git ls-remote --tags origin` → annotated `07b3b05…` + peeled `0cdcfe8` intact.
- `git cat-file -t` (pre-delete record): local `v2.4.0` = `commit` (lightweight → `6601767`); remote peeled = `0cdcfe8`.
- `ruff check src/ tests/` → "All checks passed!"; `ruff format --check` → "71 files already formatted".
- pytest tails recorded in session logs (27 / 6 / 11 passed; 1 pre-existing fail with stash proof).
- `git diff --stat` (this lane): `CHANGELOG.md`, `RELEASE_NOTES.md` + 3 lane docs; zero `src/` files.
