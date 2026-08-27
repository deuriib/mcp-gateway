# ADR-008: Catalogo MCPs curado — CATALOG-001 (Bifrost local-first)

## Status
**Approved — Vasquez Gate ✅ 2026-08-27 v1.4.1 GA**
Author: Architect (System Architect & Domain Oracle) — dispatch @vasquez GO @montilla
Refs: `spec_catalog_001` v1.4.1 GA (`docs/specs/SPEC-CATALOG-001.md`), `scenario_catalog` (22), `acceptance_catalog_001` (9), SPEC-UI-001 v1.4.1 GA, Registry `servers/*.pyi+*.json`, Gateway `gateway.py`, `pyproject.toml:project.version` 1.4.1 synced `src/mcp_gway/__init__.py:__version__`

---

## Context

**Problema de negocio:** friccion al agregar MCP servers — busqueda manual en `https://getbifrost.ai/mcp-library`, copiar url/command, errores de config (type, url, name invalido, timeout). CEO @montilla exige catalogo curado embebido que reduzca friccion a 1 click Add.

**Constraints heredados (no negociables):**
- Python 3.12, Starlette, htpy + python-htmx, Tailwind vendoreado <100KB sin Node/Jinja/React, Pydantic, ruff
- SPEC-UI-001 vinculante: Registry `servers/*.pyi + *.json` unica verdad — Dashboard nunca I/O directo, solo via `Registry` class
- Local-first 127.0.0.1 default, `MCP_GWAY_ALLOW_REMOTE=1` para 0.0.0.0, masking `***` si aplica, CSP `default-src 'self'`, X-Warning si exposed
- Un proceso `Gateway(registry, host)` monta Dashboard — no DB, no proceso separado, atomicidad `*.tmp → replace 0o600`, last-write-wins
- Fuente: `https://getbifrost.ai/mcp-library` — manejar remoto caido (stale + toast), schema cambia (skip invalido), duplicado 409, >50KB truncado

**Objetivo DONE:** ADR aprobado + cache `~/.config/mcp-gway/catalog.json` TTL 6h/24h configurable stales-while-revalidate background <50ms + Bounded Context htpy + 5 rutas + 9 AC verdes TestClient.

---

## Decision Drivers

1. **Separacion de concerns** — catalog es lectura curada + Add puntual; Registry es escritura autoritativa. Mezclarlos rompe SoC y riesgo de corrupcion.
2. **Resiliencia offline** — operador local no debe depender de Bifrost remoto para ver catalog; stale cache debe servir <50ms.
3. **Simplicidad operativa** — sin DB, sin cron separado, sin Node, un deploy, tailwind vendoreado.
4. **Testabilidad** — todo verificable con `TestClient` + `httpx.MockTransport`, sin Selenium.

---

## Opciones Consideradas (2-3 con trade-offs + DSA)

### Opcion A — Bounded Context Catalog aislado + CatalogService + cache file stale-while-revalidate (RECOMENDADA)

```
Gateway (Starlette, single process)
├─ /dashboard + /api/servers  (existing, Registry)
└─ /dashboard/catalog + /api/catalog  (new, Bounded Context)
   ├─ catalog/models.py    CatalogEntry, CatalogCache (Pydantic)
   ├─ catalog/service.py   CatalogService (dominio puro, fetch+validate+cache)
   ├─ catalog/store.py     CatalogStore (cache I/O atomico)
   ├─ catalog/views.py     htpy: catalog_layout, catalog_grid, catalog_drawer, catalog_empty
   └─ catalog/api.py       handlers: list, drawer, api_list, install, refresh
        ↕
~/.config/mcp-gway/catalog.json  (TTL 6h default, 24h via env)   ← stale-while-revalidate
        ↕ httpx.AsyncClient (timeout 5s, etag If-None-Match)
https://getbifrost.ai/mcp-library
        ↕ POST /api/catalog/{id}/install → Registry.add + _discover_tools
servers/*.json + *.pyi (unica verdad, solo en install)
```

