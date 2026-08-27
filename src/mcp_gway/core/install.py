"""Core install helpers - shared between dashboard and catalog (no HTTP)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp_gway.models import MCPServerConfig
from mcp_gway.registry import Registry

logger = logging.getLogger(__name__)

_discovery_sem = asyncio.Semaphore(3)


async def _maybe_detect_transport(config: MCPServerConfig) -> None:
    if config.type != "remote" or not config.url:
        return
    if config.resolved_transport:
        return
    try:
        from mcp_gway.core import detect_transport

        timeout = (config.timeout / 1000 + 2) if config.timeout else 7
        detected = await asyncio.wait_for(detect_transport(config), timeout=timeout)
        config.resolved_transport = detected  # type: ignore[assignment]
        logger.info("detected transport %s for %s", detected, config.name)
    except Exception as e:  # noqa: BLE001
        logger.debug("transport detection failed for %s: %s", config.name, e)


async def _acquire_and_discover(config: MCPServerConfig) -> list[Any]:
    from mcp_gway.core import discover_tools as cli_discover

    acquired = False
    try:
        try:
            await asyncio.wait_for(_discovery_sem.acquire(), timeout=5)
            acquired = True
        except TimeoutError:
            raise ConnectionError("discovery saturated")
        await _maybe_detect_transport(config)
        tools = await asyncio.wait_for(
            cli_discover(config),
            timeout=(config.timeout / 1000 + 1) if config.timeout else 6,
        )
        if (
            not tools
            and config.type == "remote"
            and getattr(config, "oauth", None) is not False
        ):
            try:
                from mcp_gway.oauth import get_authenticated_client

                client = await get_authenticated_client(config.name)
                if client is not None:
                    try:
                        await client.aclose()
                    except Exception:
                        pass
                    tools2 = await asyncio.wait_for(
                        cli_discover(config, force_auth=True),
                        timeout=6,
                    )
                    if tools2:
                        return tools2
            except Exception:
                pass
        return tools
    except ConnectionError as e:
        if "saturated" in str(e):
            raise
        return []
    except TimeoutError:
        return []
    except Exception:  # noqa: BLE001, S110
        return []
    finally:
        if acquired:
            _discovery_sem.release()


def is_duplicate(registry: Registry, config: MCPServerConfig) -> bool:
    existing_names = set(registry.list())
    try:
        json_exists = registry._safe_path(config.name, ".json").exists()  # type: ignore[attr-defined]
    except ValueError:
        raise ValueError("invalid request") from None
    try:
        pyi_exists = registry._safe_path(config.name, ".pyi").exists()  # type: ignore[attr-defined]
    except ValueError:
        pyi_exists = False
    return config.name in existing_names or json_exists or pyi_exists


async def discover_and_persist(
    registry: Registry, config: MCPServerConfig
) -> list[Any]:
    try:
        tools = await _acquire_and_discover(config)
    except ConnectionError:
        raise
    except Exception:  # noqa: BLE001, S110
        tools = []
    try:
        registry.add(config, tools)  # type: ignore[arg-type]
    except Exception as e:  # noqa: BLE001
        logger.warning("registry add failed: %s", type(e).__name__)
        raise
    return tools
