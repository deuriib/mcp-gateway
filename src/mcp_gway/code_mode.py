"""Code Mode — 4 meta-tools for LLM-driven tool orchestration."""

from __future__ import annotations

from mcp_gway.registry import Registry
from mcp_gway.sandbox import StarlarkSandbox


class CodeMode:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.sandbox = StarlarkSandbox()

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
        return self.registry.get_tool_docs(server, tool)

    def execute_tool_code(self, code: str) -> str:
        result = self.sandbox.execute(code)
        return str(result)
