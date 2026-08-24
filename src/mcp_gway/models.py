"""Pydantic models for MCP client configurations."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ConnectionType(str, Enum):
    HTTP = "http"
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"


class StdioConfig(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    envs: list[str] = Field(default_factory=list)


class MCPClientConfig(BaseModel):
    name: str
    connection_type: ConnectionType
    connection_string: str | None = None
    stdio_config: StdioConfig | None = None
    tools_to_execute: list[str] = Field(default_factory=lambda: ["*"])
    is_code_mode_client: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.isascii():
            raise ValueError("Name must contain only ASCII characters")
        if "-" in v or " " in v:
            raise ValueError("Name cannot contain hyphens or spaces")
        if v[0].isdigit():
            raise ValueError("Name cannot start with a number")
        return v

    def model_post_init(self, __context: Any) -> None:
        if self.connection_type in (ConnectionType.HTTP, ConnectionType.SSE):
            if not self.connection_string:
                raise ValueError(
                    f"connection_string required for {self.connection_type.value}"
                )
        if self.connection_type == ConnectionType.STDIO:
            if not self.stdio_config:
                raise ValueError("stdio_config required for stdio connection")


class ToolInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPServerState(BaseModel):
    name: str
    config: MCPClientConfig
    tools: list[ToolInfo] = Field(default_factory=list)
    state: str = "healthy"
