# Release Notes: v2.2.1

**Date:** 2026-09-16
**Release Manager:** montilla (CEO)
**Specs Included:** SPEC-PERF-001
**Domains-Touched:** [engineering]
**Ship Type:** deploy (documentation/tooling only)

## Highlights

- Professional performance audit tooling for MCP Gateway v2.2.0: benchmark script, runbook, findings template, architecture NFRs, and ADR
- Measurable baseline for 5 live HTTP/SSE paths, Code Mode overhead, and resource consumption across 3 transports
- Reproducible benchmark with JSON + markdown reports

## Changes

### Features

- Performance benchmark script (`bench_perf.py`) measuring latency p50/p95/p99, throughput, Code Mode overhead, and resource consumption (SPEC-PERF-001, engineering)
- Benchmark configuration (`perf_config.yaml`) with configurable targets, concurrency, and output (SPEC-PERF-001, engineering)
- Runbook (`RUNBOOK-perf.md`) for reproducing benchmarks on any machine (SPEC-PERF-001, engineering)
- Findings template (`PERF-FINDINGS.md`) for documenting top-5 costs with impact vs risk (SPEC-PERF-001, engineering)

### Domain Ships

- Architecture: NFRs added to `ARCHITECTURE.md` with measurable performance targets (ADR-011)
- Architecture: ADR-011 recording decision to add performance baselines

### Breaking Changes

- (none) — documentation/tooling only, no `src/` changes

## Known Issues

- Code Mode overhead measurement is placeholder (actual measurement requires running server)
- Baseline measured on one machine — runbook documents machine specs for reproducibility
- SLO targets are hypotheses — will be refined post-audit

## Rollback / Undo

**Code revert:** `git rm docs/specs/30_delivery/bench_perf.py docs/specs/30_delivery/perf_config.yaml docs/specs/30_delivery/RUNBOOK-perf.md docs/specs/30_delivery/PERF-FINDINGS.md docs/specs/30_delivery/TEST-MATRIX-PERF-001.md docs/specs/30_delivery/IMPLEMENTATION-PLAN-PERF-001.md`

**Non-code undo:** `git rm docs/specs/10_design/ARCHITECTURE.md` (revert NFRs), `git rm docs/architecture/ADR-011-performance-nfrs.md`, `git rm docs/specs/15_requirements/REQUIREMENTS-PERF-001.md`

**No production code affected.** Rollback is trivial `git rm` of documentation files.

## Sign-off

- [x] vasquez (CTO) — DoD verified, handoff complete
- [x] montilla (CEO) — synthesized, release shipped