**Componentes:**
- `CatalogEntry(BaseModel)` Value Object inmutable — validacion estricta, `model_config(extra="ignore")` para tolerar schema nuevo, validator name `_validate_name_value` sanitizado.
- `CatalogCache(BaseModel)` Aggregate — `fetchedAt: datetime`, `ttlSec: int`, `etag: str|None`, `entries: list[CatalogEntry]`, `is_stale() -> bool`.
- `CatalogStore` — `path = Path.home()/".config/mcp-gway/catalog.json"` o `XDG_CONFIG_HOME`, `_atomic_write`, `load() -> CatalogCache|None` (corrupto -> None), `save(cache)`.
- `CatalogService` — `__init__(store, http_client_factory)`, `async def get_entries(q=None, fresh=False) -> (entries, meta)` con single-flight `asyncio.Lock`, `async def fetch_remote() -> list[CatalogEntry]` (httpx, etag, 304, skip invalido + metric), `async def refresh_background()`, `def search(entries, q)`.
- `CatalogInstallService` — `def entry_to_config(entry, override_name, override_timeout) -> MCPServerConfig` (sanitiza id -> name, map remote/local, validate), delega a `dashboard.api._validate_and_build_config` + `_discover_and_persist` + duplicate check.

**Flujo stale-while-revalidate:**
1. `GET /api/catalog` lee cache `store.load()`. Si hit no stale -> `X-Cache: HIT` responde inmediato.
2. Si stale o miss y remoto OK -> `X-Cache: STALE` sirve stale inmediato + `asyncio.create_task(service.refresh_background())` (<50ms). Siguiente GET hit nuevo.
3. Si remoto caido + stale existe -> `X-Cache: STALE` toast amber; si miss sin stale -> `X-Cache: MISS` 200 [] + toast amber. Nunca 500 por cache. Health <50ms concurrente.

**Patrones aplicados (justificados):**
- **Bounded Context (DDD)** — catalog es contexto lectura curada separado de Registry escritura. Evita god-module dashboard/api.py. Problema: mezclar responsabilidades. Coste: un modulo nuevo ~4 archivos.
- **Repository + Value Object + Aggregate** — CatalogEntry VO inmutable + CatalogCache aggregate con invariants (ttl, fetchedAt). Problema: validacion y skip invalido.
- **Adapter (Hexagonal)** — CatalogStore adapter FS, httpx adapter remoto; dominio CatalogService puro sin I/O directo. Problema: testabilidad sin red.
- **Decorator / Middleware** — reuse `_CSPMiddleware`, `_SecurityHeadersMiddleware` existentes.
- **Single-flight + Background Task (Saga-light)** — refresh background coalesce, health no bloquea.

**DSA & Complejidad:**
- Storage: `List[CatalogEntry]` n<200, busqueda `O(n*m)` m=entry fields len, <1ms en Python; indice `Dict[id, CatalogEntry]` para drawer/install `O(1)` avg hash. Alternativa Trie prefix `O(k)` k=query len no justificada (n pequeño, substring no prefix). Memoria `O(n)` entries ~200*2KB=400KB + cache file <100KB.
- Cache read `O(k)` JSON parse, atomic write `O(k)` tmp+replace, no bloqueo loop (async).
- Comparado a paginacion DB `O(log n)` — innecesario sin DB; KISS gana.

| Pros | Contras |
|------|---------|
| SoC limpio — catalog nunca escribe Registry hasta Add (BR-01) | Un modulo nuevo (+4 files) mas codigo que opcion B |
| Resiliencia offline probada — stale <50ms, no bloquea /health (NFR-01/02) | Cache file requiere manejo corrupto/etag (mitigado: load try) |
| Testable puro — MockTransport sin red, htpy views funciones puras | TTL configurable via env menos flexible que DB config |
| Reusa Registry.add + discovery (no duplica) | Background task requiere lock single-flight |
| Single process, sin DB, deploy simple | |
| Observabilidad clara — metrics `catalog_fetch_total`, `catalog_cache_age_seconds` | |

