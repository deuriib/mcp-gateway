# HANDOFF — opencode plugin mcp-gateway → ship-release

**Skill:** `frame-ship:verify-handoff`. **Gate:** OPEN (see
`40_workspace/quality-gate/opencode-plugin/GATE_REPORT.md`).
**SPEC/HARD/GATE/DOMAINS:** bounded BRIEF — move `.opencode/plugins/mcp-gateway.ts`
→ `plugins/opencode/mcp-gateway.ts` as `plugins/{harness}/**` seed, delete
`.opencode/` completely, retarget refs, example string update /
execution_mode=single / no logic change / GATE:OPEN / DOMAINS:[engineering].
**Owner:** vasquez (CTO).

## Deliverables

| Artifact | Location | Status |
|----------|----------|--------|
| Plugin file | `plugins/opencode/mcp-gateway.ts` (146 lines) | done |
| Install guide | `plugins/opencode/INSTALL.md` (91 lines) | done |
| Version sync refs | `scripts/sync_version.py` (OWNED_TARGETS + endswith + docstring) | done |
| Package entry | `package.json` (main/exports → `./plugins/opencode/mcp-gateway.ts`) | done |

## DoD

- [x] All acceptance criteria met (move complete, `.opencode/` deleted, refs retargeted)
- [x] Tests/evidence linked (sync_check clean, ruff pass, 36 pytest pass, git status clean)
- [x] Gate OPEN (4/4 reviewers APPROVE/PASS)
- [x] Lint passes with zero warnings
- [x] No TODO/FIXME left in code
- [x] Docs/changelog: historical docs intentionally untouched (frozen records)
- [x] ADR waived — no public API/data-model/cross-cutting change (client-side plugin only)
- [x] Example string updated: `result = Server.tool(param=value, params....)`

## Blockers / Open Questions

None.

## Next agent → `frame-ship:ship-release`

Suggested commit: `feat(plugins): relocate opencode plugin to plugins/{harness}/** pattern`
body: bounded BRIEF → move + ref retarget + example string update → GATE OPEN → artifacts.
No version bump (integration, semantic-release untouched).

## Preconditions / assumptions / risks

- `.opencode/` no longer exists in this repo; opencode auto-loads from
  `<PROJECT>/.opencode/plugins/mcp-gateway.ts` — users copy per `INSTALL.md`.
- `package.json` main/exports fixed a pre-existing dangling pointer (`mcp-gway.ts`
  never existed on disk). New pointer resolves to real file.
- Historical workspace docs (`PROPOSED_CHANGES*.md`, `HANDOFF.md`, `RELEASE_NOTES.md`)
  reference old `.opencode/...` paths — frozen records, not rewritten.
- Future harnesses drop in as `plugins/<harness>/...` with no rework.
