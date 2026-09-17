# QA Re-Review — FEAT-007 (Round 2)

**Reviewer**: QA (quality-gate)
**Date**: 2026-09-15
**Spec**: docs/specs/50_archive/feat-007-observability-hardening/spec.md
**Test file**: tests/test_obsfeat007.py (19 test functions, AC-001..AC-018)
**Round 1**: qa-review.md (REJECTED — 9 pass / 10 fail = 47%)

## Verdict: ❌ REJECTED

**Rationale**: The 4 stated fixes are verified as present in source. Three of them (RC-2, RC-5, F-1) resolve cleanly. However, RC-1 fix was necessary but **not sufficient** — it resolved AC-004 and AC-016 but exposed a systemic sibling bug (RC-7: `_FakeSession` not callable) that blocks AC-013, AC-014, AC-015. Additionally, three original P0 issues (RC-3, RC-4, RC-6) remain completely unfixed. **13 PASS / 1 HANG / 5 FAIL = 68%** (improved from 47% but still failing gate threshold).

## Test Matrix

| AC | Test | R1 | R2 | Status | Root Cause |
|----|------|----|----|--------|------------|
| AC-001 | test_ac001_process_and_build_metrics_present | ✅ | ✅ | FIXED | — |
| AC-002 | test_ac002_uptime_advances_with_heartbeat | ❌ | ✅ | **RC-5 FIXED** | `>= 0.0` handles Windows fast execution |
| AC-003 | test_ac003_cardinality_cap_overflows_to_other | ✅ | ✅ | FIXED | — |
| AC-004 | test_ac004_discovery_observed_ok_and_error | ❌ | ✅ | **RC-1 FIXED** | `_FlakyCM.__call__` makes instance callable |
| AC-005 | test_ac005_sse_disconnect_counted | ❌ | ❌ HANG | **RC-6 OPEN** | `TestClient.stream("GET","/mcp")` hangs indefinitely on Windows (>30s timeout) |
| AC-006 | test_ac006_aclose_emits_shutdown_summary | ❌ | ✅ | **RC-2 FIXED** | `asyncio.run(gw.aclose())` properly awaits |
| AC-007 | test_ac007_slow_request_warns | ✅ | ✅ | FIXED | — |
| AC-008 | test_ac008_stdio_request_metrics_recorded | ✅ | ✅ | FIXED | — |
| AC-009 | test_ac009_stdio_access_log_json | ✅ | ✅ | FIXED | — |
| AC-010 | test_ac010_cli_info_silent_without_env | ✅ | ✅ | FIXED | — |
| AC-010b | test_ac010b_cli_info_emitted_with_env | ✅ | ✅ | FIXED | — |
| AC-011 | test_ac011_cli_warning_always_emitted | ✅ | ✅ | FIXED | — |
| AC-012 | test_ac012_banner_shows_degraded_hint | ❌ | ❌ | **RC-3 OPEN** | `_broken_registry` creates at `tmp_path/servers/` but CLI uses `tmp_path` as `servers_dir`; `no servers yet` instead of `degraded` |
| AC-013 | test_ac013_upstream_tool_ok_and_error | ❌ | ❌ | **RC-7 NEW** | `_FakeSession` instance patched for `ClientSession` class — not callable. `TypeError: '_FakeSession' object is not callable` at `server_factory.py:110` |
| AC-014 | test_ac014_transport_retry_accepted_when_flagged | ❌ | ❌ | **RC-7 NEW** | Same `_FakeSession` not callable after transport retry succeeds |
| AC-015 | test_ac015_no_retry_after_call_tool | ❌ | ❌ | **RC-7 NEW** | Same `_FakeSession` not callable — `_setup` never reaches `call_tool` |
| AC-016 | test_ac016_retry_off_by_default | ❌ | ✅ | **RC-1 FIXED** | Passes because `ConnectionError` raised before `ClientSession` construction |
| AC-017 | test_ac017_code_mode_skip_recorded | ❌ | ❌ | **RC-4 OPEN** | `monkeypatch.setattr(CodeMode, "make_server_struct", _boom)` — `AttributeError: <class 'CodeMode'> has no attribute 'make_server_struct'` (method lives on `ServerFactory:153`) |
| AC-018 | test_ac018_no_new_prod_dependencies | ✅ | ✅ | FIXED | — |

**Score**: 13 PASS / 1 HANG / 5 FAIL = 68% (was 47%)

## Fix Verification

### RC-1: `_FlakyCM.__call__` ✅ Present, Partially Effective

**Source**: `tests/test_obsfeat007.py:93-95`
```python
def __call__(self, *_a: object, **_k: object) -> "_FlakyCM":
    """Make instance callable — matches create_client_transport(config) signature."""
    return self
```

**Trace**: `create_client_transport(config)` → patched with `_FlakyCM` instance → `__call__` returns `self` → `__aenter__` returns `(read, write)` → ✅ transport phase works.

