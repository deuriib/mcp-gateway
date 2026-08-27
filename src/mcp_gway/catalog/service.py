"""CatalogService - domain logic with stale-while-revalidate."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from mcp_gway.catalog.models import CatalogCache, CatalogEntry
from mcp_gway.catalog.store import CatalogStore

logger = logging.getLogger(__name__)

BIFROST_URL = "https://getbifrost.ai/mcp-library"
DEFAULT_TTL = 21600
FETCH_CONTENT_LIMIT = 512 * 1024
MAX_ENTRIES = 500


def _get_ttl() -> int:
    try:
        return int(os.getenv("MCP_GWAY_CATALOG_TTL", str(DEFAULT_TTL)))
    except Exception:
        return DEFAULT_TTL


class CatalogService:
    def __init__(self, store: CatalogStore, http_factory=None) -> None:  # type: ignore[no-untyped-def]
        self.store = store
        self._lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()
        self._refresh_task: asyncio.Task | None = None
        self._refreshing = (
            False  # deprecated keep for backward compat tests that patch it
        )
        self.http_factory = http_factory or httpx.AsyncClient

    async def get_entries(
        self, q: str | None = None, fresh: bool = False
    ) -> tuple[list[CatalogEntry], dict[str, Any]]:
        if q is not None and len(q) > 200:
            raise ValueError("q too long")
        cache = self.store.load()
        now = datetime.now(UTC)
        is_stale = cache.is_stale(now) if cache else True
        ttl = _get_ttl()
        if not fresh and cache and not is_stale:
            entries = self._filter(cache.entries, q)
            return entries, {
                "fetchedAt": cache.fetchedAt.isoformat(),
                "ttlSec": cache.ttlSec,
                "stale": False,
                "total": len(entries),
                "cache": "HIT",
                "invalid_skipped": cache.invalid_skipped,
                "truncated": any(e.truncated for e in entries),
            }
        if cache and is_stale and not fresh:
            entries = self._filter(cache.entries, q)
            try:
                asyncio.create_task(self.refresh_background())
            except RuntimeError as e:
                logger.warning("catalog background no loop: %s", e)
            return entries, {
                "fetchedAt": cache.fetchedAt.isoformat(),
                "ttlSec": cache.ttlSec,
                "stale": True,
                "total": len(entries),
                "cache": "STALE",
                "invalid_skipped": cache.invalid_skipped,
                "truncated": any(e.truncated for e in entries),
            }
        try:
            new_cache = await self.fetch_remote()
            entries = self._filter(new_cache.entries, q)
            return entries, {
                "fetchedAt": new_cache.fetchedAt.isoformat(),
                "ttlSec": new_cache.ttlSec,
                "stale": False,
                "total": len(entries),
                "cache": "MISS" if not cache else "HIT",
                "invalid_skipped": new_cache.invalid_skipped,
                "truncated": any(e.truncated for e in entries),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("catalog fetch failed, serving stale/miss: %s", e)
            if cache:
                entries = self._filter(cache.entries, q)
                return entries, {
                    "fetchedAt": cache.fetchedAt.isoformat(),
                    "ttlSec": cache.ttlSec,
                    "stale": True,
                    "total": len(entries),
                    "cache": "STALE",
                    "invalid_skipped": cache.invalid_skipped,
                    "truncated": any(e.truncated for e in entries),
                    "error": type(e).__name__,
                }
            return [], {
                "fetchedAt": None,
                "ttlSec": ttl,
                "stale": False,
                "total": 0,
                "cache": "MISS",
                "invalid_skipped": 0,
                "truncated": False,
            }

    async def fetch_remote(self) -> CatalogCache:
        async with self._lock:
            cache = self.store.load()
            headers: dict[str, str] = {}
            if cache and cache.etag:
                headers["If-None-Match"] = cache.etag
            ttl = _get_ttl()
            async with self.http_factory(timeout=httpx.Timeout(5.0)) as client:  # type: ignore[call-arg]
                resp = await client.get(BIFROST_URL, headers=headers)
                if resp.status_code == 304 and cache:
                    cache.fetchedAt = datetime.now(UTC)
                    cache.ttlSec = ttl
                    self.store.save(cache)
                    return cache
                resp.raise_for_status()
                clen = resp.headers.get("content-length") or resp.headers.get(
                    "Content-Length"
                )
                if clen and clen.isdigit() and int(clen) > FETCH_CONTENT_LIMIT:
                    raise ValueError("catalog payload too large")
                body_len = len(resp.content) if hasattr(resp, "content") else 0
                if body_len and body_len > FETCH_CONTENT_LIMIT:
                    raise ValueError("catalog payload too large")
                try:
                    raw = resp.json()
                except Exception as e:
                    logger.warning("catalog json decode failed: %s", e)
                    raise
                if isinstance(raw, dict) and "entries" in raw:
                    raw_entries = raw.get("entries") or []
                elif isinstance(raw, list):
                    raw_entries = raw
                elif isinstance(raw, dict):
                    raw_entries = []
                    for v in raw.values():
                        if isinstance(v, list):
                            raw_entries = v
                            break
                else:
                    raw_entries = []
                if isinstance(raw_entries, list) and len(raw_entries) > MAX_ENTRIES:
                    raw_entries = raw_entries[:MAX_ENTRIES]
                valid: list[CatalogEntry] = []
                skipped = 0
                for item in raw_entries:
                    if not isinstance(item, dict):
                        skipped += 1
                        continue
                    try:
                        if "id" not in item and "name" in item:
                            item = dict(item)
                            item["id"] = item["name"]
                        if "name" not in item and "id" in item:
                            item = (
                                dict(item)
                                if "id" in item and "name" not in item
                                else item
                            )
                            if "name" not in item:
                                item = dict(item)
                                item["name"] = item["id"]
                        if "title" not in item:
                            item = dict(item)
                            item["title"] = item.get("name", item.get("id", ""))
                        entry = CatalogEntry(**item)
                        valid.append(entry)
                    except Exception as e:  # noqa: BLE001, PERF203
                        skipped += 1
                        logger.warning(
                            "catalog skip invalid entry id=%s err=%s",
                            item.get("id", "?"),
                            e,
                        )
                        continue
                etag = resp.headers.get("etag") or resp.headers.get("ETag")
                new_cache = CatalogCache(
                    fetchedAt=datetime.now(UTC),
                    ttlSec=ttl,
                    etag=etag,
                    entries=valid,
                    invalid_skipped=skipped,
                )
                self.store.save(new_cache)
                try:
                    logger.info(
                        "catalog fetch entries=%d skipped=%d etag=%s",
                        len(valid),
                        skipped,
                        etag,
                    )
                except Exception:
                    pass
                return new_cache

    async def refresh_background(self) -> None:
        if self._refresh_lock.locked():
            return
        if getattr(self, "_refreshing", False):
            return
        async with self._refresh_lock:
            if getattr(self, "_refreshing", False):
                return
            self._refreshing = True
            try:
                await self.fetch_remote()
            except Exception as e:  # noqa: BLE001
                logger.warning("catalog background refresh failed: %s", e)
            finally:
                self._refreshing = False

    def _filter(self, entries: list[CatalogEntry], q: str | None) -> list[CatalogEntry]:
        if not q:
            return entries
        ql = q.lower()
        result: list[CatalogEntry] = []
        for e in entries:
            if (
                ql in e.id.lower()
                or ql in e.name.lower()
                or ql in e.title.lower()
                or any(ql in t.lower() for t in e.tags)
            ):
                result.append(e)
        return result

    def get_by_id(self, id: str) -> CatalogEntry | None:
        cache = self.store.load()
        if not cache:
            return None
        idx = {e.id: e for e in cache.entries}
        if id in idx:
            return idx[id]
        import re

        sanitized = re.sub(r"[^A-Za-z0-9_]", "_", id.strip())
        if sanitized in idx:
            return idx[sanitized]
        low = id.lower()
        for k, v in idx.items():
            if k.lower() == low or k.lower() == sanitized.lower():
                return v
        return None

    def get_all_entries(self) -> list[CatalogEntry]:
        cache = self.store.load()
        if not cache:
            return []
        return cache.entries
