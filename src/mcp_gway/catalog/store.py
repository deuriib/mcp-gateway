"""CatalogStore - atomic cache I/O."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from mcp_gway.catalog.models import CatalogCache

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path.home() / ".config" / "mcp-gway" / "catalog.json"


class CatalogStore:
    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            env_path = os.getenv("CATALOG_CACHE_PATH") or os.getenv(
                "MCP_GWAY_CATALOG_PATH"
            )
            if env_path:
                path = Path(env_path)
            else:
                path = DEFAULT_CACHE_PATH
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def load(self) -> CatalogCache | None:
        try:
            if not self.path.exists():
                return None
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return CatalogCache(**data)
        except Exception as e:  # noqa: BLE001
            logger.warning("catalog load corrupt: %s", e)
            return None

    def save(self, cache: CatalogCache) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass
        data = cache.model_dump(mode="json")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        tmp.replace(self.path)
        try:
            os.chmod(self.path, 0o600)
        except Exception:
            pass
