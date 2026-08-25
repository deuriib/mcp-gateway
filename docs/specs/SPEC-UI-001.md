# Spec: Dashboard Management MCPs — SPEC-UI-001

## Spec ID: SPEC-UI-001
## Status: Complete — Shipped v0.7.0 GA (Vinculante SBTDD)
## Version: 0.7.0 GA — 2026-08-25 (181 tests passed)
## Author: Vasquez (Senior CTO Orchestrator)
## Date: 2026-08-25
## Stack Decisión: htpy + python-htmx + Starlette + TailwindCSS vendoreado (sin Node)

---

### Objective

Proveer un **dashboard local embebido en el Gateway** para gestionar visualmente los MCP servers (listar, agregar remoto/local, inspeccionar tools, enable/disable, remover, refrescar) reutilizando la Registry como única fuente de verdad, sin romper CLI ni compat OpenCode.

---

### Actors

| Actor | Rol | Interacción |
|-------|-----|-------------|
| **Operador Local** | Dev / Admin en `127.0.0.1` | Usa dashboard vía browser para CRUD/visualización de servers |
| **Gateway (Starlette)** | Host embebido | Monta rutas `/dashboard` + `/api/servers` sobre `gateway.py:Gateway.app` existente |
| **Registry** | Única fuente de verdad (`servers/*.json` + `servers/*.pyi`) | Leída/escrita exclusivamente vía `Registry` class; dashboard nunca toca FS directo |
| **MCP Server Remoto/Local** | Upstream | Contactado solo vía `refresh` / `add` (discovery `tools/list` con timeout + transport auto-detect) |
| **OAuth Provider (RFC 7591)** | Auth externo | Flujo PKCE + Dynamic Registration existente invocado desde dashboard (`refresh --auth`) |

---

### Business Rules

| Rule ID | Rule | Priority |
|---------|------|----------|
| **BR-UI-001** | Registry es **única fuente de verdad**. Todo read/write del dashboard pasa por `Registry` (`get_config`, `add`, `remove`, `update`, `list`). Prohibido I/O directo a `servers/*.json` o `*.pyi`. | **P0 — Critical** |
| **BR-UI-002** | Compat OpenCode **100%**: `type: remote` requiere `url`; `type: local` requiere `command: list[str]`. Campos opcionales: `headers`, `oauth`, `environment`, `cwd`, `timeout`, `enabled`, `resolved_transport`. Validación vía `MCPServerConfig` Pydantic. | **P0** |
| **BR-UI-003** | **Local-first por defecto**: `serve` bindea dashboard en `127.0.0.1` (no `0.0.0.0`) salvo flag explícito `--host`. Sin auth si bind es loopback; si `host != 127.0.0.1` → warning en log y header `X-Warning: exposed`. | **P0** |
| **BR-UI-004** | **Masking obligatorio** de secretos en UI y API: `headers` values, `oauth.clientSecret`, `environment` values se retornan como `***` por defecto. Revelado solo vía acción explícita `POST /api/servers/{name}/reveal` (no GET) y nunca logueado. | **P0 — Security** |
| **BR-UI-005** | **No regresión CLI**: `mcp-gway add/remove/list/inspect/refresh/serve` sigue funcionando idéntico. Dashboard es **vista** sobre Registry; CLI y dashboard concurrentes deben ver mismo estado (read-after-write). | **P0** |
| **BR-UI-006** | **SSR + API híbrido**: `GET /dashboard` SSR completo (htpy). Mutaciones vía `htmx` (`hx-post`, `hx-delete`, `hx-patch`) que consumen `POST/PATCH/DELETE /api/servers` y retornan **fragmento HTML** (no JSON) para swap. API JSON también expuesta para automatización. | **P1** |
| **BR-UI-007** | **htpy como motor de templates**: Todo HTML generado con `htpy` (Python hyperscript) + `python-htmx` helpers. Prohibido Jinja2, JSX, React, Vue. TailwindCSS **vendoreado** (`src/mcp_gway/dashboard/static/tailwind.css` commiteado) sin build Node/Vite. | **P1 — HARD** |
| **BR-UI-008** | **Arquitectura embebida**: Dashboard no es proceso separado. Se monta como `Route` + `StaticFiles` dentro de `Gateway.app`. Un solo `uvicorn.run(gateway.app)` sirve MCP (SSE/JSON-RPC) + dashboard. | **P1** |
| **BR-UI-009** | **Validación de nombre**: `name` ASCII, sin `-` ni espacios, no inicia con dígito (reusa `MCPServerConfig` validator). Error 400 con mensaje accionable si viola. | **P1** |
| **BR-UI-010** | **Discovery no bloqueante**: `add` y `refresh` ejecutan `tools/list` con `timeout` configurado (default 5000ms) y transport auto-detect `remote` (`streamable-http → sse → http`). Si discovery falla → server se guarda igual con `tools=[]` + warning toast, no rollback. OAuth 401 dispara flujo existente. | **P1** |
| **BR-UI-011** | **Enable toggle sin borrado**: `PATCH /api/servers/{name}` con `{"enabled": bool}` persiste via `Registry.add` y excluye de `list_enabled` del Gateway. Dashboard muestra badge `disabled` y no intenta discovery en disabled. | **P1** |
| **BR-UI-012** | **Inspección de tools**: `GET /api/servers/{name}` retorna config + `tool_count` + `tools[]` (lege `*.pyi` parsed). `GET /dashboard/servers/{name}` retorna drawer/fragment htpy con firmas. No expone `input_schema` crudo si > 50KB → truncado. | **P2** |
| **BR-UI-013** | **Idempotencia y concurrencia**: `POST /api/servers` con `name` existente → 409 Conflict. `DELETE` idempotente (404 si no existe). Escrituras usan `Registry.add` atómico (write `*.json` + `*.pyi` juntos). | **P2** |
| **BR-UI-014** | **Sin Node/Vite/React**: Build y runtime sin `package.json`, sin `node_modules`. CI no instala Node. Lint solo `ruff`. | **P0 — HARD** |
| **BR-UI-015** | **OAuth reutilizado, no reinventado**: Dashboard invoca `mcp_gway.oauth.run_oauth_flow` y `FileTokenStorage` existentes (RFC 7591 + PKCE). No duplica lógica de tokens. | **P1** |

