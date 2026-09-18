# INSTALL — mcp-gateway opencode plugin

> *"Haces las cosas como para Dios, por eso trabajas con excelencia y dedicación."*

Single-file local opencode plugin. No npm publish, no `package.json` `main`,
no Node/mise toolchain beyond what opencode already provides.

## Prerequisites

- `opencode` on `PATH` (`opencode --version` works).
- Gateway reachable over localhost HTTP: run
  `mcp-gway serve --transport http --host 127.0.0.1 --port 8080`
  (default entry URL `http://127.0.0.1:8080/mcp`) before starting opencode.
- Optional env overrides (export in the shell that launches opencode):
  `MCP_GWAY_URL` (custom gateway URL), `MCP_GWAY_TOKEN` (adds
  `Authorization: Bearer <token>` header only when set).
- `mcp-gway` on `PATH` where the gateway runs (`mcp-gway --help` works).

## What gets installed

| Target project path | Source in this repo | Notes |
| ------------------- | ------------------- | ----- |
| `<PROJECT>/.opencode/plugins/mcp-gateway.ts` | `<CHECKOUT>/plugins/opencode/mcp-gateway.ts` | The plugin; auto-loaded per-project (load order #4). Only impl file. |
| `<PROJECT>/skills/mcp-gway/SKILL.md` | `<CHECKOUT>/skills/mcp-gway/SKILL.md` | Skill source; plugin wires source root `"skills"` via `config.skills.paths`. |

`<CHECKOUT>` = your local checkout of this repository.
`<PROJECT>` = the target project where opencode runs.

No other files are needed. Do not create a `package.json` `main`,
do not publish anything, do not install extra runtimes.

## Option A — copy from a git checkout

```powershell
New-Item -ItemType Directory -Force -Path "<PROJECT>/.opencode/plugins" | Out-Null
Copy-Item -LiteralPath "<CHECKOUT>/plugins/opencode/mcp-gateway.ts" -Destination "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Force
New-Item -ItemType Directory -Force -Path "<PROJECT>/skills/mcp-gway" | Out-Null
Copy-Item -LiteralPath "<CHECKOUT>/skills/mcp-gway/SKILL.md" -Destination "<PROJECT>/skills/mcp-gway/SKILL.md" -Force
```

## Option B — copy via `file:///` path

Same files, sourced through an explicit `file:///` location instead of
a git working tree (useful when you only have the file path, not a clone):

```powershell
Copy-Item -LiteralPath "<FILE_URL_PATH>/plugins/opencode/mcp-gateway.ts" -Destination "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Force
Copy-Item -LiteralPath "<FILE_URL_PATH>/skills/mcp-gway/SKILL.md" -Destination "<PROJECT>/skills/mcp-gway/SKILL.md" -Force
```

`<FILE_URL_PATH>` = the local path behind your `file:///` source
(e.g. the UNC/absolute path your `file:///` URL points at).
Prefer Option A when you have a checkout; both options install
byte-identical files.

## Verify

```powershell
Test-Path -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts"
Select-String -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Pattern "MCP-GWAY v2.6.0" -SimpleMatch
Select-String -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Pattern 'mcp["gateway"]' -SimpleMatch
Select-String -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Pattern 'type: "remote"' -SimpleMatch
Select-String -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Pattern "http://127.0.0.1:8080/mcp" -SimpleMatch
Test-Path -LiteralPath "<PROJECT>/skills/mcp-gway/SKILL.md"
curl.exe -s http://127.0.0.1:8080/health
opencode --version
```

Expected:

- Plugin file exists; it mentions marker `MCP-GWAY v2.6.0` and MCP entry
  `gateway` (exactly `mcp["gateway"]`, remote HTTP
  `http://127.0.0.1:8080/mcp`, env-overridable via `MCP_GWAY_URL`,
  optional `Authorization` via `MCP_GWAY_TOKEN` only when set).
- Gateway health endpoint answers (`curl /health`) while
  `mcp-gway serve --transport http` runs on loopback.
- Skill file exists, so the plugin's `config.skills.paths` wiring
  (`"skills"` source root) resolves during skill discovery.
- `opencode --version` prints without error.

Then restart opencode in `<PROJECT>`; the plugin loads automatically
(no registration step, no config edit).

## Rollback

```powershell
Remove-Item -LiteralPath "<PROJECT>/.opencode/plugins/mcp-gateway.ts" -Force
```

Opencode then runs as before (all hooks are additive; config merge
never overwrites user values).
