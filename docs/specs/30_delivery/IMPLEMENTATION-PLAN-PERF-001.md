# Implementation Plan: SPEC-PERF-001

**Agent:** vasquez (CTO)
**Date:** 2026-09-16
**Approved By:** vasquez (CTO) — architecture review approved
**Domains-Touched:** [engineering]

## Steps

| Step | Description | Target / Files | Evidence Location | Est. Effort |
|------|-------------|----------------|-------------------|-------------|
| 1 | Create benchmark config file | `docs/specs/30_delivery/perf_config.yaml` | config file | 0.5h |
| 2 | Create benchmark script | `docs/specs/30_delivery/bench_perf.py` | script + JSON output | 4h |
| 3 | Create runbook | `docs/specs/30_delivery/RUNBOOK-perf.md` | runbook doc | 1h |
| 4 | Create findings template | `docs/specs/30_delivery/PERF-FINDINGS.md` | findings doc | 0.5h |
| 5 | Update ARCHITECTURE.md with NFRs | `docs/specs/10_design/ARCHITECTURE.md` | architecture contract | 0.5h |
| 6 | Create requirements index | `docs/specs/15_requirements/REQUIREMENTS-PERF-001.md` | requirements doc | 0.5h |
| 7 | Create ADR-011 | `docs/architecture/ADR-011-performance-nfrs.md` | ADR | 0.5h |
| 8 | Create architecture review | `docs/specs/40_workspace/architecture/ARCHITECTURE-REVIEW-PERF-001.md` | review doc | 0.5h |
| 9 | Create proposal | `docs/specs/40_workspace/backend/PROPOSED_CHANGES.md` | proposal doc | 0.5h |
| 10 | Create test/evidence matrix | `docs/specs/30_delivery/TEST-MATRIX-PERF-001.md` | evidence doc | 0.5h |

## Order of Operations

1. Config file (foundation for benchmark script)
2. Benchmark script (core deliverable — REQ-001..005)
3. Runbook (reproducibility — REQ-007)
4. Findings template (backlog — REQ-008)
5. Architecture/NFRs (contract update — REQ-007)
6. Requirements index (traceability)
7. ADR (decision record)
8. Architecture review (gate)
9. Proposal (already created)
10. Test/evidence matrix (traceability)

No dependencies between steps 1-9 (all doc creation). Step 10 depends on all prior steps for evidence.

## Rollback Points

- After step 1: `git rm docs/specs/30_delivery/perf_config.yaml` — trivial
- After step 2: `git rm docs/specs/30_delivery/bench_perf.py` — trivial
- After steps 3-9: `git rm` individual doc files — trivial
- No code in `src/` affected — rollback is always safe

## Quality Gates

- [x] Engineering: Lint (script is standalone, no src/ imports) / Tests (255 suite unaffected) / Security (no secrets in config) / Type checks (N/A for doc creation)
- [x] Architecture: ADR-011 created, ARCHITECTURE.md updated
- [x] Traceability: REQ-ID → test → artifact mapped in test matrix