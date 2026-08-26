# Observability Hybrid Pragmatic (Approach C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship stdlib JSON logs + lightweight MetricsRegistry + correlation middleware + /health|/ready|/live|/metrics without vendor lock-in, preserving local-first trust.
**Spec:** `docs/specs/SPEC-2026-08-26-observability-design.md` (ID: SPEC-2026-08-26, Approach C hybrid pragmatic: §4 ADR-OBS-001..004)
**Architecture:** Single-process Starlette Gateway adds `observability/` bounded context (logging, metrics, health, middleware) mounted via ordered middlewares (Correlation→Metrics→Logging→Security) and 4 probes. Instrumentation via injected registry into `gateway/server_proxy/sandbox/registry`. Dashboard ops card is htpy-only read view over `/health` JSON.
**Tech Stack:** Python 3.12+, Starlette>=1.6, uvicorn>=0.52, htpy>=26.5, stdlib `json`/`logging`/`contextvars`/`threading`/`time`/`uuid` only; no `prometheus_client`, no Node.

## Global Constraints
| ID | Constraint | Source (Spec §) |
|----|------------|-----------------|
| C1 | Python 3.12+, Starlette+uvicorn, htpy only, Tailwind vendored, no Jinja/React/Node, no package.json | §8 HC-OBS-01 |
| C2 | No new prod deps — prometheus_client forbidden, stdlib JSON logs only | §8 HC-OBS-02, ADR-OBS-002 |
| C3 | Type hints + `from __future__ import annotations` on all new modules, ruff clean | §8 HC-OBS-03 |
| C4 | Local-first + masking *** invariant — logs/metrics never leak secrets, /metrics gated | §8 HC-OBS-04 |
| C5 | No breaking MCP/SSE contract — headers additive | §8 HC-OBS-05 |
| C6 | Registry atomic I/O invariant — observability never writes servers/ | §8 HC-OBS-06 |
| C7 | Bounded labels/sanitized paths, exposition <10KB | §8 HC-OBS-07 |
| C8 | 186 existing tests must stay green + >15 new observability tests | §8 HC-OBS-08, §10 AC |

## Dependency Graph

```
Task 1 (logging + correlation ContextVar) ──┐
Task 2 (MetricsRegistry) ───────────────────┤
                                            ├─> Task 3 (middlewares + health + routes) ─> Task 4 (instrumentation gateway/sandbox/registry) ─> Task 6 (docs & gates)
Task 5 (dashboard ops card htpy) ───────────┘   (Task 5 can run parallel to Task 3 after Task 2 defines MetricsRegistry interface)

Parallelizable: T1 || T2 || T5 can start together (T5 needs T3 for final integration but can build views standalone). T3 needs T1+T2. T4 needs T3. T6 needs all.
Linear fallback: T1 → T2 → T3 → T4 → T5 → T6 if needing strict order.
```

---

### Task 1: Observability Logging + Correlation Context [S] [CODE-TDD]

**Files:**
- Create: `src/mcp_gway/observability/__init__.py`
- Create: `src/mcp_gway/observability/logging.py`
- Test: `tests/test_observability_logging.py`

**Interfaces:**
- Consumes: stdlib `logging`, `json`, `contextvars`, `time`, `uuid`, `re`
- Produces: `request_id_ctx: ContextVar[str | None]`, `class JSONFormatter(logging.Formatter)` with `format(record) -> str` (valid JSON line), `def setup_logging(level: str) -> None`, `def sanitize_request_id(v: str) -> str`, helpers for tests

**Acceptance Criteria (Given/When/Then):**
- Given `setup_logging("info")` and a `logging.getLogger("mcp_gway.test")` When `logger.info("hello", extra={...})` Then output line is valid JSON with `timestamp` ISO8601, `level`, `logger`, `message`, `request_id` from `request_id_ctx` if set, and no secret values in message
- Given `request_id_ctx.set("abc-123")` When formatter runs Then JSON contains `"request_id":"abc-123"`
- Given `sanitize_request_id("a\nb\r\x00" + "x"*5000)` When called Then result is `^[A-Za-z0-9_-]{1,64}$` truncated/sanitized

