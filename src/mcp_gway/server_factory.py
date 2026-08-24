"""Factory that creates server objects for the Starlark sandbox.

Bridges async MCP clients with synchronous Starlark execution by:
1. Reading server configs from the Registry
2. Creating MCP client connections on-demand
3. Wrapping async tool calls with asyncio.run()
4. Returning sync functions callable from Starlark
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp_gway.registry import Registry


class ServerFactory:
    """Creates injectable server objects for the Starlark sandbox.

    Each server object is a Starlark-compatible struct with sync methods
    that wrap async MCP tool calls.
    """

    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def call_tool(self, server: str, tool: str, **kwargs: Any) -> Any:
        """Call an MCP tool synchronously.

        Creates an MCP client connection, calls the tool, and returns the result.
        This method is injected into the Starlark sandbox as `call_tool`.
        """
        config = self._registry.get_config(server)
        return asyncio.run(self._call_tool_async(config, tool, kwargs))

    async def _call_tool_async(
        self, config: Any, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Call an MCP tool asynchronously."""
        from mcp import ClientSession
        from mcp_gway.cli import _create_client_transport

        async with _create_client_transport(config) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return _extract_result(result)

    def make_server_struct(self, server_name: str) -> object:
        """Create a Starlark-compatible server object.

        Returns a Python object whose methods map to MCP tools.
        The sandbox's inject_server() introspects this object to
        create Starlark struct methods.
        """
        config = self._registry.get_config(server_name)
        tool_names = self._get_tool_names(server_name)

        class ServerStruct:
            pass

        struct = ServerStruct()
        struct.__name__ = server_name

        for tool_name in tool_names:
            self._bind_tool_method(struct, config, tool_name)

        return struct

    def _bind_tool_method(self, struct: object, config: Any, tool_name: str) -> None:
        """Bind a synchronous tool method to the struct."""

        def make_tool_fn(cfg: Any, tn: str) -> Any:
            def tool_fn(**kwargs: Any) -> Any:
                return asyncio.run(self._call_tool_async(cfg, tn, kwargs))

            tool_fn.__name__ = tn
            return tool_fn

        setattr(struct, tool_name, make_tool_fn(config, tool_name))

    def _get_tool_names(self, server_name: str) -> list[str]:
        """Extract tool names from the server's .pyi stub."""
        content = self._registry.read_pyi(server_name)
        names: list[str] = []
        for line in content.splitlines():
            if line.startswith("def "):
                name = line.split("def ")[1].split("(")[0].strip()
                if name:
                    names.append(name)
        return names


def _extract_result(result: Any) -> Any:
    """Extract a Python-friendly result from MCP tool result."""
    if hasattr(result, "content"):
        parts = []
        for item in result.content:
            if hasattr(item, "text"):
                parts.append(item.text)
            else:
                parts.append(str(item))
        text = "\n".join(parts)
        try:
            import json

            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text
    return result
