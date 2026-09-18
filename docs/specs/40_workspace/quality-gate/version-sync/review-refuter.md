# review-refuter — version-sync sub-lane

**Skill:** `frame-ship:quality-gate` (single-mode min wave, adversarial).
**SPEC:** `docs/specs/40_workspace/engineering/PROPOSED_CHANGES-version-sync.md` (VS-001..VS-004).
**Date:** 2026-09-18. **Reviewer role:** engineering / refuter. **Gate keeper:** vasquez (CTO).

## Claims tested (all against real files, live 2026-09-18)

| # | Claim | Test | Result |
|---|-------|------|--------|
| 1 | `--check` clean at current version | `python scripts/sync_version.py --check` | ✅ `version-sync: clean at 2.5.0`, exit 0; matches `pyproject.toml:project.version = "2.5.0"` |
| 2 | `--version` override produces loud drift | `python scripts/sync_version.py --version 9.9.9 --check` | ✅ `DRIFT at 9.9.9 (2 file(s))` + unified diff (MARKER + INSTALL.md 2 hits), exit 2; proves override wins and diff path works |
| 3 | `v`-prefix accepted, garbage rejected | `--version v2.5.0 --check` / `--version bad --check` | ✅ clean at 2.5.0 exit 0 / `invalid version 'bad'` exit 2 — `normalize()` claim holds |
| 4 | Pipeline hook additive, tag flow intact | `Select-String test.yml Verify version sync` + `git diff release.yml` | ✅ step `Verify version sync → python scripts/sync_version.py --check` present after Lint/before tests; release.yml diff empty |
| 5 | `test.yml` parses | yaml import missing in sandbox python (no `yaml` module) — structural check substituted | ⚠️ noted: exact step lines verified via Select-String; indentation matches surrounding steps (3-line block); full YAML parse deferred to CI |
| 6 | Ruff clean | `uv run rtk ruff check` + `ruff format --check scripts/sync_version.py` | ✅ both exit 0 (`[]` / `1 file already formatted`) |
| 7 | Semantic-release files read-only | grep write-paths to pyproject/__init__/CHANGELOG | ✅ zero code hits; only read path `tomllib.loads(pyproject.read_text(...))` |
| 8 | Owned-refs only | `--version 9.9.9` diff file list | ✅ exactly 2 files drifted (plugin + INSTALL.md); lane doc no-marker → no-op as designed; no historical/`package.json`/`uv.lock` touch |

## Verdict

✅ PASS — 7/8 vectors confirm claims; 1 residual (item 5: local YAML parse unavailable, CI is arbiter). No falsification. Residual rides gate explicitly, does not block OPEN.
