"""Registry for managing .pyi stub files and JSON config in the servers/ directory."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mcp_gway.models import (
    ConnectionType,
    MCPClientConfig,
    MCPServerConfig,
    OAuthConfig,
    StdioConfig,
    ToolInfo,
)

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
}


def _validate_safe_name(name: str) -> None:
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise ValueError(
            "Invalid name: must not contain path separators or be '.' or '..'"
        )
    if not name.isascii():
        raise ValueError("Name must contain only ASCII characters")
    if "-" in name or " " in name:
        raise ValueError("Name cannot contain hyphens or spaces")
    if name and name[0].isdigit():
        raise ValueError("Name cannot start with a number")
    if "<" in name or ">" in name:
        raise ValueError("Name contains invalid characters")
    if not _NAME_RE.match(name):
        raise ValueError("Name must match ^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    if name.lower() in _RESERVED_NAMES:
        raise ValueError("Name is reserved")


def _get_legacy_connection_type(self: MCPServerConfig) -> ConnectionType:
    if self.type == "local":
        return ConnectionType.STDIO
    if self.resolved_transport == "sse":
        return ConnectionType.SSE
    if self.resolved_transport == "streamable-http":
        return ConnectionType.STREAMABLE_HTTP
    return ConnectionType.HTTP


def _get_legacy_connection_string(self: MCPServerConfig) -> str | None:
    if self.type == "local":
        return self.command[0] if self.command else None
    return self.url


def _get_legacy_stdio_config(self: MCPServerConfig) -> StdioConfig | None:
    if self.type == "local" and self.command:
        envs: list[str] = []
        if self.environment:
            envs = [f"{k}={v}" for k, v in self.environment.items()]
        return StdioConfig(command=self.command[0], args=self.command[1:], envs=envs)
    return None


def _get_legacy_docs_url(self: MCPServerConfig) -> str | None:
    return getattr(self, "_docs_url", None)


def _set_legacy_docs_url(self: MCPServerConfig, value: str | None) -> None:
    object.__setattr__(self, "_docs_url", value)


MCPServerConfig.connection_type = property(_get_legacy_connection_type)  # type: ignore[attr-defined]
MCPServerConfig.connection_string = property(_get_legacy_connection_string)  # type: ignore[attr-defined]
MCPServerConfig.stdio_config = property(_get_legacy_stdio_config)  # type: ignore[attr-defined]
MCPServerConfig.docs_url = property(_get_legacy_docs_url, _set_legacy_docs_url)  # type: ignore[attr-defined]


class Registry:
    def __init__(self, servers_dir: Path | str = "servers") -> None:
        self.servers_dir = Path(servers_dir)
        self.servers_dir.mkdir(parents=True, exist_ok=True)

    def ensure(self) -> None:
        self.servers_dir.mkdir(parents=True, exist_ok=True)

    def patch_enabled(self, name: str, enabled: bool) -> None:
        cfg = self.get_config(name)
        cfg.enabled = enabled
        json_path = self._safe_path(name, ".json")
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                data["enabled"] = enabled
                self._atomic_write_text(json_path, json.dumps(data, indent=2))
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
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

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

    def add(
        self, config: MCPServerConfig | MCPClientConfig, tools: list[ToolInfo]
    ) -> None:
        if isinstance(config, MCPClientConfig):
            config_data = {
                "name": config.name,
                "connection_type": config.connection_type.value,
                "connection_string": config.connection_string or "",
                "docs_url": config.docs_url or "",
            }
            if config.stdio_config:
                config_data["stdio_command"] = config.stdio_config.command
                config_data["stdio_args"] = config.stdio_config.args
                if config.stdio_config.envs:
                    config_data["stdio_envs"] = config.stdio_config.envs
            json_path = self._safe_path(config.name, ".json")
            self._atomic_write_text(json_path, json.dumps(config_data, indent=2))
        else:
            config_data: dict[str, Any] = {
                "name": config.name,
                "type": config.type,
                "enabled": config.enabled,
                "timeout": config.timeout,
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

    def remove(self, name: str) -> None:
        pyi_path = self._safe_path(name, ".pyi")
        if not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")
        pyi_path.unlink()
        json_path = self._safe_path(name, ".json")
        if json_path.exists():
            json_path.unlink()

    def update(self, name: str, tools: list[ToolInfo]) -> None:
        config = self.get_config(name)
        self.add(config, tools)

    def get_config(self, name: str) -> MCPServerConfig:
        json_path = self._safe_path(name, ".json")
        pyi_path = self._safe_path(name, ".pyi")

        if not json_path.exists() and not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")

        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if "connection_type" in data:
                return self._migrate_old_config(name, data, json_path)
            if "type" in data:
                if "oauth" in data and isinstance(data["oauth"], dict):
                    data["oauth"] = OAuthConfig(**data["oauth"])
                return MCPServerConfig(**data)
            # Fallback: try to parse as MCPServerConfig if unknown structure
            return MCPServerConfig(**data)

        return self._parse_config_from_pyi(name, pyi_path)

    def _migrate_old_config(
        self, name: str, data: dict, json_path: Path
    ) -> MCPServerConfig:
        conn_type = data["connection_type"]
        if conn_type == "stdio":
            command_parts: list[str] = []
            if data.get("stdio_command"):
                command_parts.append(data["stdio_command"])
                command_parts.extend(data.get("stdio_args", []))
            elif data.get("connection_string"):
                command_parts.append(data["connection_string"])
            environment = None
            if data.get("stdio_envs"):
                environment = {}
                for env_str in data["stdio_envs"]:
                    key, _, value = env_str.partition("=")
                    environment[key] = value
            config = MCPServerConfig(
                name=name,
                type="local",
                command=command_parts or None,
                environment=environment,
            )
        else:
            transport_map = {
                "http": "http",
                "sse": "sse",
                "streamable-http": "streamable-http",
            }
            config = MCPServerConfig(
                name=name,
                type="remote",
                url=data.get("connection_string", ""),
                resolved_transport=transport_map.get(conn_type),
            )
        config_data: dict[str, Any] = {
            "name": config.name,
            "type": config.type,
            "enabled": config.enabled,
            "timeout": config.timeout,
        }
        if config.type == "local":
            config_data["command"] = config.command
            if config.cwd:
                config_data["cwd"] = config.cwd
            if config.environment:
                config_data["environment"] = config.environment
        else:
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
        self._atomic_write_text(json_path, json.dumps(config_data, indent=2))
        return config

    def _parse_config_from_pyi(self, name: str, pyi_path: Path) -> MCPServerConfig:
        content = pyi_path.read_text(encoding="utf-8")
        connection_type = "http"
        connection_string = ""
        docs_url = ""
        stdio_command = ""
        stdio_args = "[]"
        for line in content.splitlines():
            if line.startswith("# connection_type:"):
                connection_type = line.split(":", 1)[1].strip()
            elif line.startswith("# connection_string:"):
                connection_string = line.split(":", 1)[1].strip()
            elif line.startswith("# docs_url:"):
                docs_url = line.split(":", 1)[1].strip()
            elif line.startswith("# stdio_command:"):
                stdio_command = line.split(":", 1)[1].strip()
            elif line.startswith("# stdio_args:"):
                stdio_args = line.split(":", 1)[1].strip()
        _ = docs_url  # deprecated, kept for backward compat

        conn_type = ConnectionType(connection_type)
        if conn_type == ConnectionType.STDIO:
            command = stdio_command or connection_string
            if command:
                try:
                    parsed_args = json.loads(stdio_args)
                    if not isinstance(parsed_args, list):
                        parsed_args = []
                except Exception:
                    parsed_args = []
                command_parts = [command] + parsed_args
                return MCPServerConfig(name=name, type="local", command=command_parts)
            # No command found, create with placeholder to avoid validation error
            return MCPServerConfig(name=name, type="local", command=[command or "echo"])
        else:
            transport_map = {
                "http": "http",
                "sse": "sse",
                "streamable-http": "streamable-http",
            }
            resolved = transport_map.get(connection_type)
            url = connection_string or "http://localhost"
            return MCPServerConfig(
                name=name, type="remote", url=url, resolved_transport=resolved
            )

    def read_pyi(self, name: str) -> str:
        pyi_path = self._safe_path(name, ".pyi")
        if not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")
        return pyi_path.read_text(encoding="utf-8")

    def get_docs_url(self, server: str) -> str | None:
        config = self.get_config(server)
        return getattr(config, "docs_url", None)

    def get_tool_docs(self, server: str, tool: str) -> str:
        content = self.read_pyi(server)
        lines = content.splitlines()
        in_tool = False
        doc_lines: list[str] = []
        for line in lines:
            if line.startswith(f"def {tool}("):
                in_tool = True
                doc_lines.append(line)
                continue
            if in_tool:
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

    def _generate_pyi(
        self, config: MCPServerConfig | MCPClientConfig, tools: list[ToolInfo]
    ) -> str:
        name = config.name
        lines = [
            f"# {name} server tools",
            f"# Usage: {name}.tool_name(param=value)",
            f'# For detailed docs: use getToolDocs(server="{name}", tool="tool_name")',
            "",
        ]
        for tool in tools:
            sig = self._make_signature(tool)
            lines.append(f"def {sig} -> dict:  # {tool.description}")
            lines.append("    ...")
            lines.append("")
        return "\n".join(lines)

    def _make_signature(self, tool: ToolInfo) -> str:
        params = []
        schema = tool.input_schema.get("properties", {})
        required = tool.input_schema.get("required", [])
        for param_name, param_info in schema.items():
            py_type = self._json_type_to_python(param_info.get("type", "string"))
            if param_name in required:
                params.append(f"{param_name}: {py_type}")
            else:
                params.append(f"{param_name}: {py_type} = None")
        return f"{tool.name}({', '.join(params)})"

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
