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
  - Serve-host loopback rule unchanged (`serve` binds `127.0.0.1`; non-loopback requires `MCP_GWAY_ALLOW_REMOTE=1`).
  - CLI (add/refresh) uses allow-list/unrestricted only, ignores VIA.
- Execution: `shutil.which(basename)` + `Path.resolve`; spawn only `which(basename)`; never `shell=True`/`cmd /c`/`sh -c`. `stdio_transport.resolve_windows_command` is basename→which on all platforms. `core/client._create_local_transport` re-checks policy + `cwd` strict + env before spawn.
- Same gate enforced in CLI `add`/`refresh` (re-validated before persist).
- `cwd` strict at gates: absolute + `resolve()` + `is_dir`, else `invalid_cwd`. Env denylist EXACT PATH,PATHEXT,SYSTEMROOT,COMSPEC,LD_PRELOAD,LD_LIBRARY_PATH,PYTHONPATH,PYTHONHOME,NODE_OPTIONS,NODE_PATH,NODE_EXTRA_CA_CERTS,NODE_TLS_REJECT_UNAUTHORIZED + PREFIXES DYLD_,NPM_CONFIG_,BUN_,UV_ (`NODE_ENV` permitido, no denylisted) → `denied_env`.
- Errors actionable with `reason_code`: `allow_list|unrestricted|not_allowlisted|via_dashboard_disabled|non_loopback_denied|binary_not_found|invalid_syntax|invalid_cwd|denied_env`. `binary not found in PATH` vs `command not allowed` distinct.
- Audit `audit_local_action` logs action/name/binary/reason only.
- Timeout 5000ms default, semaphore 3, local-first `serve 0.0.0.0` without `MCP_GWAY_ALLOW_REMOTE=1` → exit 2 + `X-Warning`.

## Consequences
- Operators set `MCP_GWAY_ALLOW_LOCAL_COMMANDS=npx,uvx,...` once; no code change per tool. Unrestricted is time-boxed 72h for bootstrap.
- Stored servers re-gate on CLI `refresh` when binary leaves allow-list.
- Tests must set allow-list + mock `resolve_binary`/`check_cwd` for determinism (see `test_policy_local_commands.py` AC-001..AC-012).

## Alternatives Considered
- Static list extension per tool → rejected (CEO: dynamic-no-static).
- Full paths in config → rejected (path traversal, non-portable; basenames + PATH only).
- Shell spawn for `.cmd/.ps1` → rejected (CISO: no shell; `shutil.which` covers PATHEXT without shell).

## Traces
- BR-001..BR-016 ↔ AC-001..AC-012 ↔ WU-001..WU-004 ↔ commits 896b281, 7eb8028, e1b5f14.
- Files: `src/mcp_gway/core/policy.py`, `models.py`, `stdio_transport.py`, `core/client.py`, `cli.py`.
