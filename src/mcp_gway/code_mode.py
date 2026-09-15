"""Code Mode — 4 meta-tools for LLM-driven tool orchestration (Bifrost-aligned)."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from mcp_gway.registry import Registry
from mcp_gway.sandbox import StarlarkSandbox
from mcp_gway.server_factory import ServerFactory

_VALID_BINDINGS = ("server", "tool")

# L1 Code Validation: Starlark has no imports/classes/file-IO/network.
# These patterns are rejected before execution with InvalidParams.
_BLOCKED_PATTERNS = (
    re.compile(r"^\s*import\s+", re.MULTILINE),
    re.compile(r"^\s*from\s+\S+\s+import\s+", re.MULTILINE),
    re.compile(r"^\s*class\s+\w+", re.MULTILINE),
)


def _validate_code(code: str) -> None:
    from mcp_gway.gateway import InvalidParamsError

    for rx in _BLOCKED_PATTERNS:
        if rx.search(code):
            raise InvalidParamsError(
                "executeToolCode rejects imports/classes [reason=code_validation]"
            )
    for token in ("open(", "__", "os.", "sys.", "subprocess", "socket."):
        if token in code:
            raise InvalidParamsError(
                f"executeToolCode rejects {token!r} (use MCP tools) "
                "[reason=code_validation]"
            )


class CodeMode:
    def __init__(
        self,
        registry: Registry,
        binding_level: str = "server",
        tool_execution_timeout: float = 30.0,
        max_agent_depth: int = 10,
    ) -> None:
        if binding_level not in _VALID_BINDINGS:
            raise ValueError("binding_level must be 'server' or 'tool'")
        self.registry = registry
        self.binding_level = binding_level
        self.tool_execution_timeout = tool_execution_timeout
        self.max_agent_depth = max_agent_depth
        self.sandbox = StarlarkSandbox()
        self.server_factory = ServerFactory(registry)
        self._inject_tools()

    def _is_code_mode_server(self, name: str) -> bool:
        try:
            cfg = self.registry.get_config(name)
        except Exception:
            return False
        return bool(getattr(cfg, "is_code_mode_client", True))

    def _code_mode_servers(self) -> list[str]:
        return [n for n in self.registry.list() if self._is_code_mode_server(n)]

    def _inject_tools(self) -> None:
        """Inject MCP tool access into the sandbox.

        Adds:
        - Server structs for each CodeMode server (e.g., filesystem.read_file(...))
        """
        for server_name in self._code_mode_servers():
            try:
                struct = self.server_factory.make_server_struct(server_name)
                self.sandbox.inject_server(server_name, struct)
            except Exception:  # noqa: S110 — servers may lack config, skip silently
                pass

    def refresh(self) -> None:
        """Re-sync sandbox servers with the registry (add new, drop removed)."""
        current = set(self._code_mode_servers())
        known = set(self.sandbox._modules.keys())
        for gone in known - current:
            self.sandbox._modules.pop(gone, None)
        for name in list(known & set(self.registry.list()) - current):
            self.sandbox._modules.pop(name, None)
        for name in current - known:
            try:
                struct = self.server_factory.make_server_struct(name)
                self.sandbox.inject_server(name, struct)
            except Exception:  # noqa: S110 — servers may lack config, skip silently
                pass

    def _tool_file_names(self, server: str) -> list[str]:
        """Sanitized per-tool file stems for tool-level VFS (callable names)."""
        try:
            tools = self.registry.get_pyi_tools(server)
        except Exception:
            return []
        try:
            cfg = self.registry.get_config(server)
            allow = getattr(cfg, "tools_to_execute", ["*"]) or ["*"]
        except Exception:
            allow = ["*"]
        names: list[str] = []
        for t in tools:
            safe = re.sub(r"[^A-Za-z0-9_]", "_", t.name)
            if safe and safe[0].isdigit():
                safe = f"_{safe}"
            if "*" in allow or t.name in allow or safe in allow:
                names.append(safe)
        return sorted(names)

    def list_tool_files(self, binding_level: str | None = None) -> str:
        level = binding_level or self.binding_level
        if level not in _VALID_BINDINGS:
            from mcp_gway.gateway import InvalidParamsError

            raise InvalidParamsError(
                "binding_level must be 'server' or 'tool' [reason=invalid_params]"
            )
        names = self._code_mode_servers()
        if not names:
            return "No servers connected."
        lines = ["servers/"]
        if level == "server":
            for name in names:
                lines.append(f"  {name}.pyi")
        else:
            for name in names:
                lines.append(f"  {name}/")
                for tool in self._tool_file_names(name):
                    lines.append(f"    {tool}.pyi")
        return "\n".join(lines)

    def _resolve_server(self, want: str) -> str:
        lowered = want.lower()
        for name in self.registry.list():
            if name.lower() == lowered:
                return name
        raise FileNotFoundError(f"Server '{want}' not found")

    def _resolve_tool(self, server: str, want: str) -> str:
        lowered = want.lower()
        try:
            tools = self.registry.get_pyi_tools(server)
        except Exception:
            raise FileNotFoundError(f"Server '{server}' not found") from None
        for t in tools:
            safe = re.sub(r"[^A-Za-z0-9_]", "_", t.name)
            if safe and safe[0].isdigit():
                safe = f"_{safe}"
            if t.name.lower() == lowered or safe.lower() == lowered:
                return t.name
        raise FileNotFoundError(f"Tool '{want}' not found on server '{server}'")

    def read_tool_file(
        self, fileName: str, startLine: int | None = None, endLine: int | None = None
    ) -> str:
        text = (fileName or "").strip()
        lowered = text.lower()
        if lowered.startswith("servers/"):
            text = text[len("servers/") :]
        if text.lower().endswith(".pyi"):
            text = text[: -len(".pyi")]
        text = text.strip().strip("/")
        if not text:
            from mcp_gway.gateway import InvalidParamsError

            raise InvalidParamsError(
                "readToolFile requires fileName [reason=invalid_params]"
            )
        parts = [p for p in text.split("/") if p]
        if len(parts) == 1:
            name = self._resolve_server(parts[0])
            content = self.registry.read_pyi(name)
        elif len(parts) == 2:
            name = self._resolve_server(parts[0])
            tool = self._resolve_tool(name, parts[1])
            content = self.registry.get_tool_docs(name, tool)
        else:
            from mcp_gway.gateway import InvalidParamsError

            raise InvalidParamsError(
                "readToolFile fileName must be servers/<server>.pyi or "
                "servers/<server>/<tool>.pyi [reason=invalid_params]"
            )
        if startLine is not None or endLine is not None:
            lines = content.splitlines()
            start = (startLine or 1) - 1
            end = endLine or len(lines)
            content = "\n".join(lines[start:end])
        return content

    def get_tool_docs(self, server: str, tool: str) -> str:
        name = self._resolve_server(server)
        actual_tool = tool
        try:
            actual_tool = self._resolve_tool(name, tool)
        except FileNotFoundError:
            pass
        return self.registry.get_tool_docs(name, actual_tool)

    def execute_tool_code(self, code: str, timeout: float | None = None) -> str:
        from mcp_gway.gateway import InvalidParamsError

        self.refresh()
        if not isinstance(code, str) or not code.strip():
            raise InvalidParamsError(
                "executeToolCode requires non-empty code [reason=invalid_params]"
            )
        _validate_code(code)
        result = self.sandbox.execute(
            code, timeout=timeout or self.tool_execution_timeout
        )
        logs = self.sandbox.get_logs()
        try:
            return json.dumps({"result": result, "logs": logs}, default=str)
        except Exception as e:
            raise RuntimeError(
                f"result serialization failed: {type(e).__name__}"
            ) from None

    # ── Bifrost Agent Mode ──────────────────────────────────────────────

    def classify_tool_calls(
        self, tool_calls: list[dict[str, object]]
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """Bifrost Agent Mode: split tool calls into auto/manual buckets.

        Returns (auto_executable, manual) where each item is
        {"server": str, "tool": str, "arguments": dict, "id": str|None}.
        """
        auto: list[dict[str, object]] = []
        manual: list[dict[str, object]] = []
        for tc in tool_calls:
            server = str(tc.get("server", ""))
            tool = str(tc.get("tool", ""))
            if self.server_factory.is_auto_executable(server, tool):
                auto.append(tc)
            else:
                manual.append(tc)
        return auto, manual

    def execute_agent_tool(self, tc: dict[str, object]) -> Any:
        """Execute a single tool call (auto or manual) via MCP.

        Returns the raw MCP result dict.
        """
        server = str(tc.get("server", ""))
        tool = str(tc.get("tool", ""))
        arguments = dict(tc.get("arguments", {}))  # type: ignore[arg-type]
        config = self.registry.get_config(server)
        result = asyncio.run(
            self.server_factory._call_tool_async(config, tool, arguments)
        )
        return result

    def auto_execute(
        self, tool_calls: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        """Agent loop entry: auto-execute all auto-eligible tools, return results.

        Returns list of {"id", "server", "tool", "result"} for auto-executed
        calls. Non-auto calls are returned as-is in the manual list.
        """
        auto, _manual = self.classify_tool_calls(tool_calls)
        results: list[dict[str, object]] = []
        for tc in auto:
            try:
                result = self.execute_agent_tool(tc)
                results.append(
                    {
                        "id": tc.get("id"),
                        "server": tc.get("server"),
                        "tool": tc.get("tool"),
                        "result": result,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "id": tc.get("id"),
                        "server": tc.get("server"),
                        "tool": tc.get("tool"),
                        "error": {"type": type(e).__name__, "message": str(e)},
                    }
                )
        return results
