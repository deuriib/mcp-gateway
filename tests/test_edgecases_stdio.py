"""Hermetic edge tests: stdio NDJSON + filtered stdio noise + resolve."""

from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_gway import stdio as S
from mcp_gway import stdio_transport as ST
from mcp_gway.gateway import Gateway
from mcp_gway.registry import Registry


def _gw(tmp_path):
    return Gateway(Registry(servers_dir=tmp_path / "srv"))


async def test_stdio_handle_line_variants(tmp_path):
    gw = _gw(tmp_path)
    ad = S.StdioAdapter(gw)
    assert await ad.handle_line("   ") is None
    assert await ad.handle_line(b"x" * (S.MAX_LINE_BYTES + 1)) is not None
    assert json.loads(await ad.handle_line(b"\xff\xfe"))["error"]["code"] == -32700
    assert json.loads(await ad.handle_line("not json"))["error"]["code"] == -32700
    assert json.loads(await ad.handle_line("[1,2]"))["error"]["code"] == -32600
    assert json.loads(await ad.handle_line("42"))["error"]["code"] == -32600
    assert (
        json.loads(await ad.handle_line(json.dumps({"id": 1})))["error"]["code"]
        == -32600
    )
    assert await ad.handle_line(json.dumps({"method": "notifications/x"})) is None
    out = await ad.handle_line(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
    )
    assert json.loads(out)["result"] == {}
    out = await ad.handle_line(
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping", "params": "bad"})
    )
    assert json.loads(out)["error"]["code"] == -32602
    out = await ad.handle_line(
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping", "params": {}}).encode()
    )
    assert json.loads(out)["result"] == {}


async def test_stdio_notification_exception_swallowed(tmp_path):
    gw = _gw(tmp_path)
    with patch.object(gw, "_handle_method", side_effect=RuntimeError("x")):
        ad = S.StdioAdapter(gw)
        assert await ad.handle_line(json.dumps({"method": "notifications/hi"})) is None


async def test_stdio_non_dict_response(tmp_path):
    gw = _gw(tmp_path)

    async def fake_post(body, session_id=None):
        return [1, 2]

    gw._handle_post = fake_post
    ad = S.StdioAdapter(gw)
    out = await ad.handle_line(
        json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping", "params": {}})
    )
    assert json.loads(out)["error"]["code"] == -32603


def test_capped_reader_normal_and_eof():
    r = S._CappedLineReader(io.StringIO("hello\n"))
    line, overlong, eof = r.readline_capped()
    assert line == "hello\n" and not overlong and not eof
    r2 = S._CappedLineReader(io.StringIO(""))
    line, overlong, eof = r2.readline_capped()
    assert eof and line is None


def test_capped_reader_read_errors():
    class Bad:
        def read(self, n):
            raise RuntimeError("x")

        def readline(self, limit):
            raise RuntimeError("x")

    r3 = S._CappedLineReader(Bad())
    _line, _overlong, eof = r3.readline_capped()
    assert eof

    class Weird:
        def readline(self, limit):
            return 12345

    r4 = S._CappedLineReader(Weird())
    _line, _overlong, eof = r4.readline_capped()
    assert eof

    class BadType:
        def read(self, limit):
            return object()

    r7 = S._CappedLineReader(BadType())
    assert r7.readline_capped()[2] is True


def test_capped_reader_overlong_and_helpers():
    big = "x" * (S.MAX_LINE_BYTES + 10) + "\nrest\n"
    r5 = S._CappedLineReader(io.StringIO(big))
    _line, overlong, _eof = r5.readline_capped()
    assert overlong
    assert r5._byte_len(b"ab") == 2 and r5._byte_len("ab") == 2

    class NoReadline:
        def read(self, limit):
            return "hi\n"

    r6 = S._CappedLineReader(NoReadline())
    assert r6.readline_capped()[0] == "hi\n"


async def test_run_stdio_async_eof_and_overlong(tmp_path):
    gw = _gw(tmp_path)
    out = io.StringIO()
    err = io.StringIO()
    code = await S.run_stdio_async(gw, io.StringIO(""), out, err)
    assert code == 0
    big = "x" * (S.MAX_LINE_BYTES + 5) + "\n"
    out2 = io.StringIO()
    code = await S.run_stdio_async(gw, io.StringIO(big), out2, err)
    assert code == 0 and "-32700" in out2.getvalue()
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}) + "\n"
    out3 = io.StringIO()
    code = await S.run_stdio_async(gw, io.StringIO(req), out3, err)
    assert code == 0 and '"result"' in out3.getvalue()


async def test_run_stdio_broken_pipe(tmp_path):
    gw = _gw(tmp_path)

    class BPS:
        def write(self, s):
            raise BrokenPipeError("pipe")

        def flush(self):
            pass

    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}) + "\n"
    code = await S.run_stdio_async(gw, io.StringIO(req), BPS(), io.StringIO())
    assert code == 0


@pytest.mark.parametrize(
    "command,pattern",
    [("", "must not be empty"), ("a/b", "reason="), ("a..b", "reason=")],
    ids=["empty", "slash", "dotdot"],
)
def test_resolve_windows_command_invalid(command, pattern):
    with pytest.raises(ValueError, match=pattern):
        ST.resolve_windows_command(command)


def test_resolve_windows_command_not_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda c: None)
    with pytest.raises(FileNotFoundError, match="reason=binary_not_found"):
        ST.resolve_windows_command("nosuchbin123")


def test_resolve_windows_command_ok(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda c: "/usr/bin/" + c)
    assert ST.resolve_windows_command("mybin") == "/usr/bin/mybin"


async def test_filtered_read_stream():
    async def gen():
        yield ValueError("noise1")
        yield {"ok": 1}
        yield RuntimeError("noise2")

    noise = []
    async with ST.filtered_stdio_client(read_stream=gen(), on_noise=noise.append) as (
        rs,
        w,
    ):
        assert w is None
        assert await rs.__anext__() == {"ok": 1}
        with pytest.raises(StopAsyncIteration):
            await rs.__anext__()
    assert noise == [2]

    async def gen2():
        yield {"a": 1}

    def boom(n):
        raise RuntimeError("cb fail")

    async with ST.filtered_stdio_client(read_stream=gen2(), on_noise=boom) as (
        rs2,
        _,
    ):
        assert await rs2.__anext__() == {"a": 1}
    async with ST.filtered_stdio_client(read_stream=gen2()) as (rs3, _):
        async with rs3:
            pass
        _seen = [x async for x in rs3]
        assert _seen == []


async def test_filtered_stdio_client_server_branch():
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), MagicMock()))
    cm.__aexit__ = AsyncMock(return_value=False)
    with patch("mcp.client.stdio.stdio_client", return_value=cm):
        async with ST.filtered_stdio_client(server=MagicMock()) as (rs, _w):
            assert rs is not None