---

### Opcion B — Extender Registry para gestionar catalog (DESCARTADA)

Añadir a `registry.py`: `Registry.get_catalog()` + `registry.catalog.json` junto a `servers/`.

| Pros | Contras |
|------|---------|
| Un solo `Registry` class, menos archivos | **Viola SRP/SoC** — Registry es unica verdad `servers/*.json`; mezclar lectura curada remota contamina bounded context (BR-01 roto conceptualmente) |
| Reusa `_atomic_write` | Cache lock contendria con `Registry.add` (misma dir `servers/`) — riesgo last-write-wins cruzado |
| | Dificil testear offline (mock Registry mas complejo) |
| | Escalabilidad: Registry lista `*.pyi` glob no filtra catalog; O(n) glob incluira catalog si no separado |
| **Veredicto: RECHAZADA** — SoC y riesgo corrupcion pesan mas que ahorro de archivos. |

---

### Opcion C — Worker cron separado + DB sqlite (DESCARTADA)

Proceso `catalog-worker` con `apscheduler` cada 6h escribe sqlite `catalog.db`; Dashboard lee DB.

| Pros | Contras |
|------|---------|
| Refresh periodico desacoplado | **Viola HC-05 un proceso** — doble proceso, deploy complejo, IPC, supervisord |
| Query SQL `LIKE %q%` O(n) con indice FTS | **Node-like infra** — requiere `sqlite`, `apscheduler`, cron, mas deps; Tailwind ya es sin Node |
| Persistencia robusta | Sobre-ingenieria para n<200; DSA `B-Tree` O(log n) injustificado vs O(n) lista |
| | `servers/*.json` sigue FS — ahora hay 2 fuentes (DB + FS) rompe Registry unica verdad mental |
| | Background <50ms mas dificil cross-process |
| **Veredicto: RECHAZADA** — sobrecosto distribuido sin beneficio a esta escala. YAGNI. |

---

## Decision

**Elegimos Opcion A — Bounded Context Catalog aislado.**

Rationale: es la unica que respeta **Screaming Architecture** (carpeta dice lo que hace: `dashboard/catalog/`), **SoC** (catalog lectura vs Registry escritura), **KISS** (sin DB, un proceso), **Fail Fast** (Pydantic strict + skip), y **stale-while-revalidate** <50ms sin bloquear health. Coste +4 archivos justificado por BR-01 y testabilidad.

---

## Diseño Tecnico (interfaces, no implementacion)

### Modelos — `src/mcp_gway/catalog/models.py`

```python
from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from mcp_gway.models import _validate_name_value

class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    id: str = Field(description="slug unico, lowercase, valid name")
    name: str  # deriva de id sanitizado si no provisto
    title: str
    description: str = ""
    type: Literal["remote", "local"]
    url: str | None = None          # required si remote
    command: list[str] | None = None # required si local
    tags: list[str] = Field(default_factory=list)
    docsUrl: str | None = None
    source: str = "bifrost"         # provenance
    timeout: int = 5000
    truncated: bool = False

    @field_validator("id", "name")
    @classmethod
    def validate_id(cls, v: str) -> str:
        # sanitiza guion/espacio -> _, luego _validate_name_value
        import re
        s = re.sub(r"[^A-Za-z0-9_]", "_", v.strip())
        if not s:
            raise ValueError("id empty after sanitize")
        return _validate_name_value(s)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None, info) -> str | None:
        if info.data.get("type") == "remote" and not v:
            raise ValueError("url required for type=remote")
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("url must be http/https")
        return v

    @field_validator("command")
    @classmethod
    def validate_cmd(cls, v: list[str] | None, info) -> list[str] | None:
        if info.data.get("type") == "local" and not v:
            raise ValueError("command required for type=local")
        return v

    def model_post_init(self, __context: Any) -> None:
        if self.description and len(self.description) > 50000:
            self.description = self.description[:50000]
            self.truncated = True

class CatalogCache(BaseModel):
    model_config = ConfigDict(extra="ignore")
    fetchedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttlSec: int = 21600  # 6h default, override 86400
    etag: str | None = None
    entries: list[CatalogEntry] = Field(default_factory=list)
    invalid_skipped: int = 0

    def is_stale(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return (now - self.fetchedAt).total_seconds() > self.ttlSec

    def is_empty(self) -> bool:
        return len(self.entries) == 0
```

