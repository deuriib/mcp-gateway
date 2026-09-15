"""Symlink-safe atomic file writes (single source of truth).

Registry and OAuth token storage share this helper so the lstat/symlink
dance lives in exactly one place. Files are created 0o600.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


def secure_atomic_write_text(path: Path, content: str) -> None:
    """Write text atomically, refusing symlinks at every step (fail-closed)."""
    if path.is_symlink():
        raise ValueError("refusing to write through symlink")
    try:
        st = os.lstat(path) if path.exists() else None
        if st is not None and stat.S_ISLNK(st.st_mode):
            raise ValueError("refusing to write through symlink")
    except ValueError:
        raise
    except Exception:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.is_symlink():
        raise ValueError("tmp path is symlink")
    try:
        st2 = os.lstat(tmp) if tmp.exists() else None
        if st2 is not None and stat.S_ISLNK(st2.st_mode):
            raise ValueError("tmp path is symlink")
    except ValueError:
        raise
    except Exception:
        pass
    if tmp.exists():
        try:
            tmp.unlink()
        except Exception:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
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
    if path.is_symlink():
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise ValueError("refusing to replace symlink")
    try:
        st_final = os.lstat(path) if path.exists() else None
        if st_final is not None and stat.S_ISLNK(st_final.st_mode):
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise ValueError("refusing to replace symlink")
    except ValueError:
        raise
    except Exception:
        pass
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
