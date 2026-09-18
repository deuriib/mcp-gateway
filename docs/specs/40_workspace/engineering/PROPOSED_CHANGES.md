# PROPOSED_CHANGES — opencode plugin mcp-gateway (single-mode lane)

**Spec refs (reference-only):** bounded BRIEF in parent chat (opencode plugin
mcp-gway, approved); opencode docs 2026-09-18 (`plugins`, `mcp-servers`,
`skills`, `rules`); repo `skills/mcp-gway/SKILL.md` (single source of truth
for the skill); `AGENTS.md` MCP Rules Gateway Protocol block (verbatim source).
**Execution mode:** `single` (engineering-only, direct, no dispatch).
**DOMAINS:** `[engineering]`.
**Skills cited:** `frame-ship:using-frame-ship` + `frame-ship:translate-to-spec`
(SPEC below) + `frame-ship:propose-changes` (this proposal), then
`frame-ship:execute-spec` → `frame-ship:quality-gate` → `frame-ship:verify-handoff`.
**Date:** 2026-09-18. **Owner:** vasquez (CTO, engineering chain owner).

## SPEC — REQ-IDs (testable)

- **REQ-OP-001** — Local-file plugin at `.opencode/plugins/mcp-gateway.ts`
  exporting a typed `Plugin` (`import type { Plugin } from "@opencode-ai/plugin"`),
  auto-loaded by opencode with no npm publish required.
- **REQ-OP-002** — `config` hook wires `mcp["mcp-gway"]` as local stdio
  (`command: ["mcp-gway", "serve", "--transport", "stdio"]`, `enabled: true`)
  WITHOUT overwriting a user-defined entry; merges
  `instructions` with `skills/mcp-gway/SKILL.md` if absent.
- **REQ-OP-003** — System injection via `experimental.chat.system.transform`
  appends the MCP Rules Gateway Protocol block VERBATIM (4-step order +
  Starlark calling convention + Anti-Patterns table); defensive no-throw.
- **REQ-OP-004** — Compaction re-injection via
  `experimental.session.compacting` pushing the same block prefixed with
  marker `MCP-GWAY-RULES-v1`, so rules survive compaction/summarization.
- **REQ-OP-005** — Skill wiring conforms to opencode skill rules
  (frontmatter `name`/`description`, `name == dir`, lowercase-hyphen); single
  source stays `skills/mcp-gway/SKILL.md`, referenced via `instructions`
  (no duplicated copy in this lane → no drift).
- **REQ-OP-006** — No secrets/tokens/credentials in plugin, config, logs, or
  examples; no network fetch; local-first (`serve --transport stdio`) preserved.
- **REQ-OP-007** — Verifiable without opencode runtime: structural asserts
  (exports Plugin, hooks present, verbatim block present, command shape).

## Architecture contract

Local-file plugin (auto-loaded from `.opencode/plugins/`, load order #4 after
global/project config + global plugins). Three hooks, one constant:

| Hook | Role |
| ---- | ---- |
| `config` | Merge `mcp["mcp-gway"]` + `instructions`; never overwrite user values |
| `experimental.chat.system.transform` | Append `MCP_RULES` verbatim to system prompt |
| `experimental.session.compacting` | Push `MCP-GWAY-RULES-v1` + `MCP_RULES` into compaction context |

`MCP_RULES` constant = verbatim Gateway Protocol block (source: persona
`MCP Rules — Gateway Protocol`; backticks escaped as `\`` inside the TS
template literal). All hooks wrapped so a failure degrades to no-op, never a
broken session. Assumption (stated): exact `output` shapes for the two
`experimental.*` hooks follow the `(input, output)` mutate-in-place convention
(`output.system` string-or-array; `output.context` array; `output.prompt`
replace); code handles string/array/absent defensively.

## Change list (approved targets ONLY)

1. `.opencode/plugins/mcp-gateway.ts` — NEW (the plugin; only impl file).
2. `docs/specs/40_workspace/engineering/PROPOSED_CHANGES.md` — this proposal.
3. Gate artifacts (later stages): quality-gate report + HANDOFF under
   `40_workspace/{quality-gate,verify-handoff}/`.
4. NO changes to `src/`, `tests/`, `pyproject.toml`, version, or existing skill.
   Single conventional commit suggested at close (see HANDOFF).

## REQ → test → artifact → verdict trace

| REQ | Test / evidence | Artifact | Verdict gate |
| --- | --------------- | -------- | ------------ |
| OP-001 | file exists; `export const McpGatewayPlugin: Plugin`; `export default` | `.opencode/plugins/mcp-gateway.ts` | quality-gate |
| OP-002 | source contains `mcp-gway`, `serve`, `--transport`, `stdio`, no-overwrite guard (`if (!...mcp["mcp-gway"])`), instructions merge | same file | quality-gate |
| OP-003 | verbatim block present byte-identical (4 steps + convention + table); system-transform hook present | same file | quality-gate + verify-handoff diff |
| OP-004 | `experimental.session.compacting` + `MCP-GWAY-RULES-v1` marker | same file | quality-gate |
| OP-005 | instructions entry `skills/mcp-gway/SKILL.md`; skill frontmatter rules cited | same file + existing SKILL.md | quality-gate |
| OP-006 | grep: no `Bearer|TOKEN|SECRET|Authorization` literals; no `fetch(` | same file | review-risk |
| OP-007 | structural check script output (node/tsc if available, else grep matrix) | gate report | quality-gate |

## Risk assessment (blast radius)

- Systems: 1 new TS file (opencode client-side only) + lane docs. No runtime,
  no endpoint, no migration, no data, no `src/` touch.
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
