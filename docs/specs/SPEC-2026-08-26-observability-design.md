# SPEC-2026-08-26 — Observability Design (Hybrid Pragmatic — Approach C)

## Status: Approved (CEO GO Act 1+2) — Binding
## Version: 0.8.0-draft — 2026-08-26
## Author: Vasquez (Senior CTO Orchestrator) — Domain Oracle
## Stack Decision: stdlib JSON logs + lightweight MetricsRegistry + correlation middleware + /health|/ready|/live|/metrics
## Scope: MCP Gateway (Python 3.12+, Starlette+uvicorn, htpy, Tailwind vendored, no Node)
## Cross-ref: SPEC-UI-001 v0.7.0 GA, ADR-007 release hybrid, AGENTS.md Hard constraints

---

### 1 — Objective & Business Rationale

Unblock **observability without vendor lock-in**, preserving local-first trust for GA.

- Provide **structured JSON logs** (stdlib only), **Prometheus-text metrics** via a vendored `MetricsRegistry`, **correlation IDs** per request, and **health probes** (`/health`, `/ready`, `/live`, `/metrics`) so an operator on `127.0.0.1` — or an orchestrator polling from outside — can diagnose failures without enabling remote auth.
- Keep MCP/SSE contract 100% intact, dashboard remains `htpy` only, no `package.json`, no DB, no breaking CLI.
- Business win: reduces MTTR for “no tools discovered / OAuth 401 / sandbox timeout” from “grep the terminal” to “curl health+metrics or glance dashboard ops card”.

**Done iff**: operator can `curl /health|/ready|/live|/metrics` and correlate any request via `X-Request-ID` in both response header and JSON log line; dashboard surfaces health; 186 existing tests stay green + >15 new observability tests; `ruff` clean.

---

### 2 — Actors & Scopes

| Actor | Role | Interaction |
|-------|------|-------------|
| **Operador Local** | Dev/Admin on `127.0.0.1` | Browser dashboard, `curl /metrics`, log tail |
| **Orchestrator / K8s probe** | External checker | Polls `/live` (process up) and `/ready` (can serve) |
| **Gateway (Starlette)** | Single process `:8080` | Hosts MCP + Dashboard + observability routes/middlewares |
| **Registry** | FS source `servers/*.json+*.pyi` | Checked by `/ready` aggregator |
| **Upstream MCP Servers** | Remote (HTTP/SSE/streamable) + local (stdio) | Instrumented via `mcp/client` + `sandbox` for counts/latency |
| **MetricsRegistry** | In-process ledger | Counters/Histograms/Gauges, rendered as Prometheus text at `/metrics` |

Scope is **gateway process observability only** — no per-tool tracing, no OpenTelemetry exporter, no remote log shipper (out of scope, see §10).

---

### 3 — Business Rules

