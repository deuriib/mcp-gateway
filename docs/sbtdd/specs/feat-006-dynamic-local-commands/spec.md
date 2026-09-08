---
id: FEAT-006
slug: feat-006-dynamic-local-commands
title: Dynamic Local Commands
status: Approved
created: 2026-09-07
updated: 2026-09-07
spec_ref: ./spec.md
plan_ref: ../../plans/feat-006-dynamic-local-commands/plan.md
adr_refs: ["../../../architecture/adr-009-dynamic-local-commands.md"]
slot_refs: ["spec_FEAT-006"]
branch: feat/006-dynamic-local-commands
commits: []
tags: [local, security, dashboard, cli]
---

# Spec: feat-006-dynamic-local-commands

## Spec ID: FEAT-006
## Status: Approved

### Objective
Allow dynamic local MCP binaries via allow-list without static hardcode, closing PATCH bypass, keeping local-first intact.

### Actors
- Operator (CLI `add`/`refresh` — no VIA check)
- Dashboard user (POST/PATCH/refresh/catalog — double key VIA + allow-list + loopback)
- CISO (HARD names binding, re-gate evidence)
- MCP binary on PATH (spawned only via `which(basename)`)

### Business Rules
| Rule ID | Rule | Priority |
|---------|------|----------|
| BR-001 | `MCPServerConfig.validate_cmd` is the single syntax rule, delegating to `core/policy.validate_command_syntax` | Must |
| BR-002 | Default-deny: empty allow-list denies all local commands | Must |
| BR-003 | `MCP_GWAY_ALLOW_LOCAL_COMMANDS` CSV basenames; `*` invalid = deny + warn | Must |
| BR-004 | `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL=1` + marker `~/.config/mcp-gway/.local_unrestricted` (epoch, 0o600) valid 72h TTL | Must |
| BR-005 | Dashboard ALLOW = VIA==1 AND (unrestricted OR basename in allow-list) AND host loopback; non-loopback always deny | Must |
| BR-006 | `shutil.which(basename)` + `Path.resolve`; only basenames, no paths | Must |
| BR-007 | Syntax 1-8 tokens, regex `^[A-Za-z0-9_./:@-]{1,80}$`, no `..`, no `/` bare, no shell chars `; & $ ( ) \| \`` | Must |
| BR-008 | Spawn only `execvp(which(basename))`; never `shell=True` / `cmd /c` / `sh -c` | Must |
| BR-009 | PATCH `from_edit` re-gates with same policy (fix bypass) | Must |
| BR-010 | Refresh + catalog install re-gate with same policy | Must |
| BR-011 | `cwd` absolute + realpath + `is_dir`, else `invalid_cwd` | Must |
| BR-012 | Env denylist `PATH,PATHEXT,SYSTEMROOT,COMSPEC,LD_PRELOAD,LD_LIBRARY_PATH,DYLD_*,PYTHONPATH,PYTHONHOME,NODE_OPTIONS` | Must |
| BR-013 | Audit logs action/name/binary/reason only, secrets masked `***` | Must |
| BR-014 | Actionable errors: `binary not found in PATH` vs `command not allowed`, with `reason_code` | Must |
| BR-015 | Timeout 5000ms default, discovery semaphore 3 | Should |
| BR-016 | Local-first intact: `serve 0.0.0.0` without `MCP_GWAY_ALLOW_REMOTE=1` exits 2 + `X-Warning` + banner + Reveal disabled | Must |

### Edge Cases
- CSV with spaces, empties, `*`, paths, `..` → ignored + warn, deny.
- Marker missing, non-numeric, future epoch, expired >72h → unrestricted inactive.
- `VIA=0` with allow-listed binary → deny `via_dashboard_disabled`.
- Exposed host with allow-listed binary → deny `non_loopback_denied`.
- Allow-listed but `which` None → deny `binary_not_found`.
- `cwd` relative, non-existent, file-not-dir → `invalid_cwd`.
- Env `PATH`, `DYLD_FOO`, `LD_PRELOAD` → `denied_env`.
- Concurrent CLI ↔ Dashboard writes → last-write-wins (Registry atomic).

### Constraints
- No hardcode of binary names; no naming `DYNAMIC_LOCAL`; no shell.
- Env names CISO-arbitrated binding: `MCP_GWAY_ALLOW_LOCAL_COMMANDS`, `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL`, `MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD`.
- Marker `0o600`, content epoch seconds.

### NFRs
- Discovery non-blocking for API (`202`), semaphore 3, timeout +1s margin.
- Audit never logs secret values; dashboard masking `***` preserved.
- `ruff check` + `ruff format --check` clean; full suite green.
