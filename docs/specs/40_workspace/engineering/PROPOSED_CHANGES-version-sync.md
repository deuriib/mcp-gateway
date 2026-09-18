# Proposed Changes: vasquez (CTO, engineering chain owner) — version-sync script lane

**Spec Reference:** User order 2026-09-18 — script to update version all over project + wire into release pipeline (sub-lane, reference-only packet)
**Agent:** vasquez
**Date:** 2026-09-18
**Execution_Mode:** single (inherited from packet HARD)
**Domains-Touched:** engineering

## Summary

Single source stays `pyproject.toml:project.version` (semantic-release owns it + `src/mcp_gway/__init__.py`). New stdlib-only script `scripts/sync_version.py` reads that version (or explicit `--version` override) and syncs owned refs only — plugin `MARKER`, `INSTALL.md`, `package.json` `"version"`, `README.md` / `AGENTS.md` markers via generic path — plus a `--check` step in `release.yml` (moved from `test.yml` by intent-owner hand-edit 2026-09-18; `test.yml` no longer carries the check) that fails loudly on drift without touching the tag / semantic-release flow.

> **Delta 2026-09-18 (intent-owner expansion):** `package.json` `"version"` joins the owned allow-list (JSON parse, 2-space indent + trailing newline, no-op when already at version). Source of truth stays `pyproject.toml`; semantic-release files stay read-only.
>
> **Inversion recorded (HARD-1):** user hand-edited the tree first (`release.yml` +4 check step, `test.yml` −3 removal, `sync_version.py` `package.json` JSON branch + `OWNED_TARGETS` swap lane-doc → `package.json`); this spec follows the tree, not the reverse. `OWNED_TARGETS` in-tree is now (`plugin`, `INSTALL.md`, `package.json`, `README.md`, `AGENTS.md`); the lane-doc target was dropped from automation (script docstring still mentions it — stale, code is truth). `package.json` status: **in-script** (owned JSON path, clean no-op at `2.5.0` proven), not manual.

## Changes

| Target | Change Type | Description |
|--------|-------------|-------------|
| `scripts/sync_version.py` | file-create | Stdlib-only sync script: read version from `pyproject.toml` (tomllib) or `--version X.Y.Z`; `--check` exits 2 with unified diff on drift; `--write` applies idempotently to owned refs only |
| `docs/specs/40_workspace/engineering/PROPOSED_CHANGES-version-sync.md` | document-create | This proposal (new lane file; plugin lane `PROPOSED_CHANGES.md` untouched) |
| `.github/workflows/test.yml` | file-modify | ~~Additive step `Verify version sync` (`python scripts/sync_version.py --check`) after Lint, before tests~~ — REMOVED by intent-owner hand-edit 2026-09-18 (was +3 at `8e18aa9`, now −3); check lives in `release.yml`, not here |
| `.github/workflows/release.yml` | file-modify | `Verify version sync` step (`uv run scripts/sync_version.py --check`, gated `push || released == 'true'`) after Build, before Publish — moved here from `test.yml` by intent-owner hand-edit; tag / semantic-release flow otherwise intact |
| `.opencode/plugins/mcp-gateway.ts` | file-modify (via script, not hand-edit) | Sync `const MARKER = "MCP-GWAY vX.Y.Z"` only; no logic change |
| `.opencode/INSTALL.md` | file-modify (via script, not hand-edit) | Sync `MCP-GWAY vX.Y.Z` occurrences (verify `Select-String` line + Expected marker mention) only; no guide rewrite |
| `package.json` | file-modify (via script, not hand-edit) | Sync `"version": "X.Y.Z"` via JSON parse (`json.loads`, 2-space indent + trailing newline per repo style; no-op when already at version); no dep/field reorder beyond `json.dumps` stability (verified round-trip stable) |
| `docs/specs/40_workspace/engineering/PROPOSED_CHANGES-version-sync.md` | file-modify (self, later stage) | Marker sync inside this lane doc if it carries a version marker (idempotent, optional) |

Change types per `proposal-template.md`: engineering rows use `file-*`; this row uses `document-create` for the proposal itself.

## Rationale

