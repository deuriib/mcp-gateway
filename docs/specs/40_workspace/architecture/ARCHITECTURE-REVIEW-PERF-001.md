# Architecture Review: SPEC-PERF-001

**Reviewer:** vasquez (CTO)
**Date:** 2026-09-16
**Verdict:** Approved

## Contract Compliance

| Invariant | Status | Notes |
|-----------|--------|-------|
| INV-001: `127.0.0.1` default, `0.0.0.0` exige `MCP_GWAY_ALLOW_REMOTE=1` | pass | Benchmark corre contra `127.0.0.1`; runbook documenta que no se expone `0.0.0.0` |
| INV-002: `MCP_GWAY_ALLOW_LOCAL_COMMANDS` / `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL` no renombrar | pass | No toca policy; benchmark es observación pura |
| INV-003: Sin secretos/tokens/creds en código/config/logs/ejemplos/eventos | pass | Config de benchmark (`perf_config.yaml`) contiene solo target_url, paths, concurrency — sin credenciales |
| INV-004: Hallazgo sin prueba = REFUTED | pass | SPEC-PERF-001 exige evidencia file:line para cada hallazgo; AC-006 valida esto |
| INV-005: 255 tests verdes + ruff check + ruff format | pass | REQ-006 ejecuta suite pre/post; AC-002 valida 255/255 |
| INV-006: `X-Warning: exposed` gating | pass | Benchmark no modifica health.py; gating se mantiene intacto |

## ADR Required?

- [x] Yes — ADR-011 created (`docs/architecture/ADR-011-performance-nfrs.md`)
- [x] Records decision to add NFRs to ARCHITECTURE.md

## Conditions for Approval

1. Benchmark script se ejecuta contra `127.0.0.1` exclusivamente — no exponer `0.0.0.0` durante mediciones
2. Suite 255 tests se ejecuta pre y post benchmark — si hay regresión, benchmark se detiene
3. Si hallazgos revelan vulnerabilidades → barrera review antes de implementar optimizaciones
4. Optimizaciones post-auditoría requieren spec separado + propose-changes + quality-gate

## Sign-off

- [x] vasquez (CTO) — architecture review approved
- [ ] barrera (CISO) — condicional: solo si hallazgos proponen nuevas fronteras/payloads