---

### Architecture & Design (Decisión Vinculante)

**Ganadora: htpy + Starlette embebido + API+SSR (Opción A del diseño previo)**

```
┌─────────────────────────────────────────────────────────────────┐
│  Gateway (Starlette) — Single Process :8080                     │
│  ┌──────────────────┐  ┌────────────────────────────────────┐  │
│  │ MCP (existente)  │  │ Dashboard (nuevo, embebido)        │  │
│  │ POST /mcp        │  │ GET  /dashboard            → SSR htpy│
│  │ GET  /mcp (SSE)  │  │ GET  /dashboard/servers     → frag  │
│  │ POST /mcp/messages│ │ GET  /api/servers           → JSON  │
│  │ GET  /health     │  │ POST /api/servers           → JSON+frag│
│  └──────────────────┘  │ PATCH/DELETE /api/servers/{name}   │  │
│                        │ POST /api/servers/{name}/refresh   │  │
│                        │ Static /static/tailwind.css (vendoreado)│
│                        └──────────────┬─────────────────────┘  │
│                                       │ Registry (única fuente) │
│                              servers/*.json + servers/*.pyi     │
└─────────────────────────────────────────────────────────────────┘
```

**Estructura de carpetas (Screaming Architecture):**

```
src/mcp_gway/
├── gateway.py               # monta dashboard routes (modificado, +10 líneas)
├── registry.py              # sin cambios (reusado)
├── models.py                # sin cambios (reusado)
├── oauth.py                 # reusado
└── dashboard/
    ├── __init__.py
    ├── routes.py            # Starlette Route definitions (API + SSR)
    ├── views.py             # htpy components (layout, table, forms, drawer)
    ├── api.py               # JSON handlers (validación + Registry calls)
    └── static/
        └── tailwind.css     # vendoreado, sin build (commit)
```

**Por qué htpy ganó (ADR resumido):**

