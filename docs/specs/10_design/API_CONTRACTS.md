# API Contracts: CLI Alias mgw

**Owner:** vasquez (CTO)
**Version:** v1
**Last Updated:** 2026-09-16
**Spec:** SPEC-MGW-001

## CLI Contract (packaging-only; no HTTP change)

- `mcp-gway <cmd> [flags]` ≡ `mgw <cmd> [flags]` for all `<cmd>` in `add/remove/list/inspect/refresh/serve/local-unrestricted` (+ hidden `mcp` alias path)
- `--help` output identical modulo prog name; exit 0
- `--version` identical; matches `pyproject.toml:project.version`
- Unknown flag / bad host behavior identical (`serve --host 0.0.0.0` without `MCP_GWAY_ALLOW_REMOTE=1` → `exit 2` under both names)
- No new flags, no changed defaults, no new env vars in this SPEC

## HTTP/SSE Contract (unchanged, cited for non-regression)

- `GET+POST /mcp`, `GET /health`, `/ready`, `/live`, `/metrics` — no shape change
- `POST /mcp/messages?session_id=...` alias of `_mcp_post` — untouched

## Sign-off

- Engineering: vasquez approves packaging diff (`pyproject.toml` + docs + tests)
- Security: barrera path-cite conditional — full `review-security` only if diff introduces new boundary/payload (not expected)
