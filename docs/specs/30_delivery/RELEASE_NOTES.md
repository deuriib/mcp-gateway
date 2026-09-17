# Release Notes: Unreleased batch → next hybrid release

**Date:** 2026-09-17
**Release Manager:** montilla (CEO) — single mode, direct
**Specs Included:** SPEC-MGW-001, FEAT-007 (ADR-012), ADR-010 (unified serve), SPEC-PERF-001, SPEC-READY-001
**Domains-Touched:** [engineering]
**Ship Type:** deploy (library/CLI via hybrid release; no hand tag per ADR-007)

Consolidates the 8 `CHANGELOG.md` Unreleased bullets — all merged, gated, and
pushed; this ship is the release trigger, not new implementation. Per-item
detail lives in `RELEASE_NOTES-MGW-ALIAS.md`, `RELEASE_NOTES-FEAT007.md`,
`RELEASE-NOTES-PERF-001.md` (read those by reference; nothing duplicated here).

## Highlights

- One binary name to remember: `mgw` is now a full 1:1 shortcut for `mcp-gway`
  (SPEC-MGW-001, gate OPEN, QA 532 passed / 0 failed).
- One serve command: `serve --transport [stdio|http|sse]` (default `stdio`);
  `mcp-gway mcp` is a hidden deprecated alias (ADR-010).
- Observable by default: FEAT-007 lifecycle metrics, SSE disconnect reasons,
  stdio access log, upstream CodeMode telemetry, label-cardinality cap
  (gate OPEN, 3 QA rounds).
- Safer `add`: opt-in `--retry-on-transport-error` (exactly one retry,
  transport phase only, default OFF — ADR-012 decision 9).

## Changes

### Features

- `mgw` console script bound to the same `mcp_gway.cli:main`
  (SPEC-MGW-001, engineering) — `pyproject.toml:21`
- Unified `serve --transport [stdio|http|sse]`; `--registry-dir` common to
  `serve`; `--host/--port` apply to `http|sse` only (ADR-010, engineering)
- FEAT-007 observability hardening: `build_info`, uptime/lifetime lifecycle,
  `gateway_sse_disconnects_total{reason}`, stdio per-request metrics + JSON
  access log, `discovery_duration_seconds`, upstream telemetry, degraded-serve
  banner on injection failure (ADR-012, engineering)
- `--retry-on-transport-error` on `mcp-gway add` (ADR-012 decision 9)

### Fixes

- Log-level resolution reads only `MCP_GWAY_LOG_LEVEL` (`--log-level`
  overrides, default `info`); legacy `MCP_GWAY_ENV`/`ENV`/`ENVIRONMENT`/
  `APP_ENV`/`DEBUG`/`LOG_LEVEL` fallbacks removed; inert
  `MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD` purged from docs

### Docs (internal-only, no src/ changes)

- SPEC-PERF-001 audit tooling: benchmark script, runbook, findings template,
  architecture NFRs, ADR-011 — shipped `6e159cc`

### Breaking Changes

- `--host/--port` with `--transport stdio` (incl. implicit default) is now
  `Error: --host/--port only apply to --transport http|sse` + exit 2 —
  never warn-and-ignore. Migration: drop the flags for stdio or switch
  transport.
- Legacy log-level env fallbacks removed (see Fixes). Migration: set
  `MCP_GWAY_LOG_LEVEL` or pass `--log-level`.
- Local-first intact: non-loopback bind without `MCP_GWAY_ALLOW_REMOTE=1`
  → exit 2 (unchanged legacy text).

## Known Issues

- FEAT-007 refuter: AC-004 dead-code note accepted, tracked for next release.
- FEAT-007 risk: 4 Medium (raw error text in structured stderr logs) —
  hygiene, not network-facing; tracked next sprint.
- Version/tag skew at ship time: files at 2.4.0, last tag `v2.3.0`.
  Reconciliation is owned by the hybrid automation on push (Tests →
  python-semantic-release); no hand tag, no hand version edit in this ship.

## Rollback / Undo

- `mgw`: revert one `pyproject.toml` line + delete `tests/test_cli_alias.py`
  + 4 doc lines. Owner: vasquez. ETA <15 min. Worst case unreverted:
  `mgw: command not found`, `mcp-gway` unaffected — no outage possible.
- Unified serve / FEAT-007 / retry: revert respective `cli.py` /
  `server_factory.py` / `models.py` hunks per ADRs 010/012; reinstall.
  Owner: vasquez + barrera (path-cite for trust-boundary hunks).
- Release itself: hybrid flow is tag-driven; a bad promotion is undone by
  reverting the release commit and re-running Tests. No prod deploy, no
  migration, no data to reverse.
