"""Server proxy that wraps MCP clients for sandbox use."""

from __future__ import annotations
from typing import Any


class ServerProxy:
    def __init__(self, name: str, client: Any) -> None:
        self._name = name
        self._client = client
        self._tool_names: list[str] = []

    def set_tool_names(self, names: list[str]) -> None:
        self._tool_names = names

    def __getattr__(self, tool_name: str) -> Any:
        if tool_name.startswith("_"):
            raise AttributeError(tool_name)

        async def tool_fn(**kwargs: Any) -> dict:
            return await self._client.call_tool(tool_name, kwargs)

        return tool_fn

    def __repr__(self) -> str:
        return f"ServerProxy(name={self._name!r}, tools={self._tool_names})"
