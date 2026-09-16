# ADR-012: Observability & Resilience Hardening (FEAT-007)

## Status

Accepted (implemented with FEAT-007: process metrics, cardinality guard, discovery
latency, SSE disconnect accounting, graceful shutdown summary, stdio instrumentation,
CLI structured logging, upstream tool-call telemetry, opt-in transport retry,
CodeMode skip evidence).

## Context

mcp-gateway v2.2.0 already ships an observability base (SPEC-2026-08-26, Approach C):
stdlib JSON logs, hand-rolled `MetricsRegistry`, correlation middleware, and the four
probes (`/health`, `/ready`, `/live`, `/metrics`) with local-first gating. Hardening
review surfaced concrete gaps:

- **Dead metric:** `discovery_duration_seconds` registered in `Gateway.__init__`
  but never observed (no metrics injection in `core/client.py` discovery path).
- **Unbounded cardinality:** `MetricsRegistry` had no cap on label combinations per
  metric; SPEC-2026-08-26 EC-OBS-03 promised a 200-cap with an `_other` bucket that
  was never implemented — a label storm (many servers × many tools, or attacker
  influence on path/status labels) means unbounded memory growth in `_metrics`.
- **Surface gaps:** stdio transport recorded no per-request latency or status;
  CLI management commands (`add`/`remove`/`update`/`refresh`/`list`/`inspect`) had
  no structured diagnostics; SSE client disconnects were silent; process shutdown
  left no summary; upstream MCP tool calls measured nothing, classified no failures,
  and had no retry policy.
- **Silent degradation:** CodeMode `_inject_tools`/`refresh` swallowed broken-server
  errors with bare `except: pass` — no log, no metric, indistinguishable from success.

Related: ADR-009 (local allow-list), ADR-010 (unified serve), ADR-011 (SSRF port),
SPEC-2026-08-26 (observability design, Approach C — binding to stdlib + MetricsRegistry).

## Decision — Additive hardening, stdlib-only, opt-in retry

Every change is additive: no MCP/SSE contract change, no new production dependency
(`prometheus_client`/OTel/`tenacity` remain out — HC-OBS-02 / BR-116), local-first
gating untouched.

1. **Process/build metrics** — `mcp_gway_build_info{version}`, 
   `mcp_gway_process_start_time_seconds`, `mcp_gway_uptime_seconds` (heartbeat-updated
   gauge) exposed at `/metrics`.
2. **Cardinality guard** — per-metric cap of 200 label combinations on
   `inc`/`set`/`observe`; overflow coalesces to a reserved `_other` label (EC-OBS-03
   finally honored). Lock-held atomic coalescing; total value preserved.
3. **Discovery latency** — optional injected registry into `discover_tools` /
   `refresh_server` (`core/client.py`) observes `discovery_duration_seconds{server,status}`.
4. **SSE disconnect accounting** — `gateway_sse_disconnects_total{reason}` for
   `client_disconnect|idle|queue_full|error` + WARN log; removes silent stream breaks.
5. **Graceful shutdown** — `Gateway.aclose()` emits a structured summary JSON
   (uptime, total HTTP requests, active sessions, drops) and sets `mcp_gway_lifetime_seconds`.
   Closing is observability's last chance to speak; a silent exit is an ops black hole.
6. **stdio instrumentation** — per-request `stdio_requests_total{method,status}` +
   `stdio_request_duration_seconds{method}` via the same gateway registry; JSON access
   log matches the HTTP access-log shape with `"transport":"stdio"` for cross-surface
   greps.
7. **CLI structured logging** — `_log_cli_event` on logger `mcp_gway.cli`:
   WARNING/ERROR always JSON on stderr; INFO only when `MCP_GWAY_LOG_LEVEL` is
   explicitly set. Rationale: humans get zero noise by default, operators opt into
   full events; journald-friendly; exit codes (0/1/2/130) unchanged.
8. **Upstream tool-call telemetry** — `_call_tool_async` records
   `upstream_tool_calls_total{server,tool,status=ok|error|timeout}` +
   `upstream_tool_duration_seconds{server,tool}` with explicit `TimeoutError`
   classification, via registry injected the same way sandbox/registry receive it.
