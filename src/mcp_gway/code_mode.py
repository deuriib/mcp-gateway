"""Code Mode — 4 meta-tools for LLM-driven tool orchestration."""

from __future__ import annotations

from mcp_gway.registry import Registry
from mcp_gway.sandbox import StarlarkSandbox
from mcp_gway.server_factory import ServerFactory


class CodeMode:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.sandbox = StarlarkSandbox()
        self.server_factory = ServerFactory(registry)
        self._inject_tools()

    def _inject_tools(self) -> None:
        """Inject MCP tool access into the sandbox.

        Adds:
        - call_tool(server, tool, **kwargs) function
        - Server structs for each registered server (e.g., agentmemory.search(...))
        """
        # Inject the call_tool function
        self.sandbox.set_global("call_tool", self.server_factory.call_tool)

        # Inject server structs for each registered server
        for server_name in self.registry.list():
            try:
                struct = self.server_factory.make_server_struct(server_name)
                self.sandbox.inject_server(server_name, struct)
            except Exception:
                # Skip servers that can't be loaded (missing config, etc.)
                pass

    def list_tool_files(self) -> str:
        names = self.registry.list()
        if not names:
            return "No servers connected."
        lines = ["servers/"]
        for name in names:
            lines.append(f"  {name}.pyi")
        return "\n".join(lines)

    def read_tool_file(
        self, fileName: str, startLine: int | None = None, endLine: int | None = None
    ) -> str:
        if not fileName.startswith("servers/"):
            fileName = f"servers/{fileName}"
        if not fileName.endswith(".pyi"):
            fileName += ".pyi"
        name = fileName.removeprefix("servers/").removesuffix(".pyi")
        content = self.registry.read_pyi(name)
        if startLine is not None or endLine is not None:
            lines = content.splitlines()
            start = (startLine or 1) - 1
            end = endLine or len(lines)
            content = "\n".join(lines[start:end])
        return content

    def get_tool_docs(self, server: str, tool: str) -> str:
        docs_url = self.registry.get_docs_url(server)
        tool_docs = self.registry.get_tool_docs(server, tool)
        result = tool_docs
        if docs_url:
            result += f"\n\nDocumentation URL: {docs_url}"
        return result

    def execute_tool_code(self, code: str) -> str:
        result = self.sandbox.execute(code)
        return str(result)
