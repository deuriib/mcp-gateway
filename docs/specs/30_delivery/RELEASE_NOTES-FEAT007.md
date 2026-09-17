# RELEASE_NOTES.md — FEAT-007 Observability/Resilience Hardening

**Version:** 2.3.0 (pending)
**Date:** 2026-09-15
**Spec:** `docs/specs/50_archive/feat-007-observability-hardening/spec.md`

## Highlights

Full-process observability hardening for mcp-gateway: lifecycle metrics, upstream tool telemetry, opt-in transport-phase retry, label-cardinality safety, and degraded-server visibility — all without adding a single production dependency.

## What's New

### Lifecycle Metrics (AC-001..003)
- `build_info{version}` — gateway version signal
- `process_start_time_seconds` — Unix epoch of process start
- `uptime_seconds` — updated every 30s via heartbeat
- `lifetime_seconds` — set at shutdown with structured JSON summary
- Label-cardinality cap (`_MAX_LABEL_COMBOS=200`) with overflow coalescing to `_other`

### Discovery Telemetry (AC-004)
- `discovery_duration_seconds{server,status}` — tracks tool discovery latency per server

### SSE Resilience (AC-005..007)
- `gateway_sse_disconnects_total{reason}` — counts disconnects by `client_disconnect`, `idle`, or `error`
- `aclose()` emits structured shutdown summary with uptime/requests/sessions/drops
- Slow-request WARN log at 1000ms threshold

### Stdio Observability (AC-008..009)
- Per-request metrics: `stdio_requests_total`, `stdio_request_duration_seconds`
- JSON access log with `transport:"stdio"` for structured output

### CLI Structured Events (AC-010..012)
- `_log_cli_event()` helper — structured JSON to stderr (WARNING always, INFO gated by `MCP_GWAY_LOG_LEVEL`)
- Add success/error logging with duration and tool count
- Serve banner shows degraded hint when servers fail injection

### Upstream Tool Telemetry (AC-013..014)
- `upstream_tool_calls_total{server,tool,status}` — tracks every upstream call with `timeout` classification
- `upstream_tool_duration_seconds{server,tool}` — per-tool latency histogram

### Transport-Phase Retry (AC-015..016)
- `--retry-on-transport-error` CLI flag (opt-in, default OFF)
- Retries exactly once, only during transport+initialize phase
- `session.call_tool` is NEVER retried (non-idempotent safety)
- `upstream_retries_total{server}` counter

### Degraded Server Visibility (AC-017)
- `code_mode_servers_skipped_total{reason}` — broken servers visible on `/metrics`
- WARN log on injection failure with server name + error detail
- Serve banner degraded hint when tools fail to load

### Zero Dependencies (AC-018)
- All changes use stdlib + existing dependencies only

## Breaking Changes

None. All changes are additive. MCP/SSE contract untouched.

## Deprecations

None.

## Rollback Plan

1. Revert to previous version (`git revert HEAD`)
2. No data migration needed — metrics are ephemeral
3. No config changes required — all new flags default to OFF

## Upgrade Notes

- New CLI flag `--retry-on-transport-error` is opt-in — no behavior change for existing configs
- New metrics appear on `/metrics` automatically
- `MCP_GWAY_LOG_LEVEL` env var controls INFO-level CLI logs (default: WARNING only)

## Acknowledgments

Built with the frame-ship workflow: spec → architecture → implementation → quality gate → handoff → ship.
