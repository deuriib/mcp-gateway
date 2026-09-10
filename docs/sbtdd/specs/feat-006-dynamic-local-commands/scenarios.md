---
id: FEAT-006
slug: feat-006-dynamic-local-commands
title: Dynamic Local Commands Scenarios
status: Approved
created: 2026-09-07
updated: 2026-09-07
spec_ref: ./spec.md
plan_ref: ../../plans/feat-006-dynamic-local-commands/plan.md
adr_refs: ["../../../architecture/adr-009-dynamic-local-commands.md"]
slot_refs: ["scenario_FEAT-006"]
branch: feat/006-dynamic-local-commands
commits: []
tags: [local, security]
---

# Scenarios: feat-006-dynamic-local-commands

## Preconditions
- `Registry` on isolated `tmp_path`; `discover_tools` mocked; `policy.resolve_binary` mocked where noted.
- Env controlled per scenario via `monkeypatch.setenv/delenv`.

## Feature: Dynamic local commands
As an operator
I want allow-listed local binaries to be addable from CLI
So that npm-global PATH tools work without static hardcode, without opening RCE.

### Scenario: Happy path
Given allow-list `MCP_GWAY_ALLOW_LOCAL_COMMANDS=mybin` and `which(mybin)` resolves
When POST `/api/servers` with `{"type":"local","command":["mybin","--flag"]}`
Then 201 persisted with masked env and `reason_code=allow_list`.

### Scenario: Happy path unrestricted
Given `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL=1` with fresh marker (<72h)
When POST `/api/servers` with any syntactically valid basename
Then 201 with `reason_code=unrestricted`.

### Scenario: Error case default-deny
Given empty allow-list and no unrestricted marker
When POST `/api/servers` with `{"type":"local","command":["mybin"]}`
Then 403 `command not allowed` with `reason_code=not_allowlisted`.

### Scenario: Error case wildcard
Given `MCP_GWAY_ALLOW_LOCAL_COMMANDS=*`
When POST `/api/servers` local
Then 403 deny + warn logged.

### Scenario: Error case non-loopback
Given `Gateway(registry, host="0.0.0.0")` with allow-listed binary
When POST `/api/servers` local
Then 403 `reason_code=non_loopback_denied`.

### Scenario: Error case binary missing
Given allow-listed binary but `which` returns None
When POST `/api/servers` local
Then 403 `binary not found in PATH` with `reason_code=binary_not_found`.

### Scenario: Error case PATCH bypass closed
Given existing local server `mybin` allow-listed
When PATCH `/api/servers/srv` with `{"command":["evilbin"],"_from_edit":true}` where `evilbin` not allow-listed
Then 403 `not_allowlisted`, stored config unchanged.

### Scenario: Error case refresh re-gate
Given stored local server whose binary left the allow-list
When POST `/api/servers/srv/refresh`
Then 403 re-gate deny, no discovery spawned.

### Scenario: Error case cwd and env
Given allow-listed binary
When POST local with `cwd` relative or non-dir, or `environment` with `PATH`/`DYLD_X`
Then 400 `invalid_cwd` / `denied_env`.

### Scenario: Edge case TTL expiry
Given unrestricted marker epoch older than 72h
When POST local with unlisted binary
Then 403 `not_allowlisted` (unrestricted inactive).

### Scenario: Edge case CLI allow-list
Given allow-list `MCP_GWAY_ALLOW_LOCAL_COMMANDS=mybin` and `which(mybin)` resolves
When CLI `add --type local --command "mybin"`
Then success.
