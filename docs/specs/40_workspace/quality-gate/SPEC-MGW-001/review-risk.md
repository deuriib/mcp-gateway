# Risk Review: SPEC-MGW-001 (fast gate)

**Reviewer:** review-risk (engineering)
**Date:** 2026-09-16
**Execution_Mode:** single (direct, no task dispatch)
**Skill:** `D:\GitHub\frame-ship\skills\quality-gate\SKILL.md` (+ `references/gate-report.md`)
**Template:** `D:\GitHub\frame-ship\agents\engineering\review-risk.md` (read fully; skill=process, template=craft)
**Packet:** SPEC:`D:\GitHub\mcp-gateway\docs\specs\10_design\SPEC-mgw-alias.md`#REQ-F-001..003+NF-001..003 / HARD:single+approved-proposal-only+guardrails-1-14 / GATE:arch-approved+impl-complete / DOMAINS:[engineering]
**Verdict:** conditional (template mapping: REQUEST_CHANGES on one Medium condition; no Critical/High, no ESCALATE_TO_SECURITY)

## Scope verified (diff targets read)

- `D:\GitHub\mcp-gateway\pyproject.toml:21` — one added line `mgw = "mcp_gway.cli:main"` under `[project.scripts]`; `D:\GitHub\mcp-gateway\pyproject.toml:19-20` canonical untouched.
- `D:\GitHub\mcp-gateway\tests\test_cli_alias.py:1-52` — new parity test file (3 tests).
- `README.md` (+2 lines shortcut callout), `AGENTS.md` (+1 line alias note) — additive-only doc callouts.
- `uv.lock` — single hunk `version = "2.3.0"` → `"2.4.0"` for `mcp-gway` editable package only.
- `src/mcp_gway/cli.py` — absent from `git diff --name-only`; zero runtime change confirmed.

## Findings

### F-001 (Medium, conditional): installer shim gap — R-001 unproven at gate time

- **Claim:** Nothing in the evidence proves `mgw` materializes on PATH after a real install (POSIX shim + Windows `mgw.exe` + `uv tool install`); proof is static (`[project.scripts]` entry + `importlib`-style TOML read in `D:\GitHub\mcp-gateway\tests\test_cli_alias.py:19-30`), not an install repro.
- **Evidence:** `D:\GitHub\mcp-gateway\docs\specs\40_workspace\backend\TEST_MATRIX.md:21` (AC-002 partial, "shim repro pending"); `D:\GitHub\mcp-gateway\docs\specs\40_workspace\backend\PROPOSED_CHANGES.md:57` (R-001 Likelihood Med × Impact Med).
- **Rationale:** Mechanism risk is genuinely low (`uv_build` emits console-script shims deterministically), but likelihood stays Med until one repro exists per matrix — failure mode is silent (`mgw: command not found` while `mcp-gway` works), which is exactly the kind of partial-install state users misdiagnose. Guardrails rule 10: Medium rides the gate only with an explicit condition, not silently.
- **Condition COND-001:** Before ship, run one clean-install repro (`uv build` + install + `command -v mgw` / `where mgw`, POSIX + Windows) and cite the log; rollback is one line (`D:\GitHub\mcp-gateway\pyproject.toml:21`) per `D:\GitHub\mcp-gateway\docs\specs\40_workspace\backend\PROPOSED_CHANGES.md:70`.

### F-002 (Low, rides gate): parity test compares the group to itself — R-002 mitigation weaker than stated

- **Claim:** `test_help_parity_top_commands` invokes the same imported `main` object twice and asserts `again.output == result.output` (`D:\GitHub\mcp-gateway\tests\test_cli_alias.py:41-52`), so it cannot catch prog-name rendering divergence between the two installed binaries; the "normalized diff" mitigation in `D:\GitHub\mcp-gateway\docs\specs\40_workspace\backend\PROPOSED_CHANGES.md:58` is not implemented in the test (no `prog_name` override, no cross-binary invocation).
- **Rationale:** Impact is Low (cosmetic help header only; dispatch identical by construction since both scripts bind the same object per `D:\GitHub\mcp-gateway\pyproject.toml:20-21`). Functional strength is qa/reliability's call — noted here only as residual risk, not a risk-gate block.

### F-003 (Low, rides gate): docs drift — R-003 controlled

- **Claim:** Both doc edits are additive callouts with canonical intact (`AGENTS.md` alias note; `README.md` shortcut sentence); no example was converted from `mcp-gway` to `mgw`. Verified in `git diff` (+1/+2 lines, zero removals).
- **Rationale:** Drift vector stays open long-term (Low/Low per `D:\GitHub\mcp-gateway\docs\specs\40_workspace\backend\PROPOSED_CHANGES.md:59`) but this change introduces none.

### F-004 (Info, closed): version skew — R-004 refuted by evidence

