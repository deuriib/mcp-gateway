"""htpy views for dashboard - polished minimalista."""

from __future__ import annotations

import urllib.parse
from typing import Any

import htpy


def badge(state: str | bool) -> Any:
    if isinstance(state, bool):
        state = "healthy" if state else "disabled"
    normalized = str(state).lower()
    if normalized == "healthy":
        cls = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-green-100 text-green-800"
        label = "healthy"
    elif normalized == "disabled":
        cls = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600"
        label = "disabled"
    elif normalized == "unreachable":
        cls = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-800"
        label = "unreachable"
    else:
        cls = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600"
        label = normalized
    return htpy.span(class_=cls)[label]


def _badge(enabled: bool) -> Any:
    return badge(enabled)


def empty_state() -> Any:
    return htpy.div(
        class_="flex flex-col items-center justify-center py-16 text-center"
    )[
        htpy.div(class_="mb-4 rounded-full bg-slate-100 p-4")[
            htpy.span(class_="text-2xl text-slate-400", aria_hidden="true")["◯"],
        ],
        htpy.p(class_="text-sm text-slate-500 mb-2")["No servers configured"],
        htpy.p(class_="text-sm font-semibold text-slate-700 mb-1")[
            "Add your first server"
        ],
        htpy.p(class_="text-xs text-slate-400 mb-6 max-w-sm")[
            "Connect a remote MCP endpoint or a local process to get started."
        ],
        htpy.a(
            href="#add-form",
            class_="inline-flex items-center rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition-colors",
        )["Add your first server"],
    ]


def server_row(server: dict[str, Any]) -> Any:
    name = server.get("name", "")
    typ = server.get("type", "")
    tool_count = server.get("tool_count", 0)
    enabled = server.get("enabled", True)
    timeout = server.get("timeout", 5000)
    if "state" in server:
        state = str(server["state"])
    elif not enabled:
        state = "disabled"
    elif isinstance(tool_count, int) and tool_count == 0:
        state = "unreachable"
    else:
        state = "healthy"
    quoted = urllib.parse.quote(name, safe="")
    detail_url = f"/dashboard/servers/{quoted}"
    delete_url = f"/api/servers/{quoted}"
    return htpy.tr(
        class_="transition-colors duration-150 hover:bg-slate-50",
        **{"hx-get": detail_url, "hx-target": "#drawer", "hx-swap": "innerHTML"},
    )[
        htpy.td(class_="px-4 py-2 font-mono text-sm text-slate-900")[name],
        htpy.td(class_="px-4 py-2 text-sm text-slate-700")[
            typ.upper() if isinstance(typ, str) else str(typ)
        ],
        htpy.td(class_="px-4 py-2 text-sm text-center text-slate-700")[str(tool_count)],
        htpy.td(class_="px-4 py-2 text-sm text-center text-slate-600")[f"{timeout}ms"],
        htpy.td(class_="px-4 py-2 text-sm")[badge(state),],
        htpy.td(class_="px-4 py-2 text-sm")[
            htpy.button(
                class_="text-red-600 hover:text-red-800 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded px-1",
                aria_label=f"Delete {name}",
                **{
                    "hx-delete": delete_url,
                    "hx-confirm": f"Delete {name}?",
                    "hx-target": "closest tr",
                    "hx-swap": "outerHTML",
                },
            )["Delete"],
            " ",
            htpy.button(
                class_="text-blue-600 hover:text-blue-800 text-xs ml-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded px-1",
                aria_label=f"Toggle {name}",
                **{
                    "hx-patch": delete_url,
                    "hx-vals": '{"enabled": false}',
                    "hx-target": "closest tr",
                    "hx-swap": "outerHTML",
                },
            )["Toggle"],
        ],
    ]


def server_table(servers: list[dict[str, Any]]) -> Any:
    if not servers:
        return htpy.tbody(id="server-table-body")[
            htpy.tr[htpy.td(colspan="6", class_="px-4 py-8 text-center")[empty_state()]]
        ]
    rows = [server_row(s) for s in servers]
    return htpy.tbody(id="server-table-body")[rows]


