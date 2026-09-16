# Refuter Review — FEAT-007

## Verdict: ✅ CONFIRMED (17/18) | ⚠️ PARTIALLY_REFUTED (1/18)

One claim has a genuine code-path gap; the remaining 17 are verified against live code with no counterexamples found.

---

## Claims Verified

### AC-001 ✅ process/build metrics registered
- **Evidence**: `gateway.py:225-232` — `process_start_time_seconds` gauge set to `time.time()`, `build_info` counter incremented with `__version__`.
- **Code path**: Gateway `__init__` → `self.metrics.set("process_start_time_seconds", time.time(), {})` and `self.metrics.inc("build_info", {"version": __version__})`.

### AC-002 ✅ `uptime_seconds` updated every 30s via `_heartbeat`
- **Evidence**: `gateway.py:482-496` — `_heartbeat()` runs `while True`, calls `self.metrics.set("uptime_seconds", time.monotonic() - self.start_time, {})`, then `await asyncio.sleep(30)`.
- **Code path**: Started from `__init__` (line 334) and lifespan (line 299-301).

### AC-003 ✅ label-cardinality cap `_MAX_LABEL_COMBOS=200` with `_bounded_key`
- **Evidence**: `metrics.py:12` — `_MAX_LABEL_COMBOS = 200`. `metrics.py:202-219` — `_bounded_key()` checks `key not in data and len(data) >= _MAX_LABEL_COMBOS`, returns `("_other",) * len(meta["labelnames"])`.
- **Test**: `test_obsfeat007.py:167-176` — 205 distinct labels → 201 series (200 + `_other`), overflow count = 5.

### AC-005 ✅ SSE disconnects counted by reason
- **Evidence**: `gateway.py:237-240` — metric registered with `["reason"]` labels. `gateway.py:514-553` — `event_stream()` sets reason to `"client_disconnect"` (default, CancelledError, GeneratorExit), `"idle"` (TimeoutError, None message), or `"error"` (generic Exception). `finally` block increments `gateway_sse_disconnects_total{reason}`.
- **Test**: `test_obsfeat007.py:237-247` — SSE stream disconnect counts ≥ 1.

### AC-006 ✅ `aclose()` sets `lifetime_seconds` + emits JSON shutdown summary
- **Evidence**: `gateway.py:338-365` — `aclose()` sets `self.metrics.set("lifetime_seconds", uptime, {})` and logs `{"uptime_seconds": ..., "http_requests_total": ..., "sessions_active": ..., "sse_dropped_total": ...}` via `logging.getLogger("mcp_gway.gateway").info("gateway shutdown summary", extra=summary)`.
- **Test**: `test_obsfeat007.py:250-266` — verifies shutdown summary record fields and JSON payload.

### AC-007 ✅ slow-request WARN at 1000ms threshold
- **Evidence**: `middleware.py:20` — `_SLOW_REQUEST_THRESHOLD_MS = 1000`. `middleware.py:117-118` — `if duration_ms > _SLOW_REQUEST_THRESHOLD_MS: logger.warning("slow request", extra=extra)`.
- **Test**: `test_obsfeat007.py:274-284` — monkeypatches threshold to -1, verifies WARN emitted.

### AC-008 ✅ stdio per-request metrics + JSON access log with `transport:"stdio"`
- **Evidence**: `stdio.py:54-66` — `_record()` increments `stdio_requests_total{method,status}` and observes `stdio_request_duration_seconds{method}`. `stdio.py:68-81` — `_log_access()` logs with `extra={"request_id": ..., "transport": "stdio", "path": "stdio", ...}`. Both called from `handle_line()` at lines 129-130, 134-135, 141-142, 145-146.
- **Test**: `test_obsfeat007.py:292-331` — stdio metrics recorded for `tools_call` and `notifications_initialized`.

### AC-009 ✅ stdio `request_id` via uuid4
- **Evidence**: `stdio.py:109` — `request_id = uuid.uuid4().hex`.
- **Test**: `test_obsfeat007.py:334-352` — verifies `request_id` present in JSON access log payload.

