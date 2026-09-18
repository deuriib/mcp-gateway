# PROPOSED_CHANGES — opencode plugin mcp-gateway (single-mode lane)

**Spec refs (reference-only):** bounded BRIEF in parent chat (opencode plugin
mcp-gway, approved); opencode docs 2026-09-18 (`plugins`, `mcp-servers`,
`skills`, `rules`, `config` + live schema `https://opencode.ai/config.json`);
repo `skills/mcp-gway/SKILL.md` (single source of truth
for the skill); `AGENTS.md` MCP Rules Gateway Protocol block (verbatim source).
**Execution mode:** `single` (engineering-only, direct, no dispatch).
**DOMAINS:** `[engineering]`.
**Skills cited:** `frame-ship:using-frame-ship` + `frame-ship:translate-to-spec`
(SPEC below) + `frame-ship:propose-changes` (this proposal), then
`frame-ship:execute-spec` → `frame-ship:quality-gate` → `frame-ship:verify-handoff`.
**Date:** 2026-09-18 (fix rev 2026-09-18: skill wiring via `config.skills`;
fix rev 2026-09-18b: MCP entry `gateway` + marker freeze `MCP-GWAY v2.5.0`;
fix rev 2026-09-18c: INSTALL.md scope — REQ-OP-008;
fix rev 2026-09-18d: HTTP transport — `mcp["gateway"]` remote
`http://127.0.0.1:8080/mcp` env-driven, user-approved).
**Owner:** vasquez (CTO, engineering chain owner).

## SPEC — REQ-IDs (testable)

- **REQ-OP-001** — Local-file plugin at `.opencode/plugins/mcp-gateway.ts`
  exporting a typed `Plugin` (`import type { Plugin } from "@opencode-ai/plugin"`),
  auto-loaded by opencode with no npm publish required.
- **REQ-OP-002** — `config` hook wires `mcp["gateway"]` as REMOTE HTTP
  (`type: "remote"`, `url` env-driven default
  `http://127.0.0.1:8080/mcp` via `MCP_GWAY_URL`, `enabled: true`,
  `timeout: 5000`, `oauth: false`) WITHOUT overwriting a user-defined entry;
  merges `config.skills.paths` with `"skills"` source root if absent. MCP entry
  name is EXACTLY `gateway` (never `mcp-gway`). Optional `headers:
  { Authorization: "Bearer <MCP_GWAY_TOKEN>" }` ONLY when env
  `MCP_GWAY_TOKEN` is set/non-empty (read at `config` time, never hardcoded).
  Shape evidence 2026-09-18: opencode docs `mcp-servers`
  (`type: "remote"` + `url` + `headers` + `enabled`/`timeout`, `oauth: false`
  to disable auto-OAuth for header-auth servers; env interpolation form
  `{env:VAR}` is file-config; plugin resolves `process.env` directly at
  `config` time so programmatic values need no interpolation pass).
  No-overwrite guard semantics preserved for the new shape
  (`if (!mcp["gateway"])`).
- **REQ-OP-003** — System injection via `experimental.chat.system.transform`
  appends `<!-- MCP-GWAY v2.5.0 -->` + the MCP Rules Gateway Protocol block
  VERBATIM (4-step order + Starlark calling convention + Anti-Patterns table);
  defensive no-throw. Injection marker is EXACTLY `MCP-GWAY v2.5.0` everywhere
  (single `MARKER` constant, no duplicated literals).
- **REQ-OP-004** — Compaction re-injection via
  `experimental.session.compacting` pushing the same block prefixed with
  marker `MCP-GWAY v2.5.0` (`<!-- MCP-GWAY v2.5.0 -->\n` + block), so rules
  survive compaction/summarization. Same `MARKER` constant as REQ-OP-003;
  Gateway Protocol block preserved verbatim.
- **REQ-OP-005** — Skill wiring via `config.skills` (NOT `instructions` merge,
  NOT a duplicated copy). Schema evidence 2026-09-18: live
  `https://opencode.ai/config.json` defines `skills` as OBJECT
  `{ paths?: string[], urls?: string[] }` ("Additional skill folder paths");
  `skills` loader scans `**/SKILL.md` inside each source root, so the plugin
  pushes source root `"skills"` into `config.skills.paths` (additive,
  no-overwrite). Single source stays `skills/mcp-gway/SKILL.md` → no drift.
  Defensive forward-compat: if `config.skills` ever arrives as V2 ARRAY, push
  there instead. `instructions` (`string[]` of rule files, `config#instructions`)
  is NOT touched by this plugin.
- **REQ-OP-006** — No secrets/tokens/credentials in plugin, config, logs, or
  examples; no network fetch beyond the gateway's own localhost HTTP entry;
  env names only (`MCP_GWAY_URL`, `MCP_GWAY_TOKEN`), values never hardcoded.
  Remote URL stays loopback by default (`127.0.0.1`); non-loopback only via
  explicit `MCP_GWAY_URL` operator override.
- **REQ-OP-007** — Verifiable without opencode runtime: structural asserts
  (exports Plugin, hooks present, verbatim block present, command shape).
- **REQ-OP-008** — Install guide at `.opencode/INSTALL.md` adapted to THIS
  plugin: single-file local plugin `mcp-gateway.ts` (auto-loaded per-project,
  no npm publish, no `package.json` main, no Node/mise toolchain);
  prerequisites `opencode` + `mcp-gway` on PATH; named-path style with
  Option A (git checkout copy) vs Option B (`file:///` copy); verify steps
  check marker `MCP-GWAY v2.5.0` + mcp `gateway` + skill discovery; creed
  line kept; no invented git URL / package name.

