# HANDOFF — opencode plugin mcp-gateway → ship-release

**Skill:** `frame-ship:verify-handoff`. **Gate:** OPEN (see
`40_workspace/quality-gate/opencode-plugin/GATE_REPORT.md`).
**SPEC/HARD/GATE/DOMAINS:** REQ-OP-001..007 / single + verbatim + marker /
GATE:OPEN / DOMAINS:[engineering]. **Owner:** vasquez (CTO).

## Deliverable

`.opencode/plugins/mcp-gateway.ts` (103 lines) — local-file opencode plugin
(latest format, `Plugin` from `@opencode-ai/plugin`, named + default export):
(1) `config` hook wires `mcp["mcp-gway"]` local stdio
(`mcp-gway serve --transport stdio`) + `instructions: skills/mcp-gway/SKILL.md`
without overwriting user values; (2) `experimental.chat.system.transform`
appends the MCP Rules Gateway Protocol block VERBATIM; (3)
`experimental.session.compacting` re-injects it with `MCP-GWAY-RULES-v1` marker.
Evidence: proposal `40_workspace/engineering/PROPOSED_CHANGES.md` ·
gate report above · secret scan 0 hits · structural matrix 16/16.

## DoD

- [x] qa green (structural matrix 16/16, scan clean)
- [x] ADR explicitly waived — no public API/data-model/cross-cutting change
  (opencode client-side integration only, `src/` untouched)
- [x] Docs touched: proposal + gate report + this handoff (no ADR acceptance
  docs affected)
- [x] Review wave passed, no Critical/High (1 residual + 1 precondition, both recorded)

## Next agent → `frame-ship:ship-release`

Suggested single commit (orchestrator decides):
`feat(opencode): add mcp-gateway plugin wiring MCP + skill + Gateway Rules`
body: REQ-OP-001..007 → GATE OPEN → artifacts. No version bump (integration,
semantic-release untouched).

## Preconditions / assumptions / risks

- Precondition: `mcp-gway` on PATH where opencode runs (pipx/uv tool install).
- Assumption: `experimental.*` hook `(input, output)` mutate-in-place shapes;
  code is defensive (string/array/absent + no-throw).
- Residual risk + lesson: re-gate in 90d against latest opencode plugin docs;
  pattern learned — verbatim-in-constant + idempotent marker + no-throw hooks —
  reuse for future rule-injection plugins.