### AC-010 ✅ `_log_cli_event()` helper with structured JSON
- **Evidence**: `cli.py:38-71` — helper accepts `action, status, *, server, duration_ms, detail, exc_info`. Builds structured `extra` dict. WARNING/ERROR always emitted; INFO gated by `MCP_GWAY_LOG_LEVEL` env var.
- **Test**: `test_obsfeat007.py:360-386` — verifies silent without env, emitted with env, warning always emitted.

### AC-011 ✅ add success + refresh per-server outcomes logged
- **Evidence**: `cli.py:289-295` — add success: `_log_cli_event("add", "success", server=name, ...)`. `cli.py:687-716` — refresh per-server: error (line 687), warning/no-tools (line 699), success (line 710).

### AC-012 ✅ serve banner shows `no_tools` count + degraded hint
- **Evidence**: `cli.py:496-497` — `no_tools = max(0, n - loaded_tools)` where `loaded_tools = len(getattr(gateway.code_mode.sandbox, "_modules", {}))`. `cli.py:522-528` — banner shows `{no_tools} server(s) with no tools` with degraded styling.
- **Test**: `test_obsfeat007.py:394-406` — broken registry triggers degraded banner.

### AC-013 ✅ `upstream_tool_calls_total{server,tool,status}` with `timeout` classification
- **Evidence**: `gateway.py:243-247` — metric registered with `["server", "tool", "status"]`. `server_factory.py:132-133` — `status = "timeout" if isinstance(exc, TimeoutError) else "error"`. `server_factory.py:138-141` — `metrics.inc("upstream_tool_calls_total", {"server": server, "tool": tool_label, "status": status})`.
- **Test**: `test_obsfeat007.py:458-501` — upstream ok and error both recorded.

### AC-014 ✅ `upstream_tool_duration_seconds{server,tool}`
- **Evidence**: `gateway.py:248-252` — metric registered with `["server", "tool"]` labels. `server_factory.py:142-146` — `metrics.observe("upstream_tool_duration_seconds", time.perf_counter() - start, {"server": server, "tool": tool_label})`.
- **Test**: `test_obsfeat007.py:458-486` — duration histogram observed for upstream call.

### AC-015 ✅ `session.call_tool` is NEVER retried — only transport+initialize
- **Evidence**: `server_factory.py:101-127` — retry block wraps only `_setup(stack)` (transport + `session.initialize()`). `session.call_tool(tool_name, arguments)` runs at line 125-126 AFTER the retry window. If `call_tool` fails, it hits the `except BaseException` at line 132 which sets status and re-raises — no retry.
- **Test**: `test_obsfeat007.py:534-561` — `session.call_count == 1` after failure, `upstream_retries_total == 0`.

### AC-016 ✅ `--retry-on-transport-error` default OFF
- **Evidence**: `cli.py:107-112` — `is_flag=True, default=False`. `models.py:720` — `retry_on_transport_error: bool = False`. `server_factory.py:119` — `if not getattr(config, "retry_on_transport_error", False): raise`.
- **Test**: `test_obsfeat007.py:564-574` — default config → `cm.enters == 1` (no retry), `upstream_retries_total == 0`.

### AC-017 ✅ `code_mode_servers_skipped_total{reason}` + WARN
- **Evidence**: `gateway.py:258-262` — metric registered with `["reason"]`. `code_mode.py:83-105` — `_record_skip()` emits `logging.warning("code mode server skipped", extra={...})` and `metrics.inc("code_mode_servers_skipped_total", {"reason": "inject_error"})`. Called from `_inject_tools()` (line 81) and `refresh()` (line 120).
- **Test**: `test_obsfeat007.py:409-437` — broken injection emits WARN + metric.

### AC-018 ✅ `_bounded_key` coalesces overflow to `_other` label
- **Evidence**: `metrics.py:202-219` — when `key not in data and len(data) >= _MAX_LABEL_COMBOS`, returns `("_other",) * len(meta["labelnames"])`. Applied in all write paths: `inc` (line 136), `set` (line 155), `observe` (line 176).
- **Note**: The test numbered `test_ac018` (line 582-595) tests "no new production dependencies" rather than `_bounded_key`. The `_bounded_key` behavior is tested by `test_ac003` (line 167-176). This is a numbering inconsistency in the test file, not a code gap.

---

## Claims Refuted

### AC-004 ⚠️ `discovery_duration_seconds{server,status}` observed in `discover_tools`/`refresh_server`

