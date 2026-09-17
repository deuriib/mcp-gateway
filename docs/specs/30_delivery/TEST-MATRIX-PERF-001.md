# Test / Evidence Matrix: SPEC-PERF-001

**Agent:** vasquez (CTO)
**Date:** 2026-09-16
**Domains-Touched:** [engineering]

## Traceability

| REQ-ID | Evidence ID | Description | Type | Status | Artifact |
|--------|-------------|-------------|------|--------|----------|
| REQ-F-001 | T-001 | Benchmark script executes `/mcp` POST latency measurement | Unit | pass | `docs/specs/30_delivery/bench_perf.py` |
| REQ-F-002 | T-002 | Benchmark script executes `/mcp` GET + `/mcp/messages` POST latency measurement | Unit | pass | `docs/specs/30_delivery/bench_perf.py` |
| REQ-F-003 | T-003 | Benchmark script executes health probes latency measurement | Unit | pass | `docs/specs/30_delivery/bench_perf.py` |
| REQ-F-004 | T-004 | Benchmark script measures Code Mode overhead | Unit | pass | `docs/specs/30_delivery/bench_perf.py` |
| REQ-F-005 | T-005 | Benchmark script measures resource consumption per transport | Unit | pass | `docs/specs/30_delivery/bench_perf.py` |
| REQ-F-006 | T-006 | Suite 255 tests + ruff check + ruff format pass | Integration | pass | `uv run pytest -v` output |
| REQ-F-007 | E-001 | SLO draft documented in ARCHITECTURE.md | Review | pass | `docs/specs/10_design/ARCHITECTURE.md` (NFR section) |
| REQ-F-007 | E-002 | Runbook reproducible in RUNBOOK-perf.md | Review | pass | `docs/specs/30_delivery/RUNBOOK-perf.md` |
| REQ-F-008 | E-003 | Top-5 findings with impact vs risk in PERF-FINDINGS.md | Review | pass | `docs/specs/30_delivery/PERF-FINDINGS.md` |
| REQ-NF-001 | T-007 | Benchmark runs against `127.0.0.1` only | Unit | pass | `docs/specs/30_delivery/bench_perf.py` (default target) |
| REQ-NF-002 | T-008 | Config contains no secrets/tokens | Unit | pass | `docs/specs/30_delivery/perf_config.yaml` |
| REQ-NF-003 | E-004 | Architecture review confirms invariants | Review | pass | `docs/specs/40_workspace/architecture/ARCHITECTURE-REVIEW-PERF-001.md` |

## Coverage Summary

- **Unit coverage:** 8/12 evidence items (benchmark script tests)
- **Integration coverage:** 1/12 (255 suite pass)
- **Evidence coverage:** 12/12 REQ-IDs with linked artifact
- **Acceptance criteria covered:** 6/6 (AC-001..006)

## Acceptance Criteria Trace

| AC-ID | REQ-ID | Evidence | Status |
|-------|--------|----------|--------|
| AC-001 | REQ-001..005 | `bench_perf.py` + `perf_config.yaml` + reports | pass |
| AC-002 | REQ-006 | 255/255 tests + ruff | pass |
| AC-003 | REQ-007 | `ARCHITECTURE.md` NFR section | pass |
| AC-004 | REQ-007 | `RUNBOOK-perf.md` | pass |
| AC-005 | REQ-008 | `PERF-FINDINGS.md` | pass |
| AC-006 | REQ-F-001..008 | File:line evidence in all artifacts | pass |

## Sign-off

- [x] vasquez (CTO) — test/evidence matrix complete
- [ ] barrera (CISO) — security evidence reviewed (if applicable)