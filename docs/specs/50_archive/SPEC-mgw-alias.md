# Spec: Minimal CLI Alias mgw

**ID:** SPEC-MGW-001
**Owner:** vasquez (CTO)
**Domains-Touched:** [engineering]
**Brief Reference:** BRIEF-MGW-001
**Status:** draft
**Priority:** P1
**Execution_Mode:** single (inherited from BRIEF-MGW-001, frozen 2026-09-16; no per-SPEC override)

## 1. Context

BRIEF-MGW-001 asks for `mgw` as a minimal daily driver alongside canonical `mcp-gway`. The CLI is the only surface in v2.2.0+ headless CLI-only (no dashboard/catalog). Packaging today exposes a single entry point (`pyproject.toml:19-20` → `mcp-gway = "mcp_gway.cli:main"`); the click root is a single group (`src/mcp_gway/cli.py:74-76` `def main()`). The spec freezes parity + packaging + docs so `propose-changes` can approve a one-line-class change without improvisation.

## 2. Requirements

- REQ-F-001: Both binaries expose identical command tree (`add/remove/list/inspect/refresh/serve/local-unrestricted` + hidden `mcp` alias) with identical flags and exit codes
- REQ-F-002: Normal install (`uv sync` / `uv pip install` / `uv tool install`) exposes both `mcp-gway` and `mgw` on PATH
- REQ-F-003: `mgw --help` and `mcp-gway --help` produce identical output modulo `argv[0]`; version single-source `pyproject.toml:3` ≡ `src/mcp_gway/__init__.py:__version__` (gate amendment 2026-09-16: no `--version` CLI flag exists in `cli.py` — none added in this SPEC per proposal NO-OP freeze; both binaries report via the same `__version__`)
- REQ-NF-001: No regression — full suite green + lint/format clean
- REQ-NF-002: No new trust boundary — no new endpoint, adapter, payload, port, or permission; allow-list + break-glass names unchanged
- REQ-NF-003: Docs show `mgw` as shortcut with `mcp-gway` canonical intact

## 3. Acceptance Criteria

- [ ] AC-001: `mgw <cmd> --help` exits 0 and diff vs `mcp-gway <cmd> --help` (normalized for prog name) is empty for every top-level command — evidence: new test `tests/test_cli_alias.py` + CI log
- [ ] AC-002: Clean install exposes both shims — evidence: install repro log (`uv build` + install + `where mgw` / `where mcp-gway` or POSIX `command -v`) cited in PROPOSED_CHANGES
- [ ] AC-003: `uv run pytest -v` 255/255+new green, `ruff check src/ tests/` + `ruff format --check src/ tests/` clean — evidence: CI output
- [ ] AC-004: No secret/token/credential in diff; `MCP_GWAY_ALLOW_LOCAL_COMMANDS` / `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL` strings untouched — evidence: `git diff` + grep
- [ ] AC-005: README + AGENTS.md command examples mention `mgw` shortcut without removing `mcp-gway` — evidence: doc diff file:line

## 4. Contracts & Interfaces

- Packaging: append second script entry under `[project.scripts]` in `pyproject.toml:19-20`:
  `mgw = "mcp_gway.cli:main"` (same `main` object as `mcp-gway`; no new module, no arg reshaping)
- CLI: `src/mcp_gway/cli.py:74-76` `main()` stays the single click group; both binaries bind to it. No signature change, no new options in this SPEC
- Version: single source `pyproject.toml:3` + `src/mcp_gway/__init__.py:__version__` (`[tool.semantic_release]`); both binaries report it
- Windows: `uv_build` + installer shims must emit `mgw.exe` alongside `mcp-gway.exe`; POSIX must emit both shims. No shell plugin required
- HTTP/SSE surface unchanged: `/mcp` (GET+POST), `/health`, `/ready`, `/live`, `/metrics` — alias is packaging-only

## 5. Out of Scope

- Removing or deprecating `mcp-gway`; compat is permanent in this SPEC
- Dashboard/catalog revival (retired v2.0.0)
- `0.0.0.0` exposure without `MCP_GWAY_ALLOW_REMOTE=1` + firewall/auth
- Shell completion, man pages, or key rotation / prod patch / permission widening
- `bunx` default promotion (docs-only opt-in stays; default-deny empty stays)

## 6. Dependencies

- Upstream: BRIEF-MGW-001 (read-only; never modified here)
- Build: `uv_build>=0.12.5,<0.13.0` (`pyproject.toml:22-24`); `click>=8.4.2`
- Downstream: `PROPOSED_CHANGES.md` (next stage), then `tests/test_cli_alias.py`, README/AGENTS.md edits

## 7. Traceability

| Requirement | Acceptance Criterion | Proposed Change | Evidence |
|-------------|---------------------|-----------------|----------|
| REQ-F-001 | AC-001 | PROPOSED_CHANGES.md § packaging + parity | `tests/test_cli_alias.py` + help diff |
| REQ-F-002 | AC-002 | PROPOSED_CHANGES.md § install | install repro log |
| REQ-F-003 | AC-003 (help/version subset) | PROPOSED_CHANGES.md § version | `--version` output + test |
| REQ-NF-001 | AC-003 | n/a (gate) | `pytest` + `ruff` logs |
| REQ-NF-002 | AC-004 | n/a (gate) | `git diff` + grep for env names |
| REQ-NF-003 | AC-005 | PROPOSED_CHANGES.md § docs | doc diff file:line |