| ID | Rule | Priority |
|----|------|----------|
| **BR-OBS-001** | Structured logs = JSON per line via `logging` + `json` stdlib only. No `structlog`/`loguru` deps. Schema: `timestamp, level, logger, message, request_id, method, path, status, duration_ms, server, tool` where relevant. PII/secrets never logged; masking `***` invariant preserved. | **P0** |
| **BR-OBS-002** | Correlation is mandatory: every HTTP request gets `request_id = X-Request-ID` (or `X-Correlation-ID` if supplied, else `uuid4`). Middleware echoes `X-Request-ID` in response and binds to `contextvars` for log enrichment + `Gateway._handle_post` correlation. | **P0** |
| **BR-OBS-003** | MetricsRegistry is **vendored, zero-dep**: primitives `Counter`, `Gauge`, `Histogram` (buckets `[0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2.5,5]`). Name prefix `mcp_gway_` + Prometheus `# HELP`/`# TYPE`. Render at `GET /metrics` as `text/plain; version=0.0.4`. | **P0** |
| **BR-OBS-004** | Health aggregator: `/health` = legacy compatibility `{"status":"ok"}` plus new fields; `/live` = liveness (process up, event loop not blocked); `/ready` = readiness (checks Registry readable, no deadlock, dashboard routes mounted). `200` when ready, `503` with `{"status":"not_ready","checks":{...}}` otherwise. | **P0** |
| **BR-OBS-005** | Instrumentation points (no cardinality explosion): `http_requests_total{method,path,status}`, `http_request_duration_seconds` histogram, `mcp_tool_calls_total{server,tool,status}`, `mcp_discovery_duration_seconds`, `sandbox_execute_total{status}`, `sandbox_duration_seconds`, `registry_operations_total{op}`, `gateway_sessions_active` gauge, `dashboard_rare_errors_total`. Label values are bounded (path is route template `/api/servers/{name}`, not concrete name; server label sanitized `[^A-Za-z0-9_]` → `_`). | **P0** |
| **BR-OBS-006** | `/metrics` is **local-first gated like reveal**: on non-loopback without `MCP_GWAY_ALLOW_REMOTE=1`, process already refuses to bind; if somehow exposed, `/metrics` returns `403` plus `X-Warning: exposed` and logs `exposed_metrics_request`. Secrets still masked; `/metrics` never leaks header values. | **P0 Security** |
| **BR-OBS-007** | No breaking MCP/SSE: `POST /mcp` & `GET /mcp (SSE)` semantics unchanged; added headers (`X-Request-ID`) are additive. Discovery timeout + transport auto-detect unchanged. Dashboard `htpy` remains only HTML engine. | **P0** |
| **BR-OBS-008** | Dashboard ops card is **read-only view** over Gateway metrics+health; it polls `/api/health` (or `/health` JSON) and renders badges `healthy/degraded/not_ready` with last check timestamp + latency p95 from metrics. No direct FS I/O outside Registry. | **P1** |
| **BR-OBS-009** | Atomicity & concurrency: `MetricsRegistry` uses `threading.Lock` per metric (process is single-threaded asyncio + threadpool for sandbox; lock is cheap). Writes to `servers/` remain atomic via `Registry._atomic_write_text`. | **P1** |
| **BR-OBS-010** | Type hints + `from __future__ import annotations` on all new modules; `ruff` clean is gate. | **P1 Hard** |

---

### 4 — Architecture & Design (Approach C — Hybrid Pragmatic)

**Decision: stdlib JSON logs + MetricsRegistry + correlation middleware + 4 probes**

```
┌──────────────────────────────────────────────────────────────────────┐
│ Gateway (Starlette) — Single Process :8080                           │
│ ┌────────────────┐  ┌─────────────────────┐  ┌──────────────────┐   │
│ │ MCP (existing) │  │ Dashboard (htpy)    │  │ Observability    │   │
│ │ POST /mcp      │  │ GET /dashboard      │  │ GET /health      │   │
│ │ GET /mcp (SSE) │  │ GET /api/servers    │  │ GET /ready  ─┐   │   │
│ │                │  │ Ops card (new)      │  │ GET /live   ─┤   │   │
│ └────────────────┘  └─────────────────────┘  │ GET /metrics   │   │
│                                              └──────────────────┘   │
│  Middlewares (order outer→inner):                                    │
│   1. CorrelationMiddleware (uuid, echo X-Request-ID)                  │
│   2. MetricsMiddleware (counter+histogram, status from response)      │
│   3. LoggingMiddleware (JSON access log, duration_ms)                 │
│   4. _CSP / _SecurityHeaders / _CSRF (existing)                       │
│                                                                      │
│  Registry (FS) ◄─ health aggregator checks readability ─┐            │
│  mcp/client ─instrumented─► MetricsRegistry ◄─ sandbox ◄┘            │
│  MetricsRegistry ─exposition─► /metrics (Prometheus text)             │
│  ContextVar request_id ─enrichment─► JSON logs                        │
└──────────────────────────────────────────────────────────────────────┘
```

**Folder (Screaming Architecture):**

```
src/mcp_gway/
├── observability/
│   ├── __init__.py
│   ├── logging.py      # JSONFormatter, setup_logging(), request_id ContextVar
│   ├── metrics.py      # MetricsRegistry, Counter/Gauge/Histogram, exposition
│   ├── middleware.py   # CorrelationMiddleware + MetricsMiddleware + LoggingMiddleware
│   └── health.py       # health aggregator (liveness, readiness, checks)
├── dashboard/
│   ├── views.py        # + ops_card(), health badge helpers (htpy only)
│   └── api.py          # + handle_health_detail shim if needed (still masked)
├── gateway.py          # mounts new routes, registers middlewares (outer order)
├── server_proxy.py     # instrument tool calls
├── sandbox.py          # instrument execute()
└── cli.py              # log-level wiring (reuse _resolve_log_level)
```

