---
name: mcp-gway
description: Manage MCP servers with the mcp-gway CLI (v2.2.0) — add/remove/update/list/inspect/refresh/serve/mcp/local-unrestricted plus Code Mode discovery. Use when operating the gateway CLI.
---

# mcp-gway CLI — v2.2.0

Standalone Python CLI (`mcp-gway = "mcp_gway.cli:main"`). OpenCode format only.
Registry (`servers/*.json` + `servers/*.pyi`) is the single source of truth.

## Commands (9)

| Command | Signature (from `src/mcp_gway/cli.py`) |
|---------|----------------------------------------|
| `add` | `mcp-gway add <name> --type local\|remote [flags]` |
| `remove` | `mcp-gway remove <name>` |
| `update` | `mcp-gway update <name> --tools <csv>` (`--tools` required) |
| `list` | `mcp-gway list` |
| `inspect` | `mcp-gway inspect <name>` |
| `serve` | `mcp-gway serve [--transport stdio\|http\|sse] [--host 127.0.0.1] [--port 8080] [--log-level LEVEL] [--registry-dir PATH]` (default `stdio`; `--host/--port` only with `http\|sse`) |
| `refresh` | `mcp-gway refresh [<name>] [--auth] [--oauth-port <port>]` |
| `mcp` | `mcp-gway mcp [--log-level LEVEL] [--registry-dir PATH]` — DEPRECATED hidden alias: `serve --transport stdio` equiv `mcp` (mismo loop NDJSON y mismos args a `_serve_stdio`, modulo aviso de deprecacion en stderr solo `mcp`); prefer `command: [mcp-gway, serve, --transport, stdio]` for OpenCode `type: local` |
| `local-unrestricted` | `mcp-gway local-unrestricted enable\|disable\|status` — break-glass marker 72h (0o600), explicit only |

## `add` — full flags (13, `cli.py:45-95`)

`--type` (**required**, `click.Choice(["local","remote"])`), `--url`, `--command`,
`--tools` (default `"*"`), `--env KEY=VALUE` (repeatable), `--header KEY=VALUE`
(repeatable, remote only), `--oauth-client-id`, `--oauth-client-secret`,
`--oauth-scope`, `--timeout` (int, default `5000` ms), `--enabled/--no-enabled`
(default enabled), `--oauth-port` (int, default `8989`), `--cwd`.

```bash
# Remote — transport auto-detected (streamable-http → sse → http)
mcp-gway add youtube --type remote --url https://api.example.com/mcp
mcp-gway add supabase --type remote --url https://mcp.supabase.com/mcp --header "Authorization=Bearer TOKEN"
mcp-gway add supabase --type remote --url https://mcp.supabase.com/mcp --oauth-client-id ID --oauth-client-secret SECRET --oauth-scope "openid profile"
mcp-gway add api --type remote --url https://api.example.com/mcp --timeout 10000 --enabled
mcp-gway add api --type remote --url https://api.example.com/mcp --timeout 10000 --no-enabled

# Local — --command is ONE string, split via shlex
mcp-gway add filesystem --type local --command "npx -y @anthropic/mcp-filesystem"
mcp-gway add tools --type local --command "python -m my_mcp_server" --env MY_VAR=value --cwd /path/to/workdir
```

Rules: `--command` required for `local`; `--url` required for `remote`.
Tool filter: `--tools "a,b"` restricts discovery; `"*"` keeps all.

## `serve` / `refresh` / `mcp` / `local-unrestricted` / others

```bash
mcp-gway list
mcp-gway inspect <name>            # prints stored .pyi signatures
mcp-gway remove <name>             # also deletes tokens/<name>.json + <name>_client.json
mcp-gway update <name> --tools "tool_a,tool_b"
mcp-gway refresh                   # all servers
mcp-gway refresh <name>            # one server
mcp-gway refresh <name> --auth     # force OAuth re-auth (also: --oauth-port 8989)
mcp-gway serve --port 8080                     # binds 127.0.0.1 by default
mcp-gway serve --host 127.0.0.1 --port 8080
curl -s http://127.0.0.1:8080/health | jq

# Server-side NDJSON: expose this gateway as an MCP server over stdio
mcp-gway serve --transport stdio --log-level info   # reads JSON-RPC 2.0 from stdin, answers on stdout (logs → stderr)
# OpenCode: { "type": "local", "command": ["mcp-gway", "serve", "--transport", "stdio"] }

# Break-glass 72h (explicit only — env alone never activates)
mcp-gway local-unrestricted enable
mcp-gway local-unrestricted status        # disabled|marker-missing|expired|future|marker-insecure|marker-unreadable|marker-invalid|active
mcp-gway local-unrestricted disable
```

`serve` flags: `--host` (default `127.0.0.1`), `--port` (int, default `8080`),
`--log-level trace|debug|info|warning|error|critical` (default `None` → resolved
from `MCP_GWAY_LOG_LEVEL`, else `info`).

## Guards — what does NOT exist

- `--type` accepts **only** `local|remote` (`cli.py:50`). Legacy
  `http|stdio|sse|streamable-http` are rejected by click.
- `--args` and `--docs-url` **do not exist** as CLI flags. For `local`, pass the
  full invocation as one `--command` string. There is no `--args` splitter.
- Name rule (`models.py`): `^[A-Za-z_][A-Za-z0-9_]{0,63}$`, ASCII, no
  hyphens/spaces, no path separators, not reserved (`con`, `prn`, `aux`, `nul`,
  `com1-9`, `lpt1-9`).

## Local-first security (do not bypass without explicit order)

- `serve` binds `127.0.0.1` by default. `--host 0.0.0.0` (or any non-loopback)
  without `MCP_GWAY_ALLOW_REMOTE=1` → `Error: binding to non-loopback host ...`
  + `exit 2`. With opt-in → `WARNING: server exposed on non-loopback` in log;
  never expose without firewall/auth in front.
- `local` is default-deny: `MCP_GWAY_ALLOW_LOCAL_COMMANDS="npx,uvx,python3,bunx"`
  allow-list (CSV basenames, case-insensitive). Empty = deny. `*`, paths, and
  invalid entries are denied + warn (`core/policy.py:16-80`). `--cwd` must be an
  absolute path. Denylisted env vars (`PATH`, `LD_PRELOAD`, `PYTHONPATH`, …)
  are rejected. Nota CISO opt-in: `bunx` solo como recomendado en documentación
  (no default en código, default-deny vacío se mantiene); solo opt-in con
   pin + owner + regate 90d; `bun` runtime sigue fuera; denylist
   EXACT PATH,PATHEXT,SYSTEMROOT,COMSPEC,LD_PRELOAD,LD_LIBRARY_PATH,PYTHONPATH,PYTHONHOME,NODE_OPTIONS,NODE_PATH,NODE_EXTRA_CA_CERTS,NODE_TLS_REJECT_UNAUTHORIZED + PREFIXES DYLD_,NPM_CONFIG_,BUN_,UV_ + PATH controlado (`NODE_ENV` permitido, no denylisted); prohibido `*`, paths o shell.
- `remote --url` has an SSRF-guard (`models.py:115-163`): only `http|https`;
  private/loopback/link-local/reserved/multicast hosts rejected
  (`localhost` only allowed under test harness).
- Secrets: never put real tokens in `--header` / `--oauth-client-secret`
  (shell history leak). Prefer `mcp-gway refresh <name> --auth`. Tokens live in
  `~/.config/mcp-gway/tokens/` (`0o600`).
