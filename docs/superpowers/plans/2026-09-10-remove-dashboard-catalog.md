# Remove Dashboard and Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `dashboard` and `catalog` bounded contexts completely so the Gateway serves only MCP plus probes, managed by CLI.

**Architecture:** Slim `Gateway` to mount only `/health`, `/ready`, `/live`, `/metrics`, `/mcp`, `/mcp/messages`; delete `src/mcp_gway/dashboard/` and `src/mcp_gway/catalog/`; clean CLI banner, health checks, policy dead-code, `htpy` dependency, tests, and docs. Single-process Starlette stays; no new runtime components.

**Tech Stack:** Python 3.12+, Starlette, uvicorn, click, httpx (kept for `core/transport.py` + `core/client.py`), pytest + pytest-asyncio, ruff, uv.

**Spec:** Chat-approved removal design 2026-09-10 (architectural path, user said "si al plan"): dashboard-complete removal (SSR `/dashboard` + `/api/servers` + `/static` + alias `/`), catalog-complete removal (domain + `dashboard/catalog` + cache `~/.config/mcp-gway/catalog.json` + Bifrost fetch + `MCP_GWAY_CATALOG_TTL`), `serve` keeps MCP + probes, total cleanup of deps/tests/docs. Retires `docs/specs/SPEC-UI-001.md`, `docs/specs/SPEC-CATALOG-001.md`, `SCENARIOS-CATALOG-001.md`, `ACCEPTANCE-CATALOG-001.md`, `docs/adr/ADR-008-catalog-mcp-001.md` (mark superseded). Approved defaults: `/` becomes 404 JSON, `health.checks` drops the `dashboard` key, `core/policy.via_dashboard` removed entirely.

## Global Constraints

- Python `>=3.12`, `from __future__ import annotations` in every touched module.
- Type hints on all public functions; docstrings on classes and public methods.
- `ruff check` and `ruff format --check` must pass on `src/` and `tests/` after every task.
- One work-unit commit per task: format `type(scope): subject`, imperative, lowercase, no period, max 72 chars, scope mandatory.
- Stage only the task's files, never blind `git add .`.
- `httpx` stays in dependencies (`core/transport.py` and `core/client.py` import it); only `htpy` is removed.
- `python-htmx` is not in `pyproject.toml`, nothing to remove for it (only the vendored `htmx.min.js` file gets deleted with `static/`).
- `mcp-gway serve` keeps binding default `127.0.0.1` and the `MCP_GWAY_ALLOW_REMOTE=1` gate for non-loopback.
- The orphan user cache `~/.config/mcp-gway/catalog.json` is never deleted by code; document manual `rm` only.

---

## File structure (what changes and why)

- `src/mcp_gway/gateway.py` — slimmed: no catalog/dashboard imports, no `catalog_path`/`catalog_service` params, only MCP + probe routes, `_CSRFMiddleware` deleted, `_CSPMiddleware` single policy. Single responsibility: MCP transport.
- `src/mcp_gway/dashboard/` (deleted: `__init__.py`, `api.py`, `views.py`, `routes.py`, `catalog/api.py`, `catalog/views.py`, `catalog/routes.py`, `catalog/__init__.py`, `static/tailwind.css`, `static/htmx.min.js`, `static/tailwindcss.min.js`, `static/dashboard.js`, `static/dialog.js`) — dead UI context.
- `src/mcp_gway/catalog/` (deleted: `__init__.py`, `models.py`, `service.py`, `store.py`, `install.py`) — dead curated-read context.
- `src/mcp_gway/cli.py` — `serve` banner without Dashboard lines, warning log reworded to `server exposed on non-loopback`.
- `src/mcp_gway/observability/health.py` — `handle_health` checks drop `dashboard` key; `handle_metrics` gating reads `serve_host` instead of `dashboard_host`.
- `src/mcp_gway/core/policy.py` — remove `is_via_dashboard_allowed`, `VIA_DASHBOARD_ENV`, `via_dashboard` params, `via_dashboard_disabled` branch.
- `src/mcp_gway/core/install.py` — docstring rewrite only (logic already HTTP-free).
- `pyproject.toml` — remove `htpy>=26.5.1` line; regenerate `uv.lock`.
- `tests/` — delete 5 files, edit gateway/integration/wave2/feat006/policy/observability tests, add negative 404 tests.
- `README.md`, `AGENTS.md`, `docs/specs/*`, `docs/adr/ADR-008*`, `docs/sbtdd/**feat-006**`, `docs/architecture/adr-009*` — docs cleanup.

