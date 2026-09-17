# ADR-011: Add Performance NFRs to Architecture Contract

**Date:** 2026-09-16
**Deciders:** vasquez (CTO)
**Status:** accepted

## Context

MCP Gateway v2.2.0 lacks measurable performance baselines for its 5 live HTTP/SSE paths (`/mcp` GET+POST, `/health`, `/ready`, `/live`, `/metrics`), Code Mode overhead (4 meta-tools + Starlark sandbox), and resource consumption across 3 transports (`stdio|http|sse`). Without baselines, optimization decisions are guesswork — risking regressions in 255 tests and local-first security invariants.

BRIEF-performance mandates: measure first, decide after, with excellence and dedication.

## Decision

Add a Non-Functional Requirements section to `docs/specs/10_design/ARCHITECTURE.md` declaring measurable performance targets as architectural invariants:

1. **p99 `/mcp` POST local** — target to be validated by benchmark (hipótesis <150ms, no compromiso)
2. **p99 health probes** — target <50ms local (baseline a medir)
3. **Code Mode overhead** — top-5 costs ranked with trace (file:line)
4. **Resource consumption** — CPU/memory/startup per transport documented
5. **Reproducibility** — benchmark script + runbook versionado in `docs/specs/30_delivery/`

NFRs are documented as *measured targets*, not aspirational goals. Baseline data replaces hypothesis post-audit.

## Consequences

### Positive

- Performance decisions become evidence-based, not intuition-based
- Architecture contract becomes a living baseline — future specs reference measured data
- `quality-gate` has objective criteria (p99 thresholds, test parity) instead of subjective review
- Runbook enables any operator to reproduce measurements — auditability

### Negative

- NFRs add ceremony: every performance-related spec must reference these baselines
- Baseline measured on one machine may not generalize (mitigated by runbook documenting machine specs)
- Initial targets are hypotheses — will be refined after first benchmark run

## Supersedes / Superseded By

- Supersedes: none (new decision)
- Superseded by: future ADRs may refine NFRs based on benchmark data