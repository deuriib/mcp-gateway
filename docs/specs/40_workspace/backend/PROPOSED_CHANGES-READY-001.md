# Proposed Changes: Fix `/ready` Event Loop Drift Threshold

**Spec Reference:** SPEC-READY-001
**Agent:** vasquez (CTO)
**Date:** 2026-09-17
**Execution_Mode:** single (inherited from SPEC-READY-001)
**Domains-Touched:** [engineering]

## Summary

Fix the `/ready` endpoint by increasing the event loop drift threshold from 3s to 35s. This aligns the threshold with the 30s heartbeat interval, preventing false 503 responses when the event loop is healthy.

## Changes

| Target | Change Type | Description |
|--------|-------------|-------------|
| `src/mcp_gway/observability/health.py:88` | file-modify | Change drift threshold from `3` to `35` |
| `tests/test_health.py` | file-add | Add unit test for drift threshold logic |

## Rationale

The current threshold (3s) is less than the heartbeat interval (30s), causing `/ready` to always report "not_ready" between heartbeats. Increasing to 35s (30s + 5s buffer) ensures the endpoint reflects actual event loop health.

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| Reduce heartbeat to 2s | Excessive overhead; 30s is appropriate for production |
| Remove drift check entirely | Loses valuable operational visibility |
| Make threshold configurable | Over-engineering for a simple constant fix |

## Approval Required From

- [x] Owning C-level: vasquez (engineering, owner)
- [ ] vasquez (CTO) — waiver implied by being owner + simple constant fix

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Threshold too high (miss real blocks) | Low | Medium | 35s = 30s heartbeat + 5s buffer; real blocks >35s are significant |
| Existing tests break | Low | Low | Constant change only; add specific unit test |
