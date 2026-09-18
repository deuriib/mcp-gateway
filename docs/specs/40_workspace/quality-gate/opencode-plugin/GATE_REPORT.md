# GATE_REPORT — opencode plugin mcp-gateway

**Skill:** `frame-ship:quality-gate` (single-mode min wave).
**SPEC/HARD/GATE/DOMAINS:** proposal `40_workspace/engineering/PROPOSED_CHANGES.md`
REQ-OP-001..008 / execution_mode=single / GATE:prior OPEN → re-gate docs-only
(INSTALL.md scope) / DOMAINS:[engineering].
**Date:** 2026-09-18 (re-gate 2: entry `gateway` + marker freeze `MCP-GWAY v2.5.0`;
re-gate 3 docs-only: `.opencode/INSTALL.md` REQ-OP-008;
re-gate 4: HTTP transport — remote `http://127.0.0.1:8080/mcp` env-driven,
user-approved). **Gate keeper:** vasquez (CTO).

## Verdicts

| Reviewer | Verdict | Summary |
| -------- | ------- | ------- |
| review-readability | ✅ PASS | Named + default export; `MCP_RULES`/`MARKER` constants + `GATEWAY_URL_DEFAULT` + `getEnv`/`resolveGatewayUrl`/`resolveGatewayHeaders` helpers; `ensureSkillPath` + `ensureMcpGateway` + `appendRules`; no-throw hooks; 146 lines; single `MARKER="MCP-GWAY v2.5.0"` + shared `COMPACTION_REINJECT` for chat + compaction |
| review-risk | ✅ PASS | Secret scan clean (hardcoded `Bearer ey|sk-|ghp_|gho_|AKIA|fetch(` → 0 hits; `stdio|--transport|mcp["mcp-gway"]` → 0 hits); `Authorization` only via conditional `resolveGatewayHeaders()` from `MCP_GWAY_TOKEN`; additive merge only; loopback HTTP default, `oauth: false`; entry `mcp["gateway"]` exact, no `mcp["mcp-gway"]` literal |
| review-refuter | ✅ PASS (1 residual + 1 precondition, carried) | Remote shape per opencode `mcp-servers` docs 2026-09-18 (`type: "remote"` + `url` + `headers` + `enabled`/`timeout`, `oauth: false` for header-auth/no-OAuth servers); URL default `http://127.0.0.1:8080/mcp` overridable via `MCP_GWAY_URL` (trimmed, non-empty); `headers` present ONLY when `MCP_GWAY_TOKEN` set/non-empty; no-overwrite guard preserved for `mcp["gateway"]`; `config.skills.paths` push of `"skills"` matches live schema; marker `MCP-GWAY v2.5.0` unified via `MARKER` → `COMPACTION_REINJECT`; `experimental.*` output-shape assumption contained by no-throw + string/array/absent handling; gateway reachable over loopback is operator precondition |
| qa | ✅ PASS | Structural matrix 20/20 (exports, 3 hooks incl. `config`, marker `MCP-GWAY v2.5.0` in chat + compaction, `mcp["gateway"]` exact + `type: "remote"` + URL default + `MCP_GWAY_URL` + `MCP_GWAY_TOKEN` → `Authorization` conditional + `oauth: false` + zero stdio leftovers, `skills.paths` merge + `instructions` absent, all 4 tool names, table headers) + INSTALL.md docs check: prerequisites `serve --transport http` + env exports + `curl /health`; verify asserts marker + `gateway` + `type: "remote"` + URL default; zero stale plugin names/paths, zero invented git URL/package name |

## REQ trace

OP-001 ✅ (exports) · OP-002 ✅ (remote HTTP entry: `type: "remote"` + URL
default + env overrides + `oauth: false` + conditional headers; guard for
`mcp["gateway"]` + skills-paths; no `mcp-gway` entry literal, zero stdio
leftovers) · OP-003 ✅
(verbatim system injection with `MCP-GWAY v2.5.0` marker) · OP-004 ✅ (compaction marker `MCP-GWAY v2.5.0`, unified constant) · OP-005 ✅
(`config.skills.paths` → `"skills"` source root; single-source SKILL.md) ·
OP-006 ✅ (env names only, no hardcoded secrets) · OP-007 ✅ (grep matrix evidence above) · OP-008 ✅
(`.opencode/INSTALL.md`: prerequisites `serve --transport http` + env exports
+ `curl /health`; verify asserts marker + `gateway` + remote + URL default;
creed kept; no invented URL/package; stale-name scan clean).

## GATE: OPEN

Residual: `experimental.*` hook shapes may drift with opencode releases →
no-throw containment + 90d re-gate note. Known upstream caveat (anomalyco/opencode
#20940, fixed by #28647): on unpatched opencode builds, plugin `config()`
mutations to `skills.paths` may run after skill discovery caches, leaving
plugin-registered paths invisible to the `skill` tool until the fix lands —
mitigated by additive no-overwrite push (never breaks bootstrap) + 90d re-gate.
Precondition: gateway serving HTTP on loopback
(`mcp-gway serve --transport http --host 127.0.0.1 --port 8080`) reachable at
the configured URL before opencode starts; non-loopback only via explicit
`MCP_GWAY_URL` operator override.

## Version-sync (2026-09-18, docs-only re-gate 5)

Single source of truth `pyproject.toml:project.version` = `2.5.0` (read-only,
untouched). Sweep of approved targets (plugin + INSTALL.md + proposal + this
report + HANDOFF): stale prior-version refs → 0 hits; `2.5.0` hits all exactly
`MCP-GWAY v2.5.0` (this note itself adds only exact-marker mentions); stale
marker variants → 0 live hits (one negated assertion in proposal);
`mcp["mcp-gway"]` live → 0 hits. Zero content edits — already synced, marker
kept exact. GATE stays OPEN.