| Opción | Pros | Contras | Veredicto |
|--------|------|---------|-----------|
| **htpy + python-htmx** | Tipado Python, sin template string, autocompletado, 0 JS build, SSR nativo, testable como función pura | Ecosistema pequeño | **GANADORA** — alineada a HARD sin Node |
| Jinja2 | Familiar | Strings no tipados, lógica en template, sin htmx helpers | Descartada |
| React/Vite | Rico | Viola HARD sin Node/React, bundle, duplicación | **Rechazada** |

---

### Contracts — Routes

**SSR (htpy):**

| Method | Path | Response | htmx |
|--------|------|----------|------|
| `GET` | `/dashboard` | HTML completo (layout htpy + Tailwind) | — |
| `GET` | `/dashboard/servers` | Fragmento `<tbody>` tabla servers | `hx-get` polling opcional |
| `GET` | `/dashboard/servers/{name}` | Drawer/fragment detalle + tool signatures | `hx-get` sobre row click |

**API JSON (para htmx + automatización):**

| Method | Path | Body | Response |
|--------|------|------|----------|
| `GET` | `/api/servers` | — | `200 [{name, type, enabled, tool_count, url/command, timeout}]` (secrets `***`) |
| `GET` | `/api/servers/{name}` | — | `200 {config, tools, pyi_content}` (secrets `***`) |
| `POST` | `/api/servers` | `{name, type, url|command, headers?, environment?, cwd?, timeout?, enabled?, oauth?}` | `201` + fragment si `HX-Request`, `409` si existe, `400` validación |
| `PATCH` | `/api/servers/{name}` | `{enabled?, timeout?, headers?, environment?, ...}` | `200` + fragment |
| `DELETE` | `/api/servers/{name}` | — | `204` (idempotente, `404` si no existe) |
| `POST` | `/api/servers/{name}/refresh` | `?auth=false` | `200 {tool_count, tools}` tras re-discovery; dispara OAuth si 401 |
| `POST` | `/api/servers/{name}/reveal` | `{"field": "headers|oauth|environment"}` | `200 {value}` solo loopback, rate-limited, audit log |

**Content Negotiation:** Si request tiene `HX-Request: true` → retorna `text/html` fragment htpy; si no → `application/json`.

---

### UI/UX — Minimalista con Micro-interacciones

- Tailwind vendoreado, sin build. Paleta neutra + acento, layout centra tabla con `max-w-6xl mx-auto`.
- Componentes htpy: `Layout`, `ServerTable`, `ServerRow`, `AddModal`, `InspectDrawer`, `Badge`, `Toast`.
- htmx: `hx-post` add, `hx-delete` remove con `hx-confirm`, `hx-patch` toggle enabled, `hx-get` inspect drawer, `hx-indicator` spinner, `swap-oob` para toasts.
- Animaciones: `transition-colors duration-150` en rows, `ease-out` en modal/drawer, sin JS custom salvo `htmx.org` vendoreado (CDN opcional, prefer vendoreado local `htmx.min.js`).
- Estados: `healthy` / `disabled` / `unreachable` (0 tools) con badges color.

---

### Edge Cases

| # | Caso | Comportamiento esperado |
|---|------|-------------------------|
| EC-01 | `name` duplicado en `POST /api/servers` | `409 Conflict` con mensaje `"Server 'X' already exists"` + toast error |
| EC-02 | `name` inválido (guion, espacio, dígito inicial, no-ASCII) | `400` con detalle Pydantic validator |
| EC-03 | `remote` sin `url` o `local` sin `command` | `400` `"url required for type=remote"` / `"'command' required for type=local"` |
| EC-04 | `command` como string vacío o `url` malformada | `400` validación; no escribe Registry |
| EC-05 | Discovery timeout / todos transports fallan | Guarda server con `tools=[]`, toast warning `"No tools discovered"`, badge `unreachable` |
| EC-06 | Server `disabled` → refresh | `400` `"Server is disabled, enable first"` |
| EC-07 | `DELETE` de server inexistente | `404` (idempotente, no 500) |
| EC-08 | `PATCH enabled=false` mientras hay refresh en curso | Última escritura gana; refresh aborta si config deshabilitada mid-flight |
| EC-09 | Headers/environment con secretos → GET list | Valores retornados como `***`; `reveal` requiere POST explícito loopback |
| EC-10 | `servers/` vacío | Dashboard muestra empty state con CTA "Add your first server" |
| EC-11 | `*.json` corrupto o `*.pyi` faltante | `GET /api/servers/{name}` → `500` con `"Corrupt config, remove and re-add"`; no crash Gateway |
| EC-12 | OAuth 401 en `refresh` | Dashboard muestra botón "Authenticate" que dispara `run_oauth_flow` (abre browser server-side, polling callback) |
| EC-13 | Concurrencia CLI + Dashboard escribiendo mismo `name` | Filesystem last-write-wins; `Registry.add` atómico por archivo; dashboard refresca lista tras mutación (`hx-get /dashboard/servers`) |
| EC-14 | `htmx.min.js` no carga | SSR sigue funcional (full page reload en submit); degradación graceful |
| EC-15 | `GET /dashboard` desde `host != 127.0.0.1` sin auth | Sirve igual pero log `WARNING: dashboard exposed on non-loopback` + banner UI |

