"""Catalog models - CatalogEntry VO and CatalogCache aggregate."""

from __future__ import annotations

import ipaddress
import re
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mcp_gway.models import _ALLOWED_COMMANDS, _ARG_RE, _validate_name_value


def _deny_private_url(v: str) -> str:
    if "\r" in v or "\n" in v:
        raise ValueError("url must not contain CR or LF")
    parsed = urlparse(v)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("url must be http or https")
    if not parsed.netloc:
        raise ValueError("url must have host")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("url must have host")
    low = host.lower()
    if low == "localhost" or low.endswith(".localhost") or low == "0.0.0.0":
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
            raise ValueError("url host not allowed (private IP)")
        if ip.is_unspecified:
            raise ValueError("url host not allowed")
    except ValueError as e:
        if "private" in str(e).lower() or "not allowed" in str(e).lower():
            raise
        # not an IP literal -> allow domain (already blocked localhost)
    return v


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = Field(description="slug unico, lowercase, valid name")
    name: str = Field(description="derived from id if not provided")
    title: str = Field(default="")
    description: str = Field(default="")
    type: Literal["remote", "local"]
    url: str | None = None
    command: list[str] | None = None
    tags: list[str] = Field(default_factory=list)
    docsUrl: str | None = None  # noqa: N815
    source: str = Field(default="bifrost")
    timeout: int = Field(default=5000, ge=1000, le=30000)
    truncated: bool = Field(default=False)

    @field_validator("id", "name")
    @classmethod
    def validate_id(cls, v: str) -> str:
        raw = v.strip()
        if not raw:
            raise ValueError("id empty after sanitize")
        sanitized = re.sub(r"[^A-Za-z0-9_]", "_", raw)
        if sanitized != raw:
            raise ValueError(
                "id contains invalid characters (hyphen/space not allowed)"
            )
        return _validate_name_value(raw)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:  # type: ignore[no-untyped-def]
        if v is None:
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must be http/https")
        return _deny_private_url(v)

    @field_validator("command")
    @classmethod
    def validate_cmd(cls, v: list[str] | None) -> list[str] | None:  # type: ignore[no-untyped-def]
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

    @model_validator(mode="after")
    def _check_type_constraints(self) -> CatalogEntry:
        if self.type == "remote" and not self.url:
            raise ValueError("url required for type=remote")
        if self.type == "local" and not self.command:
            raise ValueError("command required for type=local")
        return self

    def model_post_init(self, __context: Any) -> None:
        if self.description and len(self.description) > 50000:
            object.__setattr__(self, "description", self.description[:50000])
            object.__setattr__(self, "truncated", True)


class CatalogCache(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fetchedAt: datetime = Field(default_factory=lambda: datetime.now(UTC))  # noqa: N815
    ttlSec: int = Field(default=21600)  # noqa: N815
    etag: str | None = None
    entries: list[CatalogEntry] = Field(default_factory=list)
    invalid_skipped: int = Field(default=0)

    def is_stale(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        fetched = self.fetchedAt
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return (now - fetched).total_seconds() > self.ttlSec

    def is_empty(self) -> bool:
        return len(self.entries) == 0
