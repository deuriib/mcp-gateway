# qa — version-sync sub-lane

**Skill:** `frame-ship:quality-gate` (single-mode min wave, verification).
**SPEC:** `docs/specs/40_workspace/engineering/PROPOSED_CHANGES-version-sync.md` (VS-001..VS-004).
**Date:** 2026-09-18. **Reviewer role:** engineering / qa. **Gate keeper:** vasquez (CTO).

## REQ trace

| REQ | Test / evidence | Result |
|-----|-----------------|--------|
| VS-001 read pyproject + `--version` wins | `--check` clean at 2.5.0 exit 0; `--version 9.9.9 --check` drift exit 2 with diff | ✅ |
| VS-002 owned refs only | 9.9.9 diff touches plugin MARKER + INSTALL.md only; `git diff --stat` shows `test.yml` +3, no `src/`/`tests/`/release.yml | ✅ |
| VS-003 pipeline additive, loud fail, tag intact | test.yml step present after Lint; release.yml diff empty; `--check` exit 2 semantics proven | ✅ |
| VS-004 no invented scheme, sem-rel read-only | no write-path grep hits; `normalize()` strict semver; ruff clean | ✅ |

## Runs (live 2026-09-18)

- `python scripts/sync_version.py --check` → `version-sync: clean at 2.5.0`, exit 0.
- `python scripts/sync_version.py --version 9.9.9 --check` → DRIFT 2 files + diff, exit 2.
- `python scripts/sync_version.py --version v2.5.0 --check` → clean, exit 0; `--version bad` → exit 2.
- `uv run rtk ruff check scripts/sync_version.py` → exit 0; `ruff format --check` → `1 file already formatted`.
- `uv run rtk pytest tests/test_cli.py -q` → **25 passed**.
- Full suite (255 tests) NOT run locally (cost); deferred to CI `test.yml` which now includes the `--check` gate.

## Verdict

✅ PASS — 4/4 REQs traced with passing evidence. Residual: full-suite green is CI's verdict (test.yml runs `pytest -v` after the new check).