---

### Task 1: Slim the Gateway (TDD: negatives first)

**Files:**
- Modify: `src/mcp_gway/gateway.py`
- Test: `tests/test_gateway.py`

**Interfaces:**
- Consumes: `Registry(servers_dir)` fixture already in `tests/test_gateway.py:14-24`; `Gateway(registry)` constructor.
- Produces: `Gateway(registry, host="127.0.0.1").app` with routes only for `/health`, `/ready`, `/live`, `/metrics`, `/mcp`, `/mcp/messages`; constructor signature `def __init__(self, registry: Registry, host: str = "127.0.0.1") -> None`; `app.state` exposes `registry`, `serve_host`, `metrics`, `gateway`, `start_time` (no `dashboard_host`, no `catalog_service`, no `catalog_store`).

- [ ] **Step 1: Append the failing negative tests to `tests/test_gateway.py`**

```python
@pytest.mark.asyncio
async def test_removed_dashboard_routes_404(gateway):
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/", "/dashboard", "/dashboard/servers", "/api/servers", "/api/catalog"):
            response = await client.get(path)
            assert response.status_code == 404


@pytest.mark.asyncio
async def test_gateway_has_no_catalog_state(gateway):
    assert not hasattr(gateway, "catalog_service")
    assert not hasattr(gateway, "catalog_store")
    assert getattr(gateway.app.state, "serve_host", None) == "127.0.0.1"
    assert not hasattr(gateway.app.state, "dashboard_host")
    assert not hasattr(gateway.app.state, "catalog_service")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_gateway.py::test_removed_dashboard_routes_404 tests/test_gateway.py::test_gateway_has_no_catalog_state -v`
Expected: FAIL — `/dashboard` currently returns 200 and `gateway.catalog_service` exists.

- [ ] **Step 3: Edit `src/mcp_gway/gateway.py` imports — delete catalog/dashboard lines, keep the rest byte-identical**

```python
from mcp_gway import __version__
from mcp_gway.code_mode import CodeMode
from mcp_gway.observability.health import (
    handle_health,
    handle_live,
    handle_metrics,
    handle_ready,
)
```

- [ ] **Step 4: Delete the `_CSRFMiddleware` class (lines 47-103) entirely**

Delete the whole block from `class _CSRFMiddleware(BaseHTTPMiddleware):` through its `return await call_next(request)` line. Nothing replaces it. Rationale in commit body: no mutating HTTP routes remain, CLI owns writes.

- [ ] **Step 5: Simplify `_CSPMiddleware.dispatch` to one policy**

```python
class _CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response
```

- [ ] **Step 6: Slim `Gateway.__init__` signature and body**

```python
class Gateway:
    def __init__(
        self,
        registry: Registry,
        host: str = "127.0.0.1",
    ) -> None:
        self.registry = registry
        self.host = host
        self.code_mode = CodeMode(registry)
        self._sessions: dict[str, SessionInfo] = {}
```

Delete the `catalog_path`/`catalog_service` params and the whole `if catalog_service is not None: ... else: ... CatalogService ...` block.

- [ ] **Step 7: Slim route mounting and `app.state`**

```python
        self.app = Starlette(
            routes=[
                Route("/health", self._health, methods=["GET"]),
                Route("/ready", handle_ready, methods=["GET"]),
                Route("/live", handle_live, methods=["GET"]),
                Route("/metrics", handle_metrics, methods=["GET"]),
                Route("/mcp", self._mcp_sse, methods=["GET"]),
                Route("/mcp", self._mcp_post, methods=["POST"]),
                Route("/mcp/messages", self._mcp_post, methods=["POST"]),
            ]
        )
```

Delete `dashboard_routes = ...` and `catalog_routes = ...` lines plus `*dashboard_routes, *catalog_routes` entries. Delete `self.app.add_middleware(_CSRFMiddleware)`. Replace `self.app.state.dashboard_host = host` with `self.app.state.serve_host = host`, and delete the `catalog_service`/`catalog_store` state lines.