---

### Constraints — HARD (No negociables)

| ID | Constraint |
|----|------------|
| HC-01 | **Python 3.12+, Starlette, htpy, python-htmx** — únicos deps UI. No Jinja2, no FastAPI, no Flask. |
| HC-02 | **TailwindCSS vendoreado sin build**: `dashboard/static/tailwind.css` commiteado ( CDN build o `tailwindcss` CLI output vendoreado). Sin `node`, `npm`, `vite`, `package.json`. CI no instala Node. |
| HC-03 | **Local-first `127.0.0.1`**: `mcp-gway serve` default dashboard en loopback. `0.0.0.0` solo con `--host` explícito. |
| HC-04 | **Registry única fuente**: Dashboard solo via `Registry` class. Prohibido `Path("servers/...").write_text` directo fuera de Registry. |
| HC-05 | **Masking `***`**: Todo secreto en API/UI masked por defecto. |
| HC-06 | **Compat OpenCode `remote`/`local`**: Reusa `MCPServerConfig` (`type`, `url`, `command`, `headers`, `environment`, `cwd`, `oauth`, `timeout`, `enabled`, `resolved_transport`). Soporta legacy `http/sse/stdio` mapping existente. |
| HC-07 | **Reusar `servers/*.json` + `*.pyi`**: No nuevo formato, no DB, no migración. |
| HC-08 | **OAuth RFC 7591 existente**: Reusa `oauth.py` (`run_oauth_flow`, `FileTokenStorage`, PKCE). No duplicar. |
| HC-09 | **Sin romper CLI**: `add/remove/list/inspect/refresh/serve` sin cambios breaking. Tests CLI existentes deben pasar sin tocar. |
| HC-10 | **Sin Node/Vite/React**: Violación = rechazo en review. |

---

### Non-Functional Requirements

| ID | NFR | Criterio medible |
|----|-----|------------------|
| NFR-01 | **Latency SSR** | `GET /dashboard` < 150ms p95 en local (sin discovery); `GET /api/servers` < 50ms (solo FS read) |
| NFR-02 | **Discovery aislado** | `POST /api/servers` / `refresh` no bloquea event loop; timeout por transport respetado; Gateway sigue sirviendo `/health` y MCP durante discovery |
| NFR-03 | **Seguridad local** | Secret masking auditado; `reveal` solo loopback + POST; nunca log secrets; `tokens/*.json` no expuestos vía dashboard |
| NFR-04 | **Accesibilidad** | HTML semántico htpy, `aria-label` en toggles, keyboard nav en modal/drawer, contraste Tailwind AA |
| NFR-05 | **Testabilidad** | Views htpy testeables como funciones puras (assert `str(view())` contiene subtags); API con `TestClient` Starlette; sin Selenium |
| NFR-06 | **Bundle size** | `tailwind.css` vendoreado < 100KB (purged); `htmx.min.js` < 20KB; 0 JS framework |
| NFR-07 | **Resiliencia** | Gateway no crashea si dashboard route falla; error boundary retorna `500` fragment + log, MCP sigue operativo |
| NFR-08 | **Observabilidad** | Logs estructurados en `refresh`/`add` (server name, transport tried, duration, tool_count); no PII/secrets |

