# mcp-gateway — Install (V2)

> *"Haces las cosas como para Dios, por eso trabajas con excelencia y dedicación."*

Requires **opencode V2** (`opencode --version` → `2.x`). The plugin is V2-only:
`plugins/opencode/mcp-gateway.ts` exports `Plugin.define({ id: "mcp-gateway" })`
from `@opencode/plugin`. V1 (`@opencode-ai/plugin`, `plugin` key,
`experimental.*` hooks) is not supported.

## Prerequisites

- [opencode](https://opencode.ai/) V2 installed
- Git (repo is public — no `gh` auth needed unless you fork private)
- Gateway reachable over localhost HTTP: run
  `mcp-gway serve --transport http --host 127.0.0.1 --port 8080`
  (default entry URL `http://127.0.0.1:8080/mcp`) before starting opencode
- `mcp-gway` on `PATH` where the gateway runs (`mcp-gway --help` works)
- Optional env overrides (export in the shell that launches opencode):
  `MCP_GWAY_URL` (custom gateway URL), `MCP_GWAY_TOKEN` (adds
  `Authorization: Bearer <token>` header only when set)
- No npm publish, no Node/mise toolchain beyond what opencode already provides

Config locations:

- Global: `~/.config/opencode/opencode.json`
- Project override: `<your-project>/opencode.json`

> Key name is `plugins` (V2 array). The old V1 `plugin` key and
> `{"name": "mcp-gateway@..."}` object form are skipped by V2 with a
> normalization warning — use the forms below.

## Option A — Package install (normal use, Recommended)

```bash
opencode plugin add github:deuriib/mcp-gateway
```

This installs the repo as a package; the loader uses the repo-root
`package.json` (`main: ./plugins/opencode/mcp-gateway.ts`,
dependency `@opencode/plugin@2.0.9`). The `mcp-gway` skill resolves via
local-path `ctx.skill.transform` (project `canonical` → `directory` →
plugin `directory`, trying `.opencode/skills/mcp-gway/SKILL.md` then legacy
`skills/mcp-gway/SKILL.md`) plus V2 auto-discovery of
`.opencode/skills/` — never from cwd, never from URL.

Equivalent manual entry (`opencode.jsonc`):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugins": ["mcp-gateway@github:deuriib/mcp-gateway"]
}
```

## Option B — Local file (development only)

Use when editing this repo and want live changes. Copy the single file into
the project's auto-discovered plugin dir (a root-level `plugins/` dir is NOT
auto-discovered — only `.opencode/plugins/` is), plus the skill file for
auto-discovery:

```bash
mkdir -p <your-project>/.opencode/plugins <your-project>/.opencode/skills/mcp-gway
cp plugins/opencode/mcp-gateway.ts <your-project>/.opencode/plugins/mcp-gateway.ts
cp skills/mcp-gway/SKILL.md <your-project>/.opencode/skills/mcp-gway/SKILL.md
```

`@opencode/plugin` must resolve from the plugin file (nearest `node_modules`
walking up). If load fails with `Cannot find package '@opencode/plugin'`,
run `bun add -D @opencode/plugin@2.0.9` (or `npm i -D`) once in `<your-project>`.

Notes:

- The source of truth stays at `plugins/opencode/mcp-gateway.ts` (plugin) and
  `skills/mcp-gway/SKILL.md` (skill) in this repo — never edit the copies
  directly; re-copy after every edit.
- Never commit a `file:///` path to a shared project config.

## Verify

1. Quit + restart opencode (config is not hot-reloaded; `opencode service restart`).
2. `opencode api get "/api/plugin?location[directory]=<your-project>"` lists
   `mcp-gateway` with `status: active`.
3. `opencode api get "/api/skill?location[directory]=<your-project>"` lists
   `mcp-gway` (single skill; ID is path-derived, frontmatter `name` is display only).
4. Start any session — the system prompt contains `MCP-GWAY v2.8.0`
   (Gateway Protocol card, deduped by marker).
5. Gateway + MCP are live:

```bash
curl -s http://127.0.0.1:8080/health
opencode mcp list   # expect: gateway connected
opencode --version  # expect: v2.x
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Plugin not loaded after edit | quit + restart opencode (or `opencode service restart`); sessions keep the old system prompt |
| `github:` install asks for auth | repo is public — update opencode; private forks need `gh auth login` or the `git+ssh://` variant |
| Duplicated `MCP-GWAY` banner | update to latest — `systemHasRules()` dedupes by marker; don't list both git + local at once |
| Skills not found | keep only one `mcp-gateway` entry; confirm `<your-project>/.opencode/skills/mcp-gway/SKILL.md` exists (exact `SKILL.md` name) and check log for `[mcp-gateway] skill load skipped` (tells you which bases were tried) |
| Skill loads wrong content | transform guards with `if (!editor.get("mcp-gway"))` — a later source with the same ID wins; remove the duplicate |
| Build fails | plugin must stay single-file, zero runtime deps beyond `@opencode/plugin@2.0.9`: `bun build plugins/opencode/mcp-gateway.ts --external @opencode/plugin` |
| `Cannot find package '@opencode/plugin'` | install `@opencode/plugin@2.0.9` where the plugin file resolves (repo root has it; target project needs it too) |
| Old `{"name": "mcp-gateway@..."}` entry ignored | V2 wants bare `"mcp-gateway@..."` string or `{"package": ..., "options": ...}` — rewrite the entry |
| Gateway not connected | start `mcp-gway serve --transport http --host 127.0.0.1 --port 8080` first; check `MCP_GWAY_URL` / `MCP_GWAY_TOKEN` in the launching shell |

## V2 notes (behavior deltas)

- System injection is `ctx.session.hook("context")` as `{type:"text", text}`
  parts; compaction reminder is `ctx.session.hook("compaction")`.
- Skill is registered via `ctx.skill.transform` as `mcp-gway` (single skill,
  filesystem `location:`, content without frontmatter, `description` required
  for advertising). No URL fetching — URL `location` is invalid per `Skill.Info`.
- MCP server is registered via `ctx.mcp.transform` as `gateway`
  (`type: "remote"`, `url: http://127.0.0.1:8080/mcp`, `oauth: false`,
  `disabled: false`, `timeout: { catalog, execution }`).
- File-based `.opencode/skills/` discovery is the V2-native path; the
  transform is the local-path fallback/injector for the same `mcp-gway` ID.

## Which to use?

- Default: **Option A (package)** — portable, shareable.
- Only when editing `mcp-gateway.ts` or `skills/`: **Option B (local)** — then restart opencode after every edit.

## Rollback

```bash
opencode plugin remove mcp-gateway@github:deuriib/mcp-gateway
# and/or, for local copies:
rm <your-project>/.opencode/plugins/mcp-gateway.ts
```

Opencode then runs as before (all hooks are additive; transform merge
never overwrites user values).
