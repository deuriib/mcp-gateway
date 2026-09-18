# Release Notes: internal tooling — opencode plugin relocate to plugins/{harness}/** pattern

**Date:** 2026-09-18
**Release Manager:** vasquez (CTO, engineering chain owner)
**Specs Included:** bounded BRIEF — plugin relocate (plugins/opencode seed)
**Domains-Touched:** [engineering]
**Ship Type:** internal tooling + file reorganization (no deploy, no tag)

> Prior ships live in `CHANGELOG.md` (`v2.6.0`, 2026-09-18) and
> the suffixed notes (`RELEASE_NOTES-MGW-ALIAS.md`, `RELEASE_NOTES-FEAT007.md`,
> `RELEASE-NOTES-PERF-001.md`) — read those by reference, nothing duplicated here.
> This ship touches no `src/`, bumps no version, and mints no tag:
> semantic-release owns tags + `CHANGELOG.md`.

## Highlights

- Opencode plugin relocated from `.opencode/plugins/mcp-gateway.ts` to
  `plugins/opencode/mcp-gateway.ts` — seeds the `plugins/{harness}/**` pattern
  for future harnesses (claude, codex, etc.).
- `.opencode/` folder deleted completely (zero tracked files remained after move).
- `package.json` main/exports fixed: old pointer `.opencode/plugins/mcp-gway.ts`
  never existed on disk (dangling typo); new pointer resolves to real file.
- Example string in MCP_RULES updated: `result = Server.tool(param=value, params....)`
  (user-specified).

## Changes

### Features

- Plugin file moved to `plugins/opencode/mcp-gateway.ts` as `plugins/{harness}/**` seed
  (bounded BRIEF, engineering)
- Install guide moved to `plugins/opencode/INSTALL.md` with source paths updated;
  target `<PROJECT>/.opencode/plugins/mcp-gateway.ts` unchanged (opencode auto-load)

### Fixes

- `package.json` main/exports: fixed pre-existing dangling pointer (`mcp-gway.ts`
  never existed → `plugins/opencode/mcp-gateway.ts` resolves to real file)

### Breaking Changes

- None. Additive only: existing installs via old `.opencode/` path still work if
  already copied; `INSTALL.md` documents new source path for fresh installs.

## Evidence

- Gate: `docs/specs/40_workspace/quality-gate/opencode-plugin/GATE_REPORT.md` (OPEN, 4/4 reviewers)
- Handoff: `docs/specs/40_workspace/verify-handoff/opencode-plugin/HANDOFF.md` (DoD complete)
- Sync check: `scripts/sync_version.py --check` clean at 2.6.0
- Lint: `ruff check` clean, `ruff format --check` 71 files formatted
- Tests: `pytest test_registry + test_models` 36 passed
- Git: only intended files changed (2 RM renames + 3 M edits)

## Known Issues

- Historical workspace docs (`PROPOSED_CHANGES*.md`, `RELEASE_NOTES.md`) still
  cite `.opencode/...` paths — frozen records, not rewritten.

## Rollback / Undo

- No tag, no deploy, no PyPI publish, no migration, no data to reverse.
- Revert: `git revert <commit>` — single commit restores old `.opencode/` layout.
  Worst case: unreverted leaves `plugins/opencode/` (new pattern) alongside
  `.opencode/` (old pattern) — no outage, no breakage.
- NEVER `git tag -d`, NEVER push-delete any published tag as part of this ship.

## Changelog / Archive

- `CHANGELOG.md`: N/A — semantic-release owns tags + changelog; this ship is
  internal-only tooling with no `src/` change and no user-facing impact
  (owner sign-off: vasquez).
- Archive: N/A — workspace lanes stay in `docs/specs/40_workspace/`.