- [ ] **Step 8: Run gateway tests to verify they pass**

Run: `uv run pytest tests/test_gateway.py -v`
Expected: PASS including the two new tests.

- [ ] **Step 9: Lint the touched files**

Run: `uv run ruff check src/mcp_gway/gateway.py tests/test_gateway.py && uv run ruff format --check src/mcp_gway/gateway.py tests/test_gateway.py`
Expected: PASS (fix formatting if ruff rewrites).

- [ ] **Step 10: Commit**

```bash
git add src/mcp_gway/gateway.py tests/test_gateway.py
git commit -m "refactor(gateway): drop dashboard and catalog routes"
```

---

### Task 2: Delete the dashboard and catalog packages

**Files:**
- Delete: `src/mcp_gway/dashboard/__init__.py`, `src/mcp_gway/dashboard/api.py`, `src/mcp_gway/dashboard/views.py`, `src/mcp_gway/dashboard/routes.py`, `src/mcp_gway/dashboard/catalog/__init__.py`, `src/mcp_gway/dashboard/catalog/api.py`, `src/mcp_gway/dashboard/catalog/views.py`, `src/mcp_gway/dashboard/catalog/routes.py`, `src/mcp_gway/dashboard/static/tailwind.css`, `src/mcp_gway/dashboard/static/htmx.min.js`, `src/mcp_gway/dashboard/static/tailwindcss.min.js`, `src/mcp_gway/dashboard/static/dashboard.js`, `src/mcp_gway/dashboard/static/dialog.js`
- Delete: `src/mcp_gway/catalog/__init__.py`, `src/mcp_gway/catalog/models.py`, `src/mcp_gway/catalog/service.py`, `src/mcp_gway/catalog/store.py`, `src/mcp_gway/catalog/install.py`

**Interfaces:**
- Consumes: Task 1 output (nothing imports these packages anymore).
- Produces: `glob src/mcp_gway/dashboard/**/*` and `glob src/mcp_gway/catalog/**/*` return nothing; `rg "from mcp_gway.(dashboard|catalog)" src/` returns zero hits.

- [ ] **Step 1: Verify nothing in `src/` still imports the doomed packages**

Run: `uv run ruff check src/`
Expected: PASS with no `F401`/`E402` referencing `mcp_gway.dashboard` or `mcp_gway.catalog`. (Task 1 removed the only `src/` importers.)

- [ ] **Step 2: Delete the packages with git**

```bash
git rm -r src/mcp_gway/dashboard src/mcp_gway/catalog
```

Expected: `git status --short` shows `D` entries for every file listed above.

- [ ] **Step 3: Confirm zero stray references in `src/`**

Run: `rg -l "dashboard|catalog|htpy" src/ || echo "clean"`
Expected: prints `clean`. (`cli.py` still mentions dashboard word in two banner lines — Task 3 handles those; the `|| echo` tolerates that. If hits appear outside `cli.py`, stop and fix before committing.)

- [ ] **Step 4: Commit**

```bash
git add -A src/mcp_gway/dashboard src/mcp_gway/catalog
git commit -m "refactor(gateway): delete dashboard and catalog packages"
```

---

### Task 3: CLI banner, health checks, policy dead-code, install docstring

**Files:**
- Modify: `src/mcp_gway/cli.py` (serve banner lines ~389-437)
- Modify: `src/mcp_gway/observability/health.py` (lines 56, 129)
- Modify: `src/mcp_gway/core/policy.py` (lines 125-126, 170-181, 216+ `via_dashboard` params)
- Modify: `src/mcp_gway/core/install.py` (line 1 docstring)

**Interfaces:**
- Consumes: Task 1 `serve_host` state name; Task 2 deletions.
- Produces: `mcp-gway serve` prints MCP + Health lines only; `GET /health` body `checks` has keys `registry` and `routes` only; `check_basename_allowed(basename, *, host_loopback)` with no `via_dashboard` param; no `via_dashboard_disabled` reason code anywhere.

- [ ] **Step 1: Edit `src/mcp_gway/cli.py` warning log (line 391)**

