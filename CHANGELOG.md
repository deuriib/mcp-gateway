# CHANGELOG


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
