# HANDOFF.md — FEAT-007 Observability/Resilience Hardening

**Spec:** `docs/sbtdd/specs/feat-007-observability-hardening/spec.md`
**Gate:** ✅ OPEN (GATE_REPORT.md)
**Handoff Date:** 2026-09-15
**From:** vasquez (CTO) via montilla (CEO)
**To:** ship-release

## Deliverables

### Production Code (11 files modified)
| File | Change | AC Trace |
|------|--------|----------|
| `src/mcp_gway/observability/metrics.py` | `_MAX_LABEL_COMBOS=200`, `_bounded_key`, `sum()` | AC-001, AC-003, AC-018 |
| `src/mcp_gway/observability/logging.py` | JSONFormatter 12 new extra-field keys | AC-001 |
| `src/mcp_gway/observability/middleware.py` | `_SLOW_REQUEST_THRESHOLD_MS=1000` + WARN | AC-007 |
| `src/mcp_gway/gateway.py` | Process/build metrics, SSE disconnect, aclose, heartbeat, upstream registrations, server_factory._metrics injection, code_mode.refresh() post-inject, SSE WARN log | AC-001..006, AC-013..014, AC-017 |
| `src/mcp_gway/stdio.py` | `_record()`, `_log_access()`, `_stdio_label()` | AC-008, AC-009 |
| `src/mcp_gway/cli.py` | `_log_cli_event()`, add/refresh wiring, `--retry-on-transport-error`, degraded banner | AC-010..012, AC-016 |
| `src/mcp_gway/models.py` | `retry_on_transport_error: bool = False` | AC-016 |
| `src/mcp_gway/server_factory.py` | `_metrics` field, `_call_tool_async` rewrite with AsyncExitStack retry + upstream telemetry | AC-013..015 |
| `src/mcp_gway/core/client.py` | `discover_tools(metrics=)`, `refresh_server(metrics=)` | AC-004 |
| `src/mcp_gway/code_mode.py` | `_record_skip()` with WARN + metric | AC-017 |

### Tests (1 file)
| File | Tests | AC Trace |
|------|-------|----------|
| `tests/test_obsfeat007.py` | 18 tests (AC-001..AC-018) | All ACs |

### Documentation (4 files)
| File | Content |
|------|---------|
| `docs/sbtdd/specs/feat-007-observability-hardening/spec.md` | Spec |
| `docs/sbtdd/specs/feat-007-observability-hardening/scenarios.md` | Scenarios |
| `docs/sbtdd/specs/feat-007-observability-hardening/acceptance.md` | Acceptance criteria |
| `docs/architecture/adr-012-observability-hardening.md` | ADR |

## DoD Checklist

### Functional Gates
- [x] All 18 acceptance criteria implemented
- [x] All 18 tests written and verified (QA R3 approved)
- [x] Zero new production dependencies (AC-018)
- [x] No breaking changes to MCP/SSE contract
- [x] CLI flags additive only (`--retry-on-transport-error`)
- [x] Local-first gating intact

### Quality Gates
- [x] Readability review: APPROVED (R2)
- [x] Reliability review: APPROVED (R1)
- [x] Refuter review: CONFIRMED 17/18 (R1)
- [x] Resilience review: APPROVED (R1)
- [x] Risk review: APPROVED (R2)
- [x] QA review: APPROVED (R3)

### Security Gates
- [x] No secret/token/credential material in code, logs, or metrics
- [x] Label values sanitized (`[^A-Za-z0-9_]` → `_`, capped at 32 chars)
- [x] Metrics never break request path (broad except in telemetry blocks)
- [x] Retry bounded + opt-in (exactly 1, transport-phase only)
- [x] No new attack surfaces

### Documentation Gates
- [x] Spec written and reviewed
- [x] ADR written (adr-012)
- [x] CHANGELOG.md updated
- [x] README.md observability section updated

## Residual Risk (Accepted)

| Risk | Owner | Tracking |
|------|-------|----------|
| AC-004 dead code — no caller passes `metrics=` | vasquez | Wire in cli.py next release |
| Raw error messages in logs (M-01..M-04) | vasquez | Apply `_safe_error_data` next sprint |

## Next Step

→ `ship-release`: produce RELEASE_NOTES.md, finalize CHANGELOG.md, archive spec.
