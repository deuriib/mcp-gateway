"""P1-H3a CSRF state + timeout/cleanup tests — must fail before fix (RED). Hermetic."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

from mcp_gway import oauth as O


async def _run_state_mismatch(tmp_path, monkeypatch, cb_state="WRONG"):
    s = O.FileTokenStorage("statetest", storage_dir=tmp_path)
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
    monkeypatch.setattr(O.webbrowser, "open", lambda url: True)

    class CB:
        def __init__(self, port=8989):
            self._port = port
            self.callback_url = f"http://127.0.0.1:{port}/callback"

        async def start(self):
            return None

        async def wait_for_callback(self, timeout=300.0):
            return {"code": "authcode123", "state": cb_state}

    monkeypatch.setattr(O, "OAuthCallbackServer", CB)
    token_called = {"n": 0}

    class HC:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            token_called["n"] += 1
            from tests.test_edgecases_oauth import _FakeResp

            return _FakeResp(200, {"access_token": "AT", "token_type": "Bearer"})

        async def aclose(self):
            return None

    monkeypatch.setattr(O.httpx2, "AsyncClient", HC)
    out = await O.run_oauth_flow(
        "https://api.example.com/mcp", "statetest", output_callback=lambda m: None
    )
    return out, token_called["n"]


async def test_oauth_state_mismatch_rejected(tmp_path, monkeypatch):
    out, n = await _run_state_mismatch(tmp_path, monkeypatch, cb_state="WRONG-STATE")
    assert out is None, "state mismatch must abort (CSRF)"
    assert n == 0, "token exchange must not run on state mismatch"


async def test_oauth_state_match_succeeds(tmp_path, monkeypatch):
    # Patch to echo correct state: need to capture issued state via auth_url
    s = O.FileTokenStorage("stateok", storage_dir=tmp_path)
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
    captured = {}

    def fake_open(url):
        captured["url"] = url
        return True

    monkeypatch.setattr(O.webbrowser, "open", fake_open)

    class CB:
        def __init__(self, port=8989):
            self._port = port
            self.callback_url = f"http://127.0.0.1:{port}/callback"

        async def start(self):
            return None

        async def wait_for_callback(self, timeout=300.0):
            from urllib.parse import parse_qs, urlparse

            q = parse_qs(urlparse(captured["url"]).query)
            # echo back the exact issued state
            return {"code": "authcode123", "state": q.get("state", [""])[0]}

    monkeypatch.setattr(O, "OAuthCallbackServer", CB)

    class HC:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            from tests.test_edgecases_oauth import _FakeResp

            return _FakeResp(200, {"access_token": "AT", "token_type": "Bearer"})

        async def aclose(self):
            return None

    monkeypatch.setattr(O.httpx2, "AsyncClient", HC)
    out = await O.run_oauth_flow(
        "https://api.example.com/mcp", "stateok", output_callback=lambda m: None
    )
    assert out is not None
    await out.aclose()


def test_oauth_uses_timeout_8_and_cleanup():
    src = inspect.getsource(O.run_oauth_flow)
    assert "8.0" in src or "SSRF_TIMEOUT" in src, (
        "timeout 8.0 missing in run_oauth_flow (single-sourced as SSRF_TIMEOUT)"
    )
    assert "aclose" in src, "aclose cleanup missing in run_oauth_flow"
    src2 = inspect.getsource(O.discover_oauth_metadata)
    assert "8.0" in src2 or "SSRF_TIMEOUT" in src2, (
        "timeout 8.0 missing in discover_oauth_metadata (single-sourced)"
    )


def test_discover_validates_ssrf():
    src = inspect.getsource(O.discover_oauth_metadata)
    assert "validate_url_ssrf" in src or "ssrf_get" in src, "SSRF re-validation missing"
