"""Stdio transport helpers — command resolution and noise-filtered client."""

from __future__ import annotations

import shutil
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from mcp import StdioServerParameters


def resolve_windows_command(command: str) -> str:
    """Resolve a basename via PATH to its full path (execvp target).

    Only basenames are accepted — paths, separators and shell shims are
    rejected. Resolution uses ``shutil.which`` so ``PATH``/``PATHEXT``
    semantics apply on every platform. Never invokes a shell.
    """
    if not command:
        raise ValueError("Command must not be empty")
    if "/" in command or "\\" in command or ":" in command:
        raise ValueError(
            f"command must be basename, not path: {command} [reason=invalid_syntax]"
        )
    if ".." in command:
        raise ValueError("command token must not contain .. [reason=invalid_syntax]")
    resolved = shutil.which(command)
    if not resolved:
        raise FileNotFoundError(
            f"binary not found in PATH: {command} [reason=binary_not_found]"
        )
    return resolved


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

        async with stdio_client(server, errlog=sys.__stderr__) as (raw_read, write):
            filtered = _FilteredReadStream(raw_read, on_noise)
            yield filtered, write