**Risks & Rollback:**
- Risk: double handler registration → duplicate lines → Mitigation: `setup_logging` idempotent guard (`if any(isinstance(h.formatter, JSONFormatter))`) → Rollback: revert `observability/logging.py` and remove handlers loop
- Risk: ContextVar not propagated in threadpool (sandbox) → log missing id → Mitigation: log `request_id` as extra param from `Gateway._handle_post` explicitly passed → Rollback: remove extra

**Parallelizable:** Yes — with Task 2, Task 5

- [ ] **Step 1: Write failing test for JSONFormatter + sanitize + setup_logging**

```python
from __future__ import annotations
import json, logging, io
from mcp_gway.observability.logging import JSONFormatter, request_id_ctx, sanitize_request_id, setup_logging

def test_json_formatter_shape():
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(JSONFormatter())
    lg = logging.getLogger("mcp_gway.test.shape")
    lg.handlers = [h]
    lg.setLevel(logging.INFO)
    request_id_ctx.set("r-123")
    lg.info("hello")
    line = buf.getvalue().strip()
    data = json.loads(line)
    assert "timestamp" in data and "level" in data and data["request_id"] == "r-123"
    request_id_ctx.set(None)

def test_sanitize_truncates_and_strips_crlf():
    assert "\n" not in sanitize_request_id("a\nb")
    assert len(sanitize_request_id("x"*5000)) <= 64
```

- [ ] **Step 2: Run test — expect FAIL (module not found)**

Run: `uv run pytest tests/test_observability_logging.py -v`
Expected: FAIL `ModuleNotFoundError: mcp_gway.observability`

- [ ] **Step 3: Minimal implementation — create observability package + logging.py**

```python
from __future__ import annotations
import json, logging, re, time
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
_SAN_RE = re.compile(r"[^A-Za-z0-9_-]")
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rid = getattr(record, "request_id", None) or request_id_ctx.get()
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00","Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": rid,
        }
        # merge extras without leaking secrets (only whitelisted keys)
        for k in ("method","path","status","duration_ms","server","tool"):
            if hasattr(record, k):
                payload[k] = getattr(record, k)
        return json.dumps(payload, ensure_ascii=False)
def sanitize_request_id(v: str) -> str:
    s = _SAN_RE.sub("-", v.strip())[:64]
    return s.strip("-") or "unknown"
def setup_logging(level: str) -> None:
    # idempotent: attach JSONFormatter to mcp_gway handlers if not already
    ...
```

- [ ] **Step 4: Run test — expect PASS**

Run: `uv run pytest tests/test_observability_logging.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_gway/observability/__init__.py src/mcp_gway/observability/logging.py tests/test_observability_logging.py
git commit -m "feat(observability): stdlib JSON logs + request_id ContextVar (SPEC-2026-08-26 T1)"
```

---

### Task 2: MetricsRegistry — Lightweight Prometheus Text [S] [CODE-TDD]

**Files:**
- Create: `src/mcp_gway/observability/metrics.py`
- Test: `tests/test_observability_metrics.py`

**Interfaces:**
- Consumes: `threading.Lock`, `time`
- Produces: `class MetricsRegistry` with `counter(name, help, labelnames)`, `gauge(name, help, labelnames)`, `histogram(name, help, labelnames, buckets=[0.005...5])`, `inc(name, labels_dict)`, `observe(name, value, labels)`, `set_gauge`, `exposition() -> str` (sorted, `# HELP`/`# TYPE` + samples), `reset()` for tests