Research first (per HARD-1): `release.yml` = dual trigger `push tags v*` (deterministic `uv build` + `pypi-publish`) + `workflow_run Tests completed` → `semantic-release version` (auto minor/patch per `minor_tags=[feat]`, `patch_tags=[fix …]`). `[tool.semantic_release]` owns exactly `pyproject.toml:project.version` + `src/mcp_gway/__init__.py:__version__` (`version_toml` + `version_variables`). Fighting it (script writing those two files, or inventing a new scheme) would collide with the bot commit and the `v2.4.0` collision lesson (remote annotated tag stays published; recovery is `revert`, never tag-delete). So the script treats those two as READ-ONLY input.

Drift observed 2026-09-18: `pyproject.toml` + `__init__.py` + `package.json` + plugin `MARKER` + `INSTALL.md` already at `2.5.0`, while `AGENTS.md` / `README.md` / `uv.lock` / historical lane docs still carry `2.4.0` or dated entries. The script deliberately does NOT chase every `2.4.0` string — historical docs (`v2.4.0-collision/`, `baseline_*.json`, `PERF-FINDINGS-v2.4.0.md`, `CHANGELOG.md ## v2.4.0`) must stay frozen as evidence. Owned refs are the live plugin surface + this lane doc, nothing else.

Pipeline hook moved by intent-owner hand-edit 2026-09-18: `release.yml --check` (after Build, before Publish, gated `push || released == 'true'`) is the loud drift gate at publish time; `test.yml` no longer carries the check. Tag / `concurrency: release` / bot-commit logic otherwise intact.

## Owned-refs scope (closed allow-list)

IN (script may write):
- `.opencode/plugins/mcp-gateway.ts` — exactly `const MARKER = "MCP-GWAY v<ver>"` (single regex, preserves surrounding code).
- `.opencode/INSTALL.md` — exactly `MCP-GWAY v<ver>` tokens (verify snippet + expected-marker lines).
- `package.json` — exactly `"version": "<ver>"` (JSON parse; `json.dumps(indent=2) + "\n"`; verified round-trip stable at 2.5.0; invalid JSON / non-dict = safe no-op, never crash `--check`). Status: **in-script**, clean no-op at `2.5.0` proven 2026-09-18.
- `README.md`, `AGENTS.md` — `MCP-GWAY v<ver>` markers via generic `MARKER_RE` (in `OWNED_TARGETS` since `8e18aa9`; clean no-op at `2.5.0` — neither drifts).
- ~~Lane-doc marker~~ — DROPPED from `OWNED_TARGETS` by intent-owner hand-edit (was owned at `8e18aa9`, now absent from code tuple; script docstring § Owned-refs still lists it — stale, code is truth; this proposal doc is hand-maintained, not script-synced).

OUT (script must never write; `--check` must ignore):
- `pyproject.toml`, `src/mcp_gway/__init__.py` (semantic-release owns; read-only input).
- `CHANGELOG.md` (semantic-release owns).
- `uv.lock` (uv-owned), all historical / archive docs (`40_workspace/**/v2.4.0-collision/`, `30_delivery/reports/baseline_*`, `PERF-FINDINGS*`, `RELEASE_NOTES*`, `50_archive/`).
- `test.yml` (check removed — no longer a sync surface); `release.yml` tag / bot-commit logic (check step is read-only gate, never writes).

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| Script writes `pyproject.toml` + `__init__.py` (bidirectional sync) | Fights semantic-release (HARD-1); collides with bot commit; repeats v2.4.0 tag-collision class of error |
| Extend `release.yml` with auto-sync commit step | Breaks `concurrency: release` + tag determinism; risks pushing from release job; HARD-3 demands additive check, not flow change |
| Regex-replace every `2.4.0` / `2.5.0` string repo-wide | Destroys historical evidence (baselines, collision gate report, CHANGELOG); violates minimization + OUT list |
| New versioning scheme (e.g. marker without `v`, separate plugin version) | HARD-2 forbids inventing a scheme; single `MARKER` constant + `MCP-GWAY v<ver>` stays exact |

## Approval Required From

- [ ] Owning domain owner: vasquez (engineering) — mandatory, this proposal (single-mode: CTO self-records, gate verdict still required downstream)
- [ ] engineering owner (architecture/API impact — none; script is isolated dev-tooling, no `src/` touch)
- [ ] security owner — not required (no auth/data/API/PII; no secrets in script; `review-risk` scan still runs inside quality-gate per min wave)

> **Rule:** No repository file modifications during proposal phase except this proposal doc. Impl files (`scripts/`, `test.yml`) stay untouched until `execute-spec`.

