# Refuter Review: SPEC-MGW-001

**Reviewer:** review-refuter (adversarial)
**Date:** 2026-09-16
**Verdict:** conditional ("could not falsify parity; one spec-wording counterexample with mitigation")
**Skill:** `quality-gate` (`D:\GitHub\frame-ship\skills\quality-gate\SKILL.md` + `references/gate-report.md` + `references/engineering/refuter-review.md`)
**Template:** `D:\GitHub\frame-ship\agents\engineering\review-refuter.md` (read fully)
**Mode:** single (direct, no task dispatch)
**Packet:** SPEC:`D:\GitHub\mcp-gateway\docs\specs\10_design\SPEC-mgw-alias.md`#REQ + `D:\GitHub\mcp-gateway\docs\specs\10_design\ARCHITECTURE.md` INV-001..006 + proposal `D:\GitHub\mcp-gateway\docs\specs\40_workspace\backend\PROPOSED_CHANGES.md` + impl `pyproject.toml` / `tests/test_cli_alias.py` / `src/mcp_gway/cli.py:74-76` / HARD:single+approved-proposal-only+guardrails-1-14 / GATE:arch-approved+impl-complete / DOMAINS:[engineering]

## Mission

Attempt to **falsify** the implementation. Success = finding a counterexample.
Tried to break INV-001 parity (prog-name help, entry-point metadata, Windows shim, version skew), INV-002 canonical, INV-003 no new boundary, INV-006 version. Read-only inspection + `pytest tests/test_cli_alias.py` + `ruff` only; no implementation files modified.

## Attack Vectors Tried

| ID | Hypothesis | Attempt | Result |
|----|-----------|---------|--------|
| RF-001 | INV-001 breaks via prog-name-dependent help rendering | Grepped `src/mcp_gway` for `prog_name`/`argv[0]` (no hits in `cli.py`); `CliRunner().invoke(main, ["--help"])` renders `Usage: main` independent of binary name; real shims render `basename(argv[0])` on the Usage first token only, which SPEC explicitly allows modulo `argv[0]` (`SPEC-mgw-alias.md:19`) | Confirmed (holds) |
| RF-002 | INV-001 breaks via divergent entry-point binding | Read `pyproject.toml:19-21`: both scripts bind literally to `mcp_gway.cli:main`; verified installed metadata via `importlib.metadata` — `EntryPoint(name='mcp-gway', value='mcp_gway.cli:main')` + `EntryPoint(name='mgw', value='mcp_gway.cli:main')` present; single click group `src/mcp_gway/cli.py:74-76` untouched | Confirmed (holds) |
| RF-003 | INV-001 breaks on Windows shim (missing `mgw.exe`) | Ran on `win32` (this session): both console-script entry points resolve in installed metadata; `uv_build` emits `.exe` per script automatically; no shell wrapper/symlink involved (`PROPOSED_CHANGES.md:31` rejected alternative) | Confirmed (holds) |
| RF-004 | INV-006 breaks via version skew | `pyproject.toml:3` `version = "2.4.0"` == `src/mcp_gway/__init__.py:3` `__version__ = "2.4.0"`; `test_version_single_source` passes; `[tool.semantic_release]` still syncs both sources (`pyproject.toml:27-29`) | Confirmed (holds) |
| RF-005 | INV-003 breaks via new trust boundary in diff | `git diff --stat`: `AGENTS.md`, `README.md`, `pyproject.toml` (+1 line), `uv.lock` (version `2.3.0`→`2.4.0` only); secret scan of diff clean (only pre-existing doc placeholders `SECRET`/warning text); `MCP_GWAY_ALLOW_*` strings untouched; no endpoint/adapter/port/payload change | Confirmed (holds) |
| RF-006 | REQ-F-003 "`mgw --version` / `mcp-gway --version` match" holds via CLI flag | `CliRunner().invoke(main, ["--version"])` → exit 2, `Error: No such option '--version'`; no `version_option` anywhere in `src/mcp_gway/cli.py` (grep: zero hits); `test_cli_alias.py:33-38` asserts only module-level `__version__ == project.version`, never the CLI flag | **Falsified (wording)** — see CE-001 |
| RF-007 | Test proves cross-binary parity (not just self-consistency) | Read `tests/test_cli_alias.py:41-52`: help loop invokes the same `main` object twice and compares output to itself; cross-binary divergence is impossible by construction (same object) but the test cannot observe installed-shim behavior — it proves single-source, not installed parity | Confirmed with note (holds by construction; test is weaker than AC-001 wording, no runtime impact) |
| RF-008 | Full suite + lint green (REQ-NF-001) | `uv run pytest tests/test_cli_alias.py -v`: 3 passed; `ruff check src/ tests/`: all checks passed; `ruff format --check`: 71 files formatted | Confirmed (holds, scoped to alias tests + lint) |