```python
        logger.warning("server exposed on non-loopback host %s", host)
```

- [ ] **Step 2: Edit `src/mcp_gway/cli.py` serve banner — delete the Dashboard line, keep MCP + Health**

```python
    label_w = 9
    click.echo(
        f"  {_c('MCP'.ljust(label_w), dim=True)} {_c(glyph_arr, dim=True)} {_c(f'{base_url}/mcp', fg='cyan')}"
    )
```

Delete the `click.echo(... 'Dashboard' ... f'{base_url}/dashboard' ...)` block. In the non-loopback warning line, replace `'-- dashboard reachable at {host}'` with `'-- server reachable at {host}'`.

- [ ] **Step 3: Edit `src/mcp_gway/observability/health.py` health checks (line 56)**

```python
    checks = {"registry": reg_status, "routes": routes_status}
```

- [ ] **Step 4: Edit `src/mcp_gway/observability/health.py` metrics gating (line 129)**

```python
    host = getattr(request.app.state, "serve_host", "127.0.0.1")
```

- [ ] **Step 5: Edit `src/mcp_gway/core/policy.py` — remove the VIA gate helper and constant**

Delete:

```python
def is_via_dashboard_allowed() -> bool:
    return os.environ.get(VIA_DASHBOARD_ENV, "1") == "1"
```

And delete the `VIA_DASHBOARD_ENV = "MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD"` module constant. Update `check_basename_allowed` signature to:

```python
def check_basename_allowed(
    basename: str, *, host_loopback: bool
) -> PolicyDecision:
```

Delete the `if via_dashboard:` branch returning `via_dashboard_disabled`. Update every `check_local_command(..., via_dashboard=...)` call site in `policy.py` to drop the `via_dashboard` argument, keeping `host_loopback` and `require_binary` as-is. Then update the three CLI call sites in `src/mcp_gway/cli.py` (`cli_add`, `cli_add_regate`, `cli_refresh`) from `check_local_command(list(cmd_parts), via_dashboard=False, require_binary=True)` to `check_local_command(list(cmd_parts), require_binary=True)`.

- [ ] **Step 6: Edit `src/mcp_gway/core/install.py` docstring (line 1)**

```python
"""Core install helpers - discovery and persist for CLI (no HTTP)."""
```

- [ ] **Step 7: Run the affected test files**

Run: `uv run pytest tests/test_cli.py tests/test_gateway.py tests/test_observability_probes.py tests/test_observability_metrics.py tests/test_policy_local_commands.py -q`
Expected: some FAILs pointing at old `via_dashboard`/`dashboard` asserts — record them, they are Task 5 input. If failures are import errors, fix the call sites from Step 5 before proceeding.

- [ ] **Step 8: Lint**

Run: `uv run ruff check src/mcp_gway/cli.py src/mcp_gway/observability/health.py src/mcp_gway/core/policy.py src/mcp_gway/core/install.py && uv run ruff format --check src/mcp_gway/cli.py src/mcp_gway/observability/health.py src/mcp_gway/core/policy.py src/mcp_gway/core/install.py`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/mcp_gway/cli.py src/mcp_gway/observability/health.py src/mcp_gway/core/policy.py src/mcp_gway/core/install.py
git commit -m "refactor(cli): drop dashboard banner and via-dashboard gate"
```

---

### Task 4: Dependencies — remove `htpy`, keep `httpx`

**Files:**
- Modify: `pyproject.toml` (lines 10-18)
- Modified by tooling: `uv.lock`

**Interfaces:**
- Consumes: Tasks 1-2 (no `htpy` importers left; verified `rg "import htpy|from htpy" src/` hits only lived in the deleted `dashboard/views.py` files).
- Produces: `pyproject.toml` dependencies without `htpy`; `uv.lock` regenerated; `uv sync` succeeds offline-safe.

- [ ] **Step 1: Edit `pyproject.toml` dependencies**

```toml
dependencies = [
    "click>=8.4.2",
    "httpx>=0.28.1",
    "mcp>=2.0.0",
    "starlark-pyo3>=2026.1.1",
    "starlette>=1.6.0",
    "uvicorn>=0.52.4",
]
```

Delete exactly the `"htpy>=26.5.1",` line. Touch nothing else.

- [ ] **Step 2: Regenerate the lockfile and sync**

Run: `uv sync --all-groups`
Expected: exit 0, `uv.lock` shows no `htpy` entry.

- [ ] **Step 3: Prove `httpx` is still required**

Run: `rg -l "import httpx|from httpx" src/`
Expected: hits in `src/mcp_gway/core/transport.py` and `src/mcp_gway/core/client.py`. If empty, stop — something deleted too much.

- [ ] **Step 4: Smoke-test imports**

Run: `uv run python -c "import mcp_gway.gateway, mcp_gway.cli; print('imports ok')"`
Expected: prints `imports ok`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): drop htpy after dashboard removal"
```

