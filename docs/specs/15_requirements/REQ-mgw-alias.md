# Requirements Index: Minimal CLI Alias mgw

**Owner:** vasquez (CTO)
**Brief Reference:** BRIEF-MGW-001
**Domains-Touched:** [engineering]

## Functional Requirements

| ID | Requirement | Priority | Source | Spec | Domain | Evidence Type |
|----|-------------|----------|--------|------|--------|---------------|
| REQ-F-001 | Both binaries expose identical command tree + flags + exit codes | P0 | BRIEF-MGW-001 | SPEC-MGW-001 | engineering | test (`tests/test_cli_alias.py` + help diff) |
| REQ-F-002 | Clean install exposes `mcp-gway` + `mgw` on PATH | P0 | BRIEF-MGW-001 | SPEC-MGW-001 | engineering | review (install repro log) |
| REQ-F-003 | `--help`/`--version` identical modulo prog name | P1 | BRIEF-MGW-001 | SPEC-MGW-001 | engineering | test |

## Non-Functional Requirements

| ID | Requirement | Category | Target |
|----|-------------|----------|--------|
| REQ-NF-001 | Suite green + lint/format clean | Reliability | 255/255 + new tests; `ruff check` + `ruff format --check` clean |
| REQ-NF-002 | No new trust boundary / names unchanged | Security | No new endpoint/adapter/payload; `MCP_GWAY_ALLOW_*` untouched; no secrets in diff |
| REQ-NF-003 | Docs coherent (shortcut shown, canonical intact) | Usability | README + AGENTS.md diff |

## Domain Controls (only touched domains)

| Domain | Control | Owner |
|--------|---------|-------|
| engineering | Packaging diff minimal (`pyproject.toml` scripts + docs + tests); `cli.py:main` signature frozen | vasquez |
| security | Conditional lens only — full STRIDE only if new boundary appears | barrera (path-cite) |
