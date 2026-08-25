# ACCEPTANCE — SPEC-UI-001 Dashboard MCPs

## Spec ID: SPEC-UI-001
## Status: Approved → Executable Contract
## Date: 2026-08-25
## Owner: Vasquez (CTO) — Domain Oracle

> Cada AC es binaria (PASA/FALLA), derivada de SCENARIOS-UI-001.md y trazable a BR-UI-xxx. Evidencia requerida: `TestClient` o `httpx.ASGITransport`, nunca mocks de FS fuera de Registry.

---

### AC-01: SSR Dashboard base con Tailwind vendoreado

- **Trazable a**: BR-UI-006, BR-UI-007, BR-UI-008, S-02, S-26
- **Given** Registry vacía en `tmp_path/servers` y `Gateway(registry)` con dashboard montado
- **When** `GET /dashboard` vía `httpx.ASGITransport(app=gateway.app)`
- **Then**
  - `status == 200` y `content-type` contiene `text/html`
  - body contiene `<table`, `max-w-6xl mx-auto`, `<link href="/static/tailwind.css"` y `hx-get`/`htmx` attrs
  - `str(layout(...))` htpy no usa Jinja2 y Tailwind.css existe en `src/mcp_gway/dashboard/static/tailwind.css` (<100KB)
  - `GET /static/tailwind.css` → 200 y `GET /static/htmx.min.js` → 200 (si vendoreado) o fallback CDN no rompe
- **Test Data**: `tmp_path`, `Registry` vacía, no servers
- **Evidencia**: `tests/test_dashboard_views.py::test_dashboard_ssr_renders_table` + `::test_tailwind_vendored_no_node`

### AC-02: Add remote + persistencia Registry + visibilidad CLI

- **Trazable a**: BR-UI-001, BR-UI-002, BR-UI-005, BR-UI-010, S-04, EC-05
- **Given** Registry vacía
- **When** `POST /api/servers` JSON `{name:"gh", type:"remote", url:"https://example.com/mcp", timeout:5000, enabled:true}` (mock `_discover_tools` → `[]` para no red)
- **Then**
  - `201` con body `{name:"gh", tool_count:0}` o fragment si `HX-Request:true`
  - `registry.get_config("gh").url == "https://example.com/mcp"` y `servers/gh.json` + `servers/gh.pyi` existen
  - `GET /api/servers` lista contiene `gh`; `registry.list()` usado por CLI también lo lista (read-after-write)
  - Si discovery falla (timeout) → igual `201` + `tool_count 0` + warning toast fragment, no rollback
- **Test Data**: `gh`, `https://example.com/mcp`, `timeout 5000`
- **Evidencia**: `tests/test_dashboard_api.py::test_add_remote_persists`

### AC-03: Masking de secretos + reveal explícito POST loopback

- **Trazable a**: BR-UI-004, S-05, S-14, S-15, NFR-03
- **Given** server `"gh"` creado con `{headers: {"Authorization":"Bearer s3cr3t", "X-Api":"k123"}, oauth:{clientSecret:"shhh"}, environment:{"TOKEN":"xyz"}}` vía API
- **When** `GET /api/servers`, `GET /api/servers/gh`, `GET /dashboard`
- **Then** todo valor secreto == `"***"` en JSON y HTML no contiene `s3cr3t|shhh|xyz` ni en logs
- **When** `POST /api/servers/gh/reveal` body `{"field":"headers"}` desde `client` con `REMOTE_ADDR 127.0.0.1` (TestClient loopback)
- **Then** `200` con valor real `{"Authorization":"Bearer s3cr3t"}`; sin `127.0.0.1` → `403`; `GET /reveal` → `405`; audit log no contiene valor
- **Test Data**: headers s3cr3t, oauth shhh, env xyz
- **Evidencia**: `test_masking` + `test_reveal_loopback_only`

### AC-04: Toggle enabled y exclusión de list_enabled

- **Trazable a**: BR-UI-011, S-16
- **Given** server `"gh"` enabled true
- **When** `PATCH /api/servers/gh` `{"enabled": false}` + `HX-Request:true`
- **Then** `200` html fragment con badge `disabled` y `registry.get_config("gh").enabled == False` y `"gh" not in registry.list_enabled()`
- **When** `PATCH {"enabled": true}` → vuelve a habilitado y `list_enabled` lo incluye; `GET /dashboard` muestra badge `healthy`/`disabled` acorde
- **Test Data**: `gh` toggle false→true
- **Evidencia**: `test_toggle_enabled`

### AC-05: DELETE idempotente con borrado FS + tokens

