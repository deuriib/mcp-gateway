# Product Brief: Professional Performance Audit — MCP Gateway

**ID:** BRIEF-PERF-001
**Initiator:** montilla (CEO)
**Date:** 2026-09-16
**Status:** draft
**Execution_Mode:** single (frozen at frame-intent per initiator 2026-09-16; all specs follow unless overridden per SPEC with CEO waiver)
**Domains-Touched:** [engineering]

## Problem Statement

MCP Gateway v2.2.0 es un CLI Python headless que agrega múltiples servidores MCP tras un único endpoint HTTP/SSE con Code Mode + sandbox Starlark. No existe una línea base profesional de performance: se desconoce p99/p50 de `/mcp` (GET+POST), overhead de Code Mode, costo de `servers/*.pyi` discovery + `refresh`, ni consumo en `serve --transport stdio|http|sse` bajo carga local-first `127.0.0.1`.

Lo sufren hoy los usuarios OpenCode en local (devs que agregan `local|remote` y sirven por stdio/SSE) y cualquier operador que expone `http|sse`: latencias impredecibles, colas SSE sin SLO, y riesgo de optimizar a ciegas y romper 255 tests verdes.

Importa ahora porque v2.2.0 es CLI-only sin dashboard/catalog: sin auditoría, cada cambio de transporte, sandbox o policy (feat-006 allow-list + break-glass 72h) puede introducir regresiones silenciosas.

## Desired Outcome

Tener una auditoría profesional, reproducible y local-first que diga con datos dónde está el costo, qué SLO es defendible (p. ej. p99 `/mcp` local), y qué optimizar después sin romper seguridad ni los 255 tests. Éxito = medir primero, decidir después, con excelencia y dedicación.

## Scope

### In Scope

- Auditoría de latencia/throughput en 5 paths vivos `/mcp` (GET+POST), `/health`, `/ready`, `/live`, `/metrics` [engineering]
- Overhead de Code Mode (4 meta-tools), sandbox Starlark y `discover_tools` / `refresh` [engineering]
- Recursos en local: CPU/memoria/arranque en `serve --transport stdio|http|sse`, `127.0.0.1` por defecto [engineering]
- Comportamiento bajo carga: sesiones SSE, `asyncio.Queue`, timeouts, métricas Prometheus hand-rolled [engineering]
- Matriz de evidencia REQ→test→artifact para el gate [engineering]

### Out of Scope

- Cambios de producto, pricing o model (propiedad de otros dominios)
- Re-exposición `0.0.0.0` sin `MCP_GWAY_ALLOW_REMOTE=1` + firewall/auth delante
- Rotación de keys, patch prod o ampliación de permisos (el owner remedia; nosotros reportamos severidad + ubicación)
- Dashboard/catalog retirados en v2.0.0 (no revivir)

## Stakeholders

| Role | Agent | Involvement |
|------|-------|-------------|
| Sponsor | montilla | Decision authority |
| Owner | vasquez (CTO) | Delivery ownership |
| Touched | barrera (CISO) — solo como lente review si la auditoría propone nuevos endpoints/payloads/fronteras | Review / sign-off condicional |

> Craft citado por path (no inline): `agents/c-level/vasquez.md` será el único template leído en `translate-to-spec` (modo single); `agents/c-level/barrera.md` queda como path-cite condicional.

## Constraints

- Budget: por confirmar [dauhajre]
- Timeline: por confirmar factibilidad [vasquez]
- Regulatory: Ley 172-13 minimización PII — mapear flujo source→store→log→third party; cada store PII declara propósito+TTL+borrado; exports solo evidencia allowlisted, nunca dump/PII completo
- Security (guardrails 1-14): deny default; sin secretos/tokens/creds en código/config/logs/ejemplos; hallazgo sin prueba (diff/scan/log) = REFUTED; least privilege por interfaz; `MCP_GWAY_ALLOW_LOCAL_COMMANDS` / `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL` no renombrar
- Local-first: `127.0.0.1` default; `0.0.0.0` exige `MCP_GWAY_ALLOW_REMOTE=1`, si no `exit 2`
- Brand/GTM: no aplica (interno, sin anuncio externo)
- People/change: cambio mínimo, solo runbook de medición

## Open Questions

- [ ] ¿Baseline actual p50/p99 `/mcp` local en máquina referencia? [vasquez]
- [ ] ¿Carga objetivo concurrente SSE + `refresh` para SLO? [vasquez]
- [ ] ¿Ventana de medición y máquina sagrada para reproducibilidad? [vasquez]

---

# OKRs: Professional Performance Audit — MCP Gateway

**Period:** Q3 2026
**Owner:** montilla (CEO)

## Objective 1: Medir con rigor profesional el performance local-first

| Key Result | Baseline | Target | Measurement |
|------------|----------|--------|-------------|
| KR-1.1 p99 `/mcp` POST local documentado | desconocido | p99 medido + defendible (<150ms como hipótesis a validar, no compromiso) | script repro + `pytest` bench + `/metrics` en `127.0.0.1` |
| KR-1.2 Overhead Code Mode + Starlark cuantificado | desconocido | top-5 costos rankeados con traza | perfiles + matriz REQ→test→artifact |

## Objective 2: Blindar calidad mientras medimos

| Key Result | Baseline | Target | Measurement |
|------------|----------|--------|-------------|
| KR-2.1 Suite verde sin regresión | 255 tests | 255/255 verdes tras auditoría | `uv run pytest -v` + `ruff check` + `ruff format --check` |
| KR-2.2 SLOs + runbook auditables | ninguno | SLO draft + runbook repro en brief/spec | doc versionado + evidencia citada file:line |

## Objective 3: Dejar la decisión lista para optimizar

| Key Result | Baseline | Target | Measurement |
|------------|----------|--------|-------------|
| KR-3.1 Backlog priorizado por dato | ninguno | 3–5 optimizaciones con costo/riesgo owner | tabla impacto vs riesgo en handoff |
