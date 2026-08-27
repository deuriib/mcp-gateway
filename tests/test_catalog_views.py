"""Catalog views tests - htpy without jinja."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from mcp_gway.catalog.models import CatalogCache, CatalogEntry
from mcp_gway.catalog.service import CatalogService
from mcp_gway.catalog.store import CatalogStore
from mcp_gway.dashboard.catalog.views import (
    catalog_card,
    catalog_drawer,
    catalog_grid,
    catalog_layout,
)
from mcp_gway.gateway import Gateway
from mcp_gway.registry import Registry


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    return Registry(servers_dir=tmp_path / "servers")


@pytest.fixture
def catalog_store(tmp_path: Path) -> CatalogStore:
    return CatalogStore(tmp_path / "catalog.json")


@pytest.fixture
def catalog_service(catalog_store: CatalogStore) -> CatalogService:
    return CatalogService(catalog_store)


def test_catalog_card_contains_badges_and_add():
    entry = CatalogEntry(
        id="github",
        name="github",
        title="GitHub MCP",
        description="desc",
        type="remote",
        url="https://example.com/mcp",
        tags=["git"],
    )
    html = str(catalog_card(entry))
    assert "REMOTE" in html
    assert "Add" in html
    assert "github" in html.lower()

    entry2 = CatalogEntry(
        id="pg",
        name="pg",
        title="Postgres",
        type="local",
        command=["npx", "pg"],
        tags=["db"],
    )
    html2 = str(catalog_card(entry2))
    assert "LOCAL" in html2


def test_catalog_grid_empty_states():
    html = str(catalog_grid([], q="zzz"))
    assert "No matches" in html
    html2 = str(catalog_grid([], q=None))
    assert "No catalog available offline" in html2


def test_catalog_layout_contains_search_and_grid():
    entries = [
        CatalogEntry(
            id="github",
            name="github",
            title="GitHub",
            type="remote",
            url="https://example.com/mcp",
        ),
    ]
    html = str(catalog_layout(entries, q="git"))
    assert "Catalog" in html
    assert "catalog-grid" in html
    assert "max-w-6xl mx-auto" in html
    assert 'href="/static/tailwind.css"' in html or "/static/tailwind.css" in html


def test_catalog_drawer_contains_add_and_docs():
    entry = CatalogEntry(
        id="github",
        name="github",
        title="GitHub MCP",
        description="desc",
        type="remote",
        url="https://example.com/mcp",
        tags=["git"],
        docsUrl="https://docs.example.com",
    )
    html = str(catalog_drawer(entry))
    assert "GitHub MCP" in html
    assert "https://example.com/mcp" in html
    assert "Add" in html
    assert "docs.example.com" in html
    assert "<aside" in html
    assert 'role="region"' in html


@pytest.mark.asyncio
async def test_dashboard_catalog_ssr(
    registry: Registry, catalog_store: CatalogStore, catalog_service: CatalogService
):
    catalog_store.save(
        CatalogCache(
            fetchedAt=datetime.now(UTC),
            entries=[
                CatalogEntry(
                    id="github",
                    name="github",
                    title="GitHub",
                    type="remote",
                    url="https://example.com/mcp",
                )
            ],
        )
    )
    gw = Gateway(registry, catalog_service=catalog_service)
    transport = ASGITransport(app=gw.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/dashboard/catalog")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert '<div id="catalog-grid"' in r.text or 'id="catalog-grid"' in r.text
        assert "tailwind.css" in r.text


def test_vendored_tailwind_and_no_jinja():
    css = Path("src/mcp_gway/dashboard/static/tailwind.css")
    assert css.exists()
    assert css.stat().st_size < 100 * 1024
    htmx = Path("src/mcp_gway/dashboard/static/htmx.min.js")
    assert htmx.exists()
    assert htmx.stat().st_size < 100 * 1024
    assert not Path("package.json").exists()
    views_src = Path("src/mcp_gway/dashboard/catalog/views.py").read_text()
    assert "jinja" not in views_src.lower()
