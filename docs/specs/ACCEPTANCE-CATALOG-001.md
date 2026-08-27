# ACCEPTANCE — CATALOG-001 Catalogo MCPs
# Fuente: docs/specs/SPEC-CATALOG-001.md + acceptance_catalog_001 slot (9 AC)

Ver memoria slot `acceptance_catalog_001` — 9 AC ejecutables TestClient (200/201/202/409 etc).

Este archivo es espejo filesystem del slot `acceptance_catalog_001` para git.
Contenido completo persistido en agentmemory `acceptance_catalog_001` (9 AC).

## Resumen AC

| AC | Titulo | BR | Codigo esperado |
|----|--------|----|-----------------|
| AC-01 | SSR lista + search HIT | BR-01,03,04 | 200 HIT X-Cache |
| AC-02 | Stale-while-revalidate + health <50ms | BR-03 | 200 STALE/MISS |
| AC-03 | POST refresh 202 single-flight | BR-03 | 202 / 409 |
| AC-04 | Skip invalido + trunc + corrupto | BR-07,08 | 200 skip/trunc |
| AC-05 | Drawer 404 | BR-04 | 200 / 404 |
| AC-06 | Install happy Registry.add | BR-01,02 | 201 |
| AC-07 | Install 409/400/502 | BR-02,07 | 409 / 400 / 502 |
| AC-08 | Local-first exposed CSP | BR-05 | 200 X-Warning |
| AC-09 | Sin Node sin regresion | BR-04,01 | FS + ruff 0 |

Full AC: ver `acceptance_catalog_001` memory slot.
DoD: 9 AC verdes TestClient MockTransport + ruff 0 + ADR-008 aprobado.
