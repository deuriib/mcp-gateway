# Release Notes: internal tooling — opencode plugin (remote HTTP) + version-sync check

**Date:** 2026-09-18
**Release Manager:** vasquez (CTO, engineering chain owner)
**Specs Included:** REQ-OP-001..008 (opencode plugin lane), VS-001..VS-004 (version-sync sub-lane)
**Domains-Touched:** [engineering]
**Ship Type:** internal tooling + client config (no deploy, no tag)

> Prior deploy ship detail lives in `CHANGELOG.md` (`v2.5.0`, 2026-09-17) and
> the suffixed notes (`RELEASE_NOTES-MGW-ALIAS.md`, `RELEASE_NOTES-FEAT007.md`,
> `RELEASE-NOTES-PERF-001.md`) — read those by reference, nothing duplicated here.
> This ship touches no `src/`, bumps no version, and mints no tag:
> semantic-release owns tags + `CHANGELOG.md`.

## Highlights

- Opencode now talks to the gateway over loopback HTTP instead of stdio:
  the local plugin wires a `gateway` remote entry (`type: "remote"`,
  default `http://127.0.0.1:8080/mcp`, overridable via `MCP_GWAY_URL`,
  optional `Bearer` header via `MCP_GWAY_TOKEN`), marker `MCP-GWAY v2.5.0`
  (REQ-OP-001..008, gate OPEN).
- Single-file install story: `.opencode/INSTALL.md` covers copy-from-checkout
  (Option A) vs `file:///` copy (Option B) with marker + `curl /health` verify steps.
- Version drift is now CI-gated: `scripts/sync_version.py --check` runs in
  `release.yml` (`Verify version sync` step after Build, before Publish,
  gated `push || released`; moved from `test.yml` by intent-owner hand-edit
  2026-09-18); closed allow-list of owned marker targets incl. `package.json`
  `"version"` (in-script JSON path), `pyproject.toml` stays the read-only source
  (VS-001..VS-004, gate OPEN delta, `--check` clean at 2.5.0 exit 0).

## Changes

### Features

- Opencode plugin remote-HTTP env-driven entry + `config.skills.paths`
  wiring + verbatim `COMPACTION_REINJECT` marker block
  (REQ-OP-001..008, engineering) — `.opencode/plugins/mcp-gateway.ts`
- Install guide for this plugin, HTTP revision (REQ-OP-008, engineering) —
  `.opencode/INSTALL.md`
- Version-sync script (stdlib-only, `--check`/`--write`, incl. `package.json`
  JSON sync) + CI check step in `release.yml` after Build, before Publish
  (moved from `test.yml`, VS-001..VS-004, engineering) —
  `scripts/sync_version.py`, `.github/workflows/release.yml`
  (`.github/workflows/test.yml` check removed)
- Lockfile aligned to the released version (`mcp-gway` 2.4.0 → 2.5.0
  editable entry, `uv sync` artifact, no dependency change) — `uv.lock`

### Fixes

- None (no user-facing defect fixed in this ship).

### Domain Ships

- Engineering: two workspace lanes shipped as internal tooling; proposals,
  gate reports, and handoffs linked below as evidence.

### Breaking Changes

- None. Additive only: if the gateway is not serving HTTP on loopback when
  opencode starts, the `gateway` entry shows disconnected (precondition,
  never breaks bootstrap). `src/` untouched in both lanes.

## Evidence

- Plugin lane: proposal `docs/specs/40_workspace/engineering/PROPOSED_CHANGES.md`
  (rev d) · gate `docs/specs/40_workspace/quality-gate/opencode-plugin/GATE_REPORT.md`
  (OPEN) · handoff `docs/specs/40_workspace/verify-handoff/opencode-plugin/HANDOFF.md`
  · secret scan 0 hits · structural matrix 20/20.
- Version-sync lane: proposal `docs/specs/40_workspace/engineering/PROPOSED_CHANGES-version-sync.md`
  (VS-001..VS-004, delta-updated to tree truth per HARD-1 inversion) · gate `docs/specs/40_workspace/quality-gate/version-sync/GATE_REPORT.md`
  (OPEN delta, 4/4 min wave re-run on hand-edit) · handoff `docs/specs/40_workspace/verify-handoff/version-sync/HANDOFF.md`
  (delta) · `sync_version.py --check` clean at 2.5.0 · 9.9.9 drift 3 files exit 2 · ruff clean · `pytest tests/test_cli.py` 25 passed.

## Known Issues

- Re-gate the plugin in 90d against latest opencode plugin docs (watch the
  `skills` schema: stable OBJECT vs V2 ARRAY — code handles both — plus
  upstream ordering caveat on unpatched builds). Owner: vasquez.
- `package.json` version deliberately out of version-sync scope; surface as
  intent-owner question, never auto-sync. Owner: vasquez.

## Rollback / Undo

- No tag, no deploy, no PyPI publish, no migration, no data to reverse.
- Revert in reverse order: `git revert <commit-2-version-sync>`
  then `git revert <commit-1-plugin>` (hashes reported in the ship message).
  Each lane reverts independently; worst case unreverted is a disconnected
  opencode entry or a redundant CI check — no outage possible.
- NEVER `git tag -d`, NEVER push-delete any published tag as part of this
  ship. Published recovery (if ever needed) is `git revert` + PyPI yank via
  devops + vasquez. Owner: vasquez. ETA <15 min per lane.

## Changelog / Archive

- `CHANGELOG.md`: N/A — semantic-release owns tags + changelog; this ship is
  internal-only tooling + client config with no `src/` change and no
  user-facing impact (owner sign-off: vasquez).
- Archive: N/A — workspace lanes stay in `docs/specs/40_workspace/`; moving
  them to `docs/specs/50_archive/` would break the relative cross-references
  between each HANDOFF ↔ GATE_REPORT ↔ proposal. Owner sign-off: vasquez.
