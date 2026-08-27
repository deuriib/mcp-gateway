# Spec: Catalogo MCPs — CATALOG-001 (v1.4.1 GA)

## Spec ID: CATALOG-001
## Status: Approved — Vinculante SBTDD — Vasquez Gate ✅ 2026-08-27 v1.4.1 GA (refina spec_mcp_catalog Draft)
## Version: 1.4.1 GA — 2026-08-27
## Author: Architect (System Architect & Domain Oracle) — dispatch @vasquez GO @montilla
## Fuente remota: https://getbifrost.ai/mcp-library
## ADR: docs/adr/ADR-008-catalog-mcp-001.md

---

### Objective

Proveer un **catalogo curado local-first** embebido en el Dashboard que permita descubrir MCP servers desde Bifrost Registry, inspeccionar detalle y hacer **Add directo** con un click, reduciendo friccion y errores de config. Cache local stale-while-revalidate TTL configurable; nunca escribe Registry hasta Add explicito.

**DONE =** ADR aprobado + cache `~/.config/mcp-gway/catalog.json` operativo + 5 rutas verificadas via TestClient + 9 AC verdes.

---

### Actors

| Actor | Rol | Interaccion |
|-------|-----|-------------|
| **Operador Local** | Dev en 127.0.0.1 | Browse catalog, search, view drawer, Add |
| **Bifrost Registry Remoto** | https://getbifrost.ai/mcp-library | GET JSON catalog curado |
| **CatalogCache** | Cache local `~/.config/mcp-gway/catalog.json` | TTL 6h/24h stale-while-revalidate |
| **CatalogService** | Dominio puro | fetch, validate, cache, search |
| **Dashboard htpy** | UI SSR + htmx | GET /dashboard/catalog SSR + drawer |
| **Registry local** | Unica verdad `servers/*.json + *.pyi` | Solo escribe en install via Registry.add |
| **Gateway Starlette** | Host embebido | Monta catalog routes single process |

---

### Ubiquitous Language

- **CatalogEntry**: Value Object inmutable — item validado (id, name, title, description, type, url/command, tags, docsUrl)
- **CatalogCache**: Aggregate (fetchedAt, ttlSec, etag, entries)
- **Install**: Use-case CatalogEntry -> MCPServerConfig -> Registry.add + discovery
- **stale-while-revalidate**: Sirve stale <50ms si remoto caido + background refresh

---

### Business Rules

| Rule ID | Rule | Priority |
|---------|------|----------|
| **BR-01** | Cache no escribe Registry. Solo POST /api/catalog/{id}/install escribe via Registry.add | P0 |
| **BR-02** | Install reutiliza Registry.add + discovery fallback (streamable-http->sse->http). Falla -> tools=[] + toast, no rollback. Duplicado 409 | P0 |
| **BR-03** | Refresh periodico configurable default 6h/24h via MCP_GWAY_CATALOG_TTL. GET stale -> <50ms + background. POST /refresh -> 202, 409 si busy. Single-flight | P0 |
| **BR-04** | Bounded Context htpy sin Node/Jinja. Prohibido Jinja2/React/Vue. Tailwind vendoreado <100KB | P0 HARD |
| **BR-05** | Local-first loopback + masking + CSP. host!=loopback -> X-Warning exposed + banner | P0 |
| **BR-06** | last-write-wins + atomicidad *.tmp 0o600. No DB, un proceso | P1 |
| **BR-07** | Validacion skip invalido. Entry invalido -> skip + warn, 0 validas -> [] + toast | P1 |
| **BR-08** | Truncado >50KB flag truncated:true | P2 |

---

### Edge Cases

| # | Caso | Comportamiento |
|---|------|----------------|
| EC-01 | Remoto caido | Stale + toast amber; miss sin cache -> 200 [] |
| EC-02 | Schema cambia | Skip invalido + warning, no 500 |
| EC-03 | Duplicado | 409 Server already exists |
| EC-04 | Name invalido | Sanitiza + validate 400 accionable |
| EC-05 | Sin url/command | Skip no instalable |
| EC-06 | >50KB | Trunca 50000 + truncated:true |
| EC-07 | TTL concurrente | Single-flight 409 |
| EC-08 | Cache corrupto | Miss, log warning |
| EC-09 | Concurrencia install | last-write-wins |
| EC-10 | Exposed | X-Warning banner |
| EC-11 | Search sin resultados | Empty No matches |
| EC-12 | 429 | Backoff stale |

---

### Constraints HARD

HC-01 Python3.12 Starlette htpy Pydantic httpx ruff · HC-02 Tailwind <100KB sin Node · HC-03 127.0.0.1 default · HC-04 Registry unica verdad · HC-05 Un proceso · HC-06 Compat OpenCode · HC-07 CSP

---

### Contracts Routes (5 rutas)

SSR: `GET /dashboard/catalog` (lista+search+Add), `GET /dashboard/catalog/{id}` (drawer)
API: `GET /api/catalog?q=&fresh&ttl` -> 200 {entries, meta} X-Cache HIT/STALE/MISS, `POST /api/catalog/{id}/install` -> 201 Registry.add 409 si existe, `POST /api/catalog/refresh` -> 202 background
Negotiation HX-Request:true -> fragment else JSON. Search O(n) substring.

---

### Cache file

`~/.config/mcp-gway/catalog.json` { fetchedAt, ttlSec, etag, entries: [CatalogEntry] }

---

### NFRs

NFR-01 catalog hit <50ms p95 · NFR-02 refresh no bloquea health · NFR-03 resiliencia stale · NFR-04 bundle <100KB · NFR-05 test TestClient MockTransport · NFR-06 logs metrics

---

### Changelog

- **2026-08-27 — v0.8.0 refinado**: Spec CATALOG-001 bounded context cache stale-while-revalidate (22 scenarios, 9 AC).
- **2026-08-27 — v1.4.1 GA**: Alineado a 1.4.1 exacta — ADR-008 Approved Vasquez Gate ✅, badge/dashboard `__version__` 1.4.1, sync `[tool.semantic_release]`.

*Vinculante. Desviacion requiere enmienda @vasquez. SBTDD: spec_catalog_001 v1.4.1 + scenario_catalog (22) + acceptance_catalog_001 (9).*
