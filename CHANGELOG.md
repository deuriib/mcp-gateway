# CHANGELOG


## v0.6.0 (2026-08-25)

### Bug Fixes

- Address final review critical findings
  ([`1341949`](https://github.com/deuriib/mcp-gateway/commit/13419499769f593c902dcf0bba7f0e11016b9237))

- **cli**: Correct timeout None guard ordering
  ([`8b4c5e4`](https://github.com/deuriib/mcp-gateway/commit/8b4c5e49b121734b353c190e74cb8612051a1342))

- **tests**: Remove unused StdioConfig and sort imports (F401, I001)
  ([`426ff62`](https://github.com/deuriib/mcp-gateway/commit/426ff62ded5e24a854f337371f3673ffcf86f777))

Unblocks CI run 32782781915 which failed on ruff check (F401 in conftest.py:9, I001 in
  test_transport.py:3) causing Release 32782803712 to skip. No functional change — 152 tests pass,
  ruff check/format clean.

### Chores

- Sync uv.lock to 0.5.2
  ([`e195a1f`](https://github.com/deuriib/mcp-gateway/commit/e195a1fb01418a948635afcc6fb92e6bac15834c))

### Documentation

- Add OpenCode schema adoption spec and plan
  ([`98b857f`](https://github.com/deuriib/mcp-gateway/commit/98b857fccfbce94c35b6d0a2d2837d7816229565))

Co-Authored-By: Vasquez CTO <vasquez@mcp-gateway>

### Features

- **cli**: Integrate transport auto-detection
  ([`6b9d1e6`](https://github.com/deuriib/mcp-gateway/commit/6b9d1e6594dffaec07d2c16756c508fdcdf7f9c7))

- **cli**: Opencode-style options with backward compat
  ([`69163bd`](https://github.com/deuriib/mcp-gateway/commit/69163bd5cca7de3119aeee86273b55652fe07526))

- **models**: Add MCPServerConfig with OpenCode schema
  ([`a1771f0`](https://github.com/deuriib/mcp-gateway/commit/a1771f048bfbfebbb45c14b6984c5f0a0d24d5bd))

- **registry**: Opencode JSON format with auto-migration
  ([`4489f97`](https://github.com/deuriib/mcp-gateway/commit/4489f9792c41969ef168419737c6289daf9fbd3f))

- **transport**: Auto-detect streamable-http/sse/http
  ([`50bd03e`](https://github.com/deuriib/mcp-gateway/commit/50bd03edbd163e9282aac9ca52201497f62451c4))

### Refactoring

- Update fixtures to MCPServerConfig and fix lint
  ([`0fb1a32`](https://github.com/deuriib/mcp-gateway/commit/0fb1a321f715530a6a0673bf845e07fa6278b203))


## v0.5.2 (2026-08-24)

### Bug Fixes

- **sandbox**: Inject print as no-op to prevent Variable not found error
  ([`7064975`](https://github.com/deuriib/mcp-gateway/commit/70649759664c3e5945d1b911d2d54dd809a0d731))

Starlark sandbox lacked a print builtin, causing cryptic errors when users wrote print() in
  executeToolCode. Inject _noop as print so scripts with print() run without failing.


## v0.5.1 (2026-08-24)

### Bug Fixes

- Sanitize hyphenated MCP tool names for Starlark sandbox
  ([`55ca24d`](https://github.com/deuriib/mcp-gateway/commit/55ca24dd17fac49685733cdbb720106751d546f0))

MCP servers like context7 expose tools with hyphens (query-docs, resolve-library-id) which break
  Starlark struct syntax. Add _sanitize_identifier() to convert non-identifier characters to
  underscores at the Starlark boundary, preserving original names for MCP calls.


## v0.5.0 (2026-08-24)

### Bug Fixes

- Resolve ruff lint errors (S110, I001)
  ([`00bb396`](https://github.com/deuriib/mcp-gateway/commit/00bb396d81d2766e1ad683210696f33248f40aaf))

### Features

- Wire MCP tool execution into Starlark sandbox via ServerFactory
  ([`452d258`](https://github.com/deuriib/mcp-gateway/commit/452d258688ef187d667e958269b98e0af9260914))

Previously, executeToolCode ran code in an empty sandbox with no access to MCP servers. This commit
  bridges the gap by:

- Adding ServerFactory: creates server structs and call_tool function that wrap async MCP client
  calls with asyncio.run() for sync access - Extending StarlarkSandbox with set_global() for
  injecting functions - Wiring CodeMode to inject call_tool + server structs on init - Updating
  executeToolCode description to document tool access

112 tests passing, 0 regressions.


## v0.4.4 (2026-08-24)

### Bug Fixes

- Mock win32 platform in absolute_path_invalid test for CI (Linux)
  ([`1c8faad`](https://github.com/deuriib/mcp-gateway/commit/1c8faad645948334fd8747bca0f00bbced993012))

- Use Self type for __aenter__/__aiter__ (ruff PYI034)
  ([`349986e`](https://github.com/deuriib/mcp-gateway/commit/349986e3f36378616d7cdfefb97097b1ccd1e78b))

- Windows stdio transport — command resolution, noise filter, env passthrough
  ([`c4c2a69`](https://github.com/deuriib/mcp-gateway/commit/c4c2a69ee120a02a729a2bf2dad1f54628f2f221))

- Add stdio_transport.py: resolve_windows_command prefers .exe over .cmd/.bat to bypass cmd.exe
  banner injection on Windows - Add filtered_stdio_client: wraps MCP SDK stdio_client, drops
  non-JSON parse failures from read stream with on_noise callback - Fix _FilteredReadStream to
  implement async context manager protocol (__aenter__/__aexit__) required by MCP SDK dispatcher -
  Fix t.inputSchema -> t.input_schema for MCP SDK v2 compatibility - Wire StdioConfig.envs ->
  StdioServerParameters.env with --env CLI option - Wire on_noise callback in production (logs
  warning to stderr) - 22 new tests in test_stdio_transport.py, 3 new tests in test_cli.py, 1 new
  test in test_registry.py (96/96 pass, ruff clean)


## v0.4.3 (2026-08-24)

### Bug Fixes

- Refresh continues after individual server errors
  ([`4a9afe3`](https://github.com/deuriib/mcp-gateway/commit/4a9afe300efd0c3d774ada45d6798c8273cdc809))

Extract _refresh_server as standalone async function (was defined inside the for loop). Wrap each
  server refresh in try/except so a failure in one server does not abort the entire refresh cycle.


## v0.4.2 (2026-08-24)

### Bug Fixes

- Parse stdio command from connection_string in old .pyi fallback
  ([`1acdeed`](https://github.com/deuriib/mcp-gateway/commit/1acdeed05d4b856aafeeab2bf9ec822f418d4770))

Old-format STDIO .pyi files store the command in # connection_string: instead of # stdio_command:.
  The fallback parser was checking for stdio_command first and creating no StdioConfig when it was
  missing, causing validation errors on refresh.


## v0.4.1 (2026-08-24)

### Bug Fixes

- List command reads connection type from JSON config
  ([`988bba3`](https://github.com/deuriib/mcp-gateway/commit/988bba3314c6c699a7eec89c774ca7e95cdd3721))

list_servers() was parsing .pyi comments for connection_type, which no longer exist in the new
  JSON-based format. Now reads from get_config() which handles both JSON and legacy .pyi comment
  fallback.


## v0.4.0 (2026-08-24)

### Features

- Auto-auth OAuth flow, stdio config persistence, token cleanup
  ([`0c4d448`](https://github.com/deuriib/mcp-gateway/commit/0c4d448b954d66d6e320dd5bba1b3a1d94bcac58))

- Add force_auth param to _discover_tools for conditional OAuth - Add/remove/refresh commands try
  without auth first, OAuth only on failure - Persist stdio_command and stdio_args in .pyi registry
  files - Clean up stored OAuth tokens on server remove - Backward compat for old .pyi files without
  stdio comments - Add comprehensive tests for all new behaviors

- Harden gateway with session TTL, sandbox timeout, clean registry, and configurable OAuth
  ([`6d51ebc`](https://github.com/deuriib/mcp-gateway/commit/6d51ebc6099dc6656a7faf8a6aa3aa27958f0ae5))

- Session TTL + cleanup: evict idle sessions after 5min, send None sentinel to close SSE streams,
  return JSON-RPC error for expired sessions - Real sandbox timeout: ThreadPoolExecutor with
  configurable timeout (default 30s), SandboxTimeoutError for slow injected callbacks - Deduplicate
  _discover_tools: extract _create_client_transport async context manager, single flight path for
  all connection types - STREAMABLE_HTTP validation: require connection_string in model_post_init -
  Configurable OAuth port: --oauth-port option on add/refresh commands - Clean registry: config in
  JSON files, .pyi contains only tool signatures, backward compatible with old comment-style .pyi
  files - serverInfo.version now reads __version__ instead of hardcoded 0.1.0 - 22 new tests (71
  total), all passing, lint clean


## v0.3.0 (2026-08-24)

### Features

- Move servers/ to ~/.config/mcp-gway/servers/
  ([`db62a5a`](https://github.com/deuriib/mcp-gateway/commit/db62a5a6fb4eafc8547191ce8a8685f9152c31c9))


## v0.2.1 (2026-08-24)

### Bug Fixes

- Return docs_url in getToolDocs instead of opening browser
  ([`7bc1457`](https://github.com/deuriib/mcp-gateway/commit/7bc145717a113e8840d4f7dcce5c80ba4d14875a))


## v0.2.0 (2026-08-24)

### Features

- Add --docs-url option and open browser in getToolDocs
  ([`c41f412`](https://github.com/deuriib/mcp-gateway/commit/c41f41209f8c720ab3e270100201f5325a639aed))


## v0.1.4 (2026-08-24)

### Bug Fixes

- Update config path to mcp-gway in oauth, gateway, cli
  ([`9ce40ba`](https://github.com/deuriib/mcp-gateway/commit/9ce40ba8f367903b612afdbd63afc930d3f47a6e))

### Documentation

- Update package name to mcp-gway in README and AGENTS
  ([`6a3e48e`](https://github.com/deuriib/mcp-gateway/commit/6a3e48e4dc777dacf270c113f74361f3d85cc801))


## v0.1.3 (2026-08-24)

### Bug Fixes

- Rename package to mcp-gway for PyPI
  ([`e1e6622`](https://github.com/deuriib/mcp-gateway/commit/e1e6622d9b139bd23b0cae500aefef8f29ba8d66))

- Rename Python module to mcp_gway to match PyPI package name
  ([`4c6de5d`](https://github.com/deuriib/mcp-gateway/commit/4c6de5d9a6fc9d3212ba3a98c2e0a1336660a24e))


## v0.1.2 (2026-08-24)

### Bug Fixes

- Build package after semantic release bumps version
  ([`be80eeb`](https://github.com/deuriib/mcp-gateway/commit/be80eeb1f0eccb9bbd863df71d3671424b90bced))

### Continuous Integration

- Chain release workflow to run after tests pass
  ([`bfe88bc`](https://github.com/deuriib/mcp-gateway/commit/bfe88bcd0127db06385013f21a7f8a3716b50137))


## v0.1.1 (2026-08-24)

### Bug Fixes

- Update docstring format
  ([`f421602`](https://github.com/deuriib/mcp-gateway/commit/f4216026bc86c833c1fadc3bdef4cf6d9803b75b))


## v0.1.0 (2026-08-24)

### Chores

- Initial commit with plan and spec
  ([`2ebf698`](https://github.com/deuriib/mcp-gateway/commit/2ebf698e2324b91b9824b7b219dfe263d97d6aaa))

- Remove cached pycache files
  ([`44d4143`](https://github.com/deuriib/mcp-gateway/commit/44d4143e0a1946435146fc17da3b9fb6f11ddf7b))

### Continuous Integration

- Add semantic release and fix uv installation
  ([`e6db163`](https://github.com/deuriib/mcp-gateway/commit/e6db163b12d8cc6960fa02ea47729b22379fce52))

- Replace publish.yml with release.yml for automatic versioning - Add python-semantic-release
  configuration - Fix uv installation in GitHub Actions using astral-sh/setup-uv - Add branch
  triggers for main and master

### Features

- Cli commands for MCP gateway management
  ([`f86a9ae`](https://github.com/deuriib/mcp-gateway/commit/f86a9ae2c4e63386fa5cc34c796933fc0b56c5dc))

- Code mode with 4 meta-tools
  ([`12e3f72`](https://github.com/deuriib/mcp-gateway/commit/12e3f727042128f15635c2671f66d8bda44696c6))

- Http/sse gateway server with JSON-RPC 2.0
  ([`edaba81`](https://github.com/deuriib/mcp-gateway/commit/edaba81582db7575e0ba48c37d62a07318a9b27f))

- Integration test and project documentation
  ([`b55a40b`](https://github.com/deuriib/mcp-gateway/commit/b55a40bc3e9df68b9cdcd9234dadd57f5ecacea1))

- Oauth support, refresh command, SSE transport, and project docs
  ([`bc5d5d0`](https://github.com/deuriib/mcp-gateway/commit/bc5d5d051b4b6d79adeacec5d61d4c4058f73382))

- Added OAuth 2.0 support with dynamic client registration (RFC 7591) - Added refresh command for
  re-authenticating and re-discovering tools - Added POST /mcp endpoint for direct JSON-RPC - Added
  streamable-http transport type - Added agentmemory, context7, supabase, betterfullstack MCP
  servers - Professional README with architecture diagram - AGENTS.md for AI assistants - GitHub
  Actions workflows for testing and PyPI deployment - MIT License

- Project scaffold with models and tests
  ([`22f4b80`](https://github.com/deuriib/mcp-gateway/commit/22f4b80aed81def6f730df33c28e3ce02522c405))

- Registry for .pyi file CRUD operations
  ([`65d69ee`](https://github.com/deuriib/mcp-gateway/commit/65d69eef749f9de1b97f616d71bc44c2f0fbb573))

- Starlark sandbox and server proxy for code mode
  ([`1e63043`](https://github.com/deuriib/mcp-gateway/commit/1e630430b8e908afed19f37258738f93f4ecd6a7))
