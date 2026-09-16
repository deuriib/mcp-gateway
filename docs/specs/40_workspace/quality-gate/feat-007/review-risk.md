# Risk Review — FEAT-007

## Verdict: ⚠️ CONDITIONAL

**Reviewed by:** @review-risk  
**Date:** 2026-09-15  
**Scope:** Security and business risk of FEAT-007 observability/resilience hardening changes  
**Spec:** `docs/sbtdd/specs/feat-007-observability-hardening/spec.md`  
**ADR:** `docs/architecture/adr-012-observability-hardening.md`

---

## Executive Summary

FEAT-007 introduces additive observability and resilience hardening across all mcp-gateway surfaces. The implementation is structurally sound with consistent defensive patterns. **No Critical or High findings.** Four Medium findings relate to raw exception messages in structured logs that could leak sensitive data to stderr. These are conditional on log consumption context and do not affect `/metrics` or network-facing responses.

---

## Findings

### M-01: Raw Exception Messages in CLI Structured Logs

**Severity:** Medium  
**OWASP:** A03:2021 — Sensitive Data Exposure  
**File:** `src/mcp_gway/cli.py:688-693`

```python
except Exception as e:
    click.echo(f"Error refreshing {server_name}: {e}", err=True)
    _log_cli_event(
        "refresh", "error", server=server_name,
        duration_ms=...,
        detail=str(e),  # <-- raw exception message
    )
```

**Risk:** The `detail=str(e)` passes raw exception messages into structured JSON logs on stderr. Exception messages from upstream MCP connections, OAuth discovery failures, or transport errors may contain:
- OAuth tokens or authorization headers
- Internal URLs with credentials
- Connection strings or hostnames
- File system paths

**Impact:** Limited to stderr consumption. The `/metrics` endpoint is unaffected. Risk escalates if stderr is aggregated into centralized logging (ELK, Datadog, CloudWatch) where multiple operators have access.

**Mitigation:** Apply the same `_safe_error_data` pattern used in `gateway.py:80-95` — extract only `[reason=...]` tokens and exception type, never raw messages. Or create a shared `_safe_exception_summary(exc) -> dict` utility.

**Owner:** CLI surface owner

---

### M-02: Raw Exception Messages in CodeMode Skip Logs

**Severity:** Medium  
**OWASP:** A03:2021 — Sensitive Data Exposure  
**File:** `src/mcp_gway/code_mode.py:89-96`

```python
logging.getLogger("mcp_gway.code_mode").warning(
    "code mode server skipped",
    extra={
        "server": server_name,
        "reason": "inject_error",
        "detail": f"{type(exc).__name__}: {exc}",  # <-- raw message
    },
)
```

**Risk:** Same class as M-01. Exception from `server_factory.make_server_struct()` during injection could leak registry config details, file paths, or connection info.

**Impact:** Same as M-01 — stderr only, but aggregated logging widens the blast radius.

**Mitigation:** Use type-only or `[reason=...]` extraction. The `_safe_error_data` pattern from gateway.py is the canonical approach.

**Owner:** CodeMode surface owner

---

### M-03: Inconsistent Error Data Handling Across Surfaces

**Severity:** Medium  
**OWASP:** A05:2021 — Security Misconfiguration  
**Files:**
- `src/mcp_gway/gateway.py:80-95` — Safe (`_safe_error_data`)
- `src/mcp_gway/cli.py:692` — Raw `str(e)`
- `src/mcp_gway/code_mode.py:95` — Raw `f"{type(exc).__name__}: {exc}"`

**Risk:** The gateway's `_safe_error_data` is the right pattern — it extracts only allow-listed `[reason=...]` tokens and exception type. But CLI and CodeMode bypass this, creating an inconsistent security posture. A future developer copying the CLI pattern into a network-facing path would introduce a data leak.

**Mitigation:** Centralize error summarization in a shared utility (e.g., `observability/errors.py`) that all surfaces use. This eliminates the inconsistency and prevents pattern drift.

**Owner:** Cross-cutting concern — recommend single owner for error handling

---

### M-04: Metric Label Cardinality from User-Controlled Server Names

**Severity:** Medium  
**OWASP:** — (Design-level concern)  
**File:** `src/mcp_gway/observability/metrics.py:202-219`

**Risk:** Server names from `MCPServerConfig.name` flow directly into metric labels (`server` label on `upstream_tool_calls_total`, `discovery_duration_seconds`, etc.). An operator adding 200+ servers with unique names hits the cardinality cap, and the 201st server's metrics coalesce into `_other`. This is the documented behavior (BR-102), but:

1. The 200 cap is a fixed constant — no env override for high-cardinality environments
2. Server names are validated by `_validate_name_value()` (alphanumeric + underscore only, max 64 chars), so injection is prevented
3. The `_san()` / `_sanitize_identifier()` functions further sanitize to 32 chars

**Impact:** Bounded by the 200 cap + `_other` coalescing. Memory growth is linear to cap, not unbounded. The real risk is operational — operators with many servers may see metrics silently coalesce without clear indication.

