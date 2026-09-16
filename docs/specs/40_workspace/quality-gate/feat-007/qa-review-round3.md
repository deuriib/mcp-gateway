# QA Re-Review — FEAT-007 (Round 3)

## Verdict: ✅ APPROVED

All five P0 fixes from Round 2 are correctly implemented and resolve the root causes. No remaining issues.

## Fix Verification

| RC/Fix | Status | Evidence |
|--------|--------|----------|
| RC-7 — `_FakeSession` callable | ✅ | `test_obsfeat007.py:114-116` — `__call__` method returns `self`. When `monkeypatch.setattr("mcp.ClientSession", session)` (line 469) replaces the class with the instance, `ClientSession(read, write)` at `server_factory.py:110` calls `session(read, write)` → `__call__` → returns `self` → `await stack.enter_async_context(session)` → `__aenter__`. Constructor chain is sound. |
| RC-3 — `_broken_registry` path | ✅ | `test_obsfeat007.py:54-68` — `Registry(servers_dir=tmp_path)` writes `.pyi` stub directly to `tmp_path`. Comment on line 59 confirms intent. `--registry-dir tmp_path` in `test_ac012` (line 423) matches — `Registry` globs `*.pyi` from the same directory. No `servers/` subdirectory mismatch. |
| RC-4 — Monkeypatch target | ✅ | `test_obsfeat007.py:445` — `monkeypatch.setattr(ServerFactory, "make_server_struct", _boom)`. `code_mode.py:78` calls `self.server_factory.make_server_struct(server_name)`. Since `CodeMode.__init__` receives a `ServerFactory` instance, patching the class method intercepts the call via MRO. Correct target. |
| RC-6 — TestClient timeout | ✅ | `test_obsfeat007.py:254` — `TestClient(gw.app, timeout=5.0)` sets default request timeout. Lines 259-262 poll 100×20ms (2s total). The `stream` context manager exits cleanly (connection closed → SSE `finally` block runs → metric incremented). Timeout prevents indefinite hang on Windows event-loop scheduling delay. |
| F-1 — SSE WARN log assertion | ✅ | `test_obsfeat007.py:265-267` — asserts `recs[-1].reason == "idle"`. `gateway.py:554-557` emits `warning("SSE session ended", extra={"session_id": session_id, "reason": reason})`. When client disconnects without messages, `reason = "idle"`. Log message and extra fields match test assertion. |

## Architecture Fidelity

- **Metrics path**: SSE disconnect → `metrics.inc("gateway_sse_disconnects_total", {"reason": reason})` → `/metrics` exposition. Test confirms metric incremented and WARN log emitted with structured `reason` extra.
- **Degradation visibility**: Broken server → `_record_skip` → `warning("code mode server skipped")` + `metrics.inc("code_mode_servers_skipped_total")`. Both WARN log and metric asserted in `test_ac017`.
- **Transport retry boundary**: `_setup` is the only retry-eligible phase. `call_tool` is never retried (BR-112). Tests `test_ac014`/`test_ac015`/`test_ac016` verify this invariant.

## Remaining Issues

None. All P0 fixes are in place and correctly resolve the Round 2 rejection reasons.