---

### Task 5: Tests — delete orphans, fix referencers, lock negatives

**Files:**
- Delete: `tests/test_dashboard_api.py`, `tests/test_dashboard_views.py`, `tests/test_dashboard_ops.py`, `tests/test_catalog_api.py`, `tests/test_catalog_views.py`
- Modify: `tests/test_gateway.py` (done in Task 1, extend if needed), `tests/test_integration.py`, `tests/test_wave2_api.py`, `tests/test_feat006_harden.py`, `tests/test_policy_local_commands.py`, `tests/test_observability_instrumentation.py`, `tests/test_p0_fixes.py`, `tests/test_minor_hardening.py` (only the ones that fail — check each with rg first)
- Test: whole `tests/` suite

**Interfaces:**
- Consumes: Tasks 1-4 outputs.
- Produces: full suite green; no test imports `mcp_gway.dashboard`, `mcp_gway.catalog`, `CatalogService`, `CatalogStore`, or `htpy`; negative coverage asserts 404 for removed routes and absence of `dashboard` health key.

- [ ] **Step 1: List every test file referencing the removed surface**

Run: `rg -l "dashboard|catalog|CatalogService|CatalogStore|htpy|HX-Request|/api/servers" tests/`
Expected: the 5 doomed files plus a referencer list (known: `test_gateway.py`, `test_integration.py`, `test_wave2_api.py`, `test_feat006_harden.py`, `test_policy_local_commands.py`, possibly observability/p0/minor files).

- [ ] **Step 2: Delete the five orphan test files**

```bash
git rm tests/test_dashboard_api.py tests/test_dashboard_views.py tests/test_dashboard_ops.py tests/test_catalog_api.py tests/test_catalog_views.py
```

- [ ] **Step 3: Fix `tests/test_policy_local_commands.py` — drop VIA-dashboard cases**

Delete or rewrite every case asserting `reason_code="via_dashboard_disabled"` or calling `is_via_dashboard_allowed()` / `check_local_command(..., via_dashboard=True)`. Keep the `require_binary`, `invalid_syntax`, `invalid_cwd`, `denied_env`, `binary_not_found` cases untouched. Concrete example of the rewrite for a surviving case:

```python
def test_local_command_requires_binary():
    decision = check_local_command(["definitely-not-a-real-binary-xyz"], require_binary=True)
    assert decision.allowed is False
    assert decision.reason_code in ("binary_not_found", "not_allowlisted")
```

- [ ] **Step 4: Fix remaining referencers (`test_integration.py`, `test_wave2_api.py`, `test_feat006_harden.py`, observability/p0/minor as listed in Step 1)**

For each file: delete tests that `GET/POST` `/dashboard*`, `/api/servers*`, `/api/catalog*`, or assert `HX-Request` fragments, `X-Cache` headers, `catalog_grid` HTML, or `checks["dashboard"]`. Where a test asserted `checks == {"registry": ..., "dashboard": ...}`, change to:

```python
assert set(body["checks"]) == {"registry", "routes"}
```

Where a test constructed `Gateway(registry, catalog_service=...)` or `CatalogService(...)`, replace with plain `Gateway(registry)`.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all PASS. If failures remain, fix only within the files listed in Step 1, one file per rerun: `uv run pytest tests/test_integration.py -q`, then wave2, feat006, policy, observability, p0, minor.

- [ ] **Step 6: Final reference sweep on tests**

Run: `rg -l "mcp_gway.dashboard|mcp_gway.catalog|CatalogService|CatalogStore|import htpy" tests/ || echo "clean"`
Expected: prints `clean`.