**Why Approach C wins (ADR-009 sketch):**

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| A — Full OTel + Prometheus client dep | Rich ecosystem, exemplars | Heavy dep, vendor coupling, Node-like bloat, violates “stdlib first” | Rejected — premature lock-in |
| B — Minimal (only /health) | Tiny | Not enough to debug “no tools”, no correlation, no latency signal | Rejected — fails business MTTR goal |
| **C — Hybrid pragmatic** | Zero new prod deps, JSON logs stdlib, lightweight registry (<200 LOC), Prometheus text without client lib, correlation via `contextvars`, health aggregator split liveness/readiness | Manual exposition (no prom lib) | **Chosen** — CEO Act 1+2 |

**Data structures & complexity:**

- `MetricsRegistry` stores `dict[str, _Metric]` where `_Metric` is `Counter(Map label-tuple → int)`, `Histogram(Map label-tuple → bucket_counts+sum+count)`. Lookup `O(1)` average via `dict`. Label cardinality bounded → memory `O(metrics * label_combos)` small (<100 combos). Histogram observe is `O(buckets)` linear 10 buckets — negligible. Chosen over `list` scan `O(n)` or naive `array` without labels.
- `request_id` via `contextvars.ContextVar[str]` — constant-time propagation across `async` tasks, no thread-local leakage.
- Health checks are sequential, each `O(1)` FS `exists()`/`list()` → total `O(k)` with `k~3` checks, <5ms.

---

### 5 — Contracts — Endpoints & Headers

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| `GET` | `/health` | `200 {"status":"ok","version":"x.y.z","checks":{"registry":"ok","dashboard":"ok"},"uptime_seconds":123}` | Backward compat: still contains `status:ok`. Adds `checks`. Fast (<10ms), no discovery. |
| `GET` | `/ready` | `200 {"status":"ready","checks":{...}}` or `503 {"status":"not_ready",...}` | Readiness for orchestrator. Checks: `registry_readable`, `event_loop_not_blocked` (heuristic), `routes_mounted`. |
| `GET` | `/live` | `200 {"status":"alive","uptime_seconds":123}` or `503` only if loop truly dead | Liveness — lightweight, no FS I/O beyond pid check. ` <5ms`. |
| `GET` | `/metrics` | `200 text/plain; version=0.0.4` Prometheus exposition | Local-first gated. Example lines: `# HELP mcp_gway_http_requests_total Total HTTP requests` etc. No secrets. |
| **Headers** | `X-Request-ID` | Echoed on **every** response; `X-Correlation-ID` accepted as input alias | Middleware generates `uuid4().hex` if absent |
| `GET` | `/api/health` | `200 {status, checks, metrics_summary}` JSON for dashboard ops card | Consumed by `htmx` polling; secrets masked |

**Prometheus metrics (initial catalog):**

```
# HELP mcp_gway_http_requests_total Total HTTP requests
# TYPE mcp_gway_http_requests_total counter
mcp_gway_http_requests_total{method="GET",path="/health",status="200"} 42
# HELP mcp_gway_http_request_duration_seconds HTTP request latency
# TYPE mcp_gway_http_request_duration_seconds histogram
mcp_gway_http_request_duration_seconds_bucket{path="/api/servers",le="0.05"} 10
...
# HELP mcp_gway_mcp_tool_calls_total MCP tool call count by server/tool/status
# HELP mcp_gway_discovery_duration_seconds Discovery latency
# HELP mcp_gway_sandbox_execute_total Sandbox executions
# HELP mcp_gway_gateway_sessions_active Current SSE sessions (gauge)
# HELP mcp_gway_registry_operations_total Registry add/remove/update counts
```

**Logging contract (JSON per line, stdout):**

```json
{"timestamp":"2026-08-26T12:00:00.123Z","level":"INFO","logger":"mcp_gway.gateway","message":"request completed","request_id":"a3f1...","method":"POST","path":"/api/servers","status":201,"duration_ms":42,"server":"gh"}
{"timestamp":"...","level":"WARNING","logger":"mcp_gway.dashboard.api","message":"discovery saturated","request_id":"...","server":"gh"}
```

Never log header values, `clientSecret`, `environment` values. Audit log on `reveal` records `server` + `request_id` + `field` only.

---

### 6 — Data Models & Modules