---

### Out of Scope (Explícitamente NO en UI-001)

- Auth multi-usuario / login / RBAC (local-first asumido)
- Edición de `input_schema` o `*.pyi` manual
- Logs streaming de MCP servers en dashboard
- Cluster / multi-node Gateway
- WebSocket transport (no en OpenCode schema)
- Paginación (se asume < 50 servers; `list` sorted)
- Export/import bulk (futuro `SPEC-UI-002`)

---

### Dependencies

```
starlette>=1.6.0  (ya)
htpy>=0.2       (nuevo)
python-htmx>=0.4  (nuevo)  — helpers htmx attrs para htpy
uvicorn>=0.52.4 (ya)
pydantic (ya, via mcp)
```

No nuevas deps de build. `htmx.min.js` vendoreado opcional (o CDN con fallback).

---

### Acceptance Criteria — Trazabilidad SBTDD

| AC | Criterio | Evidencia |
|----|----------|-----------|
| AC-01 | `GET /dashboard` retorna HTML htpy con Tailwind y tabla servers | Test `TestClient` + snapshot `assert "<table" in html` |
| AC-02 | `POST /api/servers` remote+local persiste via Registry y aparece en `GET /api/servers` y `mcp-gway list` | E2E: add via API → CLI list → Registry JSON+pyi existen |
| AC-03 | Secrets masked `***` en `GET /api/servers` y HTML; `POST /reveal` revela solo loopback | Test masking + test reveal 403 si no loopback |
| AC-04 | `PATCH enabled` toggle persiste y `list_enabled` excluye disabled | Test toggle + Gateway `list_enabled` check |
| AC-05 | `DELETE` remover borra `*.json`+`*.pyi` y `tokens` si existen | Test delete + FS assert |
| AC-06 | `POST /refresh` con timeout usa `Registry.update` y no bloquea `/health` | Test async timeout + health concurrent |
| AC-07 | Dashboard embebido: un solo `Gateway.app` sirve `/mcp` y `/dashboard` | Test `Gateway` routes contienen `/dashboard` |
| AC-08 | Sin Node: `package.json` no existe, `ruff` pasa, `pyproject.toml` sin deps Node | CI check |
| AC-09 | Validación nombre y compat legacy `http/sse/stdio` → `remote/local` | Test 400 + test add legacy type via API mapea |

---

### Verification — Definition of Done (v0.7.0 GA — Verificado 2026-08-25)

- [x] `uv run ruff check src/ tests/` y `ruff format --check` pasan
- [x] `uv run pytest -v` 181 tests (`test_dashboard_*` API + views htpy) y CLI existentes verdes
- [x] `mcp-gway serve` en `127.0.0.1:8080` → `curl /dashboard` 200 HTML htpy + Tailwind vendoreado + `curl /api/servers` JSON masked `***`
- [x] Demostración manual: add remote, add local, toggle enabled, inspect drawer, delete, refresh con 401 → OAuth (ver `docs/specs/ACCEPTANCE-UI-001.md`)
- [x] Review waves: `readability` + `reliability` + `resilience` + `risk` → `refuter` → `qa` (sole executor) → Vasquez Gate — CEO GO

---

## ADRs

**ADR-001: htpy sobre Jinja2/React** — Tipado, testable, sin build, alineado a HARD sin Node.
**ADR-002: Embebido sobre proceso separado** — Un solo Gateway, un solo puerto, Registry sin lock distribuido, deploy simple.
**ADR-003: Tailwind vendoreado sobre build** — Evita Node, CSS purged commiteado, trade-off: update manual pero infrecuente.

---

### Changelog v0.7.0

- **2026-08-25 — v0.7.0 GA shipped**: Dashboard embebido htpy+htmx+Tailwind vendoreado, Registry única fuente, masking `***`, local-first `127.0.0.1` + `MCP_GWAY_ALLOW_REMOTE`, 181 tests, release híbrido `push v*` + `workflow_run` (ADR-007).

---

*Este SPEC es vinculante. Cualquier desviación requiere enmienda aprobada por CTO. Implementación sin SPEC es improvisación — y la improvisación no escala.*
