# SCENARIOS — CATALOG-001 Catalogo MCPs
# Fuente: docs/specs/SPEC-CATALOG-001.md + spec_catalog_001 slot + scenario_catalog slot (22 Gherkin)

Ver memoria slot `scenario_catalog` — 22 scenarios C-01..C-22 trazables BR-01..BR-08.

Este archivo es espejo filesystem del slot `scenario_catalog` para trazabilidad git.
Contenido completo persistido en agentmemory `scenario_catalog` (20000 chars, 22 scenarios).

Para ejecucion ver slot: `scenario_catalog` (agentmemory) + docs/adr/ADR-008-catalog-mcp-001.md

## Resumen escenarios

| # | Scenario | BR | Tipo |
|---|----------|----|------|
| C-01 | Lista catalog HIT grid | BR-01,03,04 | Happy |
| C-02 | Search O(n) case-ins | BR-03,06 | Happy |
| C-03 | Fragment htmx debounce | BR-04,06 | Happy |
| C-04 | Stale sirve <50ms + bg | BR-03 | Happy |
| C-05 | Remoto caido sin cache 200 [] | BR-03 | Edge |
| C-06 | Remoto caido con stale | BR-03 | Edge |
| C-07 | POST refresh 202 bg | BR-03 | Happy |
| C-08 | Refresh single-flight 409 | BR-03 | Edge |
| C-09 | Cache corrupto miss | EC-08 | Edge |
| C-10 | Schema skip invalido | BR-07 | Edge |
| C-11 | >50KB truncado | BR-08 | Edge |
| C-12 | Drawer detail | BR-04 | Happy |
| C-13 | Sin secretos | BR-05 | Security |
| C-14 | Install happy Registry.add | BR-01,02 | Happy |
| C-15 | Install override name | BR-02 | Happy |
| C-16 | Install duplicado 409 | BR-02 | Error |
| C-17 | Name invalido 400 | BR-07 | Error |
| C-18 | Discovery falla [] | BR-02 | Edge |
| C-19 | Sin url/command 502 | EC-05 | Edge |
| C-20 | Concurrencia last-write | BR-06 | Edge |
| C-21 | Exposed X-Warning | BR-05 | Security |
| C-22 | No afecta CLI | BR-01 | Happy |

Full Gherkin: ver `scenario_catalog` memory slot.
