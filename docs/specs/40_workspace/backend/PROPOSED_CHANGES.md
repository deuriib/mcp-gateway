# Proposed Changes: Professional Performance Audit — MCP Gateway

**Spec Reference:** SPEC-PERF-001
**Agent:** vasquez (CTO)
**Date:** 2026-09-16
**Execution_Mode:** single (inherited from SPEC-PERF-001)
**Domains-Touched:** [engineering]

## Summary

Auditoría de performance local-first para MCP Gateway v2.2.0. El cambio es 100% documentación y herramientas de medición: script de benchmark reproducible en `docs/specs/30_delivery/`, runbook de reproducción, plantilla de findings, y contrato de arquitectura actualizado con NFRs de performance. No se toca código fuente (`src/mcp_gateway/`).

Principio: medir con excelencia y dedicación; optimizar solo con datos.

## Changes

| Target | Change Type | Description |
|--------|-------------|-------------|
| `docs/specs/30_delivery/bench_perf.py` | file-create | Script de benchmark: carga concurrente contra 5 paths vivos, profiling Code Mode/sandbox, mide recursos CPU/mem/arranque; genera reporte JSON + markdown |
| `docs/specs/30_delivery/RUNBOOK-perf.md` | document-create | Runbook de reproducción: máquina, versión, comandos exactos, cómo leer `/metrics`, cómo interpretar percentiles |
| `docs/specs/30_delivery/PERF-FINDINGS.md` | document-create | Plantilla de findings: tabla top-5 costos con traza (file:line), impacto vs riesgo, backlog priorizado |
| `docs/specs/30_delivery/perf_config.yaml` | file-create | Configuración de benchmark: target_url, paths, concurrency, duration, warmup, output format |
| `docs/specs/10_design/ARCHITECTURE.md` | file-modify | Agregar sección Non-Functional Requirements con NFRs de performance medidos (p99 targets, availability, security posture) |
| `docs/specs/15_requirements/REQUIREMENTS-PERF-001.md` | file-create | Índice de requisitos: 8 funcionales + 7 no-funcionales + 2 domain controls |

## Rationale

Estos cambios satisfacen SPEC-PERF-001 porque:
1. **bench_perf.py** ejecuta REQ-001..005 (latencia paths, overhead Code Mode, recursos transportes) — prueba medible
2. **RUNBOOK-perf.md** satisface REQ-007 (reproducibilidad auditada) — operador puede repetir sin suposiciones
3. **PERF-FINDINGS.md** satisface REQ-008 (backlog priorizado) — tabla impacto vs riesgo con traza file:line
4. **perf_config.yaml** centraliza parámetros — config-driven, no hardcode
5. **ARCHITECTURE.md update** documenta NFRs de performance como contrato vivo — baseline como evidencia
6. **REQUIREMENTS-PERF-001.md** deja la traza REQ→test→artifact lista para quality-gate

No se toca `src/` porque es auditoría, no optimización. Optimizaciones van en specs separados post-hallazgos.

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| Optimizar directamente sin medir | Riesgo de optimizar a ciegas y romper 255 tests; sin baseline no hay criterio de éxito |
| Usar herramientas externas (Gatling, k6) | Overkill para local-first; el script propio es reproducible y mantiene control total |
| Medir solo `/mcp` | 5 paths vivos requieren baseline completo; omitir health probes da visibilidad parcial |
| Crear dashboard de performance | Fuera de alcance (CLI-only v2.2.0); métricas vía `/metrics` Prometheus son suficientes |

## Approval Required From

- [x] Owning C-level: vasquez (engineering, owner)
- [ ] vasquez (CTO, architecture impact review) — waiver implícito por ser owner + spec propio
- [ ] barrera (CISO, condicional) — solo si hallazgos proponen nuevos endpoints/payloads/fronteras

> **Rule:** No repository file modifications during proposal phase except `docs/specs/` documentation and benchmark tooling. No `src/` changes.

