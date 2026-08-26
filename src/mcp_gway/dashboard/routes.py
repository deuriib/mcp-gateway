"""Starlette routes for dashboard."""

from __future__ import annotations

from pathlib import Path

from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from mcp_gway.dashboard.api import (
    handle_api_health,
    handle_create,
    handle_dashboard,
    handle_dashboard_close,
    handle_dashboard_server_detail,
    handle_dashboard_servers,
    handle_delete,
    handle_get,
    handle_list,
    handle_oauth_start,
    handle_oauth_status,
    handle_patch,
    handle_refresh,
    handle_refresh_all,
    handle_reveal,
)
from mcp_gway.registry import Registry


def get_dashboard_routes(registry: Registry) -> list[Route | Mount]:
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    return [
        Route("/", handle_dashboard, methods=["GET"]),
        Route("/dashboard", handle_dashboard, methods=["GET"]),
        Route("/dashboard/servers", handle_dashboard_servers, methods=["GET"]),
        Route(
            "/dashboard/servers/{name}", handle_dashboard_server_detail, methods=["GET"]
        ),
        Route("/dashboard/close", handle_dashboard_close, methods=["GET"]),
        Route("/api/health", handle_api_health, methods=["GET"]),
        Route("/api/servers", handle_list, methods=["GET"]),
        Route("/api/servers/{name}", handle_get, methods=["GET"]),
        Route("/api/servers", handle_create, methods=["POST"]),
        Route("/api/servers/refresh", handle_refresh_all, methods=["POST"]),
        Route("/api/servers/{name}", handle_patch, methods=["PATCH"]),
        Route("/api/servers/{name}", handle_delete, methods=["DELETE"]),
        Route("/api/servers/{name}/refresh", handle_refresh, methods=["POST"]),
        Route("/api/servers/{name}/reveal", handle_reveal, methods=["POST"]),
        Route("/api/servers/{name}/oauth/start", handle_oauth_start, methods=["POST"]),
        Route("/api/servers/{name}/oauth/status", handle_oauth_status, methods=["GET"]),
        Mount(
            "/static",
            app=StaticFiles(directory=str(static_dir)),
            name="dashboard_static",
        ),
    ]
