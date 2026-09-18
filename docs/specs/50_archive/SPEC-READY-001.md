# Spec: Fix `/ready` Event Loop Drift Threshold

**ID:** SPEC-READY-001
**Owner:** vasquez (CTO)
**Domains-Touched:** [engineering]
**Brief Reference:** SPEC-PERF-001 (Finding 2)
**Status:** draft
**Priority:** P0
**Execution_Mode:** single (inherited from SPEC-PERF-001)

## 1. Context

The `/ready` endpoint returns HTTP 503 due to a misconfigured event loop drift threshold. The heartbeat runs every 30 seconds (`gateway.py:496`), but the drift threshold is 3 seconds (`health.py:88`). This causes `/ready` to report "not_ready" almost always, making it unusable for readiness probes.

**Root cause:** Threshold (3s) < Heartbeat interval (30s) → drift always exceeds threshold.

**Impact:** Monitoring tools flag false positives; Kubernetes/docker readiness probes fail; operational visibility degraded.

## 2. Requirements

- REQ-001: Increase event loop drift threshold from 3s to 35s (matches 30s heartbeat + 5s buffer)
- REQ-002: Add unit test verifying threshold behavior (drift < threshold → 200, drift > threshold → 503)
- REQ-003: Verify `/ready` returns 200 after fix when server is healthy

## 3. Acceptance Criteria

- [ ] AC-001: `/ready` returns HTTP 200 when server is healthy (registry ok, routes ok, event loop ok)
- [ ] AC-002: `/ready` returns HTTP 503 only when event loop drift > 35s (truly blocked)
- [ ] AC-003: Unit test passes for drift threshold logic
- [ ] AC-004: Existing 255 tests pass + ruff check + ruff format

## 4. Contracts & Interfaces

### `/ready` Endpoint (unchanged interface, fixed behavior)
```json
// Success (200)
{
  "status": "ready",
  "checks": {
    "registry": "ok",
    "routes": "ok",
    "event_loop": "ok"
  },
  "uptime_seconds": 123
}

// Failure (503)
{
  "status": "not_ready",
  "checks": {
    "registry": "ok",
    "routes": "ok",
    "event_loop": "fail: event loop blocked drift=XX.Xs"
  },
  "uptime_seconds": 123
}
```

## 5. Out of Scope

- Changing heartbeat interval (30s is appropriate for production)
- Changing other health checks (registry, routes)
- Modifying `/health`, `/live`, `/metrics` endpoints

## 6. Dependencies

- Upstream: SPEC-PERF-001 (Finding 2)
- Downstream: None (standalone fix)

## 7. Traceability

| Requirement | Acceptance Criterion | Proposed Change | Evidence |
|-------------|---------------------|-----------------|----------|
| REQ-001 | AC-001, AC-002 | `health.py:88` threshold change | Unit test |
| REQ-002 | AC-003 | `test_health.py` new test | pytest output |
| REQ-003 | AC-001 | curl `/ready` | HTTP 200 response |