---

# Risk Assessment: SPEC-PERF-001

**Proposer:** vasquez (CTO)
**Date:** 2026-09-16
**Domains-Touched:** [engineering]

## Risk Matrix

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R-001 | Benchmark script introduce regresión en suite 255 tests | Low | High | Script en `docs/specs/30_delivery/` (no `src/`); ejecutar suite pre/post; `uv run pytest -v` + `ruff check` |
| R-002 | Carga concurrente contra `/mcp` causa OOM o colapso en local | Medium | Medium | `warmup_sec` + `duration_sec` conservadores; monitorear RSS; abort si >80% RAM |
| R-003 | Medición sesgada por máquina no representativa | High | Low | Runbook documenta máquina exacta, versión git, comandos; reproducibilidad > generalización |
| R-004 | Optimización prematura post-auditoría sin aprobación | Medium | High | Out of Scope explícito; specs de optimización requieren propose-changes + quality-gate separados |
| R-005 | Hallazgos revelan vulnerabilidad de seguridad | Low | Critical | barrera review condicional; findings reportan severidad + ubicación owner remedia; no auto-fix |
| R-006 | `X-Warning: exposed` se activa accidentalmente en benchmark | Low | Medium | Benchmark corre contra `127.0.0.1` por defecto; no exponer `0.0.0.0` sin `MCP_GWAY_ALLOW_REMOTE=1` |

## Blast Radius

- **Engineering (services/data):** Solo `docs/specs/30_delivery/` (benchmark + runbook + findings). No toca `src/mcp_gateway/` ni `servers/`. Riesgo: cero afectación a código ejecutable en producción.
- **Finance (budget/controls):** Sin impacto. No hay cambios de infraestructura ni costos adicionales.
- **Legal (exposure):** Sin impacto. No hay datos PII nuevos ni exports.
- **Marketing (brand/GTM):** Sin impacto. Interno, sin anuncio externo.
- **People (team/culture):** Mínimo. Solo carga de trabajo de medición para vasquez.
- **Revenue (pipeline/targets):** Sin impacto. No hay cambios de pricing o funnels.
- **Automation/ops (runbooks/capacity):** Runbook nuevo agrega capacidad de diagnóstico; sin cambio en runbooks existentes.

## Rollback Plan

- **Benchmark script:** `git rm docs/specs/30_delivery/bench_perf.py docs/specs/30_delivery/perf_config.yaml` — rollback trivial porque es documentación nueva sin dependencias.
- **Runbook/Findings:** `git rm docs/specs/30_delivery/RUNBOOK-perf.md docs/specs/30_delivery/PERF-FINDINGS.md` — rollback trivial.
- **ARCHITECTURE.md:** `git checkout HEAD~1 -- docs/specs/10_design/ARCHITECTURE.md` — revert NFRs agregados.
- **REQUIREMENTS-PERF-001.md:** `git rm` — rollback trivial.

No hay código ejecutable afectado. Rollback = revert de docs.

## Security Considerations

- Benchmark corre contra `127.0.0.1` por defecto (local-first). No expone `0.0.0.0`.
- Sin secretos/tokens en config de benchmark (guardrails 1).
- `X-Warning: exposed` gating se mantiene intacto (observability/health.py:127-139).
- Si hallazgos proponen nuevos endpoints/payloads/fronteras → barrera review antes de implementar (path-cite: `agents/c-level/barrera.md`).
- Ley 172-13: benchmark no procesa PII; métricas son agregadas (latencia, CPU, memoria).

## Domain Considerations

- **Engineering:** Benchmark script + runbook + findings en `docs/specs/30_delivery/`; ARCHITECTURE.md actualizado con NFRs. Owner: vasquez.
- **Security:** Condicional — solo si hallazgos revelan vulnerabilidades o proponen nuevas fronteras. Owner: barrera.
- **Finance/Legal/Marketing/People/Revenue/Automation:** Sin cambios en estos dominios.
