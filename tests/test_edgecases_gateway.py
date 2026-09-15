"""Hermetic edge tests: gateway 5 live paths + SSE + alias + errors."""

from __future__ import annotations

from starlette.requests import Request
from starlette.testclient import TestClient

from mcp_gway.gateway import Gateway, _safe_error_data
from mcp_gway.models import MCPServerConfig, ToolInfo
from mcp_gway.registry import Registry


def _gw(tmp_path):
    return Gateway(Registry(servers_dir=tmp_path / "srv"))


def _handler_value_error_plain():
    def f(m, p):
        raise ValueError("something else")

    return f


def _handler_file_not_found():
    def f(m, p):
        raise FileNotFoundError("nf")

    return f


def _handler_runtime_boom():
    def f(m, p):
        raise RuntimeError("boom")

    return f


async def _put_and_expire(gw, sid):
    gw._create_session(sid)
    assert sid in gw._sessions
    gw.cleanup_expired_sessions(max_idle_seconds=9999)


def test_safe_error_data_reason_and_type():
    e = ValueError("bad [reason=not_allowlisted] extra")
    d = _safe_error_data(e)
    assert d == {"type": "ValueError", "reason": "not_allowlisted"}
    assert _safe_error_data(ValueError("plain")) == {"type": "ValueError"}

    class Boom(Exception):
        def __str__(self):
            raise RuntimeError("str fail")

    assert _safe_error_data(Boom()) == {"type": "Boom"}


def test_live_paths_health_ready_live_metrics(tmp_path):
    gw = _gw(tmp_path)
    c = TestClient(gw.app)
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers.get("Content-Security-Policy") == "default-src 'self'"
    assert "nosniff" in r.headers.get("X-Content-Type-Options", "nosniff")
    assert c.get("/ready").status_code == 200
    assert c.get("/live").json()["status"] == "alive"
    m = c.get("/metrics")
    assert m.status_code == 200 and "mcp_gway_" in m.text
    assert c.get("/metrics").headers.get("X-Request-ID")


def test_metrics_exposed_gating(tmp_path, monkeypatch):
    gw = _gw(tmp_path)
    gw.app.state.serve_host = "0.0.0.0"
    monkeypatch.delenv("MCP_GWAY_ALLOW_REMOTE", raising=False)
    c = TestClient(gw.app)
    r = c.get("/metrics")
    assert r.status_code == 403 and r.headers.get("X-Warning") == "exposed"


def test_mcp_post_initialize_ping_tools_list(tmp_path):
    gw = _gw(tmp_path)
    c = TestClient(gw.app)
    for method, check in [
        ("ping", lambda j: j["result"] == {}),
        ("initialize", lambda j: j["result"]["protocolVersion"] == "2024-11-05"),
        ("notifications/initialized", lambda j: "result" in j),
        ("tools/list", lambda j: len(j["result"]["tools"]) == 4),
    ]:
        r = c.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": {}}
        )
        assert check(r.json()), method


def test_mcp_post_unknown_method_and_tool(tmp_path):
    gw = _gw(tmp_path)
    c = TestClient(gw.app)
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "nope", "params": {}})
    assert r.json()["error"]["code"] == -32601
    r2 = c.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "nope"},
        },
    )
    assert r2.json()["error"]["code"] == -32601


def test_mcp_post_invalid_params_branches(tmp_path):
    gw = _gw(tmp_path)
    c = TestClient(gw.app)
    r = c.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "readToolFile", "arguments": {}},
        },
    )
    assert r.json()["error"]["code"] == -32602
    r = c.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "getToolDocs", "arguments": {"server": "x"}},
        },
    )
    assert r.json()["error"]["code"] == -32602
    r = c.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "executeToolCode", "arguments": {"code": 123}},
        },
    )
    assert r.json()["error"]["code"] == -32602
    r = c.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "executeToolCode", "arguments": {"code": "   "}},
        },
    )
    assert r.json()["error"]["code"] == -32602