## Counterexamples Found

| ID | Counterexample | Impact | Reproduction |
|----|---------------|--------|--------------|
| CE-001 | No `--version` CLI flag exists, so REQ-F-003/AC-003 "`mgw --version` / `mcp-gway --version`" evidence is unproducible as written. Both binaries behave identically (both exit 2 `No such option`), so INV-001 parity is NOT broken — the SPEC wording overclaims a CLI surface that was never built. `src/mcp_gway/cli.py` has no `version_option` (grep zero hits); `tests/test_cli_alias.py:33-38` covers only module-level equality. | Low — docs/wording only; zero runtime or parity impact | `uv run python -c "from click.testing import CliRunner; from mcp_gway.cli import main; r = CliRunner().invoke(main, ['--version']); print(r.exit_code, r.output)"` → `2 / Error: No such option '--version'` |

## Verdict Rationale

- pass = attempted falsification, no counterexamples found
- conditional = counterexample with mitigations available ← this review
- fail = counterexample invalidates spec

Parity (INV-001), canonical (INV-002), boundary (INV-003), local-first (INV-004 by untouched `cli.py:463-470`), env names (INV-005), version source (INV-006) all survived attack. CE-001 is a spec-wording counterexample, not a parity break: either add a `--version` flag (out of scope for this SPEC, needs proposal) or reword REQ-F-003/AC-003 to "module-level `__version__` equality, no `--version` flag in this SPEC".

## Conditions for Opening

- [ ] COND-REF-001: Reword SPEC-MGW-001 REQ-F-003 + AC-003 to drop the "`mgw --version` / `mcp-gway --version`" CLI claim (or file a follow-up SPEC adding a real `--version` flag with parity test). Owner: vasquez. No code change required for this gate.

## Risks

- Test self-consistency (RF-007): alias test compares `main` to itself; a future fork (`mgw_main()`) would still pass help-parity unless the entry-point assertion (`test_scripts_expose_both_binaries_same_main`) catches it — it does, so risk is contained.
- Install repro (AC-002) relies on `uv_build` shim emission, verified here on win32 via installed metadata but not via a clean-room `uv tool install` log in this review.

## Assumptions

- `ARCHITECTURE.md` v1 + proposal approval by vasquez already recorded (GATE packet states arch-approved).
- `uv.lock` version-only churn (`2.3.0`→`2.4.0`) is the release-line bump, not part of this SPEC's one-line change.
- Full 255-test suite green claimed by qa lane; this review scoped to alias tests + lint.

## Scoped Evidence

- `pyproject.toml:19-21` — both scripts → `mcp_gway.cli:main`
- `src/mcp_gway/cli.py:74-76` — single click group, signature untouched
- `src/mcp_gway/__init__.py:3` — `__version__ = "2.4.0"` matches `pyproject.toml:3`
- `tests/test_cli_alias.py:26-52` — entry-point + version + help tests (3 passed)
- `src/mcp_gway/cli.py:463-470` — local-first `exit 2` gate untouched
- `src/mcp_gway/cli.py:797` — hidden `mcp` alias intact alongside top-level tree
- No cross-domain need — engineering-only; no Cross-domain request to montilla.
