# Resilience Review — FEAT-007

## Verdict: ✅ APPROVED

## External Dependencies Identified

| Dependency | Layer (Hexagonal) | Pattern | Timeout | Resilience |
|---|---|---|---|---|
| Upstream MCP server (remote) | Port: `create_client_transport` | Adapter (httpx2) | SSRF_TIMEOUT (configurable) | ✅ Bounded |
| Upstream MCP server (local child) | Port: `filtered_stdio_client` | Adapter (stdio) | Process lifetime | ✅ Bounded |
| `session.call_tool` (MCP SDK) | Port: `_call_tool_async` | ClientSession | Per-config `timeout_sec` | ✅ Bounded, non-retryable |
| `session.list_tools` / `session.initialize` | Port: `discover_tools` | ClientSession | `asyncio.timeout(timeout_sec)` | ✅ Bounded |
| `MetricsRegistry` (in-process) | Core: hand-rolled | Thread-safe dict + lock | N/A | ✅ Bounded (200-cap) |
| stdio stdin/stdout | Port: `_CappedLineReader` | Adapter (readline) | `MAX_LINE_BYTES` bounded | ✅ Bounded |

## Findings

### F-1: Metrics Never Break the Request Path ✅
**Severity:** N/A (PASS)

Every `metrics.inc()` / `metrics.set()` / `metrics.observe()` call across all surfaces (`gateway.py:372-374`, `gateway.py:474-478`, `gateway.py:601-607`, `stdio.py:64-66`, `code_mode.py:99-105`, `server_factory.py:148-151`, `client.py:330-341`) is wrapped in `try/except Exception: pass` with explicit WHY comments. The request path is never poisoned by a registry error. The broad catch is justified: telemetry is fire-and-forget.

### F-2: `session.call_tool` Is Never Retried ✅
**Severity:** N/A (PASS — HARD Constraint Met)

In `server_factory.py:69-151`, the retry logic is scoped exclusively to the `_setup()` inner function (transport + initialize phase, lines 101-112). The `session.call_tool()` invocation at line 126 sits **outside** the retry try-block — if `_setup` succeeds, `call_tool` executes exactly once. If `_setup` fails on the first attempt and retry is enabled, a fresh `AsyncExitStack` is created (line 123) and `_setup` is retried — but `call_tool` has never been called. The `retried` flag (line 96/121) is only set when the transport phase fails, never when the tool phase fails. This is correct.

### F-3: Retry Is Bounded and Opt-In ✅
**Severity:** N/A (PASS)

- Default: `retry_on_transport_error = False` (BR-115, zero behavior change).
- Max retries: exactly 1 (line 119-124 — no loop, single `if` branch).
- Scope: transport/connect/initialize only (the `_setup()` coroutine).
- `upstream_retries_total` counter (line 148) makes retries visible on `/metrics`.
- Local commands never retry (spawn failure → PermissionError/FileNotFoundError, not retry-eligible).

### F-4: Cardinality Cap Prevents Unbounded Growth ✅
**Severity:** N/A (PASS)

`MetricsRegistry._bounded_key()` (line 202-219) enforces `_MAX_LABEL_COMBOS = 200` per metric under the `threading.Lock`. When the cap is hit, new label combos coalesce into `("_other",) * len(labelnames)`. The lock is held for the entire read-modify-write cycle, so concurrent writers cannot race past the cap. With the cap, `exposition()` holds the lock for at most 200 entries per metric — bounded and predictable.

### F-5: AsyncExitStack Cleanup on Retry ✅
**Severity:** N/A (PASS)

In `server_factory.py:114-128`, when the first `_setup` fails and retry triggers, the old stack is explicitly closed (`await stack.aclose()`, line 122) before a new one is created (line 123). The `finally` block at line 130 ensures the final stack is always closed regardless of outcome. No leaked connections.

### F-6: SSE Disconnect Cleanup ✅
**Severity:** N/A (PASS)

In `gateway.py:514-553`, the `event_stream()` generator's `finally` block (line 540-553) pops the session from `_sessions` and updates `gateway_sessions_active` regardless of exit reason (idle, client_disconnect, error). The `_sessions.pop(session_id, None)` with default prevents KeyError on double-cleanup. Correct.

