# SCENARIOS — SPEC-UI-001 Dashboard MCPs

## Spec ID: SPEC-UI-001
## Status: Approved
## Feature: Dashboard Management MCPs

> Trazabilidad: cada Scenario declara su BR-UI-xxx origen. Fuente vinculante: `docs/specs/SPEC-UI-001.md`.

---

### Preconditions Globales

- Registry es única fuente (`servers/*.json` + `servers/*.pyi`) vía clase `Registry`.
- Gateway montado con `Registry(tmp_path)` o `~/.config/mcp-gway/servers` en prod.
- Secrets enmascarados `***` por defecto.
- Stack: Starlette + htpy + python-htmx + Tailwind vendoreado. Sin Node.

---

```gherkin
Feature: Dashboard Management MCPs
  As an Operador Local en 127.0.0.1
  I want to gestionar MCP servers visualmente (listar, agregar, inspeccionar, enable/disable, remover, refrescar)
  So that no dependa del CLI y vea estado/health de cada server

  Background:
    Given Registry vacía en tmp_path/servers
    And Gateway embebido sirve /health, /mcp y /dashboard en un solo Starlette app

  # ── Lista y empty state ──────────────────────────────────────────
  Scenario: S-01 Lista vacía muestra empty state — Happy
    Given no hay servers en Registry            # BR-UI-001, BR-UI-013
    When GET /dashboard y GET /api/servers
    Then /dashboard retorna 200 HTML con "Add your first server" CTA
    And /api/servers retorna 200 JSON []

  Scenario: S-02 Lista con servers muestra tabla — Happy  [BR-UI-001, BR-UI-006, BR-UI-008]
    Given Registry con 2 servers: "gh" (remote https://api.github.com/mcp) y "local_echo" (local ["echo","hi"])
    When GET /dashboard
    Then HTML contiene <table> con 2 filas, badges enabled, tool_count y columnas Name/Type/Tools
    And GET /api/servers retorna 2 objetos con {name,type,enabled,tool_count,url|command}

  Scenario: S-03 Fragment htmx de tabla — Happy [BR-UI-006]
    Given Registry con 1 server
    When GET /dashboard/servers con HX-Request:true
    Then retorna 200 text/html fragmento <tbody> con filas (no layout completo)

  # ── Add remote ───────────────────────────────────────────────────
  Scenario: S-04 Add remote válido — Happy [BR-UI-002, BR-UI-005, BR-UI-010, BR-UI-013]
    Given Registry vacía
    When POST /api/servers {name:"gh", type:"remote", url:"https://example.com/mcp"}
    Then retorna 201; Registry crea gh.json y gh.pyi
    And GET /api/servers contiene gh con url y resolved_transport
    And CLI `mcp-gway list` muestra gh (read-after-write)

  Scenario: S-05 Add remote con headers secretos — masking [BR-UI-004]
    When POST /api/servers {name:"gh", type:"remote", url:"https://example.com/mcp", headers:{"Authorization":"Bearer s3cr3t"}}
    Then GET /api/servers → headers.Authorization == "***"
    And GET /dashboard HTML no contiene "s3cr3t"
    And POST /api/servers/gh/reveal {field:"headers"} desde 127.0.0.1 retorna valor real

  Scenario: S-06 Add remote duplicado — Error 409 [BR-UI-013, EC-01]
    Given server "gh" existe
    When POST /api/servers {name:"gh", type:"remote", url:"https://other.com/mcp"}
    Then 409 Conflict "Server 'gh' already exists" + toast error htmx

  Scenario: S-07 Add remote sin url — Error 400 [BR-UI-002, EC-03]
    When POST /api/servers {name:"bad", type:"remote"}
    Then 400 '"url" required for type=remote' y Registry no escribe archivo

  # ── Add local ────────────────────────────────────────────────────
  Scenario: S-08 Add local válido — Happy [BR-UI-002]
    When POST /api/servers {name:"echo_srv", type:"local", command:["echo","hi"], cwd:"/tmp", environment:{"FOO":"bar"}}
    Then 201 y GET /api/servers → environment.FOO == "***" (masked)
    And .json persiste command, cwd, environment

  Scenario: S-09 Add local sin command — Error 400 [BR-UI-002, EC-03]
    When POST /api/servers {name:"bad_local", type:"local"}
    Then 400 "'command' required for type=local"

  # ── Validación nombre ────────────────────────────────────────────
  Scenario: S-10 Nombre inválido — Error 400 [BR-UI-009, EC-02]
    When POST /api/servers con name en ["my-server","my server","1bad","café"]
    Then 400 con mensaje Pydantic "Name cannot contain hyphens..." / ASCII / digit

  Scenario: S-11 Compat legacy type mapping — Happy [BR-UI-002, BR-UI-006, HC-06]
    When POST /api/servers {name:"old_http", type:"remote", url:"https://x.com", resolved_transport:"http"}  # legacy http
    And POST con type sse/streamable-http mapeado
    Then acepta y persiste resolved_transport; GET lista muestra tipo REMOTE

  # ── Health y embebido ────────────────────────────────────────────
  Scenario: S-12 Gateway embebido single process [BR-UI-008, NFR-02]
    Given Gateway(registry) instanciado
    When inspeccionar gateway.app.routes
    Then existen rutas /health, /mcp, /mcp/messages, /dashboard, /api/servers
    And GET /health 200 durante discovery bloqueante simulado (no bloquea event loop)

  Scenario: S-13 Serve local-first 127.0.0.1 [BR-UI-003, HC-03]
    When `mcp-gway serve` sin --host y GET /dashboard desde 127.0.0.1
    Then 200 sin header X-Warning
    When serve --host 0.0.0.0
    Then log WARNING "dashboard exposed" y respuesta incluye X-Warning: exposed + banner UI

  # ── Masking y reveal ─────────────────────────────────────────────
  Scenario: S-14 Masking obligatorio [BR-UI-004, EC-09]
    Given server remote con headers, oauth.clientSecret, environment secretos
    When GET /api/servers y GET /api/servers/{name} y GET /dashboard
    Then todo secreto == "***" y nunca aparece en logs

  Scenario: S-15 Reveal solo POST loopback [BR-UI-004]
    When POST /api/servers/{name}/reveal {field:"headers"} desde 127.0.0.1
    Then 200 con valor real y audit log sin valor
    When mismo POST desde IP no-loopback o vía GET
    Then 403/405

  # ── Enable toggle ────────────────────────────────────────────────
  Scenario: S-16 Toggle enabled — Happy [BR-UI-011, AC-04]
    Given server "gh" enabled:true
    When PATCH /api/servers/gh {"enabled": false}
    Then 200 fragment htmx con badge "disabled"
    And Registry.get_config("gh").enabled == false
    And Gateway.registry.list_enabled() excluye "gh"
    And hx-patch toggle es idempotente

  # ── Remove ───────────────────────────────────────────────────────
  Scenario: S-17 Remove — Happy [BR-UI-001, AC-05, EC-07]
    Given server "gh" con gh.json, gh.pyi, tokens/gh.json
    When DELETE /api/servers/gh
    Then 204 y archivos borrados del FS
    And DELETE repetido o de inexistente → 404 (idempotente, no 500)

  # ── Refresh / discovery ──────────────────────────────────────────
  Scenario: S-18 Refresh éxito [BR-UI-010, AC-06, EC-05]
    Given server "gh" con tools=[search]
    When POST /api/servers/gh/refresh (mock discovery retorna 2 tools)
    Then 200 {tool_count:2} y Registry.update persiste nuevo .pyi

  Scenario: S-19 Refresh discovery falla guarda vacío [BR-UI-010, EC-05]
    When POST /api/servers (o refresh) con discovery timeout / transport fail
    Then server se guarda igual con tools=[] + toast warning "No tools discovered" + badge unreachable

  Scenario: S-20 Refresh de disabled bloqueado [EC-06]
    Given server disabled
    When POST /api/servers/{name}/refresh
    Then 400 "Server is disabled, enable first"

  Scenario: S-21 Refresh OAuth 401 [BR-UI-015, EC-12]
    When refresh detecta 401 y oauth != false
    Then respuesta indica "Authenticate" y dispara run_oauth_flow (mock) sin crash

  # ── Inspect ──────────────────────────────────────────────────────
  Scenario: S-22 Inspect tools [BR-UI-012, AC-?]
    Given server "gh" con .pyi de 2 defs
    When GET /api/servers/gh → 200 {config, tools, pyi_content, tool_count}
    And GET /dashboard/servers/gh → fragment drawer htpy con firmas
    When pyi input_schema >50KB → truncado

  Scenario: S-23 JSON corrupto no crashea Gateway [EC-11, NFR-07]
    Given servers/gh.json corrupto
    When GET /api/servers/gh
    Then 500 "Corrupt config, remove and re-add" y Gateway sigue sirviendo /health y /mcp

  # ── Concurrencia y no regresión ──────────────────────────────────
  Scenario: S-24 Concurrencia CLI + Dashboard [BR-UI-005, EC-13]
    When CLI `mcp-gway add` y dashboard POST concurrentes sobre mismo name
    Then last-write-wins atómico (json+pyi juntos) y GET /dashboard/servers refresca lista

  Scenario: S-25 No regresión CLI [BR-UI-005, HC-09]
    Given suite CLI existente (add/remove/list/inspect/refresh/serve)
    When ejecutar `uv run pytest tests/test_cli.py tests/test_registry.py`
    Then todos verdes sin cambios

  # ── UI/UX y constraints ──────────────────────────────────────────
  Scenario: S-26 SSR htpy + Tailwind vendoreado + htmx [BR-UI-006, BR-UI-007, HC-01, HC-02, HC-10]
    When GET /dashboard
    Then HTML generado por htpy (no Jinja), incluye <link href="/static/tailwind.css"> y hx-post/hx-delete/hx-patch attrs
    And repo no contiene package.json ni node_modules y ruff clean

  Scenario: S-27 Content negotiation HX-Request [BR-UI-006]
    When POST /api/servers con header HX-Request:true
    Then retorna text/html fragment (para swap) no JSON
    When mismo POST sin HX-Request
    Then retorna application/json 201

  Scenario: S-28 Degradación sin htmx [EC-14]
    Given htmx.min.js no carga
    When submit form add
    Then SSR fallback recarga página completa y persiste igual
```

## Trazabilidad BR → Scenarios

| BR | Scenarios |
|----|-----------|
| BR-UI-001 | S-01, S-02, S-17, S-24 |
| BR-UI-002 | S-04, S-07, S-08, S-09, S-11 |
| BR-UI-003 | S-13 |
| BR-UI-004 | S-05, S-14, S-15 |
| BR-UI-005 | S-04, S-24, S-25 |
| BR-UI-006 | S-02, S-03, S-26, S-27 |
| BR-UI-007 | S-26 |
| BR-UI-008 | S-12 |
| BR-UI-009 | S-10 |
| BR-UI-010 | S-04, S-18, S-19 |
| BR-UI-011 | S-16 |
| BR-UI-012 | S-22 |
| BR-UI-013 | S-01, S-06, S-04 |
| BR-UI-014 | S-26 |
| BR-UI-015 | S-21 |
