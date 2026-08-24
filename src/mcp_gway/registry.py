"""Registry for managing .pyi stub files in the servers/ directory."""

from __future__ import annotations

from pathlib import Path

from mcp_gway.models import MCPClientConfig, ToolInfo


class Registry:
    def __init__(self, servers_dir: Path | str = "servers") -> None:
        self.servers_dir = Path(servers_dir)
        self.servers_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.servers_dir.glob("*.pyi"))

    def add(self, config: MCPClientConfig, tools: list[ToolInfo]) -> None:
        pyi_path = self.servers_dir / f"{config.name}.pyi"
        content = self._generate_pyi(config, tools)
        pyi_path.write_text(content, encoding="utf-8")

    def remove(self, name: str) -> None:
        pyi_path = self.servers_dir / f"{name}.pyi"
        if not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")
        pyi_path.unlink()

    def update(self, name: str, tools: list[ToolInfo]) -> None:
        config = self.get_config(name)
        self.add(config, tools)

    def get_config(self, name: str) -> MCPClientConfig:
        pyi_path = self.servers_dir / f"{name}.pyi"
        if not pyi_path.exists():
            raise FileNotFoundError(f"Server '{name}' not found")
        content = pyi_path.read_text(encoding="utf-8")
        connection_type = "http"
        connection_string = ""
        docs_url = ""
        for line in content.splitlines():
            if line.startswith("# connection_type:"):
                connection_type = line.split(":", 1)[1].strip()
            elif line.startswith("# connection_string:"):
                connection_string = line.split(":", 1)[1].strip()
            elif line.startswith("# docs_url:"):
                docs_url = line.split(":", 1)[1].strip()
        return MCPClientConfig(
            name=name,
            connection_type=connection_type,
            connection_string=connection_string or None,
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
        conn_type = (
            config.connection_type.value
            if hasattr(config.connection_type, "value")
            else config.connection_type
        )
        conn_str = config.connection_string or ""
        doc_url = config.docs_url or ""
        lines = [
            f"# {name} server tools",
            f"# Usage: {name}.tool_name(param=value)",
            f'# For detailed docs: use getToolDocs(server="{name}", tool="tool_name")',
            f"# connection_type: {conn_type}",
            f"# connection_string: {conn_str}",
            f"# docs_url: {doc_url}",
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
