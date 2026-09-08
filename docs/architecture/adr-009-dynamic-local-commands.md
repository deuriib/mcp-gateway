# ADR-009: Dynamic Local Commands (allow-list + unrestricted TTL)

## Status
Approved (implemented 2026-09-07, branch `feat/006-dynamic-local-commands`)

## Context
Static `_ALLOWED_COMMANDS={npx,node,python,python3,uvx}` blocks npm-global PATH tools (e.g. agentmemory MCP) and forces code edits per binary. CEO conditional GO requires dynamic-no-static without losing local-first. CISO HARD binding on env names. CTO gate: fix PATCH `from_edit` bypass that persisted commands without re-validation.

## Decision
- Single syntax rule: `MCPServerConfig.validate_cmd → core/policy.validate_command_syntax` (1-8 tokens, basename-only, regex, no `..`, no shell chars). Model `cwd` checks absolute only; `environment` enforces denylist.
- Policy `src/mcp_gway/core/policy.py` owns allow-list + TTL + gates:
  - `MCP_GWAY_ALLOW_LOCAL_COMMANDS` CSV basenames; `*` invalid = deny + warn; empty = default-deny.
  - `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL=1` + marker `~/.config/mcp-gway/.local_unrestricted` (epoch, `0o600`, 72h TTL) → any syntactically valid basename allowed.
  - `MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD` compat, default `1`.
  - Dashboard ALLOW = VIA==1 AND (unrestricted OR in allow-list) AND serve-host loopback; non-loopback always deny.
  - CLI (add/refresh) uses allow-list/unrestricted only, ignores VIA.
- Execution: `shutil.which(basename)` + `Path.resolve`; spawn only `which(basename)`; never `shell=True`/`cmd /c`/`sh -c`. `stdio_transport.resolve_windows_command` is basename→which on all platforms. `core/client._create_local_transport` re-checks policy + `cwd` strict + env before spawn.
- Same gate enforced in: `POST /api/servers`, `PATCH /api/servers/{name}` (from_edit re-gate, fix bypass), `POST .../refresh` + bulk + background, catalog `entry_to_config` + install handler exposed-host re-gate, CLI `add`/`refresh`.
- `cwd` strict at gates: absolute + `resolve()` + `is_dir`, else `invalid_cwd`. Env denylist: `PATH,PATHEXT,SYSTEMROOT,COMSPEC,LD_PRELOAD,LD_LIBRARY_PATH,DYLD_*,PYTHONPATH,PYTHONHOME,NODE_OPTIONS` → `denied_env`.
- Errors actionable with `reason_code`: `allow_list|unrestricted|not_allowlisted|via_dashboard_disabled|non_loopback_denied|binary_not_found|invalid_syntax|invalid_cwd|denied_env`. `binary not found in PATH` vs `command not allowed` distinct.
- Audit `audit_local_action` logs action/name/binary/reason only; dashboard masking `***` intact; Reveal loopback-only intact.
- Timeout 5000ms default, semaphore 3, local-first `serve 0.0.0.0` without `MCP_GWAY_ALLOW_REMOTE=1` → exit 2 + `X-Warning` + banner unchanged.

## Consequences
- Operators set `MCP_GWAY_ALLOW_LOCAL_COMMANDS=npx,uvx,...` once; no code change per tool. Unrestricted is time-boxed 72h for bootstrap.
- Dashboard cannot escalate via PATCH/refresh/catalog when binary leaves allow-list.
- Tests must set allow-list + mock `resolve_binary`/`check_cwd` for determinism (see `test_policy_local_commands.py` AC-001..AC-012).

## Alternatives Considered
- Static list extension per tool → rejected (CEO: dynamic-no-static).
- Full paths in config → rejected (path traversal, non-portable; basenames + PATH only).
- Shell spawn for `.cmd/.ps1` → rejected (CISO: no shell; `shutil.which` covers PATHEXT without shell).

## Traces
- BR-001..BR-016 ↔ AC-001..AC-012 ↔ WU-001..WU-004 ↔ commits 896b281, 7eb8028, e1b5f14.
- Files: `src/mcp_gway/core/policy.py`, `models.py`, `catalog/models.py`, `stdio_transport.py`, `core/client.py`, `dashboard/api.py`, `dashboard/catalog/api.py`, `catalog/install.py`, `cli.py`.
