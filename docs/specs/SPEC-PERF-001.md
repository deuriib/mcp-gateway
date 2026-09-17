# Spec: Professional Performance Audit — MCP Gateway

**ID:** SPEC-PERF-001
**Owner:** vasquez (CTO)
**Domains-Touched:** [engineering]
**Brief Reference:** BRIEF-performance
**Status:** draft
**Priority:** P0
**Execution_Mode:** single (inherited from BRIEF-performance; no CEO waiver)

## 1. Context

MCP Gateway v2.2.0 es un CLI Python headless que agrega múltiples servidores MCP tras un único endpoint HTTP/SSE (`/mcp` GET+POST, `/health`, `/ready`, `/live`, `/metrics`) con Code Mode (4 meta-tools) y sandbox Starlark hermético. No existe una línea base profesional de performance: se desconoce p99/p50 de los 5 paths vivos, overhead de Code Mode + sandbox, costo de `servers/*.pyi` discovery + `refresh`, ni consumo en `serve --transport stdio|http|sse` bajo carga local-first `127.0.0.1`.

Este spec traduce BRIEF-performance a REQs testables y contrato de arquitectura para medir con rigor, blindar calidad (255 tests verdes), y dejar la decisión lista para optimizar con datos — sin optimizar a ciegas.

## 2. Requirements

- REQ-001: Medir latencia p50/p95/p99 de `/mcp` POST (JSON-RPC 2.0) en local `127.0.0.1` con carga concurrente configurable (hilos/async) y reportar percentiles + histograma Prometheus.
- REQ-002: Medir latencia p50/p95/p99 de `/mcp` GET (SSE stream + `endpoint` event) y `/mcp/messages` POST (alias al mismo handler) bajo sesiones SSE concurrentes.
- REQ-003: Medir latencia p50/p95/p99 de `/health`, `/ready`, `/live`, `/metrics` (5 paths vivos totales) como baseline de probes.
- REQ-004: Cuantificar overhead de Code Mode: tiempo de `discover_tools` (auto-detección transporte remote: streamable-http → sse → http), `refresh_server`, y ejecución de 4 meta-tools (`listToolFiles`, `readToolFile`, `getToolDocs`, `executeToolCode`) en sandbox Starlark.
- REQ-005: Medir consumo de recursos (CPU %, memoria RSS, tiempo de arranque) en `serve --transport stdio`, `serve --transport http`, `serve --transport sse` en `127.0.0.1` por defecto.
- REQ-006: Ejecutar suite completa (255 tests) antes y después de la auditoría para detectar regresiones; `ruff check` + `ruff format --check` deben pasar.
- REQ-007: Producir SLO draft defendible (p. ej. p99 `/mcp` POST < 150ms local como hipótesis a validar) + runbook reproducible (script, máquina, carga, versión) versionado en `docs/specs/30_delivery/`.
- REQ-008: Rankear top-5 costos con traza (perfil CPU/memoria) y tabla impacto vs riesgo para backlog de optimización priorizado.

## 3. Acceptance Criteria

- [ ] AC-001: Script de benchmark reproducible (`bench_perf.py` o similar) en `docs/specs/30_delivery/` que ejecute REQ-001 a REQ-005 y genere reporte JSON + markdown con percentiles, histogramas, y trazas.
- [ ] AC-002: Suite 255/255 tests verdes + `ruff check` + `ruff format --check` pasan tras auditoría (REQ-006).
- [ ] AC-003: SLO draft documentado en `docs/specs/10_design/ARCHITECTURE.md` (sección Non-Functional Requirements) con target medido, no asumido (REQ-007).
- [ ] AC-004: Runbook de reproducción en `docs/specs/30_delivery/RUNBOOK-perf.md` con máquina, versión, carga, comandos exactos, y cómo leer `/metrics` (REQ-007).
- [ ] AC-005: Tabla top-5 costos + impacto vs riesgo en `docs/specs/30_delivery/PERF-FINDINGS.md` (REQ-008).
- [ ] AC-006: Evidencia citada file:line para cada hallazgo; hallazgo sin prueba = REFUTED (guardrails).

## 4. Contracts & Interfaces

### Benchmark Interface (REQ-001 a REQ-005)
```python
# Entrada: config YAML/JSON con
#   - target_url: "http://127.0.0.1:8080"
#   - paths: ["/mcp", "/health", "/ready", "/live", "/metrics"]
#   - concurrency: int (hilos/async tasks)
#   - duration_sec: int
#   - warmup_sec: int
# Salida: JSON con percentiles p50/p95/p99, histograma buckets, throughput (req/s), errores
```

### Code Mode Profiling Interface (REQ-004)
```python
# Perfil de: discover_tools(), refresh_server(), executeToolCode() x4
# Métricas: wall-time, CPU time, memory delta, sandbox init/teardown
# Herramientas: py-spy, cProfile, tracemalloc, o `pytest-benchmark`
```

### Metrics Exposition (REQ-003, REQ-007)
- `/metrics` expone Prometheus hand-rolled (counter/gauge/histogram) via `observability/metrics.py:MetricsRegistry`
- `X-Warning: exposed` solo en `GET /metrics` → `403` cuando `0.0.0.0` sin `MCP_GWAY_ALLOW_REMOTE=1` (observability/health.py:127-139)

## 5. Out of Scope

- Cambios de código en `src/mcp_gateway/` (solo medición; optimizaciones van en specs separados tras hallazgos)
- Exposición `0.0.0.0` sin `MCP_GWAY_ALLOW_REMOTE=1` + firewall/auth
- Rotación de keys, patch prod, ampliación de permisos
- Dashboard/catalog retirados en v2.0.0
- Pricing, model, GTM, people changes

## 6. Dependencies

- Upstream: BRIEF-performance (aprobado)
- Downstream: specs de optimización basados en hallazgos (post-auditoría)
- Domain sign-offs: `barrera` (CISO) solo como lente review si hallazgos proponen nuevos endpoints/payloads/fronteras
- Tooling: `pytest`, `pytest-benchmark` o `py-spy`, `ruff`, `uv`

## 7. Traceability

| Requirement | Acceptance Criterion | Proposed Change | Evidence |
|-------------|---------------------|-----------------|----------|
| REQ-001 | AC-001 | PROPOSED_CHANGES.md | bench_perf.py + reporte JSON |
| REQ-002 | AC-001 | PROPOSED_CHANGES.md | bench_perf.py + reporte JSON |
| REQ-003 | AC-001 | PROPOSED_CHANGES.md | bench_perf.py + reporte JSON |
| REQ-004 | AC-001 | PROPOSED_CHANGES.md | perfil Code Mode + traza |
| REQ-005 | AC-001 | PROPOSED_CHANGES.md | bench_perf.py + recursos |
| REQ-006 | AC-002 | PROPOSED_CHANGES.md | `uv run pytest -v` output |
| REQ-007 | AC-003, AC-004 | PROPOSED_CHANGES.md | ARCHITECTURE.md + RUNBOOK-perf.md |
| REQ-008 | AC-005 | PROPOSED_CHANGES.md | PERF-FINDINGS.md |