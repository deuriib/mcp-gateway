"""Hermetic edge tests: oauth PKCE + tokens + discovery + callback (no network)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import stat as _stat
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from mcp_gway import oauth as O


def _tok_storage(tmp_path, name="edge_srv"):
    return O.FileTokenStorage(name, storage_dir=tmp_path)


def test_validate_server_name_ok_and_bad():
    O._validate_server_name("good_name")
    with pytest.raises(ValueError, match="hyphen|spaces|Name"):
        O._validate_server_name("bad-name!")
    with pytest.raises(ValueError, match="separator|traversal|Name"):
        O._validate_server_name("../evil")


def test_secure_atomic_write_roundtrip(tmp_path):
    p = tmp_path / "t.json"
    O._secure_atomic_write(p, '{"a": 1}')
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1}
    st = p.stat()
    if os.name != "nt":
        assert oct(_stat.S_IMODE(st.st_mode)) == oct(0o600)


def test_secure_atomic_write_refuses_symlink(tmp_path):
    if os.name == "nt":
        pytest.skip("posix symlink semantics")
    target = tmp_path / "real.json"
    target.write_text("x", encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("no symlink perm")
    with pytest.raises(ValueError, match="symlink"):
        O._secure_atomic_write(link, "y")


async def test_file_token_storage_missing_returns_none(tmp_path):
    s = _tok_storage(tmp_path)
    assert await s.get_tokens() is None
    assert await s.get_client_info() is None


async def test_file_token_storage_invalid_json_returns_none(tmp_path):
    s = _tok_storage(tmp_path)
    s._token_file.write_text("not-json", encoding="utf-8")
    assert await s.get_tokens() is None
    info_file = tmp_path / "edge_srv_client.json"
    info_file.write_text("bad", encoding="utf-8")
    assert await s.get_client_info() is None


async def test_file_token_storage_set_get_roundtrip(tmp_path):
    s = _tok_storage(tmp_path)
    tok = OAuthToken(access_token="abc", token_type="Bearer")
    await s.set_tokens(tok)
    got = await s.get_tokens()
    assert got is not None and got.access_token == "abc"


async def test_file_token_storage_client_info_roundtrip(tmp_path):
    s = _tok_storage(tmp_path)
    ci = OAuthClientInformationFull(client_id="cid123")
    await s.set_client_info(ci)
    got = await s.get_client_info()
    assert got is not None and got.client_id == "cid123"


def test_file_token_storage_rejects_traversal(tmp_path):
    with pytest.raises(ValueError, match="separator|traversal|Name"):
        O.FileTokenStorage("../evil", storage_dir=tmp_path)
    with pytest.raises(ValueError, match="separator|traversal|Name"):
        O.FileTokenStorage("bad/name", storage_dir=tmp_path)


def test_generate_pkce_shape():
    v, c = O.generate_pkce()
    assert len(v) == 128
    assert len(c) >= 40
    expect = (
        base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert c == expect


def test_parse_resource_metadata_variants():
    assert O._parse_resource_metadata_url("") is None
    assert O._parse_resource_metadata_url("Bearer realm=x") is None
    u = "https://auth.example.com/.well-known/oauth-protected-resource"
    assert O._parse_resource_metadata_url(f'Bearer resource_metadata="{u}"') == u
    assert O._parse_resource_metadata_url(f"Bearer resource_metadata='{u}'") == u
    assert O._parse_resource_metadata_url(f"Bearer resource_metadata={u}") == u


class _FakeResp:
    def __init__(self, status=404, payload=None, headers=None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}
        self.content = json.dumps(self._payload).encode()
        self.text = json.dumps(self._payload)[:200]

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, follow_redirects=True, **kw):
        return self._handler(url)

    async def post(self, url, headers=None, follow_redirects=True, **kw):
        return self._handler(url, kw)


async def test_discover_oauth_metadata_via_header_and_prm(monkeypatch):
    prm_url = "https://auth.example.com/prm"
    auth_srv = "https://auth.example.com"

    def handler(url, kw=None):
        if url == "https://api.example.com/mcp":
            return _FakeResp(
                401, {}, {"www-authenticate": f'Bearer resource_metadata="{prm_url}"'}
            )
        if url == prm_url:
            return _FakeResp(200, {"authorization_servers": [auth_srv]})
        if url == f"{auth_srv}/.well-known/oauth-authorization-server":
            return _FakeResp(
                200,
                {
                    "authorization_endpoint": "https://a/e",
                    "token_endpoint": "https://a/t",
                },
            )
        return _FakeResp(404, {})

    monkeypatch.setattr(O.httpx2, "AsyncClient", lambda *a, **k: _FakeClient(handler))
    out = await O.discover_oauth_metadata("https://api.example.com/mcp")
    assert out is not None and out["token_endpoint"] == "https://a/t"


async def test_discover_oauth_metadata_fallback_and_none(monkeypatch):
    def handler(url, kw=None):
        if url == "https://api.example.com/mcp":
            return _FakeResp(200, {})
        if "oauth-authorization-server" in url:
            return _FakeResp(
                200, {"authorization_endpoint": "e", "token_endpoint": "t"}
            )
        return _FakeResp(404, {})

    monkeypatch.setattr(O.httpx2, "AsyncClient", lambda *a, **k: _FakeClient(handler))
    out = await O.discover_oauth_metadata("https://api.example.com/mcp")
    assert out == {"authorization_endpoint": "e", "token_endpoint": "t"}
    monkeypatch.setattr(
        O.httpx2,
        "AsyncClient",
        lambda *a, **k: _FakeClient(lambda u, kw=None: _FakeResp(404, {})),
    )
    assert await O.discover_oauth_metadata("https://api.example.com/mcp") is None


async def test_discover_oauth_metadata_get_raises(monkeypatch):
    class Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise RuntimeError("net down")

    monkeypatch.setattr(O.httpx2, "AsyncClient", lambda *a, **k: Boom())
    assert await O.discover_oauth_metadata("https://api.example.com/mcp") is None


async def test_run_oauth_flow_existing_token(tmp_path, monkeypatch):
    s = O.FileTokenStorage("flowsrv", storage_dir=tmp_path)
    await s.set_tokens(OAuthToken(access_token="tok123", token_type="Bearer"))
    monkeypatch.setattr(O, "FileTokenStorage", lambda name: s)
    msgs = []
    out = await O.run_oauth_flow(
        "https://api.example.com/mcp", "flowsrv", output_callback=msgs.append
    )
    assert out is not None
    await out.aclose()


async def test_run_oauth_flow_no_metadata(monkeypatch, tmp_path):
    s = O.FileTokenStorage("nometa", storage_dir=tmp_path)
    monkeypatch.setattr(O, "FileTokenStorage", lambda name: s)
    monkeypatch.setattr(O, "discover_oauth_metadata", AsyncMock(return_value=None))
    msgs = []
    out = await O.run_oauth_flow(
        "https://api.example.com/mcp", "nometa", output_callback=msgs.append
    )
    assert out is None
    assert any("manually" in m or "token" in m.lower() for m in msgs)


async def test_run_oauth_flow_missing_endpoints(monkeypatch, tmp_path):
    s = O.FileTokenStorage("noep", storage_dir=tmp_path)
    monkeypatch.setattr(O, "FileTokenStorage", lambda name: s)
    monkeypatch.setattr(
        O,
        "discover_oauth_metadata",
        AsyncMock(
            return_value={"authorization_endpoint": None, "token_endpoint": None}
        ),
    )
    out = await O.run_oauth_flow(
        "https://api.example.com/mcp", "noep", output_callback=lambda m: None
    )
    assert out is None


def _patch_full_flow(
    monkeypatch,
    tmp_path,
    name,
    metadata,
    reg_payload=None,
    reg_status=201,
    token_payload=None,
    token_status=200,
    token_exc=None,
):
    s = O.FileTokenStorage(name, storage_dir=tmp_path)
    monkeypatch.setattr(O, "FileTokenStorage", lambda n: s)
    monkeypatch.setattr(O, "discover_oauth_metadata", AsyncMock(return_value=metadata))
    captured_auth = {}

    def _fake_open(url):
        captured_auth["url"] = url
        return True

    monkeypatch.setattr(O.webbrowser, "open", _fake_open)

    class CB:
        def __init__(self, port=8989):
            self._port = port
            self.callback_url = f"http://127.0.0.1:{port}/callback"

        async def start(self):
            return None

        async def wait_for_callback(self, timeout=300.0):
            from urllib.parse import parse_qs, urlparse

            raw = captured_auth.get("url", "")
            try:
                q = parse_qs(urlparse(raw).query)
                st = q.get("state", ["s"])[0]
            except Exception:
                st = "s"
            return {"code": "authcode123", "state": st}

    monkeypatch.setattr(O, "OAuthCallbackServer", CB)
    captured = {}

    class HC:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            captured["url"] = url
            if "register" in url:
                return _FakeResp(reg_status, reg_payload or {})
            if token_exc:
                raise token_exc
            r = _FakeResp(token_status, token_payload or {})
            return r

        async def aclose(self):
            return None

    monkeypatch.setattr(O.httpx2, "AsyncClient", HC)
    return captured


async def test_run_oauth_flow_dynamic_registration_success(tmp_path, monkeypatch):
    meta = {
        "authorization_endpoint": "https://a/auth",
        "token_endpoint": "https://a/token",
        "registration_endpoint": "https://a/register",
    }
    _patch_full_flow(
        monkeypatch,
        tmp_path,
        "dynok",
        meta,
        reg_payload={"client_id": str(uuid.uuid4())},
        token_payload={"access_token": "AT", "token_type": "Bearer"},
    )
    msgs = []
    out = await O.run_oauth_flow(
        "https://api.example.com/mcp", "dynok", output_callback=msgs.append
    )
    assert out is not None
    await out.aclose()


async def test_run_oauth_flow_manual_client_and_reg_fail(tmp_path, monkeypatch):
    meta = {
        "authorization_endpoint": "https://a/auth",
        "token_endpoint": "https://a/token",
        "registration_endpoint": "https://a/register",
    }
    cid = str(uuid.uuid4())
    _patch_full_flow(
        monkeypatch,
        tmp_path,
        "manok",
        meta,
        reg_payload={},
        reg_status=500,
        token_payload={"access_token": "AT2", "token_type": "Bearer"},
    )
    out = await O.run_oauth_flow(
        "https://api.example.com/mcp",
        "manok",
        output_callback=lambda m: None,
        oauth_config={"clientId": cid, "clientSecret": "s", "scope": "openid"},
    )
    assert out is not None
    await out.aclose()


async def test_run_oauth_flow_reg_exception_and_token_fail(tmp_path, monkeypatch):
    meta = {
        "authorization_endpoint": "https://a/auth",
        "token_endpoint": "https://a/token",
        "registration_endpoint": "https://a/register",
    }
    _patch_full_flow(
        monkeypatch,
        tmp_path,
        "regfail",
        meta,
        reg_payload={},
        token_payload={},
        token_status=400,
    )
    out = await O.run_oauth_flow(
        "https://api.example.com/mcp", "regfail", output_callback=lambda m: None
    )
    assert out is None


async def test_run_oauth_flow_token_exception(tmp_path, monkeypatch):
    meta = {
        "authorization_endpoint": "https://a/auth",
        "token_endpoint": "https://a/token",
    }
    _patch_full_flow(
        monkeypatch, tmp_path, "tokexc", meta, token_exc=RuntimeError("boom")
    )
    out = await O.run_oauth_flow(
        "https://api.example.com/mcp", "tokexc", output_callback=lambda m: None
    )
    assert out is None


async def test_run_oauth_flow_callback_timeout(tmp_path, monkeypatch):
    s = O.FileTokenStorage("cbtimeout", storage_dir=tmp_path)
    monkeypatch.setattr(O, "FileTokenStorage", lambda n: s)
    monkeypatch.setattr(
        O,
        "discover_oauth_metadata",
        AsyncMock(
            return_value={
                "authorization_endpoint": "https://a/auth",
                "token_endpoint": "https://a/token",
            }
        ),
    )

    class CBNone:
        def __init__(self, port=8989):
            self._port = port
            self.callback_url = f"http://127.0.0.1:{port}/callback"

        async def start(self):
            return None

        async def wait_for_callback(self, timeout=300.0):
            return None

    monkeypatch.setattr(O, "OAuthCallbackServer", CBNone)
    monkeypatch.setattr(O.webbrowser, "open", lambda url: True)
    out = await O.run_oauth_flow(
        "https://api.example.com/mcp", "cbtimeout", output_callback=lambda m: None
    )
    assert out is None


async def test_run_oauth_flow_invalid_manual_falls_back(tmp_path, monkeypatch):
    meta = {
        "authorization_endpoint": "https://a/auth",
        "token_endpoint": "https://a/token",
    }
    _patch_full_flow(
        monkeypatch,
        tmp_path,
        "badmanual",
        meta,
        token_payload={"access_token": "AT3", "token_type": "Bearer"},
    )
    out = await O.run_oauth_flow(
        "https://api.example.com/mcp",
        "badmanual",
        output_callback=lambda m: None,
        oauth_config={"clientId": "not-a-uuid"},
    )
    assert out is not None
    await out.aclose()


async def test_get_authenticated_client(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    s = O.FileTokenStorage("gac", storage_dir=tmp_path)
    await s.set_tokens(OAuthToken(access_token="zz", token_type="Bearer"))
    monkeypatch.setattr(O, "FileTokenStorage", lambda n, *a, **k: s)
    c = await O.get_authenticated_client("gac")
    assert c is not None
    await c.aclose()
    monkeypatch.undo()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    s2 = O.FileTokenStorage("emptygac", storage_dir=tmp_path / "e2")
    monkeypatch.setattr(O, "FileTokenStorage", lambda n, *a, **k: s2)
    assert await O.get_authenticated_client("emptygac") is None


class _MemWriter:
    def __init__(self):
        self.data = b""
        self.closed = False

    def write(self, b):
        self.data += b

    async def drain(self):
        return None

    def close(self):
        self.closed = True


class _MemReader:
    def __init__(self, raw):
        self._raw = raw

    async def read(self, n):
        return self._raw


class _FailReader:
    async def read(self, n):
        raise RuntimeError("r fail")


async def _handle_with(srv, raw):
    w = _MemWriter()
    await srv._handle_request(_MemReader(raw), w)
    return w


async def test_callback_server_handle_code():
    srv = O.OAuthCallbackServer(port=8989)
    w = await _handle_with(
        srv, b"GET /callback?code=ABC&state=S HTTP/1.1\r\nHost: x\r\n\r\n"
    )
    assert srv._result is not None
    assert b"HTTP/1.1" in w.data


async def test_callback_server_handle_nocode():
    srv2 = O.OAuthCallbackServer(port=8989)
    w = await _handle_with(srv2, b"GET /callback HTTP/1.1\r\nHost: x\r\n\r\n")
    assert b"400" in w.data


async def test_callback_server_handle_empty():
    await O.OAuthCallbackServer()._handle_request(_MemReader(b""), _MemWriter())


async def test_callback_server_handle_read_error():
    await O.OAuthCallbackServer()._handle_request(_FailReader(), _MemWriter())


async def test_callback_server_handle_broken():
    class W:
        def __init__(self):
            self.data = b""

        def write(self, b):
            self.data = b""

        async def drain(self):
            return None

        def close(self):
            pass

    await O.OAuthCallbackServer()._handle_request(_MemReader(b"BROKEN"), W())


async def test_callback_server_start_fallback_and_wait(monkeypatch):
    srv = O.OAuthCallbackServer(port=9898)
    calls = {"n": 0}

    async def fake_start_server(handler, host, port):
        calls["n"] += 1
        if port != 0 and calls["n"] < 3:
            e = OSError("address already in use")
            raise e
        m = MagicMock()
        m.sockets = [MagicMock(getsockname=lambda: ("127.0.0.1", 19999))]
        return m

    monkeypatch.setattr(asyncio, "start_server", fake_start_server)
    await srv.start()
    assert srv._port in (9899, 9900, 19999)
    assert srv.callback_url.startswith("http://127.0.0.1:")
    srv2 = O.OAuthCallbackServer(port=9898)

    async def always_busy(handler, host, port):
        raise OSError("address already in use")

    monkeypatch.setattr(asyncio, "start_server", always_busy)
    with pytest.raises(OSError, match="address already in use"):
        await srv2.start()
    srv3 = O.OAuthCallbackServer(port=9898)

    async def ok_server(handler, host, port):
        m = MagicMock()
        m.sockets = []
        m.close = MagicMock()
        m.wait_closed = AsyncMock()
        return m

    monkeypatch.setattr(asyncio, "start_server", ok_server)
    await srv3.start()
    out = await srv3.wait_for_callback(timeout=0.05)
    assert out is None