- [ ] **Step 7: Commit (two commits: deletion + fixes, to keep revert units clean)**

```bash
git add -A tests/
git commit -m "test(gateway): drop dashboard and catalog suites"
```

If Step 4 touched referencers beyond the 5 deletions and you prefer separation, split: commit the `git rm` first as `test(gateway): delete dashboard and catalog suites`, then the edits as `test(gateway): fix referencers after ui removal`. Either way, never mix `src/` files into these commits.

---

### Task 6: Docs, specs, ADRs

**Files:**
- Modify: `README.md` (delete dashboard/catalog sections, curl examples, metrics-catalog line, verification commands)
- Modify: `AGENTS.md` (delete dashboard bounded-context section, dashboard verify commands, registry/dashboard references)
- Delete: `docs/specs/SPEC-CATALOG-001.md`, `docs/specs/SCENARIOS-CATALOG-001.md`, `docs/specs/ACCEPTANCE-CATALOG-001.md`
- Modify: `docs/specs/SPEC-UI-001.md` — replace whole body with a superseded notice (keep file as tombstone), or `git rm` it if the team prefers deletion; default is tombstone (safer for links)
- Modify: `docs/adr/ADR-008-catalog-mcp-001.md` — prepend superseded notice
- Modify: `docs/architecture/adr-009-dynamic-local-commands.md`, `docs/sbtdd/specs/feat-006-dynamic-local-commands/*`, `docs/sbtdd/plans/feat-006-dynamic-local-commands/plan.md`, `CHANGELOG.md` (append entry only, never rewrite history)

**Interfaces:**
- Consumes: Tasks 1-5 (final route/behavior names are stable).
- Produces: `rg -i "dashboard|catalog" README.md AGENTS.md` returns zero hits except the CHANGELOG removal note; specs tombstoned; full test suite still green (docs-only, but verify).

- [ ] **Step 1: Rewrite `README.md`**

Delete: the "open http://127.0.0.1:8080/dashboard" quickstart line (point to `/health`), the Stack paragraph mentioning `htpy + python-htmx + TailwindCSS vendoreado`, the routes table rows for `/dashboard*` and `/api/servers*`, the htmx curl examples, the `Metrics catalog` line, the VIA-dashboard paragraph, the `test_dashboard_* + test_catalog_*` pytest line, the `curl .../dashboard | grep` verify lines, and the ASCII diagram SSR column. Replace the serve-output example with MCP + Health lines only. Append to CHANGELOG (do not edit past entries):

```markdown
## Unreleased
- **breaking**: removed dashboard (`/dashboard`, `/api/servers`, `/static`, `/` alias) and catalog (`/api/catalog`, `/dashboard/catalog`, Bifrost fetch, `~/.config/mcp-gway/catalog.json` cache). Gateway serves `/mcp`, `/health`, `/ready`, `/live`, `/metrics` only; management is CLI-only. Dropped `htpy` dependency (`httpx` kept). Delete stale cache manually: `rm ~/.config/mcp-gway/catalog.json`.
```

- [ ] **Step 2: Rewrite `AGENTS.md`**

Delete the `dashboard/` tree line and its two test-file lines, the Verification Dashboard block (`pytest tests/test_dashboard_*`, the three `curl .../dashboard` lines), the local-first warning sentence about dashboard banner (keep the `serve` bind rule itself), the Dashboard Bounded Context subsection (routes SSR/API, content negotiation, static vendoreado, masking/reveal — all of it), and the Registry line mentioning Dashboard. Keep: project overview (reword to "headless MCP gateway, CLI-managed"), commands (drop dashboard curl), testing, deployment.

- [ ] **Step 3: Tombstone the specs**

Delete `docs/specs/SPEC-CATALOG-001.md`, `docs/specs/SCENARIOS-CATALOG-001.md`, `docs/specs/ACCEPTANCE-CATALOG-001.md` with `git rm`. Overwrite `docs/specs/SPEC-UI-001.md` body with exactly:

```markdown
# SPEC-UI-001 — SUPERSEDED

Removed 2026-09-10: dashboard (`/dashboard`, `/api/servers`, `/static`) deleted.
Gateway is headless; management is CLI-only. See CHANGELOG Unreleased entry.
```

