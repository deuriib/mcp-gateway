"""HTTP/SSE gateway server for MCP protocol."""

from __future__ import annotations

from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_gateway.code_mode import CodeMode
from mcp_gateway.registry import Registry

CODE_MODE_TOOLS = [
    {
        "name": "listToolFiles",
        "description": "Lists all available virtual .pyi stub files for connected MCP servers.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "readToolFile",
        "description": "Reads a virtual .pyi file to get compact Python function signatures for tools.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fileName": {
                    "type": "string",
                    "description": "Path like servers/youtube.pyi",
                },
                "startLine": {
                    "type": "integer",
                    "description": "Optional 1-based start line",
                },
                "endLine": {
                    "type": "integer",
                    "description": "Optional 1-based end line",
                },
            },
            "required": ["fileName"],
        },
    },
    {
        "name": "getToolDocs",
        "description": "Get detailed documentation for a specific tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "The server name"},
                "tool": {"type": "string", "description": "The tool name"},
            },
            "required": ["server", "tool"],
        },
    },
    {
        "name": "executeToolCode",
        "description": "Executes Python code in a sandboxed Starlark interpreter with tool access.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"}
            },
            "required": ["code"],
        },
    },
]


class Gateway:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.code_mode = CodeMode(registry)
        self.app = Starlette(
            routes=[
                Route("/health", self._health, methods=["GET"]),
                Route("/mcp", self._mcp_post, methods=["POST"]),
                Route("/mcp", self._mcp_sse, methods=["GET"]),
            ]
        )

    async def _health(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def _mcp_post(self, request: Request) -> JSONResponse:
        body = await request.json()
        method = body.get("method")
        req_id = body.get("id")
        params = body.get("params", {})
        try:
            result = self._handle_method(method, params)
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})
        except Exception as e:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -1, "message": str(e)},
                }
            )

    async def _mcp_sse(self, request: Request) -> JSONResponse:
        return JSONResponse({"message": "SSE not yet implemented"})

    def _handle_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "tools/list":
            return {"tools": CODE_MODE_TOOLS}
        if method == "tools/call":
            return self._handle_tool_call(params)
        raise ValueError(f"Unknown method: {method}")

    def _handle_tool_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        if name == "listToolFiles":
            result = self.code_mode.list_tool_files()
        elif name == "readToolFile":
            result = self.code_mode.read_tool_file(
                fileName=arguments["fileName"],
                startLine=arguments.get("startLine"),
                endLine=arguments.get("endLine"),
            )
        elif name == "getToolDocs":
            result = self.code_mode.get_tool_docs(
                server=arguments["server"], tool=arguments["tool"]
            )
        elif name == "executeToolCode":
            result = self.code_mode.execute_tool_code(code=arguments["code"])
        else:
            raise ValueError(f"Unknown tool: {name}")
        return {"content": [{"type": "text", "text": result}]}
