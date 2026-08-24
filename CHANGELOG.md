# CHANGELOG


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
