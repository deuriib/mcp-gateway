# Readability Review — FEAT-007

## Verdict: ⚠️ CONDITIONAL

Reviewed: 11 production files + 1 test file (1,334 LOC production + 595 LOC tests)
Spec: `docs/specs/50_archive/feat-007-observability-hardening/spec.md`
ADR: `docs/architecture/adr-012-observability-hardening.md`

---

## Positive Observations

1. **FEAT-007 BR references are consistently placed** — every change site carries a `(BR-NNN)` tag linking back to the ADR decision. This is excellent traceability and makes auditing effortless.

2. **`_bounded_key` (metrics.py:202-219) reads cleanly** — the docstring explains the overflow coalescing strategy, the "no labels exempt" rule, and the edge case (real label combo equal to `_other`). One paragraph, full picture.

3. **`_log_cli_event` (cli.py:38-71) is well-structured** — the WARNING/ERROR always-emitted vs INFO-only-with-env logic is clear, the `extra` dict is self-documenting, and the docstring explains the operator vs human audience split.

4. **`StdioAdapter._record` + `_log_access` (stdio.py:54-81)** — short, single-purpose methods with docstrings that cite the BR and the "why" (cross-surface greps). The JSON access log shape matches HTTP exactly, and the `"transport": "stdio"` tag is the right seam.

5. **`code_mode._record_skip` (code_mode.py:83-105)** — replacing silent `except: pass` with structured WARN + metric is the single most important readability win in this feature. The docstring explains the *purpose* (degraded state visibility), not the mechanics.

6. **`test_obsfeat007.py`** — clean AC-XXX section headers, focused helpers (`_series`, `_FakeGateway`, `_FlakyCM`, `_FakeSession`), and 1:1 traceability to acceptance criteria. The `_broken_registry` helper's NOTE explaining the stub-retention trick is a good practice.

7. **`server_factory._call_tool_async` docstring (line 72-80)** — clearly states the telemetry scope AND the retry boundary ("transport/connect/initialize phase is the ONLY retry-eligible step"). This is the kind of comment that prevents future misuse.

---

## Findings

### F-01 — `observe()` comment wall (metrics.py:181-195)

**Severity:** High
**Principle:** Cognitive Load — walls of exploratory text require mental parsing
**Location:** `src/mcp_gway/observability/metrics.py:181-195`

The `observe()` method has 15 lines of comments that read like developer thinking-out-loud, not production documentation. Key issues:

- Line 181: "update buckets cumulative counts not needed now, just counts per bucket cumulative later" — contradicts the actual code below.
- Lines 186-195: A stream-of-consciousness paragraph explaining the cumulative logic, including self-correction ("Actually value <= le means..."), rhetorical questions ("That's what we do above?"), and a parenthetical aside. This is debug notes, not documentation.

**Recommendation:** Replace the 15-line comment block with 2-3 lines of intent:

```python
# Store per-bucket counts for buckets where value <= le.
# Exposition makes these cumulative (Prometheus convention).
```

### F-02 — Dead code: `_SANITIZE_LABEL_RE` + `sanitize_label` (middleware.py:122-127)

**Severity:** High
**Principle:** Dead Code — unused definitions create reader confusion
**Location:** `src/mcp_gway/observability/middleware.py:122-127`

`_SANITIZE_LABEL_RE` and `sanitize_label()` are defined at module scope but never called anywhere in the codebase. Meanwhile, `_handle_tool_call` in `gateway.py:670-672` defines its own local `_san()` with identical logic, and `stdio.py:33-38` has its own `_LABEL_RE` + `_stdio_label()` doing the same thing.

A reader encountering `sanitize_label` in `middleware.py` will assume it's used and search for callers — wasting time.

**Recommendation:** Either (a) remove the dead code from `middleware.py` and keep the local helpers where they're used, or (b) extract a shared `_sanitize_label` into a single location (e.g., `observability/metrics.py` or a new `observability/labels.py`) and have all three call sites reference it. Option (a) is lower-risk for this release.

### F-03 — DRY violation: label sanitization logic in 3 places

**Severity:** High
**Principle:** DRY / Maintainability — identical logic in 3 files
**Locations:**
- `gateway.py:670-672` — `_san()` local function
- `stdio.py:33-38` — `_LABEL_RE` + `_stdio_label()`
- `middleware.py:122-127` — `_SANITIZE_LABEL_RE` + `sanitize_label()`

All three replace non-alphanumeric chars with `_`, truncate to 32, and strip leading/trailing `_` with `_other` fallback. This is the same logic copy-pasted.

**Recommendation:** Consolidate into one function (reuse `middleware.sanitize_label` since it already exists) and import from the other sites. If the dead-code concern (F-02) is addressed by removing the middleware copy, create the shared function in `observability/metrics.py` (where `_escape_label` already lives).

### F-04 — Redundant `import time` inside `_serve_http` (cli.py:444)

**Severity:** Medium
**Principle:** Consistency — module-level `import time` already at line 10
**Location:** `src/mcp_gway/cli.py:444`

`import time` appears at module scope (line 10) and again inside `_serve_http` (line 444). The inner import shadows the outer for no reason.

**Recommendation:** Remove line 444. The module-level import is sufficient.

### F-05 — Redundant `import logging as _logging` in `_serve_stdio` (cli.py:390)

