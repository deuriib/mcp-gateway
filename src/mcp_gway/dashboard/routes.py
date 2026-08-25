"""Starlette routes for dashboard."""

from __future__ import annotations

from pathlib import Path

from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from mcp_gway.dashboard.api import (
    handle_create,
    handle_dashboard,
    handle_dashboard_servers,
    handle_get,
    handle_list,
)
from mcp_gway.registry import Registry


def get_dashboard_routes(registry: Registry) -> list[Route | Mount]:
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    return [
        Route("/dashboard", handle_dashboard, methods=["GET"]),
        Route("/dashboard/servers", handle_dashboard_servers, methods=["GET"]),
        Route("/api/servers", handle_list, methods=["GET"]),
        Route("/api/servers/{name}", handle_get, methods=["GET"]),
        Route("/api/servers", handle_create, methods=["POST"]),
        Mount(
            "/static",
            app=StaticFiles(directory=str(static_dir)),
            name="dashboard_static",
        ),
    ]
