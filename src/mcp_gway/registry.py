"""Registry for managing .pyi stub files and JSON config in the servers/ directory."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_gway.models import ConnectionType, MCPClientConfig, StdioConfig, ToolInfo


class Registry:
    def __init__(self, servers_dir: Path | str = "servers") -> None:
        self.servers_dir = Path(servers_dir)
        self.servers_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.servers_dir.glob("*.pyi"))

    def add(self, config: MCPClientConfig, tools: list[ToolInfo]) -> None:
        # Write JSON config
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
        json_path = self.servers_dir / f"{config.name}.json"
        json_path.write_text(json.dumps(config_data, indent=2), encoding="utf-8")

        # Write clean .pyi (signatures only)
        pyi_path = self.servers_dir / f"{config.name}.pyi"
        content = self._generate_pyi(config, tools)
        pyi_path.write_text(content, encoding="utf-8")

    def remove(self, name: str) -> None:
        pyi_path = self.servers_dir / f"{name}.pyi"
        if not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")
        pyi_path.unlink()
        json_path = self.servers_dir / f"{name}.json"
        if json_path.exists():
            json_path.unlink()

    def update(self, name: str, tools: list[ToolInfo]) -> None:
        config = self.get_config(name)
        self.add(config, tools)

    def get_config(self, name: str) -> MCPClientConfig:
        json_path = self.servers_dir / f"{name}.json"
        pyi_path = self.servers_dir / f"{name}.pyi"

        if not json_path.exists() and not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")

        # Prefer JSON config if it exists
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            conn_type = ConnectionType(data["connection_type"])
            stdio_config = None
            if conn_type == ConnectionType.STDIO and data.get("stdio_command"):
                stdio_config = StdioConfig(
                    command=data["stdio_command"],
                    args=data.get("stdio_args", []),
                    envs=data.get("stdio_envs", []),
                )
            return MCPClientConfig(
                name=name,
                connection_type=conn_type,
                connection_string=data.get("connection_string") or None,
                stdio_config=stdio_config,
                docs_url=data.get("docs_url") or None,
            )

        # Fallback: parse old-style .pyi comments for backward compatibility
        return self._parse_config_from_pyi(name, pyi_path)

    def _parse_config_from_pyi(self, name: str, pyi_path: Path) -> MCPClientConfig:
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

        conn_type = ConnectionType(connection_type)
        stdio_config = None
        if conn_type == ConnectionType.STDIO:
            # Old format: command stored in connection_string
            command = stdio_command or connection_string
            if command:
                stdio_config = StdioConfig(command=command, args=json.loads(stdio_args))

        return MCPClientConfig(
            name=name,
            connection_type=conn_type,
            connection_string=connection_string or None,
            stdio_config=stdio_config,
            docs_url=docs_url or None,
        )

    def read_pyi(self, name: str) -> str:
        pyi_path = self.servers_dir / f"{name}.pyi"
        if not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")
        return pyi_path.read_text(encoding="utf-8")

    def get_docs_url(self, server: str) -> str | None:
        config = self.get_config(server)
        return config.docs_url

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

    def _generate_pyi(self, config: MCPClientConfig, tools: list[ToolInfo]) -> str:
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
