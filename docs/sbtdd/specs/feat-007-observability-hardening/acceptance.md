---
id: FEAT-007
slug: feat-007-observability-hardening
title: Observability & Resilience Hardening Acceptance
status: Approved
created: 2026-09-15
updated: 2026-09-15
spec_ref: ./spec.md
plan_ref: ../../plans/feat-007-observability-hardening/plan.md
adr_refs: ["../../../architecture/adr-012-observability-hardening.md"]
slot_refs: ["acceptance_FEAT-007"]
branch: feat/007-observability-hardening
commits: []
tags: [observability, resilience, acceptance]
---

# Acceptance: feat-007-observability-hardening

## Acceptance Criteria

### AC-001: Build info and process start time
- **Given** started `Gateway`
- **When** GET `/metrics`
- **Then** contains `mcp_gway_build_info{version=...} 1`, `mcp_gway_process_start_time_seconds`
- **Test Data**: any version
- **Traces**: BR-101 / REQ-OBS-101

### AC-002: Uptime gauge increases
- **Given** started `Gateway`
- **When** two `/metrics` samples with a delay
- **Then** `mcp_gway_uptime_seconds` monotonic non-decreasing
- **Test Data**: 50ms delay
- **Traces**: BR-101 / REQ-OBS-101

### AC-003: Cardinality cap with _other
- **Given** counter with 201 distinct label combos
- **When** `exposition()`
- **Then** 200 labeled series + `_other`; sum preserved
- **Test Data**: 201 combos
- **Traces**: BR-102 / REQ-OBS-102

### AC-004: Discovery latency observed
- **Given** registry injected into `discover_tools`
- **When** refresh completes
- **Then** `mcp_gway_discovery_duration_seconds` has `{server,status}` observations
- **Test Data**: mocked discovery
- **Traces**: BR-103 / REQ-OBS-103

### AC-005: SSE disconnect counted
- **Given** open SSE session
- **When** client stream closes
- **Then** `gateway_sse_disconnects_total{reason="client_disconnect"}` +1 and WARN logged
- **Test Data**: TestClient SSE close
- **Traces**: BR-104 / REQ-OBS-104

### AC-006: Shutdown summary
- **Given** Gateway that served requests
- **When** `aclose()`
- **Then** JSON summary log (uptime, requests, sessions, drops) + `mcp_gway_lifetime_seconds` set
- **Test Data**: 2 requests served
- **Traces**: BR-105 / REQ-OBS-105

### AC-007: Slow-request WARN
- **Given** mocked duration > 1000 ms
- **When** request completes
- **Then** WARN log with `duration_ms > 1000`
- **Test Data**: monkeypatched elapsed
- **Traces**: BR-106 / REQ-OBS-106

### AC-008: stdio request metrics
- **Given** stdio loop handles a request
- **When** response written
- **Then** `stdio_requests_total{method,status}` +1 and duration observed
- **Test Data**: fake stdin NDJSON
- **Traces**: BR-107 / REQ-OBS-107

### AC-009: stdio JSON access log
- **Given** stdio request with request_id
- **When** handled
- **Then** JSON log with `transport="stdio"`, method, status, duration_ms
- **Test Data**: fake stdin
- **Traces**: BR-108 / REQ-OBS-108

### AC-010: CLI INFO gated by env
- **Given** `MCP_GWAY_LOG_LEVEL` unset → then set to `info`
- **When** CLI `add` succeeds in both states
- **Then** no INFO JSON (unset); INFO JSON event (set); WARNING/ERROR unaffected
- **Test Data**: valid remote server `https://api.example.com/mcp`
- **Traces**: BR-109 / REQ-OBS-109

### AC-011: CLI failure logged + exit code
- **Given** invalid add (missing url for remote)
- **When** CLI runs
- **Then** exit 1 + WARNING JSON event on stderr
- **Test Data**: `add x --type remote`
- **Traces**: BR-109 / REQ-OBS-109

### AC-012: Degraded banner
- **Given** registry with server exposing 0 tools
- **When** `serve --transport http` starts
- **Then** banner shows `N/total` + degraded hint
- **Test Data**: fixture server with empty tool list
- **Traces**: BR-110 / REQ-OBS-110

### AC-013: Upstream status classification
- **Given** mocked ok / raise / timeout
- **When** `_call_tool_async`
- **Then** `upstream_tool_calls_total{status=ok|error|timeout}` + duration histogram
- **Test Data**: three mock sessions
- **Traces**: BR-111 / REQ-OBS-111

### AC-014: Retry on transport once
- **Given** `retry_on_transport_error=true`, transport fails once then ok
- **When** tool call
- **Then** success + `upstream_retries_total{server}` == 1
- **Test Data**: mock transport
- **Traces**: BR-112, BR-113 / REQ-OBS-112, REQ-OBS-113

### AC-015: No retry after call_tool
- **Given** `retry_on_transport_error=true`, `call_tool` raises
- **When** tool call
- **Then** status `error`, retries untouched
- **Test Data**: mock session raising in call_tool
- **Traces**: BR-112 / REQ-OBS-112

### AC-016: Default off unchanged
- **Given** default config (flag unset)
- **When** transport connect fails
- **Then** error, no retry attempt
- **Test Data**: mock transport failing
- **Traces**: BR-115 / REQ-OBS-115

### AC-017: CodeMode skip with evidence
- **Given** one broken + one valid server
- **When** CodeMode injects tools
- **Then** WARN + `code_mode_servers_skipped_total{reason}` for broken; valid still works
- **Test Data**: fixture with corrupt .pyi
- **Traces**: BR-114 / REQ-OBS-114

### AC-018: No new prod deps
- **Given** pyproject dependencies
- **When** diff reviewed
- **Then** no new production dependency added (stdlib + existing only)
- **Test Data**: featureref branch vs main
- **Traces**: BR-116 / REQ-OBS-116

### AC-019: Contract + suite green
- **Given** full repo
- **When** `uv run pytest -q` and `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/`
- **Then** all green; baseline 255 tests pass alongside new tests
- **Test Data**: local run
- **Traces**: BR-116, NFRs