**Severity:** Low
**Principle:** Consistency — `logging` is already imported at module scope
**Location:** `src/mcp_gway/cli.py:390`

`import logging as _logging` is used only for `_logging.getLogger("mcp_gway.mcp")`. The module already has `import logging` at line 6. This alias is unnecessary noise.

**Recommendation:** Use the module-level `logging` import directly.

### F-06 — `_format_le` dead branch (metrics.py:324-336)

**Severity:** Medium
**Principle:** Dead Code — unreachable logic path
**Location:** `src/mcp_gway/observability/metrics.py:324-336`

The condition `le == int(le) and le not in (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5)` is impossible when `le == int(le)` is true — none of those fractional values can equal their int conversion. The `le not in (...)` clause is dead code.

**Recommendation:** Simplify to:
```python
if le == int(le):
    return str(int(le))
return str(le)
```

### F-07 — `_format_sum` is a no-op passthrough (metrics.py:339-346)

**Severity:** Low
**Principle:** KISS / YAGNI — abstraction for no benefit
**Location:** `src/mcp_gway/observability/metrics.py:339-346`

`_format_sum` does `return str(val)` in both branches (with and without the `val == int(val)` check, which also just calls `str(val)`). The function adds indirection with zero logic.

**Recommendation:** Inline `str(sum_val)` at the call site (line 306) and remove the function.

### F-08 — `re` imported inline in `server_factory.py` when already at module scope

**Severity:** Low
**Principle:** Consistency — module-level import exists
**Locations:** `server_factory.py:62,201,216`

`import re as _re` appears inside `is_auto_executable`, `_check_tool_allowed`, and `_get_tool_names`, but `re` is already imported at module scope (line 13).

**Recommendation:** Use the module-level `re` import. Remove the inline re-imports.

### F-09 — Metrics pre-registration block in `Gateway.__init__` is 70+ lines

**Severity:** Medium
**Principle:** Structure — one responsibility per block; cognitive load
**Location:** `src/mcp_gway/gateway.py:185-262`

The `__init__` method has 20+ `self.metrics.counter/histogram/gauge/set/inc` calls in a single linear block. A reader must scroll through all of them to find the non-metric code below. The `# FEAT-007 (BR-NNN)` comments help but the sheer volume is a cognitive wall.

**Recommendation:** Extract into a `_register_metrics(self)` method that returns nothing. `__init__` calls it once. This also makes the metric surface testable in isolation.

### F-10 — Triple `try/except: pass` for metrics injection (gateway.py:264-277)

**Severity:** Medium
**Principle:** Structure — defensive-but-repetitive pattern
**Location:** `src/mcp_gway/gateway.py:264-277`

Three consecutive `try: X._metrics = self.metrics except Exception: pass` blocks for registry, sandbox, and server_factory. The pattern is identical each time.

**Recommendation:** Extract into a helper `_inject_metrics(target)` or consolidate into a single try/except that handles all three:

```python
for target in (registry, self.code_mode.sandbox, self.code_mode.server_factory):
    try:
        target._metrics = self.metrics  # type: ignore[attr-defined]
    except Exception:
        pass
```

### F-11 — `_call_tool_async` is 80 lines with 4 nesting levels (server_factory.py:69-151)

**Severity:** Medium
**Principle:** Cognitive Load — deep nesting obscures control flow
**Location:** `src/mcp_gway/server_factory.py:69-151`

The method has `try > try > try > try` nesting (4 levels), with the retry logic, telemetry, and error classification all interleaved. The inner `_setup` coroutine is a good abstraction, but the outer structure makes it hard to see the flow: setup -> retry-if-transport -> call_tool -> classify -> telemetry.

**Recommendation:** The `_setup` extraction is a good first step. Consider also flattening the outer `try/finally` for telemetry into a decorator or helper, or at minimum splitting the retry logic and telemetry into clearly separated blocks with blank lines and section comments.

---

## Summary by Severity

| Severity | Count | IDs |
|----------|-------|-----|
| High | 3 | F-01, F-02, F-03 |
| Medium | 5 | F-04, F-06, F-09, F-10, F-11 |
| Low | 3 | F-05, F-07, F-08 |

---

## Conditions (for CONDITIONAL approval)

1. **F-02 + F-03 must be resolved before merge** — dead code + DRY violation across 3 files is a maintenance hazard and a reader trap. The fix is low-risk: consolidate sanitization into one function.

2. **F-01 should be resolved** — the 15-line exploratory comment block in `observe()` actively misleads readers (self-contradicting, rhetorical). Replace with 2-3 lines of intent.

3. **Remaining Medium/Low findings** are recommended but not blocking — they improve readability but don't impair understanding of the FEAT-007 logic.

---

## CONSTRAINT CHECKLIST

| Constraint | Status |
|---|---|
| Zero new production dependencies | ✅ PASS (AC-018 verified, no tenacity/prometheus-client/OTel) |
| No breaking changes to MCP/SSE contract | ✅ PASS (all changes additive, JSON-RPC 2.0 untouched) |
| CLI flags additive only | ✅ PASS (`--retry-on-transport-error` is new + default False) |
| Local-first gating intact | ✅ PASS (`serve` defaults to 127.0.0.1, SSRF guard unchanged) |