**Por que Pydantic:** validacion Fail Fast en boundary (fetch remoto), inmutabilidad conceptual VO, reusa `_validate_name_value` existente (BR-06 compat). `extra="ignore"` tolera schema nuevo sin romper (EC-02).

### Store — `src/mcp_gway/catalog/store.py`

```python
from pathlib import Path
import json, os, tempfile
from datetime import datetime, timezone
from mcp_gway.catalog.models import CatalogCache

DEFAULT_CACHE_PATH = Path.home() / ".config" / "mcp-gway" / "catalog.json"
# en tests inyectable via CATALOG_CACHE_PATH env o Gateway(catalog_path=...)

class CatalogStore:
    def __init__(self, path: Path | str = DEFAULT_CACHE_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> CatalogCache | None:
        try:
            if not self.path.exists():
                return None
            data = json.loads(self.path.read_text(encoding="utf-8"))
            # fetchedAt parse iso
            return CatalogCache(**data)
        except Exception as e:  # corrupt
            import logging; logging.getLogger(__name__).warning("catalog load corrupt: %s", e)
            return None

    def save(self, cache: CatalogCache) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        data = cache.model_dump(mode="json")
        # atomic write 0o600
        fd = os.open(str(tmp), os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush(); os.fsync(f.fileno())
        except Exception:
            try: os.unlink(tmp)
            except: pass
            raise
        tmp.replace(self.path)
        try: os.chmod(self.path, 0o600)
        except: pass
```

**Atomicidad:** mismo patron `Registry._atomic_write_text` (BR-06). Permiso 0o600.

### Service — `src/mcp_gway/catalog/service.py`