**Acceptance Criteria:**
- Given registry with `counter("http_requests_total", help, ["method","path","status"])` When `inc(..., {"method":"GET","path":"/health","status":"200"})` Then `exposition()` contains `mcp_gway_http_requests_total{method="GET",path="/health",status="200"} 1`
- Given histogram observe 0.04s Then `exposition()` contains `_bucket{le="0.05"} 1` and `_sum`/`_count`
- Given high cardinality labels Then `exposition()` deterministic sorted order

**Risks & Rollback:**
- Risk: label explosion → Mitigation: caller sanitizes; registry itself optionally caps to 200 unique combos with LRU eviction (test guard) → Rollback: delete cap logic
- Risk: threading bug with asyncio → Mitigation: `Lock` per metric short-held, no await inside → Rollback: revert to single global lock

**Parallelizable:** Yes — with Task 1, Task 5

- [ ] **Step 1: Write failing test**

```python
from mcp_gway.observability.metrics import MetricsRegistry
def test_counter_exposition():
    r = MetricsRegistry()
    r.counter("http_requests_total", "Total HTTP requests", ["method","path","status"])
    r.inc("http_requests_total", {"method":"GET","path":"/health","status":"200"})
    txt = r.exposition()
    assert '# HELP mcp_gway_http_requests_total' in txt
    assert 'mcp_gway_http_requests_total{method="GET",path="/health",status="200"} 1' in txt

def test_histogram_buckets():
    r = MetricsRegistry()
    r.histogram("http_request_duration_seconds", "HTTP latency", ["path"])
    r.observe("http_request_duration_seconds", 0.04, {"path":"/health"})
    txt = r.exposition()
    assert '_bucket{path="/health",le="0.05"} 1' in txt
    assert '_count{path="/health"} 1' in txt
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_observability_metrics.py -v`
Expected: FAIL module missing

- [ ] **Step 3: Minimal implementation — metrics.py with Counter/Gauge/Histogram dict + exposition**

```python
from __future__ import annotations
import threading
...
class MetricsRegistry:
    def counter(self, name, help, labelnames): ...
    def inc(self, name, labels):  # prefix mcp_gway_
    def exposition(self) -> str: ...
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/test_observability_metrics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_gway/observability/metrics.py tests/test_observability_metrics.py
git commit -m "feat(observability): lightweight MetricsRegistry Prometheus text (SPEC-2026-08-26 T2)"
```

---

### Task 3: Middlewares + Health Aggregator + 4 Probes [M] [CODE-TDD]

**Files:**
- Create: `src/mcp_gway/observability/middleware.py`
- Create: `src/mcp_gway/observability/health.py`
- Modify: `src/mcp_gway/gateway.py` — add `start_time`, `_last_loop_tick`, mount `GET /health|/ready|/live|/metrics`, wire middlewares in order Correlation→Metrics→Logging→CSP/Security/CSRF, expose `app.state.metrics` and `app.state.request_id_ctx`
- Test: `tests/test_observability_probes.py`

**Interfaces:**
- Consumes: `MetricsRegistry`, `request_id_ctx`, `Registry`, `Gateway`
- Produces: `CorrelationMiddleware`, `MetricsMiddleware`, `LoggingMiddleware`, `handle_health/handle_ready/handle_live/handle_metrics` (async Request -> Response), `check_registry`, `check_routes`, normalized `path_template(path) -> template` (`/api/servers/{name}`)

**Acceptance Criteria:**
- Given `Gateway(registry, host="127.0.0.1")` When `GET /health` via TestClient Then `200` contains `status:ok` + `version` + `uptime_seconds` + `checks`, and response header `X-Request-ID` present echoing supplied `X-Request-ID: test123`
- Given `GET /ready` with mocked `registry.list` raising Then `503 {"status":"not_ready"}` with `checks.registry="fail"`
- Given `GET /live` Then `200 {"status":"alive"}` <5ms and not calling registry
- Given `GET /metrics` Then `200 text/plain` with `# HELP mcp_gway_http_requests_total`
- Given any request Then JSON log line valid JSON with same `request_id`