**Effect**: AC-004 ✅, AC-016 ✅. But AC-013/014/015 still fail because the same test also patches `mcp.ClientSession` with a `_FakeSession` *instance* — and `ClientSession(read, write)` at `server_factory.py:110` tries to call it. The `_FakeSession` class lacks `__call__`.

**Verdict**: Fix is correct for its scope but the test infrastructure has a systemic pattern: mock instances patched in place of class constructors must be callable.

### RC-2: `asyncio.run(gw.aclose())` ✅ Fully Effective

**Source**: `tests/test_obsfeat007.py:260`
```python
asyncio.run(gw.aclose())
```

**Trace**: `gw.aclose()` is `async def` → `asyncio.run()` creates event loop and awaits → shutdown summary emitted → ✅

**Effect**: AC-006 ✅ passes with clean shutdown summary assertion.

### RC-5: `assert first >= 0.0` ✅ Fully Effective

**Source**: `tests/test_obsfeat007.py:160`
```python
assert first >= 0.0, "heartbeat must set uptime_seconds"
```

**Trace**: `_heartbeat()` → `time.monotonic()` delta can be 0.0 on fast Windows → `>= 0.0` accepts zero → ✅

**Effect**: AC-002 ✅ passes.

### F-1: SSE Disconnect WARN Log ✅ Implementation Present

**Source**: `src/mcp_gway/gateway.py:554-557`
```python
logging.getLogger("mcp_gway.gateway").warning(
    "SSE session ended",
    extra={"session_id": session_id, "reason": reason},
)
```

**Trace**: `event_stream()` finally block → `session_id` is in closure scope → `reason` is set by the exception type (idle/client_disconnect/error) → WARN emitted with structured extra fields → ✅

**Note**: WARN log is not wrapped in try/except (unlike the metrics calls above it). If logging itself fails, the exception would propagate. This is acceptable — logging failures should surface, not be swallowed.

**Test coverage**: No dedicated test for the WARN log message. AC-005 (which would test it) hangs due to RC-6. **This is a coverage gap.**

## Remaining Issues

### RC-3: Registry Path Misalignment (AC-012) — OPEN, P0

**Severity**: HIGH
**Root cause**: `_broken_registry(tmp_path)` creates `.pyi`/`.json` at `tmp_path / "servers" /`, but `test_ac012` passes `--registry-dir tmp_path` to the CLI. The CLI resolves `servers_dir = Path(tmp_path)` (`cli.py:471-473`), which means `Registry` looks for `*.pyi` in `tmp_path/` — but files are in `tmp_path/servers/`. Result: 0 servers found → `"no servers yet"` banner instead of `"degraded"`.

**Evidence**: Test output shows `"\n> MCP Gateway v2.2.1  ╖ ready in 15ms\n  Listening on http://127.0.0.1:8080  ╖ no servers yet"` — no "degraded" string.

**Fix**: Change `_broken_registry` to create files directly in `tmp_path` (not `tmp_path / "servers"`), OR change the CLI invocation to `["--registry-dir", str(tmp_path / "servers")]`.

### RC-4: Wrong Monkeypatch Target (AC-017) — OPEN, P0

**Severity**: HIGH
**Root cause**: Test patches `CodeMode.make_server_struct` (`test_obsfeat007.py:429`) but `CodeMode` has no such attribute. The method lives on `ServerFactory` (`server_factory.py:153`). `CodeMode._inject_tools` calls `self.server_factory.make_server_struct(server_name)` (`code_mode.py:78`).

**Evidence**: `E   AttributeError: <class 'mcp_gway.code_mode.CodeMode'> has no attribute 'make_server_struct'`

**Fix**: Change `monkeypatch.setattr(CodeMode, "make_server_struct", _boom)` to `monkeypatch.setattr(ServerFactory, "make_server_struct", _boom)`.

### RC-6: TestClient SSE Hang (AC-005) — OPEN, P0

**Severity**: HIGH
**Root cause**: `TestClient.stream("GET", "/mcp")` with SSE hangs indefinitely on Windows. The Starlette TestClient's context manager doesn't properly close the SSE streaming response.

**Evidence**: Test timed out after 30s with no output. In Round 1, timed out after 60s.

**Fix**: Either (a) use `httpx.AsyncClient` with a real uvicorn test server and explicit timeout, (b) mock the SSE endpoint to not actually stream, or (c) restructure the test to directly verify the metric increment path without going through the full HTTP stack.

### RC-7: `_FakeSession` Not Callable (NEW) — P0

**Severity**: HIGH
**Systemic pattern**: Same class of bug as RC-1. `_FakeSession` is an instance patched in place of `mcp.ClientSession` (a class). Production code at `server_factory.py:110` calls `ClientSession(read, write)`, which tries to call the `_FakeSession` instance → `TypeError`.

**Affected tests**: AC-013, AC-014, AC-015 (3 tests)

**Evidence from AC-015**:
```
src\mcp_gway\server_factory.py:110: in _setup
    session = await stack.enter_async_context(ClientSession(read, write))
TypeError: '_FakeSession' object is not callable
```

