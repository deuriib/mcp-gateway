# Architecture Contract: CLI Alias mgw

**Owner:** vasquez (CTO) for engineering contracts
**Version:** v1
**Last Updated:** 2026-09-16
**Domains-Touched:** [engineering]

## Overview

Packaging-only alias. One click group (`mcp_gway.cli:main`) bound to two console scripts (`mcp-gway` canonical + `mgw` shortcut). No runtime fork, no new service, no protocol change. HTTP/SSE surface and local-first posture untouched.

## Components

| Component | Responsibility | Interface |
|-----------|---------------|-----------|
| `[project.scripts]` | Expose both binaries on install | `pyproject.toml:19-20` → `mcp-gway` + `mgw` = `mcp_gway.cli:main` |
| `cli.main` | Single command tree + flags | `src/mcp_gway/cli.py:74-76` click group; all subcommands inherit |
| docs | Show shortcut without breaking canonical | README + AGENTS.md examples |

## Data Flow

Shell → (`mcp-gway` | `mgw`) → `mcp_gway.cli:main` → same subcommand dispatch → same registry (`servers/*.json` + `*.pyi`) → same transports (stdio/http/sse). `argv[0]` only affects help prog name rendering.

## Invariants

- INV-001: Parity 1:1 — every command/flag/exit code identical under both names
- INV-002: `mcp-gway` stays canonical; `mgw` is shortcut, never replacement in this SPEC
- INV-003: No new endpoint, adapter, payload, port, or trust boundary
- INV-004: Local-first unchanged — `127.0.0.1` default; `0.0.0.0` requires `MCP_GWAY_ALLOW_REMOTE=1` else `exit 2`
- INV-005: `MCP_GWAY_ALLOW_LOCAL_COMMANDS` / `MCP_GWAY_ALLOW_UNRESTRICTED_LOCAL` names + semantics untouched
- INV-006: Single version source (`pyproject.toml:project.version` + `src/mcp_gway/__init__.py:__version__`) reported by both binaries

## Non-Functional Requirements

- Performance: no added startup cost beyond interpreter + click dispatch (alias adds zero import)
- Availability: install must yield both shims on POSIX + Windows (`mgw.exe`)
- Security: posture unchanged, barrera conditional only — deny default, no secrets in code/config/logs/examples, least privilege per interface (guardrails 1-14)
