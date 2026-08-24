"""Stdio transport helpers — command resolution and noise-filtered client."""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from mcp import StdioServerParameters

_NATIVE_EXTENSIONS = (".exe", ".com")
_SHELL_EXTENSIONS = (".cmd", ".bat", ".ps1")
_WINDOWS_EXTENSIONS = _NATIVE_EXTENSIONS + _SHELL_EXTENSIONS


def _scan_path_for_command(command: str) -> str | None:
    """Scan PATH directories for *command*, honouring extension priority.

    Returns the matched path preserving the original filesystem casing,
    or ``None`` when no match is found.
    """
    for entry in os.get_exec_path():
        if not entry:
            continue
        directory = Path(entry)
        candidate = directory / command
        if candidate.is_file():
            return str(candidate)
        for ext in _WINDOWS_EXTENSIONS:
            candidate = directory / f"{command}{ext}"
            if candidate.is_file():
                return str(candidate)
    return None


def resolve_windows_command(command: str) -> str:
    """Resolve a command name to its full path on Windows.

    On non-Windows platforms the command is returned unchanged.

    Resolution strategy on Windows:
    - Absolute paths are validated for existence.  When the path has no
      recognized extension (.exe/.com/.cmd/.bat/.ps1) we try appending
      each extension in priority order before giving up.
    - Bare command names are resolved by scanning PATH directories,
      preferring native executables (.exe, .com) over shell shims
      (.cmd, .bat, .ps1).
    """
    if not command:
        raise ValueError("Command must not be empty")

    if sys.platform != "win32":
        return command

    path = Path(command)

    # ── absolute path ────────────────────────────────────────────
    if path.is_absolute():
        if path.exists():
            return str(path)
        if path.suffix.lower() not in _WINDOWS_EXTENSIONS:
            for ext in _WINDOWS_EXTENSIONS:
                candidate = path.with_suffix(ext)
                if candidate.exists():
                    return str(candidate)
        raise FileNotFoundError(f"Command not found: {command}")

    # ── bare name – scan PATH ────────────────────────────────────
    found = _scan_path_for_command(command)
    if found is not None:
        return found

    raise FileNotFoundError(f"Command not found: {command}")


# ── noise-filtered read stream ────────────────────────────────────


class _FilteredReadStream:
    """Wraps an async iterator and silently drops ``Exception`` items.

    Implements the async context manager protocol so the stream can be
    used with ``async with`` as expected by the MCP SDK's dispatcher.
    """

    def __init__(
        self,
        stream: AsyncIterator[Any],
        on_noise: Callable[[int], None] | None = None,
    ) -> None:
        self._stream = stream
        self._on_noise = on_noise
        self._noise_count = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        if hasattr(self._stream, "aclose"):
            await self._stream.aclose()

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> Any:
        while True:
            try:
                item = await self._stream.__anext__()
            except StopAsyncIteration:
                if self._on_noise is not None and self._noise_count > 0:
                    try:
                        self._on_noise(self._noise_count)
                    except Exception:  # noqa: S110 — intentional: callback errors must not break stream
                        pass  # Callback errors should never break stream termination
                raise
            if isinstance(item, Exception):
                self._noise_count += 1
                continue
            return item


# ── public async context manager ──────────────────────────────────


@asynccontextmanager
async def filtered_stdio_client(
    *,
    read_stream: AsyncIterator[Any] | None = None,
    on_noise: Callable[[int], None] | None = None,
    server: StdioServerParameters | None = None,
) -> AsyncIterator[tuple[AsyncIterator[Any], Any]]:
    """Wrap ``mcp.client.stdio.stdio_client`` with noise filtering.

    The yielded **read** stream drops items that are ``Exception``
    instances (banner parse failures, non-JSON noise, etc.) while
    passing valid messages through untouched.

    Parameters
    ----------
    read_stream:
        When provided the stream is filtered directly without
        creating an underlying MCP client — useful for testing.
    on_noise:
        Optional callback invoked with the total count of dropped
        ``Exception`` items once the stream is exhausted.
    server:
        ``StdioServerParameters`` forwarded to
        ``mcp.client.stdio.stdio_client`` when *read_stream* is ``None``.
    """
    if read_stream is not None:
        filtered = _FilteredReadStream(read_stream, on_noise)
        yield filtered, None
    else:
        from mcp.client.stdio import stdio_client

        async with stdio_client(server) as (raw_read, write):
            filtered = _FilteredReadStream(raw_read, on_noise)
            yield filtered, write
