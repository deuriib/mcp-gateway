"""Tests for stdio transport helpers."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from typing import Any

import pytest

from mcp_gway.stdio_transport import filtered_stdio_client, resolve_windows_command

# --- resolve_windows_command tests ---


def test_resolve_prefers_exe_over_cmd(tmp_path: Any, monkeypatch: Any) -> None:
    """A bare command name should resolve to .exe over .cmd on Windows."""
    # Create fake executables
    fake_dir = tmp_path / "fakebin"
    fake_dir.mkdir()
    (fake_dir / "mytool.exe").write_text("exe")
    (fake_dir / "mytool.cmd").write_text("cmd")
    (fake_dir / "mytool.bat").write_text("bat")

    # Monkeypatch platform and PATH
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PATH", str(fake_dir))

    result = resolve_windows_command("mytool")
    assert result == str(fake_dir / "mytool.exe")


def test_resolve_absolute_path_valid(tmp_path: Any) -> None:
    """An absolute path that exists should be returned as-is."""
    existing = tmp_path / "tool.exe"
    existing.write_text("x")
    result = resolve_windows_command(str(existing))
    assert result == str(existing)


def test_resolve_absolute_path_invalid(tmp_path: Any) -> None:
    """An absolute path that does not exist should raise FileNotFoundError."""
    missing = tmp_path / "nope.exe"
    with pytest.raises(FileNotFoundError, match="not found"):
        resolve_windows_command(str(missing))


def test_resolve_unresolvable_raises(tmp_path: Any, monkeypatch: Any) -> None:
    """Unknown command should raise FileNotFoundError with helpful message."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(FileNotFoundError, match="nonexistent_tool"):
        resolve_windows_command("nonexistent_tool")


def test_resolve_non_windows_passthrough(monkeypatch: Any) -> None:
    """On non-Windows platforms the command should pass through unchanged."""
    monkeypatch.setattr(sys, "platform", "linux")
    result = resolve_windows_command("some_tool")
    assert result == "some_tool"


def test_resolve_appends_exe_extension(tmp_path: Any, monkeypatch: Any) -> None:
    """A bare name with no extension should resolve if .exe exists in PATH."""
    fake_dir = tmp_path / "bin"
    fake_dir.mkdir()
    (fake_dir / "grepper.exe").write_text("x")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PATH", str(fake_dir))

    result = resolve_windows_command("grepper")
    assert result == str(fake_dir / "grepper.exe")


def test_resolve_appends_com_extension(tmp_path: Any, monkeypatch: Any) -> None:
    """A bare name should also resolve .com if .exe is not found."""
    fake_dir = tmp_path / "bin"
    fake_dir.mkdir()
    (fake_dir / "grepper.com").write_text("x")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PATH", str(fake_dir))

    result = resolve_windows_command("grepper")
    assert result == str(fake_dir / "grepper.com")


# --- filtered_stdio_client tests ---


class _FakeStream:
    """Minimal async iterator yielding preset items."""

    def __init__(self, items: list[Any]) -> None:
        self._items = items
        self._index = 0

    def __aiter__(self) -> AsyncIterator[Any]:
        return self

    async def __anext__(self) -> Any:
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


def _make_valid_message(text: str = "hello") -> Any:
    """Return a sentinel object that is NOT an Exception."""
    return {"role": "assistant", "content": text}


@pytest.mark.asyncio
async def test_filtered_client_drops_exceptions() -> None:
    """Exception items in the read stream should be silently dropped."""
    valid = _make_valid_message("ok")
    noise = RuntimeError("banner parse failure")

    async with filtered_stdio_client(
        read_stream=_FakeStream([noise, valid]),  # type: ignore[arg-type]
    ) as (read, _write):
        collected: list[Any] = []
        async for item in read:  # type: ignore[union-attr]
            collected.append(item)

    assert collected == [valid]


@pytest.mark.asyncio
async def test_filtered_client_forwards_valid_messages() -> None:
    """All non-Exception items should pass through untouched."""
    msg1 = _make_valid_message("first")
    msg2 = _make_valid_message("second")

    async with filtered_stdio_client(
        read_stream=_FakeStream([msg1, msg2]),  # type: ignore[arg-type]
    ) as (read, _write):
        collected: list[Any] = []
        async for item in read:  # type: ignore[union-attr]
            collected.append(item)

    assert collected == [msg1, msg2]


@pytest.mark.asyncio
async def test_filtered_client_noise_callback() -> None:
    """on_noise callback should receive the count of dropped items."""
    dropped_count = 0

    def on_noise(count: int) -> None:
        nonlocal dropped_count
        dropped_count = count

    items: list[Any] = [
        RuntimeError("one"),
        _make_valid_message("valid"),
        RuntimeError("two"),
        RuntimeError("three"),
    ]

    async with filtered_stdio_client(
        read_stream=_FakeStream(items),  # type: ignore[arg-type]
        on_noise=on_noise,
    ) as (read, _write):
        async for _ in read:  # type: ignore[union-attr]
            pass

    assert dropped_count == 3


@pytest.mark.asyncio
async def test_filtered_client_valid_with_interleaved_noise() -> None:
    """Valid items interleaved with noise should yield only valid items in order."""
    v1 = _make_valid_message("a")
    v2 = _make_valid_message("b")
    noise = RuntimeError("oops")

    items: list[Any] = [v1, noise, v2]
    async with filtered_stdio_client(
        read_stream=_FakeStream(items),  # type: ignore[arg-type]
    ) as (read, _write):
        collected: list[Any] = []
        async for item in read:  # type: ignore[union-attr]
            collected.append(item)

    assert collected == [v1, v2]


# --- Bug 4: empty string guard ---


