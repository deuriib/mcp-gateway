# QA Review — FEAT-007 Observability/Resilience Hardening

**Reviewer**: QA (quality-gate)
**Date**: 2026-09-15
**Spec**: docs/specs/50_archive/feat-007-observability-hardening/spec.md
**Acceptance**: docs/specs/50_archive/feat-007-observability-hardening/acceptance.md
**Test file**: 	ests/test_obsfeat007.py (19 test functions, AC-001..AC-018)

## Verdict: ❌ REJECTED

**Rationale**: 10 of 19 tests FAIL (53% failure rate). Root causes are systemic test infrastructure bugs (non-callable mock, sync/async mismatch, wrong patch target, path misalignment). The tests do NOT validate the actual production behavior for AC-002, AC-004, AC-005, AC-006, AC-012, AC-013–AC-016, AC-017. Additionally, BR-104 (SSE disconnect WARN log) is missing from both implementation and test.

## Test Matrix

| AC | Test | Verdict | Root Cause |
|----|------|---------|------------|
| AC-001 | test_ac001_process_and_build_metrics_present | ✅ PASS | — |
| AC-002 | test_ac002_uptime_advances_with_heartbeat | ❌ FAIL | 	ime.monotonic() delta is 0.0 on fast Windows execution; irst > 0.0 too strict |
| AC-003 | test_ac003_cardinality_cap_overflows_to_other | ✅ PASS | — |
| AC-004 | test_ac004_discovery_observed_ok_and_error | ❌ FAIL | _FlakyCM instance patched in place of callable; create_client_transport(config) raises TypeError → status="error" recorded instead of "ok" |
| AC-005 | test_ac005_sse_disconnect_counted | ❌ FAIL | TestClient.stream("GET","/mcp") hangs indefinitely on Windows (timeout at 60s+) |
| AC-006 | test_ac006_aclose_emits_shutdown_summary | ❌ FAIL | gw.aclose() is sync def but called synchronously; coroutine never awaited (RuntimeWarning confirms) |
| AC-007 | test_ac007_slow_request_warns | ✅ PASS | — |
| AC-008 | test_ac008_stdio_request_metrics_recorded | ✅ PASS | — |
| AC-009 | test_ac009_stdio_access_log_json | ✅ PASS | — |
| AC-010 | test_ac010_cli_info_silent_without_env | ✅ PASS | — |
| AC-010 | test_ac010b_cli_info_emitted_with_env | ✅ PASS | — |
| AC-011 | test_ac011_cli_warning_always_emitted | ✅ PASS | — |
| AC-012 | test_ac012_banner_shows_degraded_hint | ❌ FAIL | _broken_registry creates files at 	mp_path/servers/, but --registry-dir tmp_path uses 	mp_path as servers_dir directly → 0 servers found |
| AC-013 | test_ac013_upstream_tool_ok_and_error | ❌ FAIL | _FlakyCM instance not callable (same as AC-004); patch path mcp_gway.core.create_client_transport correct but target not callable |
| AC-014 | test_ac014_transport_retry_accepted_when_flagged | ❌ FAIL | _FlakyCM instance not callable |
| AC-015 | test_ac015_no_retry_after_call_tool | ❌ FAIL | _FlakyCM instance not callable |
| AC-016 | test_ac016_retry_off_by_default | ❌ FAIL | _FlakyCM instance not callable |
| AC-017 | test_ac017_code_mode_skip_recorded | ❌ FAIL | CodeMode has no make_server_struct attr; method lives on ServerFactory |
| AC-018 | test_ac018_no_new_prod_dependencies | ✅ PASS | — |

**Score**: 9 PASS / 10 FAIL = 47% pass rate

## Root Cause Analysis

### RC-1: _FlakyCM not callable (5 tests: AC-004, AC-013, AC-014, AC-015, AC-016)

**Systemic issue**: _FlakyCM is an async context manager class. Tests patch create_client_transport with an _instance_ (cm = _FlakyCM()). But both discover_tools and ServerFactory._call_tool_async do create_client_transport(config) — they CALL the patched value expecting it to be a callable returning an async context manager.

