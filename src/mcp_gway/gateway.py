"""HTTP/SSE gateway server for MCP protocol."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from mcp_gway.code_mode import CodeMode
from mcp_gway.registry import Registry

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
        self._sessions: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self.app = Starlette(
            routes=[
                Route("/health", self._health, methods=["GET"]),
                Route("/mcp", self._mcp_sse, methods=["GET"]),
                Route("/mcp", self._mcp_post, methods=["POST"]),
                Route("/mcp/messages", self._mcp_post, methods=["POST"]),
            ]
        )

    async def _health(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def _mcp_sse(self, request: Request) -> StreamingResponse:
        session_id = str(uuid.uuid4())
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._sessions[session_id] = queue

        async def event_stream():
            try:
                yield f"event: endpoint\ndata: /mcp/messages?session_id={session_id}\n\n"
                while True:
                    msg = await queue.get()
                    if msg is None:
                        break
                    yield f"event: message\ndata: {json.dumps(msg)}\n\n"
            finally:
                self._sessions.pop(session_id, None)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def _mcp_post(self, request: Request) -> JSONResponse:
        session_id = request.query_params.get("session_id")
        body = await request.json()
        method = body.get("method")
        req_id = body.get("id")
        params = body.get("params", {})
        try:
            result = self._handle_method(method, params)
            response = {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as e:
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -1, "message": str(e)},
            }
        if session_id and session_id in self._sessions:
            await self._sessions[session_id].put(response)
        return JSONResponse(response)

    def _handle_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mcp-gateway", "version": "0.1.0"},
            }
        if method == "notifications/initialized":
            return {}
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