**Risks & Rollback:**
- Risk: middleware order wrong → X-Request-ID missing in metrics/logs → Mitigation: integration test checks order via `gateway.app.user_middleware` inspection → Rollback: reorder adds in gateway.py
- Risk: path cardinality — concrete name in metrics → Mitigation: `path_template` normalizes `/api/servers/anything` → `.../{name}` → Rollback: revert mapping

**Parallelizable:** No — needs T1+T2

- [ ] **Step 1: Write failing tests for probes + correlation + metrics**

```python
from starlette.testclient import TestClient
from mcp_gway.gateway import Gateway
from mcp_gway.registry import Registry
def test_health_and_correlation_echo(tmp_path):
    reg = Registry(servers_dir=tmp_path/"servers")
    gw = Gateway(reg, host="127.0.0.1")
    c = TestClient(gw.app)
    r = c.get("/health", headers={"X-Request-ID":"test123"})
    assert r.status_code==200
    assert r.headers["X-Request-ID"]=="test123"
    assert r.json()["status"]=="ok"
def test_ready_503_on_registry_fail(tmp_path, monkeypatch):
    ...
def test_metrics_exposition(tmp_path):
    reg = Registry(servers_dir=tmp_path/"servers")
    gw = Gateway(reg); c=TestClient(gw.app)
    c.get("/health"); m=c.get("/metrics")
    assert m.status_code==200
    assert "# HELP mcp_gway_http_requests_total" in m.text
```

- [ ] **Step 2: Run — expect FAIL (routes not mounted)**

Run: `uv run pytest tests/test_observability_probes.py -v`
Expected: FAIL 404 /health

- [ ] **Step 3: Implement middleware.py + health.py + gateway wiring**

- `middleware.py`: Correlation (sanitize, ctx set, header echo), Metrics (perf_counter, inc counter+histogram with normalized path), Logging (JSON access log via JSONFormatter)
- `health.py`: `check_registry`, `check_routes`, handlers returning JSONResponse + CSP headers, uptime from `gateway.start_time`
- `gateway.py`: `self.start_time = time.monotonic()`, `self.metrics = MetricsRegistry()`, `self.app.state.metrics = self.metrics`, add routes for `/health|/ready|/live|/metrics`, add middlewares outer→inner (Correlation first), heartbeat task `_last_loop_tick`

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/test_observability_probes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_gway/observability/middleware.py src/mcp_gway/observability/health.py src/mcp_gway/gateway.py tests/test_observability_probes.py
git commit -m "feat(observability): correlation+metrics+logging middlewares + /health|/ready|/live|/metrics (SPEC-2026-08-26 T3)"
```

---

### Task 4: Instrumentation — Gateway / MCP Client / Sandbox / Registry [M] [CODE-TDD]

**Files:**
- Modify: `src/mcp_gway/gateway.py` — `_handle_post`/`_handle_method` instrument `mcp_tool_calls_total`, `gateway_sessions_active` gauge
- Modify: `src/mcp_gway/server_proxy.py` — `call_tool` wrapper counts
- Modify: `src/mcp_gway/sandbox.py` — `execute()` counts `sandbox_execute_total{status}` + `sandbox_duration_seconds`
- Modify: `src/mcp_gway/registry.py` — `add/remove/update/patch_enabled` increment `registry_operations_total{op}`
- Modify: `src/mcp_gway/core/client.py` if exists or `gateway discovery` path — `discovery_duration_seconds` histogram
- Test: `tests/test_observability_instrumentation.py`

**Interfaces:**
- Consumes: `MetricsRegistry` via `gateway.metrics` passed through `app.state.metrics` or imported singleton; `request_id_ctx` for log extra
- Produces: No new public API — side-effects: metrics increments, JSON logs with `server`/`tool` fields, no secret leakage

**Acceptance Criteria:**
- Given `Gateway._handle_post` with `tools/call` When called Then `mcp_gway_mcp_tool_calls_total{server="gh",tool="search",status="ok"} 1` in `/metrics`
- Given `StarlarkSandbox.execute("result='x'")` and failing/timeout variant Then `sandbox_execute_total{status="ok"|"error"|"timeout"}` increments and duration histogram observed
- Given `registry.add(config, [])` Then `registry_operations_total{op="add"} 1` in metrics and JSON log contains `server` but not secret values

**Risks & Rollback:**
- Risk: metrics access from sync `registry.add` (no request_id) → Mitigation: use thread-local registry singleton or `gateway.metrics` global fallback; log without request_id is ok → Rollback: guard with `hasattr(app.state, "metrics")`
- Risk: label injection via server name → Mitigation: sanitize to `^[A-Za-z0-9_]{1,32}$` with `re.sub(r'[^A-Za-z0-9_]', '_', name)[:32]` + cap → Rollback: revert sanitize

**Parallelizable:** No — needs T3

- [ ] **Step 1: Write failing instrumentation tests**

```python
def test_tool_call_increments_metric(tmp_path):
    reg = Registry(servers_dir=tmp_path/"servers")
    gw = Gateway(reg); c=TestClient(gw.app)
    # mock code_mode to avoid real tool, call via _handle_post
    ...
    txt = c.get("/metrics").text
    assert 'mcp_gway_mcp_tool_calls_total' in txt

