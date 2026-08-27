"""Install helpers - entry to config."""

from __future__ import annotations

import logging
import os
import re

from mcp_gway.catalog.models import CatalogEntry
from mcp_gway.core.install import discover_and_persist, is_duplicate
from mcp_gway.models import MCPServerConfig, _validate_name_value

logger = logging.getLogger(__name__)

__all__ = ["discover_and_persist", "entry_to_config", "is_duplicate"]


def entry_to_config(
    entry: CatalogEntry,
    override_name: str | None = None,
    timeout: int | None = None,
) -> MCPServerConfig:
    if entry.type == "local":
        allow = os.getenv("MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD", "1")
        if allow != "1":
            logger.warning("blocked local install without allow env id=%s", entry.id)
            raise PermissionError(
                "local servers not allowed via dashboard (set MCP_GWAY_ALLOW_LOCAL_VIA_DASHBOARD=1)"
            )
    name_raw = override_name or entry.name or entry.id
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name_raw.strip())
    if not sanitized:
        raise ValueError("invalid name derived from catalog id")
    _validate_name_value(sanitized)
    t = timeout if timeout is not None else entry.timeout
    if t is not None:
        if not isinstance(t, int):
            try:
                t = int(t)
            except Exception as e:
                raise ValueError("timeout must be int 1000-30000") from e
        if t < 1000 or t > 30000:
            raise ValueError("timeout must be 1000-30000")
    base: dict[str, object] = {
        "name": sanitized,
        "type": entry.type,
        "enabled": True,
        "timeout": t,
    }
    if entry.type == "remote":
        if not entry.url:
            raise ValueError("url required for type=remote")
        base["url"] = entry.url
    else:
        if not entry.command:
            raise ValueError("command required for type=local")
        base["command"] = entry.command
    return MCPServerConfig(**base)  # type: ignore[arg-type]