## Architecture contract

Local-file plugin (auto-loaded from `.opencode/plugins/`, load order #4 after
global/project config + global plugins). Three hooks, one constant, plus two
env resolvers for the HTTP entry:

| Hook | Role |
| ---- | ---- |
| `config` | Merge `mcp["gateway"]` remote HTTP + `skills.paths` (`"skills"` source root); never overwrite user values |
| `experimental.chat.system.transform` | Append `<!-- MCP-GWAY v2.5.0 -->` + `MCP_RULES` verbatim to system prompt |
| `experimental.session.compacting` | Push `MCP-GWAY v2.5.0` + `MCP_RULES` into compaction context |

Env resolvers (no-throw): `resolveGatewayUrl()` =
`MCP_GWAY_URL.trim()` or `http://127.0.0.1:8080/mcp`;
`resolveGatewayHeaders()` = `{ Authorization: "Bearer <MCP_GWAY_TOKEN>" }`
iff `MCP_GWAY_TOKEN` set/non-empty, else no `headers` key. `oauth: false`
always (gateway has no OAuth; prevents spurious auto-OAuth discovery against
localhost, per opencode `mcp-servers` guidance for header-auth servers).

`MCP_RULES` constant = verbatim Gateway Protocol block (source: persona
`MCP Rules — Gateway Protocol`; backticks escaped as `\`` inside the TS
template literal). All hooks wrapped so a failure degrades to no-op, never a
broken session. Assumption (stated): exact `output` shapes for the two
`experimental.*` hooks follow the `(input, output)` mutate-in-place convention
(`output.system` string-or-array; `output.context` array; `output.prompt`
replace); code handles string/array/absent defensively.

## Change list (approved targets ONLY)

1. `.opencode/plugins/mcp-gateway.ts` — NEW (the plugin; only impl file).
2. `.opencode/INSTALL.md` — NEW (install guide for THIS plugin; only docs file, REQ-OP-008).
3. `docs/specs/40_workspace/engineering/PROPOSED_CHANGES.md` — this proposal.
4. Gate artifacts (later stages): quality-gate report + HANDOFF under
   `40_workspace/{quality-gate,verify-handoff}/`.
5. NO changes to `src/`, `tests/`, `pyproject.toml`, version, or existing skill.
   Single conventional commit suggested at close (see HANDOFF).

## REQ → test → artifact → verdict trace

| REQ | Test / evidence | Artifact | Verdict gate |
| --- | --------------- | -------- | ------------ |
| OP-001 | file exists; `export const McpGatewayPlugin: Plugin`; `export default` | `.opencode/plugins/mcp-gateway.ts` | quality-gate |
| OP-002 | source contains `mcp["gateway"]`, `type: "remote"`, `url`, `MCP_GWAY_URL`, `http://127.0.0.1:8080/mcp`, `oauth: false`, `MCP_GWAY_TOKEN` → `Authorization` conditional, no-overwrite guard (`if (!...mcp["gateway"])`), skills-paths merge; source contains NO `mcp["mcp-gway"]`, NO `--transport`, NO `stdio` in the entry | same file | quality-gate |
| OP-003 | verbatim block present byte-identical (4 steps + convention + table); system-transform hook present + `MARKER` (`MCP-GWAY v2.5.0`) in chat inject path | same file | quality-gate + verify-handoff diff |
| OP-004 | `experimental.session.compacting` + `MCP-GWAY v2.5.0` marker (single `MARKER` constant, no `MCP-GWAY-RULES-v1` literal) | same file | quality-gate |
| OP-005 | `config.skills.paths` contains `"skills"`; `instructions` untouched; skill frontmatter rules cited | same file + existing SKILL.md | quality-gate |
| OP-006 | grep: env names only (`MCP_GWAY_URL`, `MCP_GWAY_TOKEN`); no hardcoded `Bearer ey|sk-|ghp_|gho_|AKIA` shapes, no `fetch(`; `Authorization` only via conditional `resolveGatewayHeaders()` | same file | review-risk |
| OP-007 | structural check script output (node/tsc if available, else grep matrix) | gate report | quality-gate |
| OP-008 | file exists; mentions `MCP-GWAY v2.5.0` + `gateway`; zero stale plugin names/paths; Option A vs B + verify steps present | `.opencode/INSTALL.md` | quality-gate |

## Risk assessment (blast radius)

- Systems: 1 TS file (opencode client-side only) + lane docs. No `src/` touch.
  Transport shifts from spawned stdio (`mcp-gway serve --transport stdio`) to
  localhost HTTP (`http://127.0.0.1:8080/mcp` via `mcp-gway serve --transport
  http` running separately) — new precondition: gateway reachable over
  loopback; worst case opencode shows the entry disconnected and runs as
  before (hooks are additive; config merge never overwrites).
- Teams/customers/regulators/revenue: none — dev-tooling integration; worst
  case the plugin fails to load and opencode runs as before (hooks are
  additive; config merge never overwrites).
- Secrets: none introduced (constraint HARD). Verbatim block contains no PII.
- Irreversible actions: NONE. Rollback = delete the plugin file (+ revert the
  single commit).
- Residual risk: `experimental.*` hook shapes may drift with opencode releases
  → mitigated by defensive no-throw hooks + assumption stated above + 90d
  re-gate note in HANDOFF.

## Approvers

- Owning domain owner vasquez (engineering) — mandatory, this proposal.
- Gate: `quality-gate` OPEN required; `verify-handoff` HANDOFF required.
- No security-owner gate required (no auth/data/API/PII touched), but
  `review-risk` scan runs inside quality-gate (min review wave).