def test_sandbox_metrics(tmp_path):
    from mcp_gway.sandbox import StarlarkSandbox
    ...
def test_registry_metrics(tmp_path):
    ...
```

- [ ] **Step 2: Run — expect FAIL (counters missing)**

Run: `uv run pytest tests/test_observability_instrumentation.py -v`
Expected: FAIL assert metrics missing

- [ ] **Step 3: Implement instrumentation hooks (guarded by MetricsRegistry existence)**

- `server_proxy.py`: wrap `call_tool` try/except to inc counter with `status="ok|error"` + observe discovery duration via `app.state.metrics` if present.
- `sandbox.py`: `with time.perf_counter()` then `inc` status buckets.
- `registry.py`: accept optional `metrics: MetricsRegistry|None` param or lazy lookup via `import` of singleton; simplest: increment via `logging` + attempt `from mcp_gway.observability.metrics import global_registry` fallback without hard coupling (or pass `metrics` from `Gateway` by monkeypatching `Registry.add` wrappers).

- [ ] **Step 4: Run — expect PASS** (may need to expose `gateway.metrics` as module-level singleton for import)

Run: `uv run pytest tests/test_observability_instrumentation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_gway/gateway.py src/mcp_gway/server_proxy.py src/mcp_gway/sandbox.py src/mcp_gway/registry.py tests/test_observability_instrumentation.py
git commit -m "feat(observability): instrument gateway+sandbox+registry counters+histograms (SPEC-2026-08-26 T4)"
```

---

### Task 5: Dashboard Ops Card — Health Surfacing (htpy) [S] [CODE-TDD]

**Files:**
- Modify: `src/mcp_gway/dashboard/views.py` — add `ops_card(health: dict, metrics_summary: dict)`, `health_badge(status)`, extend `layout(servers, warning_banner, health?)` to render ops section with `max-w-6xl mx-auto` Tailwind, `hx-get="/api/health"` polling optional, status dot classes reused from `_DOT_COLORS`
- Modify: `src/mcp_gway/dashboard/api.py` — add `GET /api/health` JSON handler (reuses `health.check_registry` + metrics snapshot) and `handle_dashboard` passes health to layout
- Test: `tests/test_dashboard_ops.py` (or extend `test_dashboard_views`)

**Interfaces:**
- Consumes: `health` dict `{status, checks, uptime_seconds, version}`, `metrics_summary` optional `{requests_total, p95_ms}`
- Produces: `htpy` fragment `ops_card` with `id="ops-card"`, badge color mapping `healthy→emerald`, `degraded→amber`, `not_ready→red`, `aria-label`, polling `hx-get`

**Acceptance Criteria:**
- Given `GET /dashboard` When registry healthy Then HTML contains `id="ops-card"` and `healthy` badge and `Uptime` text and `X-Request-ID` header in response
- Given `GET /api/health` Then `200 {status, checks}` JSON masked (no secrets), and `HX-Request:true` returns `text/html` fragment
- Given `GET /dashboard` with `host != 127.0.0.1` Then banner amber + metrics card still masks secrets

**Risks & Rollback:**
- Risk: mixing dashboard JSON + htpy fragment breaks CSP → Mitigation: reuse `_csp_headers()` in api handler → Rollback: drop fragment branch
- Risk: Tailwind class drift → Mitigation: reuse existing `_BASE_BADGE` + `_DOT_COLORS` → Rollback: simple `span` fallback

**Parallelizable:** Yes — can start with T1||T2, final integration needs T3's `health.check_registry`

- [ ] **Step 1: Write failing view tests**

```python
def test_dashboard_ops_card_renders(tmp_path):
    from mcp_gway.dashboard.views import ops_card
    html = str(ops_card({"status":"ok","checks":{"registry":"ok"},"uptime_seconds":10}, {"requests_total":5}))
    assert 'id="ops-card"' in html
    assert 'healthy' in html.lower()
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/test_dashboard_ops.py -v`
Expected: FAIL `ImportError: cannot import ops_card`

- [ ] **Step 3: Implement views.py ops_card + api.py /api/health handler + routes.py mount**

```python
def ops_card(health, metrics_summary=None):
    badge_state = "healthy" if health.get("status")=="ok" else "unreachable"
    return htpy.section(id="ops-card", class_="rounded-2xl border border-slate-200 ...")[
        htpy.div(class_="flex items-center gap-2")[ badge(badge_state), ...],
        htpy.p(class_="text-xs")[ f"Uptime {health.get('uptime_seconds')}s" ]
    ]
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/test_dashboard_ops.py tests/test_dashboard_views.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_gway/dashboard/views.py src/mcp_gway/dashboard/api.py src/mcp_gway/dashboard/routes.py tests/test_dashboard_ops.py
git commit -m "feat(dashboard): ops card health badges htpy + /api/health (SPEC-2026-08-26 T5)"
```

---

### Task 6: Docs, Gates & Verification — README + ruff/pytest + >15 tests aggregate [S] [INFRA]

**Files:**
- Modify: `README.md` — add Observability section with `curl` one-liners for `/health|/ready|/live|/metrics` + `X-Request-ID` + dashboard ops card screenshot note
- Modify: `docs/specs/SPEC-2026-08-26-observability-design.md` if DoD updates
- Test: aggregate `tests/test_observability_*.py` — ensure >15 new tests total counting T1-T5; add `tests/test_observability_e2e.py` with 3 integration checks if needed
- Verify: `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/` and `uv run pytest -v` ≥201 tests green

**Interfaces:**
- Consumes: all prior tasks
- Produces: `README.md` observability docs, CI parity proofs

**Acceptance Criteria:**
- Given `uv run ruff check src/ tests/` When run Then exit 0
- Given `uv run pytest -v` Then ≥201 tests pass (186 + >15)
- Given `README.md` Then contains `curl -s http://127.0.0.1:8080/metrics | head` and notes masking local-first preserved
- Given `curl -H "X-Request-ID: demo" http://127.0.0.1:8080/health -D -` Then response header echo and JSON log line in `capsys`/`caplog` contains `demo`

