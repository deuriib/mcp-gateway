# Product Brief: Minimal CLI Alias mgw — MCP Gateway

**ID:** BRIEF-MGW-001
**Initiator:** montilla (CEO)
**Date:** 2026-09-16
**Status:** draft
**Execution_Mode:** single (frozen at frame-intent per initiator 2026-09-16; all specs follow unless overridden per SPEC with CEO waiver)
**Domains-Touched:** [engineering]

## Problem Statement

`mcp-gway` es preciso pero largo para uso diario. Escribirlo docenas de veces al día frena el flujo en terminal, aumenta typos y fricción en runbooks y onboarding.

Lo sufre hoy el operador local-first (dev que hace `add/list/refresh/serve --transport stdio|http|sse` en `127.0.0.1`): quiere un nombre mínimo como `mgw` sin perder compatibilidad con scripts y docs existentes que ya usan `mcp-gway`.

Importa ahora porque v2.2.0 es CLI-only headless sin dashboard/catalog: el CLI es la única superficie. Un alias corto sube velocidad sin romper nada.

## Desired Outcome

Tener `mgw` como alias total de `mcp-gway`: cada comando, flag y help funciona idéntico bajo ambos nombres, con `mcp-gway` como canónico y `mgw` como atajo. Éxito = escribo menos, rompo cero, con excelencia y dedicación.

## Scope

### In Scope

- Alias `mgw` paridad 1:1 con `mcp-gway` (add/remove/list/inspect/refresh/serve/local-unrestricted + flags) [engineering]
- Empaquetado: entry-point / script / shim que expone ambos binarios en install normal (`uv/pip`) [engineering]
- Help `--help` y versión idénticos bajo ambos nombres [engineering]
- Docs + README + runbook actualizados con `mgw` como atajo recomendado [engineering]
- Matriz de evidencia REQ→test→artifact para el gate [engineering]

### Out of Scope

- Renombrar o eliminar `mcp-gway` (se queda como canónico; compat garantizada)
- Revivir dashboard/catalog retirados en v2.0.0
- Re-exposición `0.0.0.0` sin `MCP_GWAY_ALLOW_REMOTE=1` + firewall/auth delante
- Rotación de keys, patch prod o ampliación de permisos (el owner remedia; nosotros reportamos severidad + ubicación)
- Autocompletado shell (solo si sale gratis del entry-point; si no, backlog)

## Stakeholders

| Role | Agent | Involvement |
|------|-------|-------------|
| Sponsor | montilla | Decision authority |
| Owner | vasquez (CTO) | Delivery ownership |
| Touched | — | Ningún otro dominio; `barrera` (CISO) solo como path-cite condicional si el empaquetado introduce nueva frontera de confianza |

> Craft citado por path (no inline): `agents/c-level/vasquez.md` será el único template leído en `translate-to-spec` (modo single); `agents/c-level/barrera.md` queda como path-cite condicional.

## Constraints

- Budget: por confirmar [dauhajre]
- Timeline: por confirmar factibilidad [vasquez]
- Regulatory: Ley 172-13 minimización PII — alias no añade stores PII; mapear flujo source→store→log→third party si help/logs tocan PII; exports solo evidencia allowlisted
- Security (guardrails 1-14): deny default; sin secretos/tokens/creds en código/config/logs/ejemplos; hallazgo sin prueba (diff/scan/log) = REFUTED; least privilege por interfaz; `MCP_GWAY_ALLOW_LOCAL_COMMANDS` / `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL` no renombrar
- Local-first: sin cambio — `127.0.0.1` default; `0.0.0.0` exige `MCP_GWAY_ALLOW_REMOTE=1`, si no `exit 2`
- Brand/GTM: no aplica (interno, sin anuncio externo)
- People/change: cambio mínimo, solo atajo + docs

## Open Questions

- [ ] ¿Mecanismo de alias preferido: segundo `project.scripts` entry-point vs wrapper/shim? [vasquez]
- [ ] ¿Comportamiento en Windows (shims `.exe`) + `uv tool install` verificado? [vasquez]
- [ ] ¿Alcance docs: README + AGENTS.md + help text, o solo README? [vasquez]

---

# OKRs: Minimal CLI Alias mgw — MCP Gateway

**Period:** Q3 2026
**Owner:** montilla (CEO)

## Objective 1: Escribir menos sin romper nada

| Key Result | Baseline | Target | Measurement |
|------------|----------|--------|-------------|
| KR-1.1 Paridad `mgw` ↔ `mcp-gway` | solo `mcp-gway` | 100% comandos/flags funcionan bajo ambos nombres | matriz REQ→test→artifact + `mgw --help` vs `mcp-gway --help` diff vacío |
| KR-1.2 Instalación expone ambos binarios | un binario | `mgw` + `mcp-gway` tras `uv sync` / install | repro install limpio + `which`-style check citado file:line |

## Objective 2: Blindar calidad mientras abreviamos

| Key Result | Baseline | Target | Measurement |
|------------|----------|--------|-------------|
| KR-2.1 Suite verde sin regresión | 255 tests | 255/255 verdes + nuevos tests alias | `uv run pytest -v` + `ruff check` + `ruff format --check` |
| KR-2.2 Docs coherentes | solo `mcp-gway` | README/runbook muestran `mgw` como atajo, canónico intacto | doc versionado + evidencia citada file:line |