### F-7: Graceful Shutdown (aclose) ✅
**Severity:** N/A (PASS)

`Gateway.aclose()` (line 338-365): cancels heartbeat task (with `CancelledError` catch), emits shutdown summary (uptime, request totals, session count, drops), and sets `lifetime_seconds`. The broad `except Exception: pass` on the summary block is justified: shutdown must never raise hiding cancellation. The Starlette lifespan `_lifespan` (line 291-307) guarantees `aclose()` is called via `finally`.

### F-8: Heartbeat Task Lifecycle ✅
**Severity:** Low (observation)

The heartbeat (`_heartbeat()`, line 482-496) runs every 30 seconds. Each tick is individually wrapped in `try/except Exception: pass`, so a single tick failure cannot kill the loop. The task is created at init and in the lifespan, and cancelled in `aclose()`. No leaked task risk.

### F-9: stdio Broken Pipe → Clean Exit ✅
**Severity:** N/A (PASS)

`run_stdio_async()` (line 278-289) catches `BrokenPipeError` on stdout writes and exits with code 0. The `_record()` method (line 54-66) is called before the write attempt, so metrics are captured even on pipe failure. The `_CappedLineReader` (line 152-224) bounds reads to `MAX_LINE_BYTES + 2` and drains overlong lines in bounded chunks — no OOM on malicious input.

### F-10: POST Body Read Is Bounded ✅
**Severity:** N/A (PASS)

`_read_limited_json()` (line 628-644) streams the body incrementally (`async for chunk in request.stream()`) and rejects at `MAX_BODY_BYTES` (SSRF_MAX_BODY). The read happens **outside** the POST semaphore slot (line 569-573), so a slow sender doesn't hold concurrency budget. Correct.

### F-11: Metrics `sum()` Narrow Catch ✅
**Severity:** Low (observation)

`MetricsRegistry.sum()` (line 221-239) uses `try/except (TypeError, ValueError): continue` per entry. This is narrower than bare `except Exception` — it only skips genuinely un-sumable values (dicts, non-numeric). If the internal data structure is corrupted (unexpected type), the exception propagates. This is acceptable for a shutdown-summary utility.

### F-12: `discovery_duration_seconds` Observation ✅
**Severity:** N/A (PASS)

`discover_tools()` (line 329-341) observes the metric in a `finally` block with `try/except Exception: pass`. The metric is optional (requires `metrics` injection). When absent (CLI path), it's a no-op. When present (serve-plane), it always fires regardless of success/failure/timeout. Correct.

## Conditions

None. All HARD constraints from the spec are met:

- **HARD: `session.call_tool` never retried** — verified (F-2).
- **HARD: metrics never break request path** — verified (F-1).
- **HARD: local-first gating intact** — no changes to `serve` host binding, SSRF port, or allow-list env names.
- **HARD: zero new prod deps** — all changes use stdlib `threading`, `asyncio`, `logging`, `time` + existing `MetricsRegistry`.

## Summary

FEAT-007 introduces well-scoped resilience hardening:

| Area | Pattern | Verdict |
|---|---|---|
| Transport retry | Opt-in, bounded (N=1), transport-phase only, `call_tool` excluded | ✅ |
| Metrics isolation | Broad except on every telemetry call, request path untouched | ✅ |
| Cardinality bound | 200-cap + `_other` coalescing, lock-held atomic | ✅ |
| Resource cleanup | AsyncExitStack properly closed, SSE sessions popped on disconnect, heartbeat cancelled on shutdown | ✅ |
| Timeout handling | All external I/O has per-config timeout; POST body + semaphore acquire bounded | ✅ |
| Graceful degradation | Broken servers logged + counted (BR-114), not silently swallowed | ✅ |
| Shutdown | aclose() cancels tasks + emits summary; lifespan guarantees cleanup | ✅ |

The implementation follows the ADR faithfully. Retry is correctly scoped to the transport handshake (the non-idempotent-safe boundary), metrics are fire-and-forget, and cardinality is memory-bounded. No resilience gaps that would block APPROVE.