- **Claim:** No skew exists: `D:\GitHub\mcp-gateway\pyproject.toml:3` (`version = "2.4.0"`) ≡ `src/mcp_gway/__init__.py:__version__ = "2.4.0"` ≡ `uv.lock` (`mcp-gway` 2.4.0). INV-006 (`D:\GitHub\mcp-gateway\docs\specs\10_design\ARCHITECTURE.md:31`) holds.

## Security posture (diff verified, not assumed)

- **No new trust boundary:** no endpoint, adapter, payload, port, or permission added — diff touches packaging metadata + docs + tests only; `src/` untouched. INV-003 (`D:\GitHub\mcp-gateway\docs\specs\10_design\ARCHITECTURE.md:28`) and INV-004 (local-first) hold; REQ-NF-002 satisfied.
- **Allow-list / break-glass untouched:** `git diff` piped through `MCP_GWAY_ALLOW` grep returns zero matches; INV-005 (`D:\GitHub\mcp-gateway\docs\specs\10_design\ARCHITECTURE.md:30`) holds.
- **No secrets in diff:** secret-pattern scan of `git diff` hits only pre-existing context lines (`AGENTS.md` CLI placeholder `--oauth-client-secret SECRET` + shell-history warning); zero added credential/token material. Guardrail 1 holds.
- **No escalation to security:** the proposal's conditional barrera lens (`D:\GitHub\mcp-gateway\docs\specs\40_workspace\backend\PROPOSED_CHANGES.md:41`) is not triggered — no new boundary/payload found. No Cross-domain request; engineering-only verdict stands.

## Variances (from `TEST_MATRIX.md:25-28`)

- **V-001 (missing `--version` flag):** Confirmed by design, not a gap — `cli.py` exposes no `--version` click option (`grep version src/mcp_gway/cli.py` hits only banner/health `__version__` usage at `cli.py:476,517`). Adding one would exceed the approved proposal (SPEC §4: "No signature change, no new options"). Risk: Low. Recommend SPEC amendment or follow-up proposal; rides gate.
- **V-002 (`uv.lock` 2.3.0→2.4.0 auto-sync):** Benign — aligns the lock with the single version source after the 2.4.0 release; pre-existing drift, not authored. Keep sync, do not revert (reverting would reintroduce skew against F-004). Risk: Low. Rides gate.

## Blast radius (residual after COND-001)

Packaging-only; services/data untouched. Worst case = `mgw: command not found` with `mcp-gway` fully working — no outage, no data path, no PII flow touched (`PROPOSED_CHANGES.md:64-66` concur). Rollback <15 min, one line + test/doc revert, owner vasquez via backend.

## Risks

- R-001 shim gap (Med/Med) → gated by COND-001, residual ~Low after repro.
- R-002 prog-name flake (Med/Low) → residual Low; test self-comparison noted in F-002.
- R-003 docs drift (Low/Low) → no new drift introduced.
- R-004 version skew (Low/Low) → refuted, closed.

## Assumptions

- `uv_build>=0.12.5,<0.13.0` emits a shim per `[project.scripts]` entry on POSIX + Windows (standard behavior; COND-001 exists because it is assumed, not yet demonstrated for this repo).
- Single execution mode: no subagent dispatch; this file is the reviewer's only write — no implementation files modified.
- Full-suite green + lint/format (REQ-NF-001 / AC-003) is qa's verdict, not re-litigated here.

## Scoped evidence (every claim → file:line; finding without evidence = refuted)

- Proposal + risk lens: `D:\GitHub\mcp-gateway\docs\specs\40_workspace\backend\PROPOSED_CHANGES.md:55-74` (R-001..R-004, blast radius, rollback, security).
- Variance log: `D:\GitHub\mcp-gateway\docs\specs\40_workspace\backend\TEST_MATRIX.md:20-28`.
- SPEC: `D:\GitHub\mcp-gateway\docs\specs\10_design\SPEC-mgw-alias.md:17-22` (REQs), `:26-30` (ACs), `:34-39` (contracts).
- Invariants: `D:\GitHub\mcp-gateway\docs\specs\10_design\ARCHITECTURE.md:26-31` (INV-001..006).
- ADR: `D:\GitHub\mcp-gateway\docs\architecture\adr-013-cli-alias-mgw.md:11-16` (Option A), `:26-33` (consequences).
- Impl: `D:\GitHub\mcp-gateway\pyproject.toml:19-21` (scripts), `:3` + `src/mcp_gway/__init__.py:__version__` (single source), `D:\GitHub\mcp-gateway\tests\test_cli_alias.py:26-52` (3 tests).
- Diff proof: `git diff --stat` (4 files, 5 insertions, 1 deletion), `git diff --name-only` (no `src/` entry), `MCP_GWAY_ALLOW` grep clean, secret scan clean of added lines.
