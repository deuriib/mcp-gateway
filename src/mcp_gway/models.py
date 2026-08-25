"""Pydantic models for MCP client and server configurations."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


def _validate_name_value(v: str) -> str:
    if not v:
        raise ValueError("Name must not be empty")
    if "/" in v or "\\" in v or v in (".", ".."):
        raise ValueError("Name must not contain path separators or be '.' or '..'")
    if not v.isascii():
        raise ValueError("Name must contain only ASCII characters")
    if "-" in v or " " in v:
        raise ValueError("Name cannot contain hyphens or spaces")
    if v[0].isdigit():
        raise ValueError("Name cannot start with a number")
    if "<" in v or ">" in v or '"' in v or "'" in v or "&" in v:
        raise ValueError("Name contains invalid characters")
    if not _NAME_RE.match(v):
        raise ValueError("Name must match ^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    if v.lower() in _RESERVED_NAMES:
        raise ValueError("Name is reserved")
    return v


# ──────────────────────────────────────────────────────────────────────
# Legacy models (deprecated, kept for backward compat during migration)
# ──────────────────────────────────────────────────────────────────────


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
    docs_url: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_name_value(v)

    def model_post_init(self, __context: Any) -> None:
        if self.connection_type in (
            ConnectionType.HTTP,
            ConnectionType.SSE,
            ConnectionType.STREAMABLE_HTTP,
        ):
            if not self.connection_string:
                raise ValueError(
                    f"connection_string required for {self.connection_type.value}"
                )
        if self.connection_type == ConnectionType.STDIO:
            if not self.stdio_config:
                raise ValueError("stdio_config required for stdio connection")


# ──────────────────────────────────────────────────────────────────────
# Shared models
# ──────────────────────────────────────────────────────────────────────


class ToolInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────
# New OpenCode-aligned models
# ──────────────────────────────────────────────────────────────────────


class OAuthConfig(BaseModel):
    clientId: str | None = None
    clientSecret: str | None = None
    scope: str | None = None


class MCPServerConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    type: Literal["local", "remote"]

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_name_value(v)

    enabled: bool = True
    timeout: int = 5000

    # type=local
    command: list[str] | None = None
    cwd: str | None = None
    environment: dict[str, str] | None = None

    # type=remote
    url: str | None = None
    headers: dict[str, str] | None = None
    oauth: OAuthConfig | bool | None = None

    # Internal: resolved after connection test, stored in JSON
    resolved_transport: Literal["sse", "streamable-http", "http"] | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.type == "local":
            if not self.command:
                raise ValueError("'command' required for type=local")
        elif self.type == "remote":
            if not self.url:
                raise ValueError("'url' required for type=remote")


class MCPServerState(BaseModel):
    name: str
    config: MCPServerConfig
    tools: list[ToolInfo] = Field(default_factory=list)
    state: str = "healthy"