9. **Opt-in transport retry** — `MCPServerConfig.retry_on_transport_error: bool =
   False` + CLI `--retry-on-transport-error`: exactly one retry, **only** when the
   failure happens in the transport/connect/initialize phase; **never** when
   `session.call_tool` was invoked (non-idempotent side effects). Default-off means
   zero behavior change for existing configs. Counter `upstream_retries_total{server}`.
   Rationale: connection-level flakiness is the recoverable failure class; tool
   execution is not retry-safe by default (cf. HTTP `POST` semantics — retry only
   transport handshake, never the business op).
10. **CodeMode skip evidence** — bare `except: pass` replaced with structured WARN +
    `code_mode_servers_skipped_total{reason}`; degradation is visible, not silent.

## Alternatives Considered

- **Adopt `prometheus_client` / OTel SDK: REJECTED.** Violates HC-OBS-02 (stdlib
  only, vendored registry); the existing hand-rolled `MetricsRegistry` already
  exposes Prometheus text (0.0.4) and satisfies the four-probe contract; adding an
  SDK buys aggregation we don't consume (no remote push, local scraper only, CLI-only
  headless).
- **Retry by default: REJECTED.** Default-on retries across all tool calls would
  double non-idempotent side effects (file writes, sends, mutations) on transient
  hiccups that actually reached the server. Opt-in per server keeps the safe default
  and lets operators enable it where transport flakiness is known and calls are
  idempotent.
- **Readiness reaching upstream: REJECTED.** `/ready` stays local-only (registry +
  routes + loop). Reaching every upstream on every probe adds latency, load, and
  false negatives (a server being slow ≠ gateway not ready). Upstream health is
  emergent from tool-call telemetry, not a probe contract.

## Consequences

- **Positive:** bounded cardinality (memory-safe under label storms); every surface
  speaks structured JSON; upstream failures classified for SLOs (`ok|error|timeout`);
  degraded upstream/CodeMode states visible at a glance; shutdown leaves a summary;
  `grep '"transport":"stdio"'` and `'transport":"http'` unify debugging across modes.
- **Negative:** +~25 tests / new metrics surface to maintain; opt-in retry adds one
  public config field (`retry_on_transport_error`) and one CLI flag — documented,
  default off; INFO CLI events are suppressed by default (operator must set
  `MCP_GWAY_LOG_LEVEL` to see them).
- **HARD intact (non-negotiable):** `serve` binds `127.0.0.1` by default; local
  allow-list env names unchanged (ADR-009); SSRF port unchanged (ADR-011); no new
  prod dependency (HC-OBS-02 / BR-116); MCP/SSE JSON-RPC contract unchanged.

## Traces (post-implementation)

- `src/mcp_gway/observability/metrics.py` — cardinality guard + `_other` coalescing.
- `src/mcp_gway/gateway.py` — process metrics, heartbeat uptime gauge, SSE disconnect
  accounting, `aclose()` summary, registry injection points.
- `src/mcp_gway/observability/middleware.py` — slow-request WARN (> 1000 ms).
- `src/mcp_gway/core/client.py` — discovery latency observation, retry-aware connect.
- `src/mcp_gway/stdio.py` — per-request metrics + JSON access log.
- `src/mcp_gway/cli.py` — `_log_cli_event`, degraded banner summary.
- `src/mcp_gway/server_factory.py` — upstream telemetry + opt-in transport retry.
- `src/mcp_gway/models.py` — `retry_on_transport_error` field + validation.
- `src/mcp_gway/code_mode.py` — skip WARN + `code_mode_servers_skipped_total`.

## Acceptance Criteria (1:1 ↔ tests)

FEAT-007 `docs/sbtdd/specs/feat-007-observability-hardening/acceptance.md`
AC-001..AC-019 map 1:1 to tests in `tests/test_obsfeat007_*.py` (per-AC), plus
`test_observability_*` extensions. Verify: `uv run pytest -q` (full suite green) and
`uv run ruff check src/ tests/` + `uv run ruff format --check src/ tests/` (0).