---
id: FEAT-007
slug: feat-007-observability-hardening
title: Observability & Resilience Hardening Scenarios
status: Approved
created: 2026-09-15
updated: 2026-09-15
spec_ref: ./spec.md
plan_ref: ../../plans/feat-007-observability-hardening/plan.md
adr_refs: ["../../../architecture/adr-012-observability-hardening.md"]
slot_refs: ["scenario_FEAT-007"]
branch: feat/007-observability-hardening
commits: []
tags: [observability, resilience]
---

# Scenarios: feat-007-observability-hardening

## Preconditions
- `Registry` on isolated `tmp_path`; `Gateway(reg, host="127.0.0.1")`; TestClient.
- Upstream MCP clients mocked (`server_factory` or `core.client` patch points).
- Time mocked with `time.perf_counter`/`monotonic` deltas or monkeypatched sleeps.

## Feature: Process & cardinality (Fase A)
As an operator
I want process-level metrics and bounded label cardinality
So that long-running gateways are diagnosable and memory-safe under label storms.

### Scenario: Build info and start time present
Given a started Gateway
When GET `/metrics`
Then exposition contains `mcp_gway_build_info{version="..."} 1` and `mcp_gway_process_start_time_seconds`

### Scenario: Uptime gauge increases
Given a started Gateway
When GET `/metrics` twice with a small delay
Then `mcp_gway_uptime_seconds` second sample >= first sample

### Scenario: Cardinality overflow coalesces to _other
Given a counter metric
When 201 distinct label combinations are incremented
Then exposition shows 200 labeled series plus one `_other` series carrying the remaining count

## Feature: Discovery metric (Fase A)
### Scenario: Refresh records discovery latency
Given `discover_tools` mocked to return after a known delay
When a refresh runs with the registry injected
Then `mcp_gway_discovery_duration_seconds` histogram has an observation with `{server,status}`

## Feature: SSE disconnects (Fase A)
### Scenario: Client disconnect counted
Given an open SSE session
When the client closes the stream
Then `mcp_gway_gateway_sse_disconnects_total{reason="client_disconnect"}` increments and a WARN log is emitted

## Feature: Graceful shutdown (Fase A)
### Scenario: aclose summary
Given a Gateway that served requests
When `aclose()` is called
Then a structured JSON log with uptime/requests/sessions/drops is emitted and `mcp_gway_lifetime_seconds` set

## Feature: Slow requests (Fase A)
### Scenario: WARN above threshold
Given an HTTP request that takes > 1000 ms (mocked)
When it completes
Then LoggingMiddleware emits WARN with `duration_ms > 1000`

## Feature: stdio transport (Fase B)
### Scenario: Request metrics recorded
Given a stdio loop handling a `tools/call` request
When the response is written
Then `mcp_gway_stdio_requests_total{method,status}` increments and duration histogram observes
### Scenario: JSON access log
Given a stdio request with a request_id
When handled
Then a JSON access log with `"transport":"stdio"`, method, status, duration_ms, request_id is emitted

## Feature: CLI management (Fase C)
### Scenario: INFO logged only with env
Given `MCP_GWAY_LOG_LEVEL` unset
When CLI `add` succeeds
Then no INFO JSON on stderr
When `MCP_GWAY_LOG_LEVEL=info` is set
Then an INFO JSON event `{action:"add",status:"success",duration_ms,...}` appears on stderr
### Scenario: Failure always logged
Given `mcp-gway add` with an invalid config
When it exits 1
Then a WARNING JSON event is emitted to stderr

## Feature: Degraded banner (Fase C)
### Scenario: Zero-tool hint
Given a registry with one server exposing 0 tools
When `serve --transport http` starts
Then banner shows `enabled/total` and `degraded: N server(s) with no tools — run mcp-gway refresh <name>`

## Feature: Upstream instrumentation (Fase D)
### Scenario: Status classified
Given upstream `call_tool` mocked ok / raising / timing out
When invoked through `_call_tool_async`
Then `mcp_gway_upstream_tool_calls_total` increments with `status=ok|error|timeout` respectively plus duration histogram

## Feature: Opt-in retry (Fase D)
### Scenario: Transport retry once
Given `retry_on_transport_error=true` and transport connect fails once then succeeds
When the tool call runs
Then it succeeds and `mcp_gway_upstream_retries_total{server}` == 1
### Scenario: No retry after call_tool
Given `retry_on_transport_error=true` and `session.call_tool` raises
When the tool call runs
Then status `error`, retries counter untouched
### Scenario: Default off unchanged
Given `retry_on_transport_error` unset (default false) and transport connect fails
When the tool call runs
Then error, no retry attempt

## Feature: CodeMode degradation (Fase D)
### Scenario: Broken server skipped with evidence
Given one valid and one broken server config
When CodeMode injects tools
Then the broken server is skipped with a WARN + `mcp_gway_code_mode_servers_skipped_total{reason}` and the valid one still exposes tools