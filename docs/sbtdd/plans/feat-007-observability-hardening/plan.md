---
id: FEAT-007
slug: feat-007-observability-hardening
title: Observability & Resilience Hardening Plan
status: Approved
created: 2026-09-15
updated: 2026-09-15
spec_ref: ../../specs/feat-007-observability-hardening/spec.md
plan_ref: ./plan.md
adr_refs: ["../../../architecture/adr-012-observability-hardening.md"]
slot_refs: ["plan_FEAT-007"]
branch: feat/007-observability-hardening
commits: []
tags: [observability, resilience, plan]
---

# Plan: feat-007-observability-hardening

> **Deviation record:** translate-to-spec + execute-spec normally run via bound
> subagents; subagent infra failed (502/cancel 2026-09-15). CEO ordered delivery
> to continue inline; `vasquez` gates at verify-handoff, reviewers gate at quality-gate.

## Work Units

| WU | Scope | ACs | Target files |
|----|-------|-----|--------------|
| WU-001 | A1+A2: process/build metrics + cardinality guard | AC-001..003 | `observability/metrics.py`, `gateway.py` |
| WU-002 | A3: discovery metric injection | AC-004 | `core/client.py` |
| WU-003 | A4+A5+A6: SSE disconnects, shutdown summary, slow-request WARN | AC-005..007 | `gateway.py`, `observability/middleware.py` |
| WU-004 | B1+B2: stdio metrics + JSON access log | AC-008..009 | `stdio.py` |
| WU-005 | C1+C2: CLI `_log_cli_event` + degraded banner | AC-010..012 | `cli.py` |
| WU-006 | D1: upstream instrumentation | AC-013 | `server_factory.py`, `gateway.py` |
| WU-007 | D2: opt-in retry (model + flag + logic) | AC-014..016 | `models.py`, `cli.py`, `server_factory.py`, `core/client.py` |
| WU-008 | D3: CodeMode skip evidence | AC-017 | `code_mode.py` |
| WU-009 | E: tests, README, CHANGELOG, deps guard | AC-018..019 + NFRs | `tests/`, `README.md`, `CHANGELOG.md`, `pyproject.toml` (unchanged deps) |

## Order & Dependencies
1. WU-001 (foundation: registry behavior changes affect all later metrics) → 2. WU-002, WU-003 (independent, both on WU-001) → 3. WU-004, WU-005 (independent) → 4. WU-006, WU-007 (WU-007 depends on WU-006: retry logic instruments into the same `_call_tool_async`) → 5. WU-008 (independent) → 6. WU-009 (last: tests + docs + full verification).

Each WU commits as one historical step (universal-rules: linear history, grouped commit).

## Verification
- Per-WU: targeted pytest for its ACs + `ruff check` on changed files.
- WU-009: `uv run pytest -q` (full), `uv run ruff check src/ tests/`, `uv run ruff format --check src/ tests/`.