# INSTALL — mcp-gateway opencode plugin (V2)

> *"Haces las cosas como para Dios, por eso trabajas con excelencia y dedicación."*

Single-file local opencode V2 plugin (`@opencode/plugin`, `Plugin.define({ id: "mcp-gateway" })`). No npm publish, no Node/mise toolchain beyond what opencode already provides.

## Prerequisites

- `opencode` V2 on `PATH` (`opencode --version` prints `v2.x`).
- Gateway reachable over localhost HTTP: run
  `mcp-gway serve --transport http --host 127.0.0.1 --port 8080`
  (default entry URL `http://127.0.0.1:8080/mcp`) before starting opencode.
- Optional env overrides (export in the shell that launches opencode):
  `MCP_GWAY_URL` (custom gateway URL), `MCP_GWAY_TOKEN` (adds
  `Authorization: Bearer <token>` header only when set).
- `mcp-gway` on `PATH` where the gateway runs (`mcp-gway --help` works).
- `@opencode/plugin` resolvable from the target project (the plugin imports
  it and Bun resolves via ancestor `node_modules`). If the plugin shows
  `failed: Plugin failed to load / Cannot find package '@opencode/plugin'`
  in `opencode api get "/api/plugin?location%5Bdirectory%5D=<PROJECT>"`,
  run `bun add -D @opencode/plugin@2.0.9` (or `npm i -D`) once in `<PROJECT>`.

## What gets installed

| Target project path | Source in this repo | Notes |
| ------------------- | ------------------- | ----- |
| `<PROJECT>/.opencode/plugins/mcp-gateway.ts` | `<CHECKOUT>/plugins/opencode/mcp-gateway.ts` | The plugin; auto-loaded per-project. Only impl file. V2-only, no V1 shim. |
| `<PROJECT>/.opencode/skills/mcp-gway/SKILL.md` | `<CHECKOUT>/skills/mcp-gway/SKILL.md` | Skill source; auto-discovered by V2 (no config edit). |

`<CHECKOUT>` = your local checkout of this repository.
`<PROJECT>` = the target project where opencode runs.

Legacy `<PROJECT>/skills/mcp-gway/SKILL.md` still loads via the plugin's `ctx.skill.transform` fallback, but new installs should use `.opencode/skills/`.

No other files are needed. Do not publish anything, do not install extra runtimes.
`package.json` keeps `main`/`exports` pointing at the plugin file with dependency `@opencode/plugin` (pinned to the targeted V2 release).

## Option A — copy from a git checkout

```powershell
New-Item -ItemType Directory -Force -Path "<PROJECT>/.opencode/plugins" | Out-Null
Copy-Item -LiteralPath "<CHECKOUT>/plugins/opencode/mcp-gateway.ts" -Destination "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Force
New-Item -ItemType Directory -Force -Path "<PROJECT>/.opencode/skills/mcp-gway" | Out-Null
Copy-Item -LiteralPath "<CHECKOUT>/skills/mcp-gway/SKILL.md" -Destination "<PROJECT>/.opencode/skills/mcp-gway/SKILL.md" -Force
```

## Option B — copy via `file:///` path

Same files, sourced through an explicit `file:///` location instead of
a git working tree (useful when you only have the file path, not a clone):

```powershell
Copy-Item -LiteralPath "<FILE_URL_PATH>/plugins/opencode/mcp-gateway.ts" -Destination "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Force
Copy-Item -LiteralPath "<FILE_URL_PATH>/skills/mcp-gway/SKILL.md" -Destination "<PROJECT>/.opencode/skills/mcp-gway/SKILL.md" -Force
```

`<FILE_URL_PATH>` = the local path behind your `file:///` source
(e.g. the UNC/absolute path your `file:///` URL points at).
Prefer Option A when you have a checkout; both options install
byte-identical files.

## Verify

```powershell
Test-Path -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts"
Select-String -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Pattern "MCP-GWAY v2.7.0" -SimpleMatch
Select-String -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Pattern '@opencode/plugin' -SimpleMatch
Select-String -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Pattern 'Plugin.define' -SimpleMatch
Select-String -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Pattern 'ctx.mcp.transform' -SimpleMatch
Select-String -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Pattern 'ctx.session.hook("context"' -SimpleMatch
Select-String -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Pattern 'ctx.session.hook("compaction"' -SimpleMatch
Select-String -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Pattern 'type: "remote"' -SimpleMatch
Select-String -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Pattern "http://127.0.0.1:8080/mcp" -SimpleMatch
Test-Path -LiteralPath "<PROJECT>/.opencode/skills/mcp-gway/SKILL.md"
curl.exe -s http://127.0.0.1:8080/health
opencode --version
```

Expected:

- Plugin file exists; it mentions marker `MCP-GWAY v2.7.0`, imports `@opencode/plugin`, defines `id: "mcp-gateway"`, registers `gateway` via `ctx.mcp.transform` (remote HTTP `http://127.0.0.1:8080/mcp`, `oauth: false`, `disabled: false`, `timeout: { catalog, execution }`, env-overridable via `MCP_GWAY_URL`, optional `Authorization` via `MCP_GWAY_TOKEN` only when set).
- System rules injected via `ctx.session.hook("context")` and re-injected via `ctx.session.hook("compaction")` (never throws, deduped by marker).
- Gateway health endpoint answers (`curl /health`) while
  `mcp-gway serve --transport http` runs on loopback.
- Skill file exists under `.opencode/skills/`, so V2 auto-discovery resolves it with no config edit.
- `opencode --version` prints `v2.x` without error.

Then restart opencode in `<PROJECT>` (`opencode service restart` if using the shared background service); the plugin loads automatically (no registration step, no config edit).

## Rollback

```powershell
Remove-Item -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Force
```

Opencode then runs as before (all hooks are additive; transform merge
never overwrites user values).
