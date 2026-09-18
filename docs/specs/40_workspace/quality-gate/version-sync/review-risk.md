# review-risk — version-sync sub-lane

**Skill:** `frame-ship:quality-gate` (single-mode min wave).
**SPEC:** `docs/specs/40_workspace/engineering/PROPOSED_CHANGES-version-sync.md`.
**Date:** 2026-09-18. **Reviewer role:** engineering / risk (security lens). **Gate keeper:** vasquez (CTO).

## Scope

Confirm: no-secrets / no-network / allow-listed paths only.

## Evidence (live, 2026-09-18)

- Secret scan: `secret|token|password|api_key|subprocess|os.system|socket|requests|urllib|http.|fetch(|os.environ|getenv` against `scripts/sync_version.py` → 1 hit, benign: line 11 docstring word "tokens" in "`MCP-GWAY vX.Y.Z` tokens". Zero credential/network primitives. No `subprocess`, no `socket`, no `requests`/`urllib`, no `fetch(`, no `os.environ`/`getenv`.
- Imports: `argparse`, `difflib`, `re`, `sys`, `pathlib.Path`, stdlib `tomllib` (function-local). No third-party, no network module.
- Write-path proof: grep for write to `pyproject.toml` / `__init__.py` / `CHANGELOG.md` → zero code hits (only docstring "never writes" statement). Only `write_text` target is `drifts` from `OWNED_TARGETS` closed tuple (3 allow-listed relative paths). `pyproject.toml` opened read-only via `read_text` + `tomllib.loads`.
- Path traversal: `OWNED_TARGETS` is a fixed tuple of 3 relative paths; `root / rel` only; no user-controlled path input except `--root` (operator CI default `.`); `--version` validated against strict `^\d+\.\d+\.\d+...$` via `normalize_version()` (verified: `--version bad` → exit 2 `invalid version`).
- Pipeline: additive `test.yml` step only; `git diff -- .github/workflows/release.yml` → empty (tag / semantic-release flow intact). Non-loopback / SSRF / PII: none touched (version strings only).
- OWASP screen: no new endpoints/adapters/boundaries/payloads; no authN/Z; no data exposure; no deps added.

## Verdict

✅ PASS — no Critical/High/Medium findings. No `barrera` escalation needed.
