"""Wave2 — gateway CSP header."""

from pathlib import Path

import pytest
from httpx2 import ASGITransport, AsyncClient

from mcp_gway.gateway import Gateway
from mcp_gway.registry import Registry


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    return Registry(servers_dir=tmp_path / "servers")


@pytest.fixture
def gateway(registry: Registry) -> Gateway:
    return Gateway(registry)


@pytest.mark.asyncio
async def test_csp_header(gateway: Gateway) -> None:
    transport = ASGITransport(app=gateway.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
        assert r.headers.get("content-security-policy") == "default-src 'self'"
