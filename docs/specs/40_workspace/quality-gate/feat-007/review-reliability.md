# Reliability Review — FEAT-007

## Verdict: ✅ APPROVED

The implementation is correct, well-structured, and faithfully honors the spec and
ADR contracts. All 18 acceptance criteria have corresponding tests. The retry
guarantee (never retry after `session.call_tool`) is properly enforced.
Cardinality is bounded. Telemetry never breaks the request path. No new production
dependencies.

The findings below are Medium/Low severity — none blocks approval.

---

## Findings

### F-1 (Medium) — `code_mode.refresh()` second loop is dead code

**File:** `src/mcp_gway/code_mode.py:113`

```python
for name in list(known & set(self.registry.list()) - current):
    self.sandbox._modules.pop(name, None)
```

**Root cause (set algebra):** Due to operator precedence, `-` binds tighter than
`&`, so this evaluates as `known & (registry - current)`. However, the first loop
(`known - current`) already removes every module not in `current` — including any
that might also be in the registry. The second loop is therefore redundant: it
pops names that were already popped by the first loop, or pops nothing new.

**Practical impact:** None in current usage — the loop is a harmless no-op. But it
misleads future maintainers into thinking a distinct cleanup path exists here.

**Fix:** Remove lines 113-114 entirely, or rewrite as
`for name in list((known & set(self.registry.list())) - current):` if the intent
was to keep servers in the sandbox that are in the registry but dropped from
current (which the first loop already handles).

---

### F-2 (Medium) — `_call_tool_async` retries `_setup` as a unit: transport AND initialize

**File:** `src/mcp_gway/server_factory.py:101-124`

The `_setup` coroutine bundles `create_client_transport` AND
`ClientSession.__aenter__` + `session.initialize()`. When retry fires, both are
retried as a unit.

**ADR-012 wording (Decision 9):** "exactly one retry, **only** when the failure
happens in the transport/connect/initialize phase." This is satisfied — the ADR
explicitly includes "initialize" in the retry-eligible window. However, if a
future change splits `_setup` or if `session.initialize()` starts doing
side-effectful work (e.g., registering event handlers), the retry boundary
leaks.

**Risk:** Low today. The retry boundary is correct per current ADR, but the
co-location of transport+initialize in one retryable unit is a coupling that
deserves a comment clarifying the deliberate design.

---

### F-3 (Medium) — Missing test: `TimeoutError` classified as `timeout` (not `error`)

**File:** `tests/test_obsfeat007.py`

AC-013 tests `ok` and `error` status. AC-016 tests retry-off-by-default. But no
test exercises the `TimeoutError -> status="timeout"` branch in
`server_factory.py:133`. The code is correct (`isinstance(exc, TimeoutError)`
catches the right class), but the classification path is unproven.

**Evidence:** `test_ac013_upstream_tool_ok_and_error` uses `ConnectionError` for
the error path. No test raises `TimeoutError` from `_setup` or `call_tool`.

**Suggested test:** A `_FlakyCM` or `_FakeSession` that raises `TimeoutError`
during transport phase, asserting `upstream_tool_calls_total{status="timeout"}`.

---

### F-4 (Low) — Retry double-counts `upstream_tool_calls_total` across attempts

**File:** `src/mcp_gway/server_factory.py:136-148`

When a retry occurs, the `finally` block fires after the first failed attempt
(once for each attempt). Each attempt increments `upstream_tool_calls_total` with
its own status: first `error`, then `ok`. For Prometheus scrapes between the two
attempts, the intermediate `error` count is visible — this is expected behavior
for counters, not a bug. But operators should know that a retried call appears as
**two** series increments, not one with a `retried` label.

**Impact:** Informational. Metrics are correct per Prometheus counter semantics.

---

### F-5 (Low) — Private attribute injection pattern (`_metrics`) is fragile

**File:** `src/mcp_gway/gateway.py:265-277`

```python
registry._metrics = self.metrics          # type: ignore[attr-defined]
self.code_mode.sandbox._metrics = self.metrics  # type: ignore[attr-defined]
self.code_mode.server_factory._metrics = self.metrics  # type: ignore[attr-defined]
```

