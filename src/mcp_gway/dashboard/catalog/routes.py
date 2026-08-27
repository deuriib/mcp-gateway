"""Catalog routes - mounted in gateway single process."""

from __future__ import annotations

from starlette.routing import Route

from mcp_gway.dashboard.catalog.api import (
    handle_catalog_drawer,
    handle_catalog_install,
    handle_catalog_list,
    handle_catalog_page,
    handle_catalog_refresh,
)


def get_catalog_routes(catalog_service, registry):  # type: ignore[no-untyped-def]
    _ = (catalog_service, registry)
    return [
        Route("/dashboard/catalog", handle_catalog_page, methods=["GET"]),
        Route("/dashboard/catalog/{id}", handle_catalog_drawer, methods=["GET"]),
        Route("/api/catalog", handle_catalog_list, methods=["GET"]),
        Route("/api/catalog/{id}/install", handle_catalog_install, methods=["POST"]),
        Route("/api/catalog/refresh", handle_catalog_refresh, methods=["POST"]),
    ]