def test_mcp_post_list_read_docs_execute_ok(tmp_path):
    reg = Registry(servers_dir=tmp_path / "srv")
    reg.add(
        MCPServerConfig(name="srv1", type="remote", url="https://api.example.com/mcp"),
        [
            ToolInfo(
                name="hello",
                description="hi",
                input_schema={
                    "properties": {"q": {"type": "string"}},
                    "required": ["q"],
                },
            )
        ],
    )
    gw = Gateway(reg)
    c = TestClient(gw.app)
    r = c.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "listToolFiles", "arguments": {}},
        },
    )
    assert "srv1" in r.json()["result"]["content"][0]["text"]
    r = c.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "readToolFile", "arguments": {"fileName": "srv1"}},
        },
    )
    assert "hello" in r.json()["result"]["content"][0]["text"]
    r = c.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "getToolDocs",
                "arguments": {"server": "srv1", "tool": "hello"},
            },
        },
    )
    assert "hello" in r.json()["result"]["content"][0]["text"]
    r = c.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "executeToolCode",
                "arguments": {"code": "result = 1 + 1"},
            },
        },
    )
    assert "2" in r.json()["result"]["content"][0]["text"]


def test_mcp_post_error_mapping_value_error(tmp_path, monkeypatch):
    gw = _gw(tmp_path)
    monkeypatch.setattr(gw, "_handle_method", _handler_value_error_plain())
    c = TestClient(gw.app)
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
    assert r.json()["error"]["code"] == -32603


def test_mcp_post_error_mapping_file_not_found(tmp_path, monkeypatch):
    gw = _gw(tmp_path)
    monkeypatch.setattr(gw, "_handle_method", _handler_file_not_found())
    c = TestClient(gw.app)
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
    assert r.json()["error"]["code"] == -32603


def test_mcp_post_error_mapping_runtime(tmp_path, monkeypatch):
    gw = _gw(tmp_path)
    monkeypatch.setattr(gw, "_handle_method", _handler_runtime_boom())
    c = TestClient(gw.app)
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
    assert r.json()["error"]["code"] == -32603


def test_mcp_post_session_not_found(tmp_path):
    gw = _gw(tmp_path)
    c = TestClient(gw.app)
    r = c.post(
        "/mcp/messages?session_id=nosuch",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
    )
    assert r.json()["error"]["code"] == -32001


def test_mcp_post_alias_and_limits(tmp_path):
    gw = _gw(tmp_path)
    c = TestClient(gw.app)
    r = c.post(
        "/mcp/messages",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}},
    )
    assert r.json()["result"] == {}
    r = c.post(
        "/mcp", content=b"not-json", headers={"content-type": "application/json"}
    )
    assert r.status_code == 400
    big = b"x" * 1048577
    r = c.post(
        "/mcp",
        content=big,
        headers={"content-type": "application/json", "content-length": str(len(big))},
    )
    assert r.status_code == 413


async def test_sse_session_lifecycle_and_cleanup(tmp_path):
    gw = _gw(tmp_path)
    sid = "s1"
    await _put_and_expire(gw, sid)
    assert gw.cleanup_expired_sessions(max_idle_seconds=300.0) == 0
    gw._create_session("old")
    gw._sessions["old"].last_activity -= 1000
    assert gw.cleanup_expired_sessions(max_idle_seconds=1.0) == 1


async def test_sse_stream_and_post_to_session(tmp_path):
    gw = _gw(tmp_path)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/mcp",
        "headers": [],
        "query_string": b"",
    }
    req = Request(scope)
    resp = await gw._mcp_sse(req)
    assert resp.media_type == "text/event-stream"
    assert len(gw._sessions) == 1
    sid = next(iter(gw._sessions))
    info = gw._sessions[sid]
    await info.queue.put({"jsonrpc": "2.0", "id": 1, "result": {}})
    await info.queue.put(None)
    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
        if len(chunks) >= 2:
            try:
                await resp.body_iterator.aclose()
            except Exception:
                pass
            break
    assert any("endpoint" in c for c in chunks)
    assert len(gw._sessions) == 0


def test_csp_and_security_headers(tmp_path):
    gw = _gw(tmp_path)
    c = TestClient(gw.app)
    r = c.get("/health")
    assert r.headers.get("Content-Security-Policy") == "default-src 'self'"
    assert r.headers.get("X-Frame-Options") == "DENY"
