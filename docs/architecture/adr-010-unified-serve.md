# ADR-010: Unified `serve --transport [stdio|http|sse]` (default stdio)

## Status
Accepted (implemented; `tests/test_serve_unified.py` AC-01..AC-08 green; suite 255 passed 2026-09-12)

## Context
Two entry points served the same stdio NDJSON loop: `mcp-gway mcp` (server-side stdin/stdout) and `mcp-gway serve` (HTTP/SSE). The Registry (`servers/*.json` + `servers/*.pyi`) is the single source of truth and Code Mode discovery is transport-agnostic. Keeping two first-class commands duplicates the stdio path, doubles the CLI contract surface, and confuses OpenCode `type: local` wiring (`command: [mcp-gway, mcp]` vs `[mcp-gway, serve, --transport, stdio]`). Local-first (`127.0.0.1` default, non-loopback without `MCP_GWAY_ALLOW_REMOTE=1` → exit 2) and stdout-pure NDJSON (banners `err=True`, logs to stderr) must hold on every path.

## Decision — Opcion A (adoptada): `serve` unificado, default `stdio`
- `mcp-gway serve --transport [stdio|http|sse]` con default `stdio` (`show_default=True`); `--registry-dir` es opcion comun de `serve`; `--host/--port` solo aplican a `http|sse` — con `stdio` (incluido el default implicito) → `Error: --host/--port only apply to --transport http|sse` + exit 2, nunca warn-and-ignore (deteccion por `ctx.get_parameter_source`, no por valor).
- `mcp-gway mcp` pasa a alias oculto (`hidden=True`) sin logica propia: avisa `[mcp] deprecated, use serve --transport stdio` en stderr y delega a `_serve_stdio()` con los mismos args. Equivalencia exacta: `serve --transport stdio` ≡ `mcp` — mismo loop NDJSON y mismos args a `_serve_stdio`, modulo aviso de deprecacion en stderr (solo `mcp`).
- `http`/`sse` comparten el mismo `Gateway.app` (sin fork); stdio nunca abre sockets y mantiene stdout puro NDJSON (`run_stdio_async`; banners y logs a stderr). Local-first intacto: non-loopback sin `MCP_GWAY_ALLOW_REMOTE=1` → exit 2 con texto legacy.
- Uso recomendado OpenCode `type: local`: `command: [mcp-gway, serve, --transport, stdio]`.

## Alternatives Considered
- Opcion B — Mantener `mcp` como comando de primera clase separado de `serve`: RECHAZADA. Duplica el contrato stdio (dos caminos al mismo loop), dobla la superficie de help/tests y perpetua la ambiguedad OpenCode `command: [mcp-gway, mcp]` vs `serve --transport stdio`. Los tests AC-02/AC-07 exigen un unico loop (`_serve_stdio`) sin logica propia en el alias (`run_stdio_async`/`Gateway` no aparecen en `mcp_cmd`).
- Opcion C — `serve` con default `http` (stdio solo via `mcp`): RECHAZADA. Rompe el caso primario headless/OpenCode `type: local` (el default debe ser el modo sin sockets), arriesga stdout contaminado y debilita local-first por defecto. AC-01 exige default `stdio`; AC-04/AC-06 exigen local-first y stdout puro en ese default.

## Consequences
- Un solo contrato CLI para servir; `mcp` sigue operativo como alias oculto durante la transicion (aviso en stderr, stdout intacto).
- `--host/--port` con `stdio` fallan duro (exit 2) aunque vengan del default implicito — nunca se ignoran en silencio (AC-03 + gate sin flag `--transport`).
- `--registry-dir` comun: el mismo flag resuelve `Registry(servers_dir)` en stdio y en http/sse (AC-08).
- Docs/CHANGELOG describen la equivalencia como: mismo loop NDJSON y mismos args a `_serve_stdio`, modulo aviso de deprecacion en stderr (solo `mcp`).

## Traces
- `src/mcp_gway/cli.py:343-680` (`_serve_stdio`, `_serve_http`, `serve --transport`, alias oculto `mcp`, `local-unrestricted`)
- `src/mcp_gway/gateway.py:192-201` (7 Route entries; `/mcp/messages` es alias POST al mismo handler `_mcp_post`, no endpoint independiente)
- `src/mcp_gway/stdio.py:171-234` (`run_stdio_async`: loop NDJSON, stdout puro, stderr para logs, sin sockets)
- Tests: `tests/test_serve_unified.py` AC-01..AC-08 (default stdio, equivalencia, gate exit 2, local-first, mismo app, stdout puro, alias oculto, registry-dir comun).