**Risks & Rollback:**
- Risk: README drift from spec → Mitigation: copy-paste contracts table from §5 verbatim → Rollback: `git checkout HEAD -- README.md`
- Risk: ruff flags due to new imports → Mitigation: run `ruff check --fix` before commit → Rollback: `ruff` ignore only if justified with `noqa` comment referencing Spec ID

**Parallelizable:** No — needs T1-T5 done

- [ ] **Step 1: Write/validate docs + aggregate test count gate**

```bash
uv run pytest tests/test_observability*.py -v
# expect >=15 passed
grep -c "curl" README.md
```

- [ ] **Step 2: Run ruff & pytest full gates**

Run: `uv run ruff check src/ tests/` then `uv run ruff format --check src/ tests/` then `uv run pytest -q`
Expected: all 0 / PASS

- [ ] **Step 3: Verify manual curl one-liners (TestClient level)**

Run: `uv run pytest tests/test_observability_e2e.py -v` (or inline `python -c "from starlette.testclient import TestClient; ..."`) to print `/health` JSON, `/metrics` head, header echo proof

- [ ] **Step 4: Commit (and push if allowed)**

```bash
git add README.md tests/test_observability_e2e.py docs/specs/SPEC-2026-08-26-observability-design.md
git commit -m "docs(observability): README curl gates + verification >15 tests ruff clean (SPEC-2026-08-26 T6)"
```

