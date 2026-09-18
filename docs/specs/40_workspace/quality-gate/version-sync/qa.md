# qa — version-sync sub-lane

**Skill:** `frame-ship:quality-gate` (single-mode min wave, verification).
**SPEC:** `docs/specs/40_workspace/engineering/PROPOSED_CHANGES-version-sync.md` (VS-001..VS-004).
**Date:** 2026-09-18. **Reviewer role:** engineering / qa. **Gate keeper:** vasquez (CTO).

## REQ trace

| REQ | Test / evidence | Result |
|-----|-----------------|--------|
| VS-001 read pyproject + `--version` wins | `--check` clean at 2.5.0 exit 0; `--version 9.9.9 --check` drift exit 2 with diff; `--version bad` exit 2 | ✅ |
| VS-002 owned refs only (plugin + INSTALL + `package.json` + README/AGENTS; lane-doc dropped) | 9.9.9 diff touches plugin MARKER + INSTALL.md + `package.json` version only (3 files); `README`/`AGENTS` clean no-op; `git diff --stat` shows `release.yml` +4 / `test.yml` −3, no `src/`/`tests/` | ✅ |
| VS-003 pipeline in `release.yml`, loud fail, tag intact | release.yml step present after Build/before Publish (gated push/released); test.yml removal verified; `--check` exit 2 semantics proven | ✅ |
| VS-004 no invented scheme, sem-rel read-only | no write-path grep hits; `normalize()` strict semver; ruff clean | ✅ |

## Runs (live 2026-09-18 — delta re-run)

- `python scripts/sync_version.py --check` → `version-sync: clean at 2.5.0`, exit 0.
- `python scripts/sync_version.py --version 9.9.9 --check` → DRIFT 3 files + diff (plugin + INSTALL + package.json), exit 2.
- `python scripts/sync_version.py --version v2.5.0 --check` → clean, exit 0; `--version bad` → exit 2.
- `uv run rtk ruff check scripts/sync_version.py` → exit 0 (`[]`); `ruff format --check` → `1 file already formatted`.
- `uv run pytest tests/test_cli.py -q` → **25 passed**.
- Full suite (255 tests) NOT run locally (cost); deferred to CI (`pytest -v` still in `test.yml`; `--check` gate now lives in `release.yml`).

## Verdict

✅ PASS — 4/4 REQs traced with passing evidence. Residual: full-suite green is CI's verdict.