The `type: ignore[attr-defined]` suppressions confirm these are private
attributes accessed from outside the class. If any of `Registry`,
`StarlarkSandbox`, or `ServerFactory` renames `_metrics`, the injection silently
fails (caught by bare `except: pass`). The `getattr` reads in consumers
(`code_mode.py:97`, `server_factory.py:94`) degrade gracefully to `None`, so
telemetry is lost but the request path is unbroken.

**Impact:** Low — the coupling is localized to `Gateway.__init__` and the
`_record_skip` / `_call_tool_async` consumers. A shared Protocol or constructor
parameter would be cleaner but violates the "additive only" constraint.

---

### F-6 (Low) — `MetricsRegistry.sum()` silently skips histogram entries

**File:** `src/mcp_gway/observability/metrics.py:221-239`

The `sum()` method iterates `data.values()` and skips `dict` payloads (histograms).
This is correct for `http_requests_total` (counter) and `gateway_sse_dropped_total`
(counter). But if a caller passes a histogram name, they get `0.0` with no
indication the metric type was wrong.

**Impact:** No current caller passes a histogram name to `sum()`. The behavior is
documented in the docstring. Defensive, not a bug.

---

### F-7 (Low) — `stdio.py` generates a fresh `request_id` per line, not correlated to JSON-RPC `id`

**File:** `src/mcp_gway/stdio.py:109`

```python
request_id = uuid.uuid4().hex
```

This is the stdio access-log correlation ID, unrelated to the JSON-RPC `id`
field (which is the client-assigned request identifier). The naming could confuse
operators grepping for `request_id` across stdio and HTTP logs.

**Impact:** Informational — the HTTP path uses `X-Request-ID` header correlation;
the stdio path generates its own. Both flow through `JSONFormatter` correctly.

---

## Test Coverage Assessment

| AC    | Test                                    | Verdict |
|-------|-----------------------------------------|---------|
| AC-001| test_ac001_process_and_build_metrics    | Pass    |
| AC-002| test_ac002_uptime_advances              | Pass    |
| AC-003| test_ac003_cardinality_cap              | Pass    |
| AC-004| test_ac004_discovery_observed           | Pass    |
| AC-005| test_ac005_sse_disconnect_counted       | Pass    |
| AC-006| test_ac006_aclose_shutdown_summary      | Pass    |
| AC-007| test_ac007_slow_request_warns           | Pass    |
| AC-008| test_ac008_stdio_request_metrics        | Pass    |
| AC-009| test_ac009_stdio_access_log_json        | Pass    |
| AC-010| test_ac010_cli_info_silent / _emitted   | Pass    |
| AC-011| test_ac011_cli_warning_always           | Pass    |
| AC-012| test_ac012_banner_degraded              | Pass    |
| AC-013| test_ac013_upstream_ok_and_error        | Pass    |
| AC-014| test_ac014_transport_retry_accepted     | Pass    |
| AC-015| test_ac015_no_retry_after_call_tool     | Pass    |
| AC-016| test_ac016_retry_off_by_default         | Pass    |
| AC-017| test_ac017_code_mode_skip_recorded      | Pass    |
| AC-018| test_ac018_no_new_prod_dependencies     | Pass    |

**Missing coverage (non-blocking):**
- TimeoutError -> `status="timeout"` classification (F-3)
- MetricsRegistry exception in gateway request path (broad `except` proven by code
  inspection, no test)
- `code_mode.refresh()` with a server in `known` but removed from registry while
  still in `current` (F-1 edge)

---

## Contract Compliance

| Contract                              | Status | Evidence                           |
|---------------------------------------|--------|------------------------------------|
| BR-112: never retry after call_tool  | Pass   | AC-015, `server_factory.py:125-128`|
| BR-115: retry default off            | Pass   | AC-016, `models.py:720`            |
| BR-116: zero new prod deps           | Pass   | AC-18, `pyproject.toml` inspection |
| MCP/SSE JSON-RPC unchanged           | Pass   | No handler signature changes       |
| Local-first gating intact            | Pass   | `serve` binds 127.0.0.1 default    |
| Metrics never break request path     | Pass   | All metric blocks wrapped in try/  |
|                                       |        | except with broad catch            |
| Cardinality cap = 200                | Pass   | AC-003, `_bounded_key` + tests     |
