---
id: FEAT-006
slug: feat-006-dynamic-local-commands
title: Dynamic Local Commands Acceptance
status: Approved
created: 2026-09-07
updated: 2026-09-07
spec_ref: ./spec.md
plan_ref: ../../plans/feat-006-dynamic-local-commands/plan.md
adr_refs: ["../../../architecture/adr-009-dynamic-local-commands.md"]
slot_refs: ["acceptance_FEAT-006"]
branch: feat/006-dynamic-local-commands
commits: []
tags: [local, security, acceptance]
---

# Acceptance: feat-006-dynamic-local-commands

## Acceptance Criteria

### AC-001: Allow-list permits listed basename
- **Given** `MCP_GWAY_ALLOW_LOCAL_COMMANDS=mybin`, `resolve_binary→/usr/bin/mybin`, `check_cwd→tmp`
- **When** POST `/api/servers` `{"name":"a","type":"local","command":["mybin"]}`
- **Then** 201, `tool_count` present
- **Test Data**: `mybin`, mock discover `[]`
- **Traces**: BR-003, BR-006

### AC-002: Default-deny blocks unlisted
- **Given** empty allow-list, no marker
- **When** POST local `["otherbin"]`
- **Then** 403 `command not allowed`, `reason_code=not_allowlisted`
- **Test Data**: `otherbin`
- **Traces**: BR-002

### AC-003: Wildcard denied
- **Given** `MCP_GWAY_ALLOW_LOCAL_COMMANDS=*`
- **When** POST local `["mybin"]`
- **Then** 403 deny
- **Test Data**: `*`
- **Traces**: BR-003

### AC-004: Unrestricted fresh allows any
- **Given** `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL=1` + marker epoch now, `resolve_binary→/bin/x`
- **When** POST local `["freshbin"]`
- **Then** 201
- **Test Data**: marker `now`, `freshbin`
- **Traces**: BR-004

### AC-005: Unrestricted expired denies
- **Given** `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL=1` + marker epoch now-73h
- **When** POST local `["freshbin"]`
- **Then** 403 `not_allowlisted`
- **Test Data**: epoch `now-73h`
- **Traces**: BR-004

### AC-007: Non-loopback denies
- **Given** `Gateway(registry, host="0.0.0.0")`, allow-list `mybin`
- **When** POST local `["mybin"]`
- **Then** 403 `non_loopback_denied`
- **Test Data**: host `0.0.0.0`
- **Traces**: host loopback gate (serve-level; former BR-005 removed 2026-09-10)

### AC-008: Binary missing actionable
- **Given** allow-list `mybin`, `resolve_binary→None`
- **When** POST local `["mybin"]`
- **Then** 403 `binary not found in PATH`, `reason_code=binary_not_found`
- **Test Data**: `mybin`
- **Traces**: BR-006, BR-014

### AC-009: PATCH re-gate closes bypass
- **Given** stored `srv` with `mybin` allow-listed
- **When** PATCH `/api/servers/srv` `{"command":["evilbin"],"_from_edit":true}`
- **Then** 403, stored command still `["mybin"]`
- **Test Data**: `evilbin` unlisted
- **Traces**: BR-009

### AC-010: Refresh re-gate
- **Given** stored local `srv` with binary removed from allow-list
- **When** POST `/api/servers/srv/refresh`
- **Then** 403 deny, no discovery call
- **Test Data**: `srv`
- **Traces**: BR-010

### AC-011: cwd and env gates
- **Given** allow-list `mybin`
- **When** POST local with `cwd:"relative/path"` then with `environment:{"PATH":"x"}` then `{"DYLD_FOO":"x"}`
- **Then** 400 `invalid_cwd` / `denied_env` respectively
- **Test Data**: `relative/path`, `PATH`, `DYLD_FOO`
- **Traces**: BR-011, BR-012

### AC-012: CLI allow-list + audit clean
- **Given** allow-list `mybin`, `resolve_binary→/usr/bin/mybin`
- **When** CLI `add --type local --command "mybin"` and `refresh`
- **Then** exit 0; logs contain `reason=allow_list` without secret values
- **Test Data**: `mybin`, env `FOO=bar` masked in registry GET
- **Traces**: BR-013, BR-014