## Risk assessment

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R-001 | Script overwrites semantic-release-owned files | Low (closed allow-list + read-only input) | High (version fight, tag collision repeat) | `pyproject.toml` + `__init__.py` opened read-only; no write path exists in code; `--check` greps prove it |
| R-002 | Script rewrites historical evidence (`v2.4.0` docs, baselines) | Low (OUT list + narrow regexes) | Med (audit trail loss) | Regexes anchored to `MARKER` / `MCP-GWAY v` live files only; historical dirs never globbed; grep matrix in evidence |
| R-003 | `test.yml` check blocks releases on false positive | Low (idempotent, exact match) | Med (auto-release stalls) | Check runs on `Tests` (visible before release); `--check` prints unified diff; `--write` reproduces it locally; additive step only |
| R-004 | Version format drift (`v` prefix vs bare) | Low (single `normalize()` fn) | Low (marker mismatch) | Accept `2.5.0` or `v2.5.0` input, canonicalize to `MCP-GWAY vX.Y.Z` + bare `X.Y.Z` where needed; strict `^\d+\.\d+\.\d+$` validation |
| R-005 | `package.json` reformat churn (key reorder / indent drift) | Low (round-trip verified stable) | Low (noisy diff) | JSON path returns original bytes when `version` already matches (no rewrite); else `json.dumps(indent=2, ensure_ascii=False) + "\n"` (matches repo LF + 2-space + trailing newline); invalid JSON = safe no-op, never crash `--check` |

## Blast Radius

- Systems: 1 dev-tooling script + 1 CI check step in `release.yml` (+4, moved from `test.yml` −3) + 3 live sync surfaces (plugin marker + INSTALL.md + `package.json` version; `README`/`AGENTS` markers owned but clean no-op). No `src/`, no `tests/`, no runtime, no transport, no registry change.
- Teams/customers/regulators/revenue: none — worst case CI goes red on drift and the author runs `python scripts/sync_version.py --write` locally; no prod, no PII, no secret, no external send.
- Secrets: none introduced (HARD security-1: no secret/token/credential in code/config/logs/examples; script handles version strings only).

## Rollback Plan

- Revert the single `execute-spec` commit (script + `test.yml` step); plugin marker files return to prior committed values via `git checkout -- .opencode/`. No tag move, no PyPI action, no migration. Owner: vasquez. ETA: minutes.

## Security Considerations

No auth/data/external-API/PII touched. Script is stdlib-only (`argparse`, `pathlib`, `re`, `tomllib`, `difflib`, `sys`) — no network, no subprocess, no env-secret reads, no `fetch(`. Version input validated against strict semver; paths constrained to repo root (no traversal: allow-listed relative targets only).

## Domain Considerations

Engineering only. Finance/legal/marketing/people/revenue/automation-ops: no impact — deleted per template (non-touched domains).

## REQ → test → artifact → verdict trace (for execute-spec + quality-gate)

| REQ (lane) | Test / evidence | Artifact | Verdict gate |
|------------|-----------------|----------|--------------|
| VS-001 script reads `pyproject.toml` version, `--version` override wins | `python scripts/sync_version.py --check` dry-run output at `2.5.0` = clean; `--version 9.9.9 --check` shows diff | `scripts/sync_version.py` | quality-gate |
| VS-002 syncs owned refs only (MARKER + INSTALL.md + `package.json` version + `README`/`AGENTS` markers; lane-doc dropped) | grep matrix: `MCP-GWAY v<ver>` hits only in owned files + `package.json` version match; `pyproject`/`__init__` untouched proof via `git diff --stat`; `--version 9.9.9` drift = 3 files (plugin + INSTALL + package.json) | same script | quality-gate + review-risk |
| VS-003 pipeline hook in `release.yml`, fails loudly, tag flow intact | `release.yml` carries `Verify version sync` after Build / before Publish (gated `push \|\| released`); `test.yml` diff = removal only; `--check` exit-2 semantics proven | `.github/workflows/release.yml` (+4) / `.github/workflows/test.yml` (−3) | quality-gate |
| VS-004 never invents scheme; semantic-release files read-only | source grep: no write to `pyproject.toml`/`__init__.py`/`CHANGELOG.md` in script | same script | review-architecture (waive-eligible: no contract change) |

## Skills cited

`frame-ship:using-frame-ship` (bootstrap, already injected — not re-loaded) + `frame-ship:propose-changes` (this stage) → next `frame-ship:execute-spec` → `frame-ship:quality-gate` → `frame-ship:verify-handoff`. Path cites required on every delivered unit.