An _FlakyCM instance is not callable (no __call__). This raises TypeError: '_FlakyCM' object is not callable, caught by the broad xcept Exception in both discover_tools and _call_tool_async, resulting in status="error" instead of the expected behavior.

**Impact**: AC-004 records status="error" instead of status="ok" because the transport creation fails at the call level. AC-013–AC-016 never test retry behavior at all — they all fail with TypeError before reaching the retry logic.

**Fix**: Add __call__ to _FlakyCM:
`python
def __call__(self, *args, **kwargs):
    return self
`
Or replace patch with a factory function:
`python
def _transport_factory(*args, **kwargs):
    return _FlakyCM(fails=fails)
monkeypatch.setattr("mcp_gway.core.create_client_transport", _transport_factory)
`

### RC-2: Sync/async mismatch in AC-006

gw.aclose() is declared sync def (gateway.py:338). The test calls it synchronously in a sync test function. The coroutine object is created but never awaited. RuntimeWarning: "coroutine 'Gateway.aclose' was never awaited".

**Fix**: Either make test async and wait gw.aclose(), or wrap in syncio.run().

### RC-3: Registry path misalignment in AC-012

_broken_registry(tmp_path) creates 	mp_path / "servers" / "brokensrv.pyi". But serve --registry-dir tmp_path resolves servers_dir = Path(tmp_path) (cli.py:471-474). The registry at 	mp_path finds no .pyi files (they're at 	mp_path/servers/), so 
 = 0 → "no servers yet" instead of the degraded banner.

**Fix**: Either change _broken_registry to create files directly in 	mp_path, or pass str(tmp_path / "servers") as --registry-dir.

### RC-4: Wrong monkeypatch target in AC-017

Test patches CodeMode.make_server_struct but this attribute doesn't exist on CodeMode. The method lives on ServerFactory (server_factory.py:153). CodeMode._inject_tools calls self.server_factory.make_server_struct(server_name) (code_mode.py:78).

**Fix**: Patch ServerFactory.make_server_struct instead.

### RC-5: Time resolution in AC-002

On Windows, 	ime.monotonic() can return the same value for both Gateway.__init__ and the first heartbeat tick when execution is fast. The assertion irst > 0.0 is too strict — should be >= 0.0 or add a small sleep.

### RC-6: TestClient SSE hang in AC-005

TestClient.stream("GET", "/mcp") with SSE hangs indefinitely on Windows. The testclient's context manager doesn't properly close the SSE stream, causing the test to never complete.

**Fix**: Use httpx.AsyncClient with a real test server, or mock the SSE endpoint, or add a timeout with pytest-timeout.

## Findings

### F-1: Implementation Gap — BR-104 SSE Disconnect WARN Log (Severity: HIGH)

**Spec**: BR-104 requires gateway_sse_disconnects_total{reason=...} **+ WARN log on stream break**.
**Implementation**: gateway.py:548-553 only does metrics.inc("gateway_sse_disconnects_total", {"reason": reason}). There is **no WARN log** emitted.

Neither the test nor the implementation covers the WARN requirement of BR-104.

### F-2: Implementation Gap — TimeoutError Classification (Severity: MEDIUM)

**Spec**: BR-111 requires TimeoutError classified as status=timeout.
**Implementation**: server_factory.py:133 correctly does status = "timeout" if isinstance(exc, TimeoutError) else "error".
**Test gap**: AC-013 only tests ok (ConnectionError) and rror (ConnectionError). There is **no test for TimeoutError → 	imeout** classification.

### F-3: Known Dead Code — AC-004 Production Path (Severity: HIGH)

Confirmed from refuter review: discover_tools in client.py:283-341 accepts metrics: object | None = None, but **no production caller passes metrics=**. The efresh CLI command (cli.py:680-684) calls efresh_server(config, server_name, auth, oauth_port) which calls discover_tools(cfg, force_auth=False, metrics=metrics) — but metrics defaults to None since efresh_server doesn't receive one either.

The discovery_duration_seconds metric is dead code in production. It can only be observed via the injected test in AC-004 (which itself doesn't work due to RC-1).

### F-4: Missing Edge Case Tests

| Edge Case (from spec) | Status |
|----------------------|--------|
| 201 label combos → 200 + _other, sum preserved | ✅ Tested (AC-003) |
| Retry on: transport fail once then ok → success + retries_total +1 | ❌ Not tested (AC-014 fails with RC-1) |
| Retry on: call_tool raises → no retry | ❌ Not tested (AC-015 fails with RC-1) |
| TimeoutError → status 	imeout | ❌ Not tested (no AC covers this) |
| stdio broken pipe → exit-0 path + metrics before exit | ❌ Not tested |
| CLI env unset → no INFO JSON; WARN/ERROR unaffected | ✅ Tested (AC-010/AC-011) |
| Banner 0 servers → "no servers yet"; N servers with 0 tools → degraded hint | ❌ Not tested (AC-012 fails with RC-3) |
| Shutdown with zero requests → summary logs with 0s | ❌ Not tested (AC-006 fails with RC-2) |
| Cardinality overflow concurrent writers → lock-held, atomic | ❌ Not tested (single-threaded only) |
| discovery_duration_seconds with registry absent → no-op | ❌ Not tested |

### F-5: No CLI Exit Code Assertions (Severity: LOW)

BR-109 specifies exit codes 0/1/2/130 preserved. AC-011 test asserts xit 1 indirectly (via CliRunner result.exit_code) but only checks the WARNING log, not the exit code value.

### F-6: AC-010 Test is Unit-Level, Not Integration

AC-010 tests _log_cli_event directly rather than the CLI dd command end-to-end. The acceptance scenario says "Given CLI dd succeeds in both states" but the test calls _log_cli_event directly.

## Conditions

This gate is **REJECTED** with the following required fixes before re-gate:

### P0 (Must Fix — blocks approval)

1. **Fix _FlakyCM mock** (RC-1): Add __call__ or replace patches with factory functions. Affects 5 tests (AC-004, AC-013–AC-016).
2. **Fix close() async call** (RC-2): Wrap in syncio.run() or make test async. Affects AC-006.
3. **Fix _broken_registry path** (RC-3): Align --registry-dir with where .pyi files are created. Affects AC-012.
4. **Fix monkeypatch target** (RC-4): Patch ServerFactory.make_server_struct not CodeMode.make_server_struct. Affects AC-017.

### P1 (Should Fix — before quality gate re-run)

5. **Add TimeoutError classification test**: New test for TimeoutError → status=timeout in _call_tool_async. Covers BR-111.
6. **Fix AC-002 assertion**: Change > 0.0 to >= 0.0 or add 	ime.sleep(0.01) before heartbeat.
7. **Fix AC-005 SSE hang**: Use mock/async test approach for SSE disconnect detection.
8. **Add BR-104 WARN log** in implementation (gateway.py event_stream finally block) and test for it.

### P2 (Nice to Have — documented as gaps)

9. Document discovery_duration_seconds dead code path — either wire production callers or mark as test-only diagnostic.
10. Add concurrent cardinality overflow test for MetricsRegistry.
11. Add stdio broken pipe test.
12. Add shutdown-with-zero-requests test.

## Execution Evidence

`
Test batch 1 (AC-001,003,007,008,009,010,010b,011,018): 9 passed in 4.28s
Test batch 2 (AC-012,013,014,015,016,017,018): 1 passed, 6 failed in 4.28s
AC-002: 1 failed — assert 0.0 > 0.0
AC-004: 1 failed — assert 0 == 1 (status=error instead of ok)
AC-005: TIMEOUT (hung >60s)
AC-006: 1 failed — RuntimeError: coroutine never awaited
Total: 9 pass / 10 fail = 47% pass rate
`

## Summary

The test suite has the **right intent** (18 ACs mapped to 19 tests with clear traceability) but suffers from **systemic test infrastructure bugs** that prevent 53% of tests from validating actual behavior. The _FlakyCM non-callable issue alone blocks 5 tests spanning the critical retry and upstream telemetry paths (AC-013–AC-016). Additionally, one implementation gap (missing BR-104 WARN log) and one dead-code path (discovery_duration_seconds with no production caller) require attention.

**This gate cannot CLOSE until P0 items are fixed and all 19 tests pass.**