Prepend to `docs/adr/ADR-008-catalog-mcp-001.md`:

```markdown
> SUPERSEDED 2026-09-10: catalog removed (Bifrost fetch, cache, `/api/catalog`, `/dashboard/catalog`). Kept for history.
```

In `docs/architecture/adr-009-dynamic-local-commands.md` and the `feat-006` spec/scenarios/acceptance/plan/verify files, delete only the `dashboard`/`catalog` gate sentences and file-list mentions (`dashboard/api.py`, `dashboard/catalog/api.py`, `catalog/install.py`); keep the CLI + `core/policy` behavior descriptions.

- [ ] **Step 4: Verify docs sweep**

Run: `rg -i "dashboard|catalog|htpy|hx-get|hx-post" README.md AGENTS.md docs/specs/ || echo "clean"`
Expected: prints `clean` (CHANGELOG and the two SUPERSEDED tombstones are excluded from this glob on purpose — they intentionally contain the words).

- [ ] **Step 5: Commit**

```bash
git add README.md AGENTS.md CHANGELOG.md docs/
git commit -m "docs(gateway): retire dashboard and catalog specs"
```

---

### Task 7: Final verification and release note

**Files:**
- None (verification only; release is a separate manual step per repo policy).

**Interfaces:**
- Consumes: Tasks 1-6.
- Produces: green lint + format + full suite + live-probe evidence pasted into the final summary.

- [ ] **Step 1: Lint and format check**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
Expected: `All checks passed` for both.

- [ ] **Step 2: Full test suite**

Run: `uv run pytest -v`
Expected: all PASS, zero `FAILED`/`ERROR`. Note the final count for the summary (was 254 pre-removal; expect fewer after deleting 5 files).

- [ ] **Step 3: Live probe — serve and curl (proves the gateway is headless)**

Run: `uv run mcp-gway serve --port 18099 & sleep 3; curl -s -o /dev/null -w "health %{http_code}\n" http://127.0.0.1:18099/health; curl -s -o /dev/null -w "dashboard %{http_code}\n" http://127.0.0.1:18099/dashboard; curl -s -o /dev/null -w "api-servers %{http_code}\n" http://127.0.0.1:18099/api/servers; curl -s -o /dev/null -w "api-catalog %{http_code}\n" http://127.0.0.1:18099/api/catalog; curl -s -o /dev/null -w "root %{http_code}\n" http://127.0.0.1:18099/; kill %1`
Expected: `health 200`, `dashboard 404`, `api-servers 404`, `api-catalog 404`, `root 404`.

- [ ] **Step 4: Confirm worktree status is clean of strays**

Run: `git status --short && rg -l "mcp_gway.dashboard|mcp_gway.catalog|import htpy" src/ tests/ || echo "clean"`
Expected: clean working tree except the intended commits; prints `clean`.

---

## Self-review

**1. Spec coverage:** chat-approved scope items mapped — dashboard-complete (Task 1 routes/state, Task 2 deletion, Task 3 banner/health, Task 5 negative 404 tests, Task 6 docs); catalog-complete (Task 1 service/state removal, Task 2 deletion, Task 5 catalog suite deletion, Task 6 spec deletion + cache `rm` note); MCP+CLI intact (`/mcp`, probes, CLI commands untouched except banner/policy args); total cleanup (`htpy` Task 4, tests Task 5, docs Task 6). No gaps.

**2. Placeholder scan:** no TBD/TODO/"appropriate handling"/"similar to Task N" — every step carries exact file paths, line anchors, literal code blocks, literal commands with expected outputs, and literal commit messages.

**3. Type consistency:** constructor `Gateway(registry, host)` used uniformly in Tasks 1 and 5; state key `serve_host` introduced in Task 1 Step 7, consumed in Task 1 test and Task 3 Step 4 with the same string; `check_basename_allowed(basename, *, host_loopback)` signature from Task 3 Step 5 matches the rewritten test call in Task 5 Step 3; `checks == {"registry", "routes"}` in Task 3 Step 3 matches the Task 5 Step 4 assertion rewrite. Fixed inline during drafting.