**Trace for AC-013**: `_FlakyCM.__call__` succeeds (RC-1 fix works) → transport created → `_FakeSession` patched for `ClientSession` → `ClientSession(read, write)` → TypeError → `status="error"` → test expects `"ok"` → FAIL.

**Trace for AC-014**: Transport fails first attempt (as designed) → retry succeeds → `_FakeSession` → TypeError → FAIL.

**Trace for AC-015**: `_FlakyCM` succeeds → `_FakeSession` → TypeError → FAIL. `call_tool` never runs so we can't verify the no-retry-after-call behavior.

**Fix**: Add `__call__` to `_FakeSession` (same pattern as RC-1 fix):
```python
def __call__(self, *_a: object, **_k: object) -> "_FakeSession":
    """Make instance callable — matches ClientSession(read, write) signature."""
    return self
```

**Why this wasn't caught in RC-1 analysis**: RC-1 masked this. Both `_FlakyCM` and `_FakeSession` had the same non-callable problem. Fixing `_FlakyCM` removed the first barrier, revealing the second. The original QA review noted "53% failure rate" but the root causes were layered — fixing one layer unmasks the next.

### F-2: TimeoutError Classification Not Tested — P1

**Severity**: MEDIUM
**Status**: Unchanged from Round 1. No test for `TimeoutError → status=timeout` classification (`server_factory.py:133`). AC-013 only tests `ConnectionError → error`. Covers BR-111.

### F-3: Dead Code Path (discovery_duration_seconds) — P2

**Severity**: MEDIUM
**Status**: Unchanged from Round 1. `discover_tools()` accepts `metrics=` parameter but no production caller passes it. The `discovery_duration_seconds` metric can only be observed via injected test in AC-004. Document as test-only diagnostic or wire into production callers.

## Execution Evidence

```
R2 Individual Test Runs (Windows, Python 3.12.14):

test_ac001:  ✅ PASS  (0.80s)
test_ac002:  ✅ PASS  (0.90s)   ← was FAIL (RC-5)
test_ac003:  ✅ PASS  (0.15s)
test_ac004:  ✅ PASS  (8.03s)   ← was FAIL (RC-1)
test_ac005:  ❌ HANG  (>30s)    ← still FAIL (RC-6)
test_ac006:  ✅ PASS  (0.85s)   ← was FAIL (RC-2)
test_ac007:  ✅ PASS  (0.80s)
test_ac008:  ✅ PASS  (0.20s)
test_ac009:  ✅ PASS  (0.25s)
test_ac010:  ✅ PASS  (0.15s)
test_ac010b: ✅ PASS  (0.15s)
test_ac011:  ✅ PASS  (0.15s)
test_ac012:  ❌ FAIL  (0.83s)    ← still FAIL (RC-3)
test_ac013:  ❌ FAIL  (8.13s)   ← was FAIL, NEW root cause (RC-7)
test_ac014:  ❌ FAIL  (8.06s)   ← was FAIL, NEW root cause (RC-7)
test_ac015:  ❌ FAIL  (8.13s)   ← was FAIL, NEW root cause (RC-7)
test_ac016:  ✅ PASS  (8.04s)   ← was FAIL (RC-1)
test_ac017:  ❌ FAIL  (1.28s)   ← still FAIL (RC-4)
test_ac018:  ✅ PASS  (0.15s)

Full suite: aborted at test_ac005 (SSE hang blocks subsequent tests)
Score: 13 PASS / 1 HANG / 5 FAIL = 68% pass rate
```

## Conditions for Approval

### P0 (Must Fix — blocks approval)

1. **Fix `_FakeSession.__call__`** (RC-7): Add `__call__` returning self. Affects AC-013, AC-014, AC-015.
2. **Fix `_broken_registry` path** (RC-3): Align file creation with `--registry-dir`. Affects AC-012.
3. **Fix monkeypatch target** (RC-4): Patch `ServerFactory.make_server_struct`, not `CodeMode.make_server_struct`. Affects AC-017.
4. **Fix SSE TestClient hang** (RC-6): Replace `TestClient.stream` with a non-hanging approach. Affects AC-005.
5. **Add WARN log assertion for F-1**: The implementation is correct but no test asserts the `"SSE session ended"` WARN log with `session_id`/`reason` extras. Needs coverage once AC-005 is fixed (or as a separate unit test).

### P1 (Should Fix — before quality gate re-run)

6. **Add TimeoutError classification test** (F-2): New test for `TimeoutError → status=timeout`.
7. **Document discovery_duration_seconds dead code** (F-3): Either wire production callers or mark as test-only.

## Summary

Round 2 shows **incremental progress** (47% → 68%) — 3 of 4 stated fixes work correctly, and the F-1 implementation gap is resolved. However, the fix for RC-1 exposed a systemic sibling issue (RC-7) with the same root cause in a different mock, and 3 of the 4 original P0 items remain unfixed. The test suite still cannot complete its full run (AC-005 SSE hang blocks sequential execution). The codebase needs 5 more targeted fixes before this gate can close.

**This gate RE-REJECTS. P0 items 1-5 above are required before re-gate.**