**`observability/logging.py`**
- `request_id_ctx: ContextVar[str|None]`
- `class JSONFormatter(logging.Formatter)` → `json.dumps(record.__dict__ filtered + contextvar)`; `timestamp` as ISO8601 UTC with `time.time_ns()`.
- `def setup_logging(level: str) -> None` — attaches `JSONFormatter` to `mcp_gway` handlers if not already, idempotent, respects `cli._resolve_log_level`.

**`observability/metrics.py`**
- `class MetricsRegistry` with `counter(name, help, labelnames)`, `gauge`, `histogram(name, help, labelnames, buckets)`, `inc/observe/set`, `exposition() -> str` (renders Prometheus text sorted deterministically). Thread-safe via `Lock`.
- Typed `from __future__ import annotations` everywhere.

**`observability/middleware.py`**
- `class CorrelationMiddleware(BaseHTTPMiddleware)` — read `X-Request-ID`/`X-Correlation-ID`, set `ctx`, set response header, also set `request.state.request_id`.
- `class MetricsMiddleware(BaseHTTPMiddleware)` — `start = time.perf_counter()`, `await call_next`, then `registry.counter(...).inc` and `histogram.observe(duration)`. Path is normalized via `request.url.path` template mapping (naive: replaces `/api/servers/<anything>` → `/api/servers/{name}` to bound cardinality).
- `class LoggingMiddleware(BaseHTTPMiddleware)` — JSON access log at `INFO` with `duration_ms`.

Order is critical: Correlation outermost so inner middlewares see `request_id`.

**`observability/health.py`**
- `async def check_registry(registry: Registry) -> tuple[str,str]` → try `registry.list()` + read one config, return `("ok","")` or `("fail",reason)`.
- `def check_routes(app: Starlette) -> ...`
- `async def handle_health(request)`, `handle_ready`, `handle_live` — all <10ms, health aggregator returns `503` if any check fails. Uptime from `gateway.start_time` (`time.monotonic()` at init).

**Instrumentation hooks:**
- `gateway.Gateway._handle_post` → `metrics.counter("mcp_tool_calls_total").inc(server, tool, status)` + log with `request_id`.
- `server_proxy.ServerProxy.call_tool` / `core.client.discover_tools` → discovery histogram.
- `sandbox.StarlarkSandbox.execute` → `sandbox_execute_total{status=ok|error|timeout}` + duration histogram; errors logged without code dump beyond 500 chars.
- `registry.Registry.add/remove/update` → `registry_operations_total{op}`.

---

### 7 — Edge Cases & Failure Modes

| # | Case | Expected |
|---|------|----------|
| EC-OBS-01 | `GET /metrics` from non-loopback without `MCP_GWAY_ALLOW_REMOTE=1` | Gateway would have exited at `serve` pre-check; if route still hit, return `403 {"detail":"metrics not exposed"}` + `X-Warning: exposed`, audit log |
| EC-OBS-02 | `X-Request-ID` supplied by client contains CRLF / 8KB | Sanitize: `[^A-Za-z0-9_-]` filtered, truncate to 64 chars, else ignore and generate uuid |
| EC-OBS-03 | Metrics label value is user-controlled `name` with high cardinality (1000 servers) | Path template normalization + server label `re.sub(r'[^A-Za-z0-9_]', '_', name)[:32]` caps cardinality; overflow goes to `"_other"` bucket after 200 unique labels (eviction LRU) |
| EC-OBS-04 | `registry.list()` throws during `/ready` | `/ready` returns `503` with `checks.registry = "fail: <type>"`, does not throw 500; `/live` still 200 |
| EC-OBS-05 | Sandbox timeout | Increment `sandbox_execute_total{status="timeout"}` + log `level=WARN` with `duration_ms`, no stack trace of user code |
| EC-OBS-06 | Event loop blocked (>2s) — readiness heuristic | `/ready` checks last `Gateway._last_loop_tick` (updated by `asyncio.create_task` heartbeat every 1s); if drift >3s → `not_ready` |
| EC-OBS-07 | Log volume high (1000 rps) | JSON formatter is sync but cheap; no `await` in log path; metrics histogram is `O(buckets)`; no allocation per request beyond dict lookup |
| EC-OBS-08 | `/health` called concurrently with `refresh` background discovery | No lock contention; discovery semaphore (3) unchanged; health is sync FS only |
| EC-OBS-09 | Dashboard polls `/api/health` with `HX-Request:true` | Content negotiation: `HX-Request` → fragment `ops_card` HTML; else JSON |
| EC-OBS-10 | `registry_operations_total` incremented on failed add (validation) | Do not increment; only on successful `registry.add` |

