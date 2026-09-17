# Requirements Index: Professional Performance Audit — MCP Gateway

**Owner:** vasquez (CTO)
**Brief Reference:** BRIEF-performance
**Domains-Touched:** [engineering]

## Functional Requirements

| ID | Requirement | Priority | Source | Spec | Domain | Evidence Type |
|----|-------------|----------|--------|------|--------|---------------|
| REQ-F-001 | Medir latencia p50/p95/p99 de `/mcp` POST (JSON-RPC 2.0) en local `127.0.0.1` con carga concurrente configurable | P0 | BRIEF-performance | SPEC-PERF-001 | engineering | test (benchmark script + JSON report) |
| REQ-F-002 | Medir latencia p50/p95/p99 de `/mcp` GET (SSE) y `/mcp/messages` POST bajo sesiones SSE concurrentes | P0 | BRIEF-performance | SPEC-PERF-001 | engineering | test (benchmark script + JSON report) |
| REQ-F-003 | Medir latencia p50/p95/p99 de `/health`, `/ready`, `/live`, `/metrics` (5 paths vivos totales) | P0 | BRIEF-performance | SPEC-PERF-001 | engineering | test (benchmark script + JSON report) |
| REQ-F-004 | Cuantificar overhead de Code Mode: `discover_tools`, `refresh_server`, 4 meta-tools en sandbox Starlark | P0 | BRIEF-performance | SPEC-PERF-001 | engineering | test (profiling + trace) |
| REQ-F-005 | Medir consumo CPU/memoria/arranque en `serve --transport stdio|http|sse` en `127.0.0.1` | P0 | BRIEF-performance | SPEC-PERF-001 | engineering | test (resource sampling + report) |
| REQ-F-006 | Ejecutar suite 255 tests + `ruff check` + `ruff format --check` antes y después | P0 | BRIEF-performance | SPEC-PERF-001 | engineering | test (CI parity) |
| REQ-F-007 | Producir SLO draft defendible + runbook reproducible versionado | P0 | BRIEF-performance | SPEC-PERF-001 | engineering | review (doc + runbook) |
| REQ-F-008 | Rankear top-5 costos con traza + tabla impacto vs riesgo para backlog | P1 | BRIEF-performance | SPEC-PERF-001 | engineering | review (findings doc) |

## Non-Functional Requirements

| ID | Requirement | Category | Target |
|----|-------------|----------|--------|
| REQ-NF-001 | Local-first: `127.0.0.1` default, `0.0.0.0` solo con `MCP_GWAY_ALLOW_REMOTE=1` | Security | `exit 2` sin opt-in |
| REQ-NF-002 | Deny default: `MCP_GWAY_ALLOW_LOCAL_COMMANDS` vacío = deny; `*` inválido | Security | feat-006 policy |
| REQ-NF-003 | Sin secretos/tokens/creds en código/config/logs/ejemplos/eventos | Security | Guardrails 1, 5 |
| REQ-NF-004 | Hallazgo sin prueba (diff/scan/log) = REFUTED | Security | Guardrails 9 |
| REQ-NF-005 | Ley 172-13: minimización PII, mapear flujo source→store→log→third party | Privacy | Purpose+TTL+deletion por store |
| NF-006 | Reproducibilidad: script único, máquina sagrada, versión git, carga configurada | Performance | Runbook versionado |
| NF-007 | Suite verde: 255/255 tests + ruff check + ruff format --check | Quality | CI parity |

## Domain Controls (only touched domains)

| Domain | Control | Owner |
|--------|---------|-------|
| engineering | Benchmark script, profiling, resource measurement, SLO draft, runbook, findings | vasquez |
| security | Lente review condicional si hallazgos proponen nuevos endpoints/payloads/fronteras | barrera (path-cite: agents/c-level/barrera.md) |