**Verdict: PARTIALLY_REFUTED — observation code exists but is dead in all production paths**

The metric is registered (`gateway.py:196-198`) and `discover_tools()` contains the observation code (`core/client.py:324-341`). However, **no production caller passes `metrics=` to `discover_tools` or `refresh_server`**, making the observation unreachable in live operation.

**Evidence of the gap:**

1. **CLI `add` command** (`cli.py:238`): `discovered = asyncio.run(discover_tools(config))` — no `metrics=` kwarg. The `metrics` parameter defaults to `None`, so the `finally` block at `client.py:329` skips observation (`if metrics is not None:` → False).

2. **CLI `add` after OAuth** (`cli.py:271`): `discovered = asyncio.run(discover_tools(config, force_auth=True))` — no `metrics=`.

3. **CLI `refresh` command** (`cli.py:682-683`):
   ```python
   discovered = asyncio.run(
       refresh_server(config, server_name, auth, oauth_port)
   )
   ```
   `refresh_server` signature (`client.py:344-349`): `metrics: object | None = None`. Since `metrics` is not passed, it defaults to `None`.

4. **`refresh_server` internal retry path** (`client.py:385`): Even if `metrics` were passed to `refresh_server`, the OAuth retry path calls `discover_tools(cfg, force_auth=True)` **without** forwarding `metrics`:
   ```python
   discovered = await discover_tools(cfg, force_auth=True)  # metrics= dropped!
   ```

5. **Gateway serving path**: `discover_tools` is never called from `gateway.py`. The `code_mode.refresh()` path (`gateway.py:283-284`) calls `make_server_struct()`, not `discover_tools()`.

**Impact**: `discovery_duration_seconds` is pre-registered for exposition stability but **always shows zero/count 0** in `/metrics`. The observation code is unreachable dead code.

**Counterexample (disproof)**: Start the gateway, run `mcp-gway refresh <server>`, query `/metrics` — `discovery_duration_seconds_count` remains 0 regardless of how many discovery operations occurred.

**Recommendation**: Either (a) pass `metrics=self.metrics` from CLI refresh/add paths, or (b) remove the pre-registration and observation code to avoid misleading operators who expect this metric to be populated.

---

## Summary Table

| AC | Claim | Verdict | Evidence |
|----|-------|---------|----------|
| AC-001 | process/build metrics registered | ✅ CONFIRMED | `gateway.py:225-232` |
| AC-002 | uptime_seconds updated every 30s | ✅ CONFIRMED | `gateway.py:482-496` |
| AC-003 | label-cardinality cap 200 | ✅ CONFIRMED | `metrics.py:12,202-219` |
| AC-004 | discovery_duration_seconds observed | ⚠️ PARTIALLY_REFUTED | Dead code — no caller passes `metrics=` |
| AC-005 | SSE disconnects by reason | ✅ CONFIRMED | `gateway.py:514-553` |
| AC-006 | aclose shutdown summary | ✅ CONFIRMED | `gateway.py:338-365` |
| AC-007 | slow-request 1000ms threshold | ✅ CONFIRMED | `middleware.py:20,117-118` |
| AC-008 | stdio per-request metrics | ✅ CONFIRMED | `stdio.py:54-81` |
| AC-009 | stdio request_id via uuid4 | ✅ CONFIRMED | `stdio.py:109` |
| AC-010 | _log_cli_event helper | ✅ CONFIRMED | `cli.py:38-71` |
| AC-011 | add/refresh outcomes logged | ✅ CONFIRMED | `cli.py:289-295,687-716` |
| AC-012 | degraded banner | ✅ CONFIRMED | `cli.py:496-528` |
| AC-013 | upstream tool calls + timeout | ✅ CONFIRMED | `server_factory.py:132-141` |
| AC-014 | upstream tool duration | ✅ CONFIRMED | `server_factory.py:142-146` |
| AC-015 | call_tool never retried | ✅ CONFIRMED | `server_factory.py:116-127` |
| AC-016 | retry default OFF | ✅ CONFIRMED | `cli.py:107-112`, `models.py:720` |
| AC-017 | skipped servers + WARN | ✅ CONFIRMED | `code_mode.py:83-105` |
| AC-018 | _bounded_key → _other | ✅ CONFIRMED | `metrics.py:202-219` |
