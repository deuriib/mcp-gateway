# HANDOFF — opencode plugin mcp-gateway → ship-release

**Skill:** `frame-ship:verify-handoff`. **Gate:** OPEN (see
`40_workspace/quality-gate/opencode-plugin/GATE_REPORT.md`).
**SPEC/HARD/GATE/DOMAINS:** REQ-OP-001..008 / single + entry `gateway` remote
HTTP env-driven + marker `MCP-GWAY v2.5.0` + INSTALL.md (REQ-OP-008) /
GATE:OPEN (re-gate 4 HTTP) / DOMAINS:[engineering]. **Owner:** vasquez (CTO).

## Deliverable

`.opencode/plugins/mcp-gateway.ts` (146 lines) — local-file opencode plugin
(latest format, `Plugin` from `@opencode-ai/plugin`, named + default export):
(1) `config` hook wires `mcp["gateway"]` REMOTE HTTP (`type: "remote"`,
URL `resolveGatewayUrl()` default `http://127.0.0.1:8080/mcp` overridable via
`MCP_GWAY_URL`, `enabled: true`, `timeout: 5000`, `oauth: false`, plus
`headers: { Authorization: "Bearer <MCP_GWAY_TOKEN>" }` ONLY when
`MCP_GWAY_TOKEN` set — shape per opencode `mcp-servers` docs 2026-09-18,
`oauth: false` per header-auth guidance; `process.env` resolved directly at
`config` time via no-throw `getEnv`, file-config `{env:VAR}` interpolation
NOT relied upon for programmatic values) + `config.skills.paths: ["skills"]`
(source root for `skills/mcp-gway/SKILL.md`, per live schema
`https://opencode.ai/config.json`; V2-array forward-compat; `instructions`
untouched) without overwriting user values (guard `if (!mcp["gateway"])`;
no `mcp["mcp-gway"]` literal; zero stdio leftovers); (2)
`experimental.chat.system.transform`
appends `<!-- MCP-GWAY v2.5.0 -->` + the MCP Rules Gateway Protocol block VERBATIM via shared `COMPACTION_REINJECT` (`MARKER` → inject string, single constant); (3)
`experimental.session.compacting` re-injects the same string with `MCP-GWAY v2.5.0` marker.
Plus `.opencode/INSTALL.md` (REQ-OP-008, HTTP rev) — install guide adapted to
THIS plugin: single-file local `mcp-gateway.ts` (auto-loaded per-project, no npm
publish, no `package.json` main, no Node/mise toolchain); prerequisites
opencode + gateway serving `serve --transport http` on loopback + optional
`MCP_GWAY_URL` / `MCP_GWAY_TOKEN` exports + `mcp-gway` on PATH where the
gateway runs; named-path style (`<CHECKOUT>`/`<PROJECT>`/
`<FILE_URL_PATH>`) with Option A (git checkout copy) vs Option B (`file:///`
copy); verify steps check marker `MCP-GWAY v2.5.0` + mcp `gateway` +
`type: "remote"` + URL default + `curl /health`; creed line kept; no invented
git URL/package name.
Evidence: proposal `40_workspace/engineering/PROPOSED_CHANGES.md` (rev d) ·
gate report above · secret scan 0 hits (hardcoded `Bearer ey|sk-|ghp_|gho_|AKIA|fetch(`;
`stdio|--transport|mcp["mcp-gway"]` leftovers 0 hits) · structural matrix 20/20 ·
INSTALL.md checks (exists + marker + `gateway` + remote + URL + zero stale names).

## DoD

- [x] qa green (structural matrix 20/20, scan clean)
- [x] ADR explicitly waived — no public API/data-model/cross-cutting change
  (opencode client-side integration only, `src/` untouched)
- [x] Docs touched: proposal + gate report + this handoff + `.opencode/INSTALL.md`
  (no ADR acceptance docs affected)
- [x] Review wave passed, no Critical/High (1 residual + 1 precondition, both recorded)

## Next agent → `frame-ship:ship-release`

Version-sync (2026-09-18, docs-only): swept approved targets vs
`pyproject.toml` 2.5.0 — stale prior-version refs 0, every `2.5.0` hit exactly
`MCP-GWAY v2.5.0`, zero content edits, marker kept exact. GATE OPEN
re-affirmed (see gate report re-gate 5).

Suggested single commit (orchestrator decides):
`feat(opencode): switch mcp-gateway plugin to remote HTTP env-driven entry`
body: REQ-OP-001..008 → GATE OPEN (re-gate 4 HTTP) → artifacts. No version bump (integration,
semantic-release untouched).

## Preconditions / assumptions / risks

- Precondition: gateway serving HTTP on loopback before opencode starts
  (`mcp-gway serve --transport http --host 127.0.0.1 --port 8080`); entry shows
  disconnected otherwise (additive, never breaks bootstrap).
- Assumption: `experimental.*` hook `(input, output)` mutate-in-place shapes;
  code is defensive (string/array/absent + no-throw). Programmatic `config`
  values need no `{env:VAR}` interpolation — plugin resolves `process.env`
  directly at `config` time (file-config `{env:VAR}` form documented but not
  relied upon).
- Residual risk + lesson: re-gate in 90d against latest opencode plugin docs
  (watch `skills` schema: stable OBJECT `{paths,urls}` vs V2 ARRAY — code
  handles both; plus upstream #20940 ordering caveat on unpatched builds);
  pattern learned — verbatim-in-constant + idempotent marker + no-throw hooks +
  schema-first skill wiring (`config.skills`, never `instructions`) —
  reuse for future rule-injection plugins.