def test_resolve_empty_string_raises_value_error() -> None:
    """Passing an empty string to resolve_windows_command should raise ValueError."""
    with pytest.raises(ValueError, match="must not be empty"):
        resolve_windows_command("")


# --- Bug 3: bare name with existing extension ---


def test_scan_path_bare_name_with_extension(tmp_path: Any, monkeypatch: Any) -> None:
    """A bare command like 'node.exe' should be found directly, not appended."""
    fake_dir = tmp_path / "bin"
    fake_dir.mkdir()
    (fake_dir / "node.exe").write_text("x")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PATH", str(fake_dir))

    result = resolve_windows_command("node.exe")
    assert result == str(fake_dir / "node.exe")


# --- Bug 1: explicit server parameter ---


@pytest.mark.asyncio
async def test_filtered_client_explicit_server_param() -> None:
    """filtered_stdio_client should accept `server` kwarg, not **params."""
    msg = _make_valid_message("ok")
    async with filtered_stdio_client(
        read_stream=_FakeStream([msg]),
        server=None,
    ) as (read, _write):
        collected: list[Any] = []
        async for item in read:  # type: ignore[union-attr]
            collected.append(item)
    assert collected == [msg]


# --- Bug 2: on_noise exception safety ---


@pytest.mark.asyncio
async def test_filtered_client_on_noise_exception_does_not_corrupt() -> None:
    """If on_noise callback raises, stream termination should still work."""

    def bad_on_noise(count: int) -> None:
        raise RuntimeError("callback blew up")

    items: list[Any] = [
        RuntimeError("noise"),
        _make_valid_message("valid"),
    ]

    async with filtered_stdio_client(
        read_stream=_FakeStream(items),  # type: ignore[arg-type]
        on_noise=bad_on_noise,
    ) as (read, _write):
        collected: list[Any] = []
        async for item in read:  # type: ignore[union-attr]
            collected.append(item)

    assert collected == [_make_valid_message("valid")]


# --- Smoke test: real stdio_client path ---


@pytest.mark.asyncio
async def test_filtered_client_real_stdio_client_smoke() -> None:
    """Smoke-test the real stdio_client branch with a trivial subprocess.

    The subprocess prints a single valid JSON-RPC message and exits.
    We iterate the read stream to confirm the message actually flows through.
    """
    from mcp import StdioServerParameters

    msg = '{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}'
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            f"import sys; sys.stdout.write({msg!r}); sys.stdout.write('\\n'); sys.stdout.flush()",
        ],
    )
    async with filtered_stdio_client(server=params) as (read, _write):
        collected: list[Any] = []
        async for item in read:  # type: ignore[union-attr]
            collected.append(item)

    from mcp.types import JSONRPCResponse

    assert len(collected) == 1
    first = collected[0]
    response = first.message  # SessionMessage wraps a JSONRPCResponse
    assert isinstance(response, JSONRPCResponse)
    assert response.jsonrpc == "2.0"
    assert response.id == 1
    assert response.result == {"tools": []}


@pytest.mark.asyncio
async def test_filtered_client_real_stdio_mixes_valid_and_noise() -> None:
    """A stream with valid JSON lines interleaved with noise yields only valid ones.

    The subprocess prints: noise line, valid JSON-RPC, noise line, valid JSON-RPC.
    The filter should deliver exactly the two valid messages in order.
    """
    from mcp import StdioServerParameters

    valid1 = '{"jsonrpc":"2.0","id":1,"result":{}}'
    valid2 = '{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}'
    script = (
        "import sys\n"
        "lines = [\n"
        "    'some random noise text',\n"
        f"    {valid1!r},\n"
        "    '>>>banner garbage<<<',\n"
        f"    {valid2!r},\n"
        "]\n"
        "for line in lines:\n"
        "    sys.stdout.write(line + '\\n')\n"
        "sys.stdout.flush()\n"
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", script],
    )
    async with filtered_stdio_client(server=params) as (read, _write):
        collected: list[Any] = []
        async for item in read:  # type: ignore[union-attr]
            collected.append(item)

    # The noise lines are parsed by the MCP SDK and may arrive as exceptions
    # (dropped by the filter) or may not be parseable as JSON-RPC at all.
    # We only assert on valid JSON-RPC messages that survive filtering.
    from mcp.types import JSONRPCResponse

    assert len(collected) == 2
    r1 = collected[0].message
    r2 = collected[1].message
    assert isinstance(r1, JSONRPCResponse)
    assert isinstance(r2, JSONRPCResponse)
    assert r1.id == 1
    assert r2.id == 2


# --- FIX 2: on_noise callback with real stdio subprocess ---


@pytest.mark.asyncio
async def test_filtered_client_real_stdio_with_noise_logs_warning():
    """Subprocess with noise lines should invoke on_noise callback with correct count."""
    from mcp import StdioServerParameters

    valid = '{"jsonrpc":"2.0","id":1,"result":{}}'
    script = (
        "import sys\n"
        "lines = [\n"
        "    'noise line 1',\n"
        "    'noise line 2',\n"
        "    'noise line 3',\n"
        f"    {valid!r},\n"
        "]\n"
        "for line in lines:\n"
        "    sys.stdout.write(line + '\\n')\n"
        "sys.stdout.flush()\n"
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", script],
    )

    noise_count = 0

    def on_noise(count: int) -> None:
        nonlocal noise_count
        noise_count = count

    async with filtered_stdio_client(server=params, on_noise=on_noise) as (
        read,
        _write,
    ):
        collected: list[Any] = []
        async for item in read:  # type: ignore[union-attr]
            collected.append(item)

    # We should get at least 1 valid message through
    assert len(collected) >= 1
    # The noise callback should have been called (count may vary based on
    # how the MCP SDK parses noise — could be 1-3 exceptions)
    assert noise_count >= 1