---

## Coverage Matrix
| Spec Req (ID) | Description | Task(s) | Status |
|---------------|-------------|---------|--------|
| R1 / BR-OBS-001 | JSON logs stdlib, request_id enrichment, sanitize, setup_logging | T1 | ✅ |
| R2 / BR-OBS-002 | Correlation middleware X-Request-ID echo + ContextVar | T3 (needs T1) | ✅ |
| R3 / BR-OBS-003 | MetricsRegistry vendored Prometheus text, <200 LOC | T2 | ✅ |
| R4 / BR-OBS-004 | Health aggregator /health (compat) + /ready (503) + /live | T3 | ✅ |
| R5 / BR-OBS-005 | Metrics catalog counters/histograms, bounded labels templated path | T2,T3,T4 | ✅ |
| R6 / BR-OBS-006 | Local-first gating for /metrics + no secret leak | T3,T4 | ✅ |
| R7 / BR-OBS-007 | No breaking MCP/SSE, headers additive | T3,T4 | ✅ |
| R8 / BR-OBS-008 | Dashboard ops card htpy + /api/health | T5 | ✅ |
| R9 / BR-OBS-009 | Threading.Lock bounded context, atomic registry invariant | T2,T4 | ✅ |
| R10 / AC-OBS-01..08 | All 8 acceptance probes (health/ready/live/metrics/correlation/instrumentation/masking/dashboard/no-regression) | T3,T4,T5,T6 | ✅ |
| NFR-OBS-01..07 | Latency <2ms, availability, correctness, security, operability gates | T3,T6 | ✅ |

No gaps — every BR/AC maps to a task.

## Self-Review

**1. Spec coverage:** Coverage matrix checked — every BR-OBS-001..010 and AC-OBS-01..08 mapped; no uncovered R. Extra NFRs covered by T6 gates.

**2. Placeholder scan:** No TBD/TODO/"implement later"/"handle edge cases" without code — all steps have concrete test code + impl snippets + exact `uv run` commands.

**3. Type consistency:** `MetricsRegistry.counter/exposition`, `health.check_registry(registry: Registry)`, `path_template`, `request_id_ctx: ContextVar[str|None]`, `ops_card(health: dict, metrics_summary)` signatures consistent across T2→T3→T4→T5 Consumes/Produces.

**4. DAG sanity:** Acyclic: T1,T2,T5 start → T3 joins them → T4 needs T3 → T6 needs all. Parallelizable marks correct (T1||T2||T5). No forward dependency.

**5. Sizing:** 6 tasks, ~30 steps (<40), each S/M sized; fits 5-8 task hard limit. Independent buildable: T1 and T2 each produce importable module with tests; T3 produces shippable Gateway with probes even without instrumentation; T5 view testable pure function.

Fixes applied inline — none pending.