**Mitigation:** Consider adding a `_other` series count or a `cardinality_overflow_total` counter so operators can detect when coalescing activates. Low priority — the current behavior is safe, just opaque.

**Owner:** Observability owner

---

## Positive Findings (Defense-in Depth)

### P-01: Retry Mechanism Is Well-Bounded

**Files:** `src/mcp_gway/server_factory.py:114-124`, `src/mcp_gway/models.py:720`

The retry is:
- **Opt-in** (`retry_on_transport_error=False` by default, BR-115)
- **Exactly one** retry (not unbounded)
- **Transport/connect phase only** — `session.call_tool` is never re-run (BR-112)
- **Timeout-bounded** — each attempt respects `timeout_sec`

Worst case: 2x timeout per tool call. No amplification vector. The `MAX_POST_CONCURRENT=32` semaphore limits parallel calls.

### P-02: Consistent Defensive Metrics Pattern

Every `inc`/`set`/`observe` call across gateway.py, server_factory.py, stdio.py is wrapped in `try/except Exception: pass` with a WHY comment. Metrics never break the request path. This is the correct pattern and is applied consistently.

### P-03: Label Sanitization Is Consistent Across Surfaces

All label-producing code paths use the same pattern:
- `[^A-Za-z0-9_]` replaced with `_`
- Capped at 32 chars
- `_other` fallback for empty results

Files: `gateway.py:670-672`, `stdio.py:37`, `server_factory.py:93`, `middleware.py:122-127`

### P-04: `aclose()` Shutdown Summary Is Exception-Safe

`gateway.py:338-365` — The entire summary is wrapped in `try/except Exception: pass`. The `lifetime_seconds` gauge is set before the summary log, so even if logging fails, the metric is recorded. Shutdown never raises.

### P-05: Heartbeat Is Resource-Bounded

`gateway.py:482-496` — The heartbeat runs every 30s, performs O(n) session cleanup (n <= 128), and updates one gauge. No I/O, no network, no locks beyond the session dict. No resource exhaustion risk.

### P-06: SSE Disconnect Accounting Is Clean

`gateway.py:540-553` — Each SSE disconnect increments one counter and one gauge in the `finally` block. Runs once per connection. No amplification possible.

### P-07: `_log_cli_event` INFO Suppression Is Good Hygiene

`cli.py:38-71` — INFO events only emitted when `MCP_GWAY_LOG_LEVEL` is explicitly set. WARN/ERROR always emitted. Exit codes preserved. Zero noise for humans by default.

---

## Known Finding from Refuter (Accepted)

**AC-004 (`discovery_duration_seconds`) is dead code.** No production caller passes `metrics=` to `discover_tools()` or `refresh_server()`. The metric is registered in Gateway but always shows zero.

**Risk:** Low — wasted complexity, not a security risk. The metric is harmlessly registered. The `metrics` parameter exists as an optional injection point that a future serving-plane agent mode could use.

**Recommendation:** Accept as-is for now. If the metric remains unused after the next release, remove it to reduce cognitive overhead.

---

## Trust Boundary Analysis

| Boundary | Expected (ADR-012) | Actual | Status |
|----------|---------------------|--------|--------|
| Local-first (127.0.0.1 default) | Untouched | Untouched | PASS |
| SSRF guard on remote URLs | Untouched | Untouched | PASS |
| MCP/SSE JSON-RPC contract | No change | No change | PASS |
| CLI exit codes (0/1/2/130) | Preserved | Preserved | PASS |
| No new prod deps | stdlib only | stdlib only | PASS |
| `/metrics` local-only | Gated by host check | Gated by host check | PASS |
| Break-glass marker (72h TTL) | Untouched | Untouched | PASS |

---

## Conditions for APPROVAL

1. **M-01 / M-02 / M-03 (Data Exposure):** Adopt `_safe_error_data` pattern (or a shared utility) for CLI and CodeMode exception logging. Target: next sprint. Risk is Medium and limited to stderr, so this does not block shipping but should be tracked.

2. **M-04 (Cardinality Opacity):** Consider adding a `cardinality_overflow_total` counter in a future release so operators can detect when `_other` coalescing activates. Low priority.

3. **AC-004 (Dead Code):** Accept for now. Track for removal if unused after next release.

---

## Residual Risk

| Risk | Severity | Owner | Mitigation |
|------|----------|-------|------------|
| Raw exception messages in CLI/CodeMode logs | Medium | CLI/CodeMode owner | Adopt `_safe_error_data` pattern (next sprint) |
| Cardinality coalescing is opaque to operators | Medium | Observability owner | Add overflow counter (future) |
| `discovery_duration_seconds` dead code | Low | — | Accept; remove if unused next release |

---

## Verdict

**CONDITIONAL** — Approved with conditions. No Critical or High findings. The four Medium findings (raw exception messages in structured logs) are limited to stderr consumption and do not affect `/metrics` or network-facing responses. The implementation is structurally sound with consistent defensive patterns across all surfaces.

**Next steps:**
1. Track M-01/M-02/M-03 for next sprint remediation
2. Proceed to quality-gate verdict
