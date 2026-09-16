---
id: FEAT-007
slug: feat-007-observability-hardening
title: Observability & Resilience Hardening
status: Approved
created: 2026-09-15
updated: 2026-09-15
spec_ref: ./spec.md
plan_ref: ../../plans/feat-007-observability-hardening/plan.md
adr_refs: ["../../../architecture/adr-012-observability-hardening.md"]
slot_refs: ["spec_FEAT-007"]
branch: feat/007-observability-hardening
commits: []
tags: [observability, resilience, cli]
---

# Spec: feat-007-observability-hardening

## Spec ID: FEAT-007
## Status: Approved

> **Note on stage ownership:** translate-to-spec is bound to `vasquez`; subagent
> dispatch failed on infra (502/cancel, 2026-09-15) and the CEO ordered delivery
> to continue. This spec set was produced by the executing assistant from the
> approved brief. `vasquez` gates it at verify-handoff.

### Objective
Close observability, resilience, availability and graceful-degradation gaps in
mcp-gateway v2.2.0 across all surfaces (HTTP/SSE serving plane, stdio transport,
CLI management commands, upstream MCP calls) — additive only, stdlib-only, no
breaking changes, local-first intact.

### Actors
- Operator (CLI `add`/`remove`/`update`/`refresh`/`list`/`inspect`, `serve`)
- Orchestrator / Prometheus scraper (`/metrics` on 127.0.0.1)
- Probe system (`/health`, `/ready`, `/live`)
- Upstream MCP server (remote or local child process)
- LLM client (OpenCode `type: local|remote` over stdio/SSE)

### Business Rules
| Rule ID | REQ ID | Rule | Priority |
|---------|--------|------|----------|
| BR-101 | REQ-OBS-101 | `mcp_gway_build_info{version}` + `mcp_gway_process_start_time_seconds` + `mcp_gway_uptime_seconds` (gauge heartbeat-updated) exposed in `/metrics` | Must |
| BR-102 | REQ-OBS-102 | MetricsRegistry caps label-combinations per metric at 200; overflow coalesces into `_other` label (fulfills EC-OBS-03) | Must |
| BR-103 | REQ-OBS-103 | `discovery_duration_seconds{server,status}` observed on `discover_tools`/`refresh_server` via injected registry | Must |
| BR-104 | REQ-OBS-104 | `gateway_sse_disconnects_total{reason=client_disconnect\|idle\|queue_full\|error}` + WARN log on stream break | Must |
| BR-105 | REQ-OBS-105 | `Gateway.aclose()` logs structured summary (uptime, total HTTP requests, active sessions, drops) + sets `mcp_gway_lifetime_seconds` | Must |
| BR-106 | REQ-OBS-106 | LoggingMiddleware emits WARN when `duration_ms > 1000` (fixed constant, no env) | Should |
| BR-107 | REQ-OBS-107 | stdio mode records `mcp_gway_stdio_requests_total{method,status}` + `mcp_gway_stdio_request_duration_seconds{method}` via gateway metrics | Must |
| BR-108 | REQ-OBS-108 | stdio per-request JSON access log, HTTP access-log shape + `"transport":"stdio"`, request_id coherent | Must |
| BR-109 | REQ-OBS-109 | CLI `_log_cli_event(action,status,duration_ms,server)` on logger `mcp_gway.cli`: WARN/ERROR always JSON to stderr; INFO only when `MCP_GWAY_LOG_LEVEL` explicitly set; exit codes 0/1/2/130 preserved | Must |
| BR-110 | REQ-OBS-110 | `serve --transport http|sse` banner shows enabled/total servers + degraded hint when a server has 0 tools | Should |
| BR-111 | REQ-OBS-111 | `server_factory._call_tool_async` records `mcp_gway_upstream_tool_calls_total{server,tool,status=ok\|error\|timeout}` + `mcp_gway_upstream_tool_duration_seconds{server,tool}`; `TimeoutError` classified as `timeout` | Must |
| BR-112 | REQ-OBS-112 | Opt-in retry `MCPServerConfig.retry_on_transport_error: bool = False` + CLI flag `--retry-on-transport-error`: exactly one retry, transport/connect/initialize phase only; **never** retried once `session.call_tool` invoked | Must |
| BR-113 | REQ-OBS-113 | `mcp_gway_upstream_retries_total{server}` counters accepted retries | Must |
| BR-114 | REQ-OBS-114 | CodeMode `_inject_tools`/`refresh` broken servers: structured WARN + `mcp_gway_code_mode_servers_skipped_total{reason}`, never silent | Must |
| BR-115 | REQ-OBS-115 | Retry default off → zero behavior change for existing configs | Must |
| BR-116 | REQ-OBS-116 | HARD guard: zero new prod deps (stdlib + existing); no MCP/SSE contract change; local-first gating intact | Must |

### Edge Cases
- 201 label combos → 200 tracked + `_other`, total values preserved across split.
- Retry on: transport create fails once then ok → success + `retries_total` +1; `call_tool` raises → no retry, status `error`.
- Local command spawn failure → error, **no** retry (retry is remote-transport-only; spawn is cheap and retry masks misconfig).
- `TimeoutError` in upstream → status `timeout` (not `error`).
- stdio broken pipe → existing exit-0 path untouched; metrics recorded before exit.
- CLI: env unset → no INFO JSON to stderr; WARN/ERROR still emitted; no duplicates.
- Banner: 0 servers, or N servers with 0 tools → degraded hint accurate.
- Shutdown with zero requests → summary still logs with 0s.
- Cardinality overflow under concurrent writers → lock-held, atomic coalesce.
- `discovery_duration_seconds` with registry absent → no-op (registry optional injection).

### Constraints
- HARD: no new prod dependencies; stdlib `logging` + hand-rolled `MetricsRegistry` only (HC-OBS-02).
- HARD: no breaking changes — MCP/SSE JSON-RPC contract, probe responses, CLI exit codes all unchanged.
- HARD: local-first gating (`127.0.0.1` default, `MCP_GWAY_ALLOW_REMOTE=1`, X-Warning) intact.
- Retry is opt-in per server; docs must warn about non-idempotent tool calls.

### NFRs
- `/metrics` exposition typical < 10 KB; bounded by BR-102 cardinality cap.
- Added middleware overhead < 2 ms p95 (incremental, no new I/O in probes).
- `/health`, `/ready`, `/live` < 10 ms; readiness stays local-only (no upstream reachability calls).
- Probes remain graceful under load (existing concurrency limits untouched).
- `uv run ruff check src/ tests/` 0; `uv run ruff format --check src/ tests/` 0; full suite green (255 baseline + new).