def add_form() -> Any:
    return htpy.section(
        id="add-server-section",
        class_="mt-8 bg-white shadow-sm rounded-lg border border-slate-200 p-6",
    )[
        htpy.h2(class_="text-lg font-semibold text-slate-900 mb-4")["Add Server"],
        htpy.form(
            id="add-form",
            method="post",
            action="/api/servers",
            class_="space-y-4",
            **{
                "hx-post": "/api/servers",
                "hx-target": "#server-table-body",
                "hx-swap": "outerHTML",
                "hx-indicator": "#add-spinner",
            },
        )[
            htpy.div(class_="grid grid-cols-1 md:grid-cols-2 gap-4")[
                htpy.div[
                    htpy.label(
                        class_="block text-xs font-medium text-slate-700 mb-1",
                        for_="field-name",
                    )["Name *"],
                    htpy.input(
                        id="field-name",
                        name="name",
                        placeholder="my_server",
                        required=True,
                        class_="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                    ),
                ],
                htpy.div[
                    htpy.label(
                        class_="block text-xs font-medium text-slate-700 mb-1",
                        for_="field-type",
                    )["Type *"],
                    htpy.select(
                        id="field-type",
                        name="type",
                        required=True,
                        class_="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                    )[
                        htpy.option(value="remote", selected=True)["remote"],
                        htpy.option(value="local")["local"],
                    ],
                ],
            ],
            htpy.div[
                htpy.label(
                    class_="block text-xs font-medium text-slate-700 mb-1",
                    for_="field-url",
                )["URL (remote)"],
                htpy.input(
                    id="field-url",
                    name="url",
                    type="url",
                    placeholder="https://example.com/mcp",
                    class_="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                ),
            ],
            htpy.div[
                htpy.label(
                    class_="block text-xs font-medium text-slate-700 mb-1",
                    for_="field-command",
                )["Command (local)"],
                htpy.input(
                    id="field-command",
                    name="command",
                    placeholder="npx -y my-mcp",
                    class_="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                ),
            ],
            htpy.div(class_="grid grid-cols-1 md:grid-cols-2 gap-4")[
                htpy.div[
                    htpy.label(
                        class_="block text-xs font-medium text-slate-700 mb-1",
                        for_="field-headers",
                    )["Headers (JSON)"],
                    htpy.textarea(
                        id="field-headers",
                        name="headers",
                        placeholder='{"Authorization": "Bearer ***"}',
                        rows="2",
                        class_="w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                    )[[]],
                ],
                htpy.div[
                    htpy.label(
                        class_="block text-xs font-medium text-slate-700 mb-1",
                        for_="field-env",
                    )["Environment (JSON)"],
                    htpy.textarea(
                        id="field-env",
                        name="environment",
                        placeholder='{"FOO": "***"}',
                        rows="2",
                        class_="w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500",
                    )[[]],
                ],
            ],
            htpy.div(class_="flex items-center gap-3")[
                htpy.button(
                    type="submit",
                    class_="inline-flex items-center rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition-colors",
                )["Add Server"],
                htpy.span(
                    id="add-spinner",
                    class_="htmx-indicator opacity-0 transition-opacity duration-150 inline-flex items-center text-xs text-slate-500",
                )[
                    htpy.span(
                        class_="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600"
                    )[[]],
                    "Loading…",
                ],
            ],
        ],
    ]


def add_modal() -> Any:
    return add_form()


def layout(servers: list[dict[str, Any]], warning_banner: bool = False) -> Any:
    healthy = sum(
        1 for s in servers if s.get("enabled", True) and s.get("tool_count", 0) > 0
    )
    total = len(servers)
    table = htpy.table(
        class_="min-w-full divide-y divide-slate-200 border border-slate-200"
    )[
        htpy.thead(class_="bg-slate-50")[
            htpy.tr[
                htpy.th(
                    class_="px-4 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-tight"
                )["Name"],
                htpy.th(
                    class_="px-4 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-tight"
                )["Type"],
                htpy.th(
                    class_="px-4 py-2 text-center text-xs font-medium text-slate-500 uppercase tracking-tight"
                )["Tools"],
                htpy.th(
                    class_="px-4 py-2 text-center text-xs font-medium text-slate-500 uppercase tracking-tight"
                )["Timeout"],
                htpy.th(
                    class_="px-4 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-tight"
                )["Enabled"],
                htpy.th(
                    class_="px-4 py-2 text-left text-xs font-medium text-slate-500 uppercase tracking-tight"
                )["Actions"],
            ]
        ],
        server_table(servers),
    ]

    warning = (
        htpy.div(
            class_="bg-amber-100 border-l-4 border-amber-500 text-amber-800 p-3 mb-4 rounded",
            role="alert",
        )["Warning: dashboard exposed on non-loopback"]
        if warning_banner
        else htpy.fragment[[]]
    )

    health_badge = (
        badge("healthy")
        if total == 0 or healthy == total
        else badge("unreachable" if healthy == 0 else "healthy")
    )

    return htpy.html[
        htpy.head[
            htpy.meta(charset="utf-8"),
            htpy.meta(name="viewport", content="width=device-width, initial-scale=1"),
            htpy.title["MCP Gateway Dashboard"],
            htpy.link(rel="stylesheet", href="/static/tailwind.css"),
            htpy.script(src="/static/htmx.min.js")[[]],
        ],
        htpy.body(class_="bg-slate-50 text-slate-900 antialiased")[
            htpy.div(class_="max-w-6xl mx-auto px-4 py-8")[
                htpy.header(class_="flex items-center justify-between mb-6")[
                    htpy.h1(class_="text-2xl font-bold tracking-tight text-slate-900")[
                        "MCP Gateway Dashboard"
                    ],
                    htpy.div(class_="flex items-center gap-3")[
                        htpy.span(class_="text-xs text-slate-500")[
                            f"{healthy}/{total} healthy" if total else "0 servers"
                        ],
                        health_badge,
                        htpy.span(
                            id="global-spinner",
                            class_="htmx-indicator opacity-0 transition-opacity duration-150 text-xs text-slate-500",
                        )["Loading…"],
                    ],
                ],
                warning,
                htpy.main(class_="space-y-6")[
                    htpy.div(
                        class_="bg-white shadow-sm rounded-lg border border-slate-200 overflow-hidden",
                        **{
                            "hx-get": "/dashboard/servers",
                            "hx-trigger": "load",
                            "hx-target": "#server-table-body",
                            "hx-swap": "outerHTML",
                            "hx-indicator": "#global-spinner",
                        },
                    )[table],
                    add_form(),
                    htpy.div(id="drawer", class_="mt-4")[[]],
                ],
                htpy.div(
                    id="toast",
                    class_="fixed top-4 right-4 z-50 space-y-2",
                    **{"hx-swap-oob": "true"},
                )[[]],
            ]
        ],
    ]
