"""Tests for transport auto-detection."""

import asyncio

import pytest

from mcp_gway.models import MCPServerConfig


def test_detect_transport_streamable_http_success(monkeypatch):
    config = MCPServerConfig(name="test", type="remote", url="https://example.com/mcp")

    async def mock_streamable_http(url, timeout=5000, **kwargs):
        return True

    async def mock_sse(url, timeout=5000, **kwargs):
        return False

    monkeypatch.setattr("mcp_gway.transport._try_streamable_http", mock_streamable_http)
    monkeypatch.setattr("mcp_gway.transport._try_sse", mock_sse)
    from mcp_gway.transport import detect_transport

    result = asyncio.run(detect_transport(config))
    assert result == "streamable-http"


def test_detect_transport_fallback_to_sse(monkeypatch):
    config = MCPServerConfig(name="test", type="remote", url="https://example.com/mcp")

    async def mock_streamable_http(url, timeout=5000, **kwargs):
        return False

    async def mock_sse(url, timeout=5000, **kwargs):
        return True

    monkeypatch.setattr("mcp_gway.transport._try_streamable_http", mock_streamable_http)
    monkeypatch.setattr("mcp_gway.transport._try_sse", mock_sse)
    from mcp_gway.transport import detect_transport

    result = asyncio.run(detect_transport(config))
    assert result == "sse"


def test_detect_transport_fallback_to_http(monkeypatch):
    config = MCPServerConfig(name="test", type="remote", url="https://example.com/mcp")

    async def mock_streamable_http(url, timeout=5000, **kwargs):
        return False

    async def mock_sse(url, timeout=5000, **kwargs):
        return False

    async def mock_http(url, timeout=5000, **kwargs):
        return True

    monkeypatch.setattr("mcp_gway.transport._try_streamable_http", mock_streamable_http)
    monkeypatch.setattr("mcp_gway.transport._try_sse", mock_sse)
    monkeypatch.setattr("mcp_gway.transport._try_http", mock_http)
    from mcp_gway.transport import detect_transport

    result = asyncio.run(detect_transport(config))
    assert result == "http"


def test_detect_transport_all_fail_raises(monkeypatch):
    config = MCPServerConfig(name="test", type="remote", url="https://example.com/mcp")

    async def mock_fail(url, timeout=5000, **kwargs):
        return False

    monkeypatch.setattr("mcp_gway.transport._try_streamable_http", mock_fail)
    monkeypatch.setattr("mcp_gway.transport._try_sse", mock_fail)
    monkeypatch.setattr("mcp_gway.transport._try_http", mock_fail)
    from mcp_gway.transport import detect_transport

    with pytest.raises(ConnectionError, match="All transports failed"):
        asyncio.run(detect_transport(config))


def test_detect_transport_respects_timeout(monkeypatch):
    config = MCPServerConfig(
        name="test", type="remote", url="https://example.com/mcp", timeout=3000
    )
    captured = []

    async def mock_streamable_http(url, timeout=None, **kwargs):
        captured.append(timeout)
        return False

    async def mock_sse(url, timeout=None, **kwargs):
        captured.append(timeout)
        return False

    async def mock_http(url, timeout=None, **kwargs):
        captured.append(timeout)
        return True

    monkeypatch.setattr("mcp_gway.transport._try_streamable_http", mock_streamable_http)
    monkeypatch.setattr("mcp_gway.transport._try_sse", mock_sse)
    monkeypatch.setattr("mcp_gway.transport._try_http", mock_http)
    from mcp_gway.transport import detect_transport

    asyncio.run(detect_transport(config))
    assert all(t == 3000 for t in captured)