---

### 8 — Constraints HARD (Non-Negotiable)

| ID | Constraint |
|----|------------|
| HC-OBS-01 | Python 3.12+, Starlette+uvicorn, htpy only. No Jinja2/React/Vue/Node. Tailwind vendored untouched. |
| HC-OBS-02 | No new production dependencies: stdlib `json`, `logging`, `contextvars`, `time`, `uuid` plus existing `starlette`/`htpy` only. `prometheus_client` is **forbidden**. |
| HC-OBS-03 | `uv`/`mise` workflow unchanged; `ruff check` + `ruff format --check` must pass. Type hints + `from __future__ import annotations`. |
| HC-OBS-04 | Local-first preserved: `serve --host 127.0.0.1` default, `MCP_GWAY_ALLOW_REMOTE=1` gating unchanged; secret masking `***` never regresses; logs never contain secrets. |
| HC-OBS-05 | No breaking MCP/SSE: `POST /mcp`, `GET /mcp`, `POST /mcp/messages?session_id=` unchanged externally; added headers are additive. |
| HC-OBS-06 | Registry atomic I/O invariant: `Registry` remains sole FS writer for `servers/*.json+*.pyi`; observability never writes to Registry. |
| HC-OBS-07 | Bounded labels + sanitized paths only; metrics exposition <10KB at typical <20 servers. |
| HC-OBS-08 | Tests: 186 existing green + >15 new observability tests (health probes, metrics exposition, correlation header, JSON log shape, masking). |

---

### 9 — Non-Functional Requirements

| ID | NFR | Measurable |
|----|-----|------------|
| NFR-OBS-01 | Latency overhead | Added middleware <2ms p95 per request (perf_counter measured); `/health` <10ms, `/metrics` <15ms, `/live` <5ms local |
| NFR-OBS-02 | Availability | `/health`, `/live`, `/ready` never throw 500; Degraded registry → 503 with body, Gateway still serves MCP+SRE probes |
| NFR-OBS-03 | Correctness | `X-Request-ID` echo on 100% responses; JSON logs are valid JSON per line; Prometheus exposition parses with `promtool check metrics` mental model |
| NFR-OBS-04 | Observability completeness | Every HTTP status counted; every MCP tool call counted; every sandbox execute counted; every registry mutation counted |
| NFR-OBS-05 | Security | Secrets masked in JSON logs + `/metrics` + dashboard; reveal audit log contains no values; CSP unchanged |
| NFR-OBS-06 | Operability | `uv run ruff check` 0; `uv run pytest -q` 0 failures; `curl` one-liners documented in README |
| NFR-OBS-07 | Maintainability | `observability/` is a bounded context with ports: `MetricsRegistry` is a Value Object with explicit exposition, not a global singleton if possible (injected via `Gateway` + `app.state.metrics`) |

---

### 10 — Dependencies, Risks, Out of Scope & Acceptance

**Dependencies:**
```
starlette>=1.6  (already)
uvicorn>=0.52   (already)
htpy>=26.5      (already, for ops card)
python stdlib only for logging/metrics (json, logging, contextvars, threading)
```

**Risks & Mitigations:**
- Risk: prometheus text hand-rolled has formatting bug → Mitigation: exposition snapshot tests vs. regex (`^# HELP`, `^mcp_gway_`) + `ruff` + literal string compare.
- Risk: log volume floods stdout in prod → Mitigation: `setup_logging` respects `MCP_GWAY_LOG_LEVEL`; default `info` in dev, `warning` in prod (`cli._resolve_log_level` env mapping).
- Risk: label cardinality DoS → Mitigation: template normalization + sanitization + cap (see EC-OBS-03).
- Risk: middleware order wrong → Mitigation: explicit test asserts `CorrelationMiddleware` is outermost via `gateway.app.user_middleware` inspection.

**Out of Scope (explicitly NOT in 0.8.0):**
- OpenTelemetry traces/spans, Jaeger export, `prometheus_client` dep, Grafana dashboards, remote log shipping, per-tool input_schema tracing, cluster multi-node aggregation, RBAC/auth for `/metrics` beyond local-first, auto-provisioned TLS.

**Acceptance Criteria (BINDING, traceable to SCENARIOS-OBS-001):**

