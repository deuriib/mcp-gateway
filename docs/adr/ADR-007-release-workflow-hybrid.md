# ADR-007: Hybrid Release Workflow (tag push + semantic-release)

## Status
Accepted — 2026-08-25 — Vasquez CTO Gate for v0.7.0 GA

## Context
- pyproject.toml y src/mcp_gway/__init__.py en 0.6.0, objetivo GA es 0.7.0
- branch master ahead origin/master by 2 commits (fix hardening), working tree DIRTY con 5 archivos modificados (dashboard/api.py 899 líneas, routes.py, views.py, gateway.py, registry.py) + 2 tests untracked
- release.yml actual solo dispara via `workflow_run` Tests completed en main/master usando python-semantic-release@v9 + uv build + pypa/gh-action-pypi-publish
- AGENTS.md Deployment especifica `on: push tags v*` con uv_build — mismatch crítico
- Semver config: minor_tags=["feat"], patch_tags=["fix","perf"] — sin feat desde v0.6.0, semantic-release NO bumpeará a 0.7.0 automáticamente
- ruff/pytest verdes (181 passed) pero sobre tree dirty — bloquea tag limpio
- CEO GO 2026-08-25 exige tag v0.7.0 pusheado, workflow verde, pip verify, trazabilidad AC->evidencia

## Decision
Adoptar **Estrategia Híbrida (Opción C)** como arquitectura de release:

`on: push tags v*` **AND** `workflow_run Tests completed` en el mismo workflow, con lógica condicional en jobs.

### Diseño
```yaml
on:
  push:
    tags: ["v*"]
  workflow_run:
    workflows: ["Tests"]
    types: [completed]
    branches: [main, master]
jobs:
  release:
    if: ${{ github.event_name == 'push' || github.event.workflow_run.conclusion == 'success' }}
    steps:
      - checkout@v7 fetch-depth 0
      - setup-python@v7 (3.12) + setup-uv@v10 + uv sync
      - semantic-release@v9 sólo si event_name == 'workflow_run' (id: release)
      - uv build si (event_name == 'push' OR steps.release.outputs.released == 'true')
      - pypi-publish si mismo condicional
```

## Options Considered

### Opción A — Mantener solo semantic-release automático
- Pros: sin cambio workflow, semver puro, trazabilidad via conventional commits
- Cons: requiere feat commit para minor; delay workflow_run; no cumple spec AGENTS.md de tag push; imposible forzar 0.7.0 sin feat; CEO espera tag determinístico
- Veredicto: descartada como única vía para GA, válida para patches futuros

### Opción B — Migrar solo a tag push v*
- Pros: coincide con AGENTS.md, determinístico, control CEO, inmediato a PyPI
- Cons: bypasea semantic-release, pierde automatización patches, requiere edición workflow igualmente, riesgo de divergencia futura
- Veredicto: válida como fallback si híbrida falla, pero pierde flexibilidad

### Opción C — Híbrida (ELEGIDA)
- Pros: máxima flexibilidad; soporta patches automáticos (fix → 0.7.1 via semantic-release) y GAs manuales (feat → 0.7.0 via tag); resuelve mismatch permanente; future-proof; cumple AGENTS.md y mantiene inversión semantic-release
- Cons: complejidad condicional, necesita test de concurrencia, dos triggers pueden solaparse
- Mitigación: concurrency: release, permisos contents write + id-token write, condicional explícito, fetch-depth 0

## Consequences
- Release v0.7.0 se hará via bump manual sincronizado (pyproject.toml + __init__.py) + tag v0.7.0 push → dispara workflow push path (semver bypaseado)
- Parches futuros fix/perf seguirán bump automático via workflow_run path sin tag manual
- Observabilidad: logs de ambos paths visibles en GitHub Actions; PyPI publish trazable via OIDC; pip index verify
- Riesgo residual Low: workflow dual probado localmente via `actionlint`; concurrencia serializada; sin secretos expuestos

## Compliance
- Semver, uv_build backend, version sync dual-file (version_toml + version_variables)
- Checkout@v7, setup-python@v7, setup-uv@v10 (Node24) preservados
- Un commit atómico por unidad, sin Co-authored-by

## References
- pyproject.toml [tool.semantic_release] vers 2026-08-25
- .github/workflows/release.yml antes del fix (workflow_run only)
- AGENTS.md Deployment: workflow triggers on v* tags
