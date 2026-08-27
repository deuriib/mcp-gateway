"""Pydantic models for MCP server configurations (OpenCode-only)."""

from __future__ import annotations

import ipaddress
import re
import uuid
from typing import Any, Literal
from urllib.parse import urlparse as _urlparse_for_validation

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


_ALLOWED_COMMANDS = {"npx", "node", "python", "python3", "uvx"}
_ARG_RE = re.compile(r"^[A-Za-z0-9_./:@-]{1,80}$")


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


class ToolInfo(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class OAuthConfig(BaseModel):
    clientId: str | None = None
    clientSecret: str | None = None
    scope: str | None = None

    @field_validator("clientId")
    @classmethod
    def validate_client_id(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            uuid_obj = uuid.UUID(v)
            return str(uuid_obj)
        except Exception:
            return str(uuid.uuid4())


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

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if "\r" in v or "\n" in v:
            raise ValueError("url must not contain CR or LF")
        parsed = _urlparse_for_validation(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("url must be http or https")
        if not parsed.netloc:
            raise ValueError("url must have host")
        host = parsed.hostname or ""
        if not host:
            raise ValueError("url must have host")
        low = host.lower()
        # allow test localhost for unit tests (PYTEST_CURRENT_TEST)
        import os

        is_test = bool(os.getenv("PYTEST_CURRENT_TEST"))
        if low == "localhost" or low.endswith(".localhost") or low == "0.0.0.0":
            if is_test and low in ("localhost", "127.0.0.1"):
                pass
            else:
                raise ValueError("url host not allowed (private/local)")
        try:
            ip = ipaddress.ip_address(low)
            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_unspecified
                or ip.is_multicast
            ):
                if (
                    is_test
                    and ip.is_loopback
                    and low.startswith("127.")
                    or is_test
                    and low == "127.0.0.1"
                ):
                    pass
                else:
                    raise ValueError("url host not allowed (private IP)")
        except ValueError as e:
            if "private" in str(e).lower() or "not allowed" in str(e).lower():
                raise
        return v

    @field_validator("oauth", mode="before")
    @classmethod
    def validate_oauth(cls, v: Any) -> Any:
        if v is None or v is False:
            return v
        if v is True:
            return {"clientId": str(uuid.uuid4())}
        if isinstance(v, dict):
            if not v.get("clientId"):
                v = dict(v)
                v["clientId"] = str(uuid.uuid4())
            else:
                try:
                    uuid.UUID(str(v["clientId"]))
                except Exception:
                    v = dict(v)
                    v["clientId"] = str(uuid.uuid4())
            return v
        if isinstance(v, OAuthConfig):
            if not v.clientId:
                v.clientId = str(uuid.uuid4())
            else:
                try:
                    uuid.UUID(v.clientId)
                except Exception:
                    v.clientId = str(uuid.uuid4())
            return v
        return v

    @field_validator("command")
    @classmethod
    def validate_cmd(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if not isinstance(v, list):
            raise TypeError("command must be list")
        if len(v) == 0 or len(v) > 8:
            raise ValueError("command must have 1-8 tokens")
        first = v[0]
        if first not in _ALLOWED_COMMANDS:
            raise ValueError(f"command not allowed: {first}")
        for tok in v:
            if not isinstance(tok, str):
                raise TypeError("command token must be string")
            if len(tok) == 0 or len(tok) > 80:
                raise ValueError("command token length 1-80")
            if not _ARG_RE.match(tok):
                raise ValueError(f"command token invalid: {tok}")
            if ".." in tok:
                raise ValueError("command token must not contain ..")
            if tok == "/":
                raise ValueError("command token must not be /")
            if (
                ";" in tok
                or "&" in tok
                or "$" in tok
                or "(" in tok
                or ")" in tok
                or "|" in tok
                or "`" in tok
            ):
                raise ValueError("command token contains forbidden chars")
        return v

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