| AC | Criteria | Evidence |
|----|----------|----------|
| AC-OBS-01 | `GET /health` returns `200 {status:"ok",checks,version,uptime_seconds}` and `GET /ready` ready/not_ready semantics with `503` on injected registry failure | `tests/test_observability.py::test_health_ok`, `test_ready_not_ready_on_registry_fail` |
| AC-OBS-02 | `GET /live` returns `200 {status:"alive"}` <5ms, never calls registry | `test_live_always_alive` + timing assert |
| AC-OBS-03 | `GET /metrics` returns `text/plain` with `# HELP mcp_gway_http_requests_total` and at least `http_requests_total` + `http_request_duration_seconds_bucket` plus server/tool counters after one tool call | `test_metrics_exposition` |
| AC-OBS-04 | Every HTTP response includes `X-Request-ID` equal to request's header or generated `uuid4`; JSON log line for same request contains same `request_id` and valid JSON, no secret values | `test_correlation_header_echo`, `test_json_log_shape` (caplog JSON parse) |
| AC-OBS-05 | Instrumentation: after `POST /mcp` tools/list, `mcp_tool_calls_total` increments; after sandbox `execute_tool_code`, `sandbox_execute_total` increments; after `registry.add`, `registry_operations_total` increments | `test_metrics_increment_on_tool_call`, `test_sandbox_metrics`, `test_registry_metrics` |
| AC-OBS-06 | Local-first + masking preserved: `GET /metrics` never contains `***`-origin secrets; `GET /dashboard` still masks; `reveal` still loopback-only POST | `test_metrics_no_secrets`, `test_reveal_still_gated` |
| AC-OBS-07 | Dashboard ops card: `GET /dashboard` contains ops section with health badge (`healthy`/`degraded`) and `GET /dashboard/servers` polling fragment included; `htpy` only | `test_dashboard_ops_card_renders` |
| AC-OBS-08 | No regression: 186 existing tests green, `ruff check` + `ruff format --check` 0, MCP/SSE `POST /mcp` tools/list still 200, no `package.json` introduced | CI parity |

**Verification — Definition of Done:**

- [ ] `uv run ruff check src/ tests/` 0 and `uv run ruff format --check src/ tests/` 0
- [ ] `uv run pytest -v` ≥201 tests (186 baseline + >15 new) green
- [ ] `curl -s http://127.0.0.1:8080/health | jq .status` → `"ok"`; `curl -s http://127.0.0.1:8080/ready` → 200/503 semantics; `curl -s http://127.0.0.1:8080/live` → alive; `curl -s http://127.0.0.1:8080/metrics | head` → `# HELP mcp_gway_...`
- [ ] `curl -s -H "X-Request-ID: test123" http://127.0.0.1:8080/health -D - | grep X-Request-ID` → `test123`
- [ ] Dashboard: `GET /dashboard` HTML contains `ops`/`health` badge text (htpy string assert)
- [ ] Review waves: `readability`+`reliability`+`resilience`+`risk` → `refuter` → `qa` (sole executor) → Vasquez Gate — CEO GO

---

### ADRs

**ADR-OBS-001: stdlib JSON logs over structured-log dep** — Zero deps, `logging` is already wired via `cli.serve` level resolution. Trade-off: no `structlog` context binding sugar, solved via `ContextVar`.

**ADR-OBS-002: vendored MetricsRegistry over prometheus_client** — Avoids extra dep + registry global state; Prometheus text is simple enough to render manually and snapshot-test. Trade-off: no exemplars/openmetrics advanced features — acceptable at GA.

**ADR-OBS-003: split /health vs /ready vs /live** — Follows Kubernetes probe semantics; `/health` kept for backward compat while `/ready`/`/live` are new. Single aggregator module with tiny checks keeps coupling low.

**ADR-OBS-004: middleware ordering Correlation→Metrics→Logging→Security** — Guarantees every log/metric has `request_id`; security headers still applied innermost.

---

### Changelog

- **2026-08-26 — v0.8.0-draft**: Approved Approach C hybrid pragmatic. Scope locked to stdlib logs + MetricsRegistry + correlation + 4 probes + dashboard ops card. Spec binding for plan decomposition.

---

*Self-review (Vasquez): Checked against AGENTS.md HARD (Python 3.12+, Starlette, htpy, no Node, local-first, masking, atomic Registry), 10 sections present, contracts explicit, ECs cover security/cardinality/liveness, trade-offs documented (A vs B vs C), complexity justification included, done criteria testable. Ready for `writing-plans` decomposition.*