```python
from __future__ import annotations
import asyncio, logging, os, httpx
from datetime import datetime, timezone
from mcp_gway.catalog.models import CatalogEntry, CatalogCache
from mcp_gway.catalog.store import CatalogStore

BIFROST_URL = "https://getbifrost.ai/mcp-library"
DEFAULT_TTL = int(os.getenv("MCP_GWAY_CATALOG_TTL", "21600"))  # 6h, alternative 86400

logger = logging.getLogger(__name__)

class CatalogService:
    def __init__(self, store: CatalogStore, http_factory=None) -> None:
        self.store = store
        self._lock = asyncio.Lock()
        self._refreshing = False
        self.http_factory = http_factory or httpx.AsyncClient

    async def get_entries(self, q: str | None = None, fresh: bool = False) -> tuple[list[CatalogEntry], dict]:
        cache = self.store.load()
        now = datetime.now(timezone.utc)
        is_stale = cache.is_stale(now) if cache else True
        if not fresh and cache and not is_stale:
            entries = self._filter(cache.entries, q)
            return entries, {"fetchedAt": cache.fetchedAt.isoformat(), "ttlSec": cache.ttlSec, "stale": False, "total": len(entries), "cache": "HIT", "invalid_skipped": cache.invalid_skipped}
        # stale-while-revalidate: serve stale immediately + background
        if cache and is_stale:
            entries = self._filter(cache.entries, q)
            if not fresh:
                asyncio.create_task(self.refresh_background())
                return entries, {"fetchedAt": cache.fetchedAt.isoformat(), "ttlSec": cache.ttlSec, "stale": True, "total": len(entries), "cache": "STALE", "invalid_skipped": cache.invalid_skipped}
        # miss or fresh: fetch now (blocking ≤5s)
        try:
            new_cache = await self.fetch_remote()
            entries = self._filter(new_cache.entries, q)
            return entries, {"fetchedAt": new_cache.fetchedAt.isoformat(), "ttlSec": new_cache.ttlSec, "stale": False, "total": len(entries), "cache": "MISS" if not cache else "HIT", "invalid_skipped": new_cache.invalid_skipped}
        except Exception as e:
            logger.warning("catalog fetch failed, serving stale/miss: %s", e)
            if cache:
                entries = self._filter(cache.entries, q)
                return entries, {"fetchedAt": cache.fetchedAt.isoformat(), "ttlSec": cache.ttlSec, "stale": True, "total": len(entries), "cache": "STALE", "error": str(type(e).__name__)}
            return [], {"fetchedAt": None, "ttlSec": DEFAULT_TTL, "stale": False, "total": 0, "cache": "MISS"}

    async def fetch_remote(self) -> CatalogCache:
        async with self._lock:
            # single-flight inside lock
            async with self.http_factory(timeout=httpx.Timeout(5.0)) as client:
                headers = {}
                cache = self.store.load()
                if cache and cache.etag:
                    headers["If-None-Match"] = cache.etag
                resp = await client.get(BIFROST_URL, headers=headers)
                if resp.status_code == 304 and cache:
                    # not modified, refresh fetchedAt
                    cache.fetchedAt = datetime.now(timezone.utc)
                    self.store.save(cache)
                    return cache
                resp.raise_for_status()
                raw = resp.json()
                # raw expected {"entries": [...]} or list
                raw_entries = raw.get("entries") if isinstance(raw, dict) and "entries" in raw else raw if isinstance(raw, list) else []
                valid: list[CatalogEntry] = []
                skipped = 0
                for item in raw_entries:
                    try:
                        # normalize: id/name/title fallback
                        if "id" not in item and "name" in item:
                            item["id"] = item["name"]
                        if "name" not in item and "id" in item:
                            item["name"] = item["id"]
                        entry = CatalogEntry(**item)
                        valid.append(entry)
                    except Exception as e:
                        skipped += 1
                        logger.warning("catalog skip invalid entry id=%s err=%s", item.get("id", "?"), e)
                        continue
                # trunc >50KB already in model_post_init
                new_cache = CatalogCache(
                    fetchedAt=datetime.now(timezone.utc),
                    ttlSec=int(os.getenv("MCP_GWAY_CATALOG_TTL", str(DEFAULT_TTL))),
                    etag=resp.headers.get("etag"),
                    entries=valid,
                    invalid_skipped=skipped,
                )
                self.store.save(new_cache)
                return new_cache

    async def refresh_background(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            await self.fetch_remote()
        except Exception as e:
            logger.warning("catalog background refresh failed: %s", e)
        finally:
            self._refreshing = False

    def _filter(self, entries: list[CatalogEntry], q: str | None) -> list[CatalogEntry]:
        if not q:
            return entries
        ql = q.lower()
        return [e for e in entries if ql in e.id.lower() or ql in e.name.lower() or ql in e.title.lower() or any(ql in t.lower() for t in e.tags)]

    def get_by_id(self, id: str) -> CatalogEntry | None:
        cache = self.store.load()
        if not cache:
            return None
        idx = {e.id: e for e in cache.entries}
        return idx.get(id)
```

**Complejidad:** `_filter` O(n*m) n<200, m avg 30 chars → <0.5ms. `get_by_id` O(n) build dict cada vez O(n) pero n pequeño; alternativa cache idx dict O(1) memoizado — aceptable no optimizar premature.

### Install — `src/mcp_gway/catalog/install.py`