- **Trazable a**: BR-UI-001, BR-UI-013, S-17, EC-07
- **Given** server `"gh"` con `gh.json`, `gh.pyi` y `tokens/gh.json` (creado manualmente en tmp_path)
- **When** `DELETE /api/servers/gh`
- **Then** `204`, `gh.json` y `gh.pyi` no existen en FS, token file borrado si existe
- **When** `DELETE /api/servers/gh` repetido o `DELETE /api/servers/nope`
- **Then** `404` JSON `{"detail":"Server 'gh' not found"}` no `500`; hx-delete con `hx-confirm` en HTML
- **Test Data**: `gh`, token dummy
- **Evidencia**: `test_delete_removes_files`

### AC-06: Refresh con timeout no bloqueante y re-discovery

- **Trazable a**: BR-UI-010, NFR-02, S-18, S-19, S-20
- **Given** server `"gh"` enabled
- **When** `POST /api/servers/gh/refresh` con mock `gateway` que `asyncio.sleep(0.2)` dentro de discovery y concurrent `GET /health`
- **Then** `/health` responde `200` <50ms mientras refresh en vuelo (no bloquea loop)
- **When** mock retorna 2 tools → `200 {tool_count:2}` y `registry.read_pyi("gh")` contiene ambas defs
- **When** discovery timeout/falla → `200` con `tool_count 0` y toast warning no 500
- **When** server disabled → `POST /refresh` → `400 "Server is disabled, enable first"`
- **Test Data**: timeout 5000ms, mock tools `[search, fetch]`
- **Evidencia**: `test_refresh_nonblocking` + `test_refresh_disabled_blocked`

### AC-07: Embebido single-process Gateway sirve MCP + Dashboard

- **Trazable a**: BR-UI-008, S-12
- **Given** `gateway = Gateway(registry)`
- **When** inspeccionar `gateway.app.routes` y `httpx` calls
- **Then** rutas contienen `/health`, `/mcp`, `/mcp/messages`, `/dashboard`, `/dashboard/servers`, `/api/servers`, `/static/tailwind.css`
- **And** `POST /mcp` (tools/list) y `GET /dashboard` ambos `200` en mismo `app`; `Gateway` no duplica proceso; `serve` host default `127.0.0.1`
- **Test Data**: inspeccion de routes, TestClient dual
- **Evidencia**: `test_gateway_embeds_dashboard`

### AC-08: Sin Node / sin regresión CLI / ruff limpio

- **Trazable a**: BR-UI-005, BR-UI-014, HC-10, HC-09, S-25, S-26
- **Given** repo root
- **When** `assert not Path("package.json").exists()` y `not Path("node_modules").exists()` y `uv run ruff check src/ tests/` y `ruff format --check`
- **Then** ambos `0` exit; `pyproject.toml` no contiene deps Node; `mcp-gway list/add/remove/inspect/refresh` tests existentes verdes (no touch)
- **Test Data**: FS checks, ruff run
- **Evidencia**: `test_no_node_artifacts` + CI `ruff` + `pytest tests/test_cli.py -q`

### AC-09: Validación nombre y compat legacy + error handling

- **Trazable a**: BR-UI-002, BR-UI-009, BR-UI-006, HC-06, S-10, S-11, EC-02/03/04/07/11
- **Given** Registry vacía
- **When** `POST /api/servers` con `name` en `["my-server","my server","1bad","café",""]` → cada uno `400` con detalle Pydantic accionable
- **When** `POST {type:"remote"}` sin `url` → `400 '"url" required for type=remote'`; `POST {type:"local"}` sin `command` → `400`
- **When** `POST {type:"remote", resolved_transport:"sse"}` legado → `201` y `config.resolved_transport=="sse"`
- **When** `GET /api/servers/gh` con `gh.json` corrupto (`{bad json`) → `500 {"detail":"Corrupt config, remove and re-add"}` y `GET /health` sigue `200`; `POST /api/servers` con name existente → `409`
- **Test Data**: nombres inválidos, payloads sin url/command, json corrupto
- **Evidencia**: `test_validation_and_legacy`

---

### DoD Checklist Wave 1 (lista+add+health) — Vertical Slice mínimo para CEO demo

- [ ] AC-01, AC-02, AC-07, AC-08, AC-09 parcial (lista+add+health) verdes vía `TestClient` (httpx.ASGITransport)
- [ ] `uv run ruff check src/ tests/` y `ruff format --check` 0
- [ ] `uv run pytest -v` incluye `test_dashboard_*` + CLI existentes verdes
- [ ] `Gateway.app` sirve `/dashboard` (SSR htpy) y `/api/servers` (JSON) en mismo proceso
- [ ] Tailwind vendoreado commit, htpy obligatorio, Registry única fuente, masking ***

### Fuera de Wave 1 (Wave 2)

- reveal audit, OAuth refresh, inspect drawer, unreachable badge, PATCH granular headers/env — AC-03 parcial reveal, AC-04, AC-05, AC-06 full entran en Wave 2 tras Wave 1 verde.

### Persistencia

- Este archivo + `SCENARIOS-UI-001.md` son contrato ejecutable. Guardar copia en `agentmemory` slots `scenario_dashboard` y `acceptance_SPEC-UI-001` si disponible.
