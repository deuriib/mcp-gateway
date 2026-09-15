"""Registry for managing .pyi stub files and JSON config in the servers/ directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp_gway.models import MCPServerConfig, OAuthConfig, ToolInfo, _validate_name_value


def _validate_safe_name(name: str) -> None:
    _validate_name_value(name)


class Registry:
    def __init__(self, servers_dir: Path | str = "servers") -> None:
        self.servers_dir = Path(servers_dir)
        self.servers_dir.mkdir(parents=True, exist_ok=True)
        self._metrics: Any = None

    def ensure(self) -> None:
        self.servers_dir.mkdir(parents=True, exist_ok=True)

    def _inc_registry_metric(self, op: str) -> None:
        try:
            metrics = getattr(self, "_metrics", None)
            if metrics is not None:
                metrics.inc("registry_operations_total", {"op": op})
        except Exception:
            pass

    def patch_enabled(self, name: str, enabled: bool) -> None:
        cfg = self.get_config(name)
        cfg.enabled = enabled
        json_path = self._safe_path(name, ".json")
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                data["enabled"] = enabled
                self._atomic_write_text(json_path, json.dumps(data, indent=2))
                self._inc_registry_metric("patch")
                return
            except Exception:  # noqa: BLE001
                pass
        self.add(cfg, [])

    def _safe_path(self, name: str, suffix: str) -> Path:
        _validate_safe_name(name)
        p = self.servers_dir / f"{name}{suffix}"
        try:
            resolved_base = self.servers_dir.resolve()
            resolved_path = p.resolve()
            if not resolved_path.is_relative_to(resolved_base):
                raise ValueError("Invalid name: path traversal detected")
        except ValueError:
            raise
        except Exception:
            raise ValueError("Invalid name: path traversal detected")
        return p

    def _atomic_write_text(self, path: Path, content: str) -> None:
        """Delegate to shared secureio helper (single symlink-safe impl)."""
        from mcp_gway.secureio import secure_atomic_write_text

        self.servers_dir.mkdir(parents=True, exist_ok=True)
        secure_atomic_write_text(path, content)

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.servers_dir.glob("*.pyi"))

    def list_enabled(self) -> list[str]:
        result: list[str] = []
        for name in self.list():
            try:
                cfg = self.get_config(name)
                if getattr(cfg, "enabled", True):
                    result.append(name)
            except Exception:
                result.append(name)
        return result

    def add(self, config: MCPServerConfig, tools: list[ToolInfo]) -> None:
        config_data: dict[str, Any] = {
            "name": config.name,
            "type": config.type,
            "enabled": config.enabled,
            "timeout": config.timeout,
            "is_code_mode_client": getattr(config, "is_code_mode_client", True),
            "tools_to_execute": getattr(config, "tools_to_execute", ["*"]),
            "tools_to_auto_execute": getattr(config, "tools_to_auto_execute", []),
        }
        if config.type == "local":
            config_data["command"] = config.command
            if config.cwd:
                config_data["cwd"] = config.cwd
            if config.environment:
                config_data["environment"] = config.environment
        else:  # remote
            config_data["url"] = config.url
            if config.headers:
                config_data["headers"] = config.headers
            if config.oauth is not None:
                if isinstance(config.oauth, bool):
                    config_data["oauth"] = config.oauth
                else:
                    config_data["oauth"] = config.oauth.model_dump()
            if config.resolved_transport:
                config_data["resolved_transport"] = config.resolved_transport
        json_path = self._safe_path(config.name, ".json")
        self._atomic_write_text(json_path, json.dumps(config_data, indent=2))

        pyi_path = self._safe_path(config.name, ".pyi")
        content = self._generate_pyi(config, tools)
        self._atomic_write_text(pyi_path, content)
        self._inc_registry_metric("add")

    def remove(self, name: str) -> None:
        pyi_path = self._safe_path(name, ".pyi")
        if not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")
        pyi_path.unlink()
        json_path = self._safe_path(name, ".json")
        if json_path.exists():
            json_path.unlink()
        self._inc_registry_metric("remove")

    def update(self, name: str, tools: list[ToolInfo]) -> None:
        config = self.get_config(name)
        self.add(config, tools)
        # add already counts; avoid double count for update if needed we count add, but spec says registry_operations_total{op="update"} not needed double
        # To ensure update is counted, we inc update additionally but not double if add already counted?
        # We already counted add via self.add, so for update we add extra "update" label
        self._inc_registry_metric("update")

    def get_config(self, name: str) -> MCPServerConfig:
        json_path = self._safe_path(name, ".json")
        pyi_path = self._safe_path(name, ".pyi")

        if not json_path.exists() and not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")

        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if "oauth" in data and isinstance(data["oauth"], dict):
                data["oauth"] = OAuthConfig(**data["oauth"])
            return MCPServerConfig(**data)

        raise FileNotFoundError(f"Server '{name}' not found")

    def read_pyi(self, name: str) -> str:
        pyi_path = self._safe_path(name, ".pyi")
        if not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")
        return pyi_path.read_text(encoding="utf-8")

    def get_pyi_tools(self, name: str) -> list[ToolInfo]:
        content = self.read_pyi(name)
        tools: list[ToolInfo] = []
        for line in content.splitlines():
            if line.startswith("def ") and "(" in line:
                try:
                    tool_name = line[4 : line.index("(")].strip()
                except ValueError:
                    continue
                if not tool_name:
                    continue
                desc = ""
                if "#" in line:
                    desc = line.split("#", 1)[1].strip()
                tools.append(ToolInfo(name=tool_name, description=desc))
        return tools

    def get_tool_docs(self, server: str, tool: str) -> str:
        import re as _re

        content = self.read_pyi(server)
        lines = content.splitlines()
        candidates = {tool, _re.sub(r"[^A-Za-z0-9_]", "_", tool)}
        for c in tuple(candidates):
            if c and c[0].isdigit():
                candidates.add(f"_{c}")
        in_tool = False
        doc_lines: list[str] = []
        for line in lines:
            if line.startswith("def "):
                hit = any(line.startswith(f"def {c}(") for c in candidates)
                if hit:
                    in_tool = True
                    doc_lines.append(line)
                    continue
                if in_tool:
                    break
            elif in_tool:
                if line.startswith("def ") or (
                    line.strip()
                    and not line.startswith(" ")
                    and not line.startswith("\t")
                ):
                    break
                doc_lines.append(line)
        if not doc_lines:
            return f"Tool '{tool}' not found on server '{server}'"
        return "\n".join(doc_lines)

    def _generate_pyi(self, config: MCPServerConfig, tools: list[ToolInfo]) -> str:
        import re as _re

        name = config.name
        lines = [
            f"# servers/{name}.pyi",
            f"# Usage: {name}.tool_name(param=value)",
            f'# For detailed docs: use getToolDocs(server="{name}", tool="tool_name")',
            "# Note: hyphenated MCP names are exposed sanitized (hyphens -> underscores).",
            "# Use sanitized names in executeToolCode as Server.tool_name(...).",
            "",
        ]
        for tool in tools:
            sig = self._make_signature(tool)
            desc = tool.description or ""
            first_line = desc.splitlines()[0] if desc else ""
            safe = _re.sub(r"[^A-Za-z0-9_]", "_", tool.name)
            if safe and safe[0].isdigit():
                safe = f"_{safe}"
            if safe != tool.name:
                lines.append(
                    f"def {sig} -> dict:  # {first_line} [original: {tool.name}]"
                )
            else:
                lines.append(f"def {sig} -> dict:  # {first_line}")
            lines.append("    ...")
            lines.append("")
        return "\n".join(lines)

    def _make_signature(self, tool: ToolInfo) -> str:
        import re as _re

        params = []
        schema = tool.input_schema.get("properties", {})
        required = tool.input_schema.get("required", [])
        for param_name, param_info in schema.items():
            py_type = self._json_type_to_python(param_info.get("type", "string"))
            safe_param = _re.sub(r"[^A-Za-z0-9_]", "_", param_name)
            if safe_param and safe_param[0].isdigit():
                safe_param = f"_{safe_param}"
            if param_name in required:
                params.append(f"{safe_param}: {py_type}")
            else:
                params.append(f"{safe_param}: {py_type} = None")
        safe_name = _re.sub(r"[^A-Za-z0-9_]", "_", tool.name)
        if safe_name and safe_name[0].isdigit():
            safe_name = f"_{safe_name}"
        return f"{safe_name}({', '.join(params)})"

    @staticmethod
    def _json_type_to_python(json_type: str) -> str:
        mapping = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "array": "list",
            "object": "dict",
        }
        return mapping.get(json_type, "Any")
