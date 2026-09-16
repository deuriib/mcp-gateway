"""Factory that creates server objects for the Starlark sandbox.

Bridges async MCP clients with synchronous Starlark execution by:
1. Reading server configs from the Registry
2. Creating MCP client connections on-demand
3. Wrapping async tool calls with asyncio.run()
4. Returning sync functions callable from Starlark
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from mcp_gway.registry import Registry

# Characters not allowed in Python identifiers
_INVALID_IDENTIFIER_RE = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize_identifier(name: str) -> str:
    """Replace non-identifier characters with underscores.

    MCP tool names may contain hyphens (e.g. query-docs) which are
    invalid as Python/Starlark identifiers.
    """
    sanitized = _INVALID_IDENTIFIER_RE.sub("_", name)
    if sanitized and sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    return sanitized


class ServerFactory:
    """Creates injectable server objects for the Starlark sandbox.

    Each server object is a Starlark-compatible struct with sync methods
    that wrap async MCP tool calls.
    """

    def __init__(self, registry: Registry) -> None:
        self._registry = registry
        # FEAT-007: injected by Gateway (BR-111) — upstream tool telemetry.
        self._metrics: object | None = None

    def is_auto_executable(self, server: str, tool: str) -> bool:
        """Bifrost Agent Mode classification: executable AND auto-approved."""
        try:
            config = self._registry.get_config(server)
        except Exception:
            return False
        if not getattr(config, "is_code_mode_client", True):
            return False
        try:
            self._check_tool_allowed(config, tool)
        except Exception:
            return False
        auto = getattr(config, "tools_to_auto_execute", []) or []
        if "*" in auto:
            return True
        import re as _re

        safe = _re.sub(r"[^A-Za-z0-9_]", "_", tool)
        if safe and safe[0].isdigit():
            safe = f"_{safe}"
        return tool in auto or safe in auto

    async def _call_tool_async(
        self, config: Any, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Call an MCP tool asynchronously with a bounded per-config timeout.

        FEAT-007 (BR-111/112/113): every call records upstream telemetry
        (``upstream_tool_calls_total`` + ``upstream_tool_duration_seconds``,
        classifying ``timeout`` vs ``error``). With opt-in
        ``retry_on_transport_error`` the transport/connect/initialize phase is
        retried exactly once — ``session.call_tool`` is never re-run, so a
        non-idempotent tool cannot be executed twice on a transient blip.
        """
        from mcp import ClientSession

        from mcp_gway.core import create_client_transport

        self._check_tool_allowed(config, tool_name)

        raw_timeout = getattr(config, "timeout", 5000)
        if raw_timeout is None or raw_timeout <= 0:
            timeout_sec = 5.0
        else:
            timeout_sec = raw_timeout / 1000
        server = getattr(config, "name", "unknown")
        tool_label = _sanitize_identifier(tool_name) or "_other"
        metrics = self._metrics
        status = "error"
        retried = False
        start = time.perf_counter()
        try:
            from contextlib import AsyncExitStack

            async def _setup(stack: Any) -> Any:
                """Transport + initialize phase — the ONLY retry-eligible step.

                At this point the tool call has not started, so re-running this
                phase cannot duplicate a side effect (BR-112).
                """
                read, write = await stack.enter_async_context(
                    create_client_transport(config)
                )
                session = await stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(session.initialize(), timeout=timeout_sec)
                return session

            stack = AsyncExitStack()
            try:
                try:
                    session = await _setup(stack)
                except Exception:
                    if not getattr(config, "retry_on_transport_error", False):
                        raise
                    retried = True
                    await stack.aclose()
                    stack = AsyncExitStack()
                    session = await _setup(stack)
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments), timeout=timeout_sec
                )
                status = "ok"
                return _extract_result(result)
            finally:
                await stack.aclose()
        except BaseException as exc:  # noqa: BLE001 — telemetry classifies, then re-raises
            status = "timeout" if isinstance(exc, TimeoutError) else "error"
            raise
        finally:
            if metrics is not None:
                try:
                    metrics.inc(
                        "upstream_tool_calls_total",
                        {"server": server, "tool": tool_label, "status": status},
                    )
                    metrics.observe(
                        "upstream_tool_duration_seconds",
                        time.perf_counter() - start,
                        {"server": server, "tool": tool_label},
                    )
                    if retried:
                        metrics.inc("upstream_retries_total", {"server": server})
                except Exception:
                    # WHY broad: telemetry must never alter the tool outcome.
                    pass

    def make_server_struct(self, server_name: str) -> object:
        """Create a Starlark-compatible server object.

        Returns a Python object whose methods map to MCP tools.
        The sandbox's inject_server() introspects this object to
        create Starlark struct methods. Only tools_to_execute-allowed
        tools are bound (Bifrost Tool ACL).
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
        """Bind a synchronous tool method to the struct.

        Uses sanitized attribute names (hyphens → underscores) so that
        the struct is introspectable by the Starlark sandbox.
        The original tool_name is preserved for MCP calls.
        """

        def make_tool_fn(cfg: Any, tn: str) -> Any:
            def tool_fn(**kwargs: Any) -> Any:
                return asyncio.run(self._call_tool_async(cfg, tn, kwargs))

            tool_fn.__name__ = tn
            return tool_fn

        safe_name = _sanitize_identifier(tool_name)
        setattr(struct, safe_name, make_tool_fn(config, tool_name))

    def _check_tool_allowed(self, config: Any, tool_name: str) -> None:
        """Enforce tools_to_execute allow-list; ["*"] allows all."""
        allow = getattr(config, "tools_to_execute", ["*"]) or ["*"]
        if "*" in allow:
            return
        allowed = set(allow)
        if tool_name in allowed:
            return
        import re as _re

        safe = _re.sub(r"[^A-Za-z0-9_]", "_", tool_name)
        if safe and safe[0].isdigit():
            safe = f"_{safe}"
        if safe in allowed:
            return
        from mcp_gway.gateway import InvalidParamsError

        raise InvalidParamsError(
            f"tool '{tool_name}' not in tools_to_execute [reason=tool_not_allowed]"
        )

    def _get_tool_names(self, server_name: str) -> list[str]:
        """Extract tool names from the server's .pyi stub, filtered by ACL."""
        import re as _re

        content = self._registry.read_pyi(server_name)
        names: list[str] = []
        for line in content.splitlines():
            if line.startswith("def "):
                name = line.split("def ")[1].split("(")[0].strip()
                if not name:
                    continue
                m = _re.search(r"\[original:\s*([^\]]+)\]", line)
                if m:
                    orig = m.group(1).strip()
                    if orig:
                        names.append(orig)
                        continue
                names.append(name)
        try:
            config = self._registry.get_config(server_name)
            allow = getattr(config, "tools_to_execute", ["*"]) or ["*"]
            if "*" not in allow:
                allowed = set(allow)
                filtered: list[str] = []
                for n in names:
                    safe = _re.sub(r"[^A-Za-z0-9_]", "_", n)
                    if safe and safe[0].isdigit():
                        safe = f"_{safe}"
                    if n in allowed or safe in allowed:
                        filtered.append(n)
                return filtered
        except Exception:
            pass
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