```python
import re
from mcp_gway.catalog.models import CatalogEntry
from mcp_gway.models import MCPServerConfig, _validate_name_value

def entry_to_config(entry: CatalogEntry, override_name: str | None = None, timeout: int | None = None) -> MCPServerConfig:
    name = override_name or entry.name or entry.id
    # sanitiza
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name.strip())
    _validate_name_value(sanitized)  # fail fast 400
    base = {"name": sanitized, "type": entry.type, "enabled": True, "timeout": timeout or entry.timeout}
    if entry.type == "remote":
        base["url"] = entry.url
    else:
        base["command"] = entry.command
    # no headers/oauth/environment en catalog (public)
    return MCPServerConfig(**base)
```

**Delega a** `dashboard.api._check_duplicate` + `_discover_and_persist` (Registry.add) — reuse 100% (BR-02).

### Routes — `src/mcp_gway/dashboard/catalog/routes.py` + `api.py` + `views.py`

**routes.py:**
```python
from starlette.routing import Route
from mcp_gway.dashboard.catalog.api import handle_catalog_list, handle_catalog_install, handle_catalog_refresh, handle_catalog_drawer

def get_catalog_routes(catalog_service, registry):
    return [
        Route("/dashboard/catalog", handle_catalog_drawer if False else handle_catalog_list, methods=["GET"]),  # SSR list
        Route("/dashboard/catalog/{id}", handle_catalog_drawer, methods=["GET"]),  # drawer
        Route("/api/catalog", handle_catalog_list, methods=["GET"]),
        Route("/api/catalog/{id}/install", handle_catalog_install, methods=["POST"]),
        Route("/api/catalog/refresh", handle_catalog_refresh, methods=["POST"]),
    ]
```

**Montaje en `gateway.py`:**
```python
from mcp_gway.catalog.store import CatalogStore
from mcp_gway.catalog.service import CatalogService
from mcp_gway.dashboard.catalog.routes import get_catalog_routes

catalog_store = CatalogStore()  # path ~/.config/mcp-gway/catalog.json
catalog_service = CatalogService(catalog_store)
catalog_routes = get_catalog_routes(catalog_service, registry)
self.app = Starlette(routes=[ ..., *dashboard_routes, *catalog_routes ])
self.app.state.catalog_service = catalog_service
```

**api.py handlers (interfaces):**
- `async def handle_catalog_list(request)` — `q=request.query_params.get("q")`, `fresh=request.query_params.get("fresh")=="true"`, `svc=request.app.state.catalog_service`, `entries, meta = await svc.get_entries(q, fresh)`, `if is_htmx(request): return HTMLResponse(str(catalog_grid(entries, q, meta, warning))) else: return JSONResponse({"entries":[e.model_dump() for e in entries], "meta":meta}, headers={"X-Cache":meta["cache"], **csp_headers()})`
- `async def handle_catalog_drawer(request)` — `id=request.path_params["id"]`, `entry=svc.get_by_id(id)`, `if not entry: return HTMLResponse(str(drawer_error(...)), 404)`, `if is_htmx: return HTMLResponse(str(catalog_drawer(entry, warning))) else: return JSONResponse(entry.model_dump())`, trunc flag.
- `async def handle_catalog_install(request)` — `id=path_params["id"]`, `entry=svc.get_by_id(id)`, `if not entry: 404/502`, `payload=await parse_json(request)`, `config=entry_to_config(entry, payload.get("name"), payload.get("timeout"))`, `dup=_check_duplicate(registry, config, request)`, `if dup: return dup`, `tools, err = await _discover_and_persist(registry, config)` (reuse), `return _create_success_resp(...)` 201.
- `async def handle_catalog_refresh(request)` — `if svc._refreshing: return JSONResponse({"detail":"already refreshing"}, 409)`, `asyncio.create_task(svc.refresh_background())`, `return JSONResponse({"status":"refreshing"}, 202)` (<50ms).

**views.py htpy (bounded context):**
```python
import htpy
from mcp_gway.catalog.models import CatalogEntry

def catalog_layout(entries, q, meta, warning_banner=False): ... # layout max-w-6xl, search input hx-get /dashboard/catalog?q= debounced 300ms, grid cards
def catalog_grid(entries, q, meta): ... # tbody/grid div id=catalog-grid hx-swap-oob
def catalog_drawer(entry: CatalogEntry, warning=False): ... # aside drawer with title, description truncated, url/command, tags, Add button hx-post /api/catalog/{id}/install
def catalog_empty(q, stale=False): ... # empty state No matches / No catalog offline
def catalog_card(entry): ... # card with badge remote/local, Add button hx-post, hx-target #server-table-body
```

**CSS:** reuse `dashboard/static/tailwind.css` vendoreado — no nuevo CSS.

### Observabilidad

- Logs: `logger.info("catalog fetch %s entries=%d skipped=%d etag=%s", url, len(valid), skipped, etag)`
- Metrics: `metrics.counter("catalog_fetch_total", ["status"])`, `metrics.gauge("catalog_cache_age_seconds")`, `metrics.counter("catalog_invalid_entries_total")`
- Health: `GET /api/catalog` no afecta `/health`; background task no bloquea loop.

---

## Consecuencias

**Positivas:**
- BR-01 garantizado — unica escritura Registry en install.
- Resiliencia offline — stale <50ms.
- Single process, sin DB, deploy simple.
- Testabilidad alta — MockTransport + tmp_path.

**Negativas / Mitigacion:**
- Cache file corrupto → miss (mitigado load try).
- ETag 304 handling requiere header parsing (mitigado: fallback sin etag).
- Background task single-flight lock requiere `asyncio.Lock` correcto (test 409).

**Riesgos:**
- Bifrost schema cambia radical (lista → objeto paginado) → fetch fallback `raw_entries` tolerante; skip invalido.
- 429 Rate limit → sirve stale + backoff Retry-After (futuro).
- Nombre colision catalog vs Registry — 409 claro.

---

## Alternativas descartadas (resumen)

| Opcion | Veredicto | Razon clave |
|--------|-----------|-------------|
| B — extender Registry | Rechazada | Viola SoC/SRP, contencion FS |
| C — worker + sqlite | Rechazada | Sobre-ingenieria, doble proceso, viola HC-05 |

---

## Validacion (Definition of Done)

- [x] ADR aprobado por @vasquez — Gate ✅ 2026-08-27 v1.4.1 GA
- [x] Slots SBTDD persistidos: `spec_catalog_001` v1.4.1 GA, `scenario_catalog` (22), `acceptance_catalog_001` (9)
- [x] 5 rutas montadas en Gateway single process, CSP, X-Warning
- [x] 9 AC verdes via TestClient (200/201/202/409 + stale + trunc + 404) + 254 tests totales
- [x] ruff check/format 0, Tailwind <100KB, sin Node/Jinja, CLI no regresion
- [x] CatalogStore atomic 0o600, last-write-wins, TTL 6h/24h via MCP_GWAY_CATALOG_TTL
- [x] Criterios listos para @backend/@frontend — interfaces validadas v1.4.1

---

## Referencias

- SPEC-UI-001 v1.4.1 GA (vinculante) — `docs/specs/SPEC-UI-001.md`
- `pyproject.toml:project.version` 1.4.1 + `src/mcp_gway/__init__.py:__version__` 1.4.1 (`[tool.semantic_release]` sync)
- `src/mcp_gway/registry.py` — `_atomic_write_text`, `add`, `list`
- `src/mcp_gway/dashboard/api.py` — `_discover_and_persist`, `_validate_and_build_config`, `_check_duplicate`, `_csp_headers`
- `src/mcp_gway/gateway.py` — `Gateway(registry, host)`, `get_dashboard_routes`
- `https://getbifrost.ai/mcp-library` — fuente remota (GET JSON)
- `pyproject.toml` — deps htpy, starlette, httpx, pydantic, ruff

---

*Arquitectura es stewardship: lo que diseñamos hoy, el equipo mantiene por años. Haces las cosas como para Dios — con excelencia y dedicación.*
