"""htpy views for dashboard - polished minimalista."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

import htpy


def badge(state: str | bool) -> Any:
    if isinstance(state, bool):
        state = "healthy" if state else "disabled"
    normalized = str(state).lower()
    if normalized == "healthy":
        cls = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-green-100 text-green-800 transition-colors duration-150"
        label = "healthy"
    elif normalized == "disabled":
        cls = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600 transition-colors duration-150"
        label = "disabled"
    elif normalized == "unreachable":
        cls = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-800 transition-colors duration-150"
        label = "unreachable"
    else:
        cls = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600 transition-colors duration-150"
        label = normalized
    return htpy.span(class_=cls)[label]


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
            class_="inline-flex items-center rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 hover:shadow-md active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition-all duration-150",
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
    patch_url = f"/api/servers/{quoted}"
    delete_url = f"/api/servers/{quoted}"
    toggle_val = not enabled
    toggle_label = "Disable" if enabled else "Enable"
    return htpy.tr(
        class_="transition-colors duration-150 hover:bg-slate-50 cursor-pointer group",
        **{"hx-get": detail_url, "hx-target": "#drawer", "hx-swap": "innerHTML"},
    )[
        htpy.td(class_="px-4 py-3 font-mono text-sm text-slate-900")[name],
        htpy.td(class_="px-4 py-3 text-sm text-slate-700")[
            typ.upper() if isinstance(typ, str) else str(typ)
        ],
        htpy.td(class_="px-4 py-3 text-sm text-center text-slate-700")[str(tool_count)],
        htpy.td(class_="px-4 py-3 text-sm text-center text-slate-600")[f"{timeout}ms"],
        htpy.td(class_="px-4 py-3 text-sm")[badge(state),],
        htpy.td(class_="px-4 py-3 text-sm")[
            htpy.div(class_="flex items-center gap-1.5")[
                htpy.button(
                    class_="inline-flex items-center rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-200 hover:text-slate-900 active:scale-95 transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-indigo-500",
                    aria_label=f"View {name}",
                    **{
                        "hx-get": detail_url,
                        "hx-target": "#drawer",
                        "hx-swap": "innerHTML",
                        "onclick": "event.stopPropagation()",
                    },
                )["View"],
                htpy.button(
                    class_="inline-flex items-center rounded-md bg-white border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 active:scale-95 transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-indigo-500",
                    aria_label=f"{toggle_label} {name}",
                    **{
                        "hx-patch": patch_url,
                        "hx-vals": json.dumps({"enabled": toggle_val}),
                        "hx-headers": '{"Content-Type":"application/json"}',
                        "hx-target": "#server-table-body",
                        "hx-swap": "outerHTML",
                        "onclick": "event.stopPropagation()",
                    },
                )[toggle_label],
                htpy.button(
                    class_="inline-flex items-center rounded-md bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-100 hover:text-red-800 active:scale-95 transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-red-500",
                    aria_label=f"Delete {name}",
                    **{
                        "hx-delete": delete_url,
                        "hx-confirm": f"Delete server '{name}'? This cannot be undone.",
                        "hx-target": "#server-table-body",
                        "hx-swap": "outerHTML",
                        "onclick": "event.stopPropagation()",
                    },
                )["Delete"],
            ]
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
        class_="mt-8 bg-white shadow-sm rounded-xl border border-slate-200 p-6 transition-shadow duration-150 hover:shadow-md",
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
                        class_="w-full rounded-md border border-slate-300 px-3 py-2 text-sm transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 hover:border-slate-400",
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
                        class_="w-full rounded-md border border-slate-300 px-3 py-2 text-sm transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 hover:border-slate-400",
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
                    class_="w-full rounded-md border border-slate-300 px-3 py-2 text-sm transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 hover:border-slate-400",
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
                    class_="w-full rounded-md border border-slate-300 px-3 py-2 text-sm transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 hover:border-slate-400",
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
                        class_="w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-mono transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 hover:border-slate-400",
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
                        class_="w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-mono transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 hover:border-slate-400",
                    )[[]],
                ],
            ],
            htpy.div(class_="flex items-center gap-3")[
                htpy.button(
                    type="submit",
                    class_="inline-flex items-center rounded-md bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 hover:shadow-md active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition-all duration-150",
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


def drawer_error(message: str, status: int = 404) -> Any:
    cls = (
        "bg-red-100 border border-red-200 text-red-800 p-4 rounded"
        if status >= 500
        else "bg-amber-100 border border-amber-200 text-amber-800 p-4 rounded"
    )
    return htpy.div(id="drawer", class_="fixed inset-0 z-50 flex justify-end")[
        htpy.div(
            class_="absolute inset-0 bg-slate-900/30 backdrop-blur-sm transition-opacity duration-150",
            **{
                "hx-get": "/dashboard/close",
                "hx-target": "#drawer",
                "hx-swap": "innerHTML",
            },
            aria_hidden="true",
        )[[]],
        htpy.aside(
            class_="relative w-full max-w-md bg-white shadow-xl h-full overflow-y-auto transform transition-transform duration-300 translate-x-0 p-6 border-l border-slate-200",
            role="dialog",
            aria_label="Error",
        )[
            htpy.div(class_="flex items-center justify-between mb-4")[
                htpy.h2(class_="text-lg font-semibold text-slate-900")["Error"],
                htpy.button(
                    class_="rounded-md p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-colors duration-150",
                    aria_label="Close",
                    **{
                        "hx-get": "/dashboard/close",
                        "hx-target": "#drawer",
                        "hx-swap": "innerHTML",
                    },
                )["\u00d7"],
            ],
            htpy.div(class_=cls)[message],
        ],
    ]


def server_drawer(
    server: dict[str, Any],
    pyi_content: str,
    truncated: bool,
    warning_banner: bool = False,
) -> Any:
    name = server.get("name", "")
    typ = server.get("type", "")
    timeout = server.get("timeout", 5000)
    enabled = server.get("enabled", True)
    tool_count = server.get("tool_count", 0)
    quoted = urllib.parse.quote(name, safe="")
    if not enabled:
        state = "disabled"
    elif isinstance(tool_count, int) and tool_count == 0:
        state = "unreachable"
    else:
        state = "healthy"
    toggle_val = not enabled
    toggle_label = "Disable" if enabled else "Enable"
    patch_url = f"/api/servers/{quoted}"
    refresh_url = f"/api/servers/{quoted}/refresh"
    reveal_url = f"/api/servers/{quoted}/reveal"
    delete_url = f"/api/servers/{quoted}"
    close_attrs = {
        "hx-get": "/dashboard/close",
        "hx-target": "#drawer",
        "hx-swap": "innerHTML",
    }
    url_val = server.get("url")
    command_val = server.get("command")
    if isinstance(command_val, list):
        command_str = " ".join(str(x) for x in command_val)
    elif command_val is not None:
        command_str = str(command_val)
    else:
        command_str = ""
    resolved = server.get("resolved_transport")
    cwd_val = server.get("cwd")
    headers_val = server.get("headers")
    env_val = server.get("environment")
    headers_text = (
        json.dumps(headers_val, indent=2)
        if isinstance(headers_val, dict)
        else ("***" if headers_val else "")
    )
    env_text = (
        json.dumps(env_val, indent=2)
        if isinstance(env_val, dict)
        else ("***" if env_val else "")
    )
    return htpy.div(id="drawer", class_="fixed inset-0 z-50 flex justify-end")[
        htpy.div(
            class_="absolute inset-0 bg-slate-900/30 backdrop-blur-sm transition-opacity duration-150",
            **close_attrs,
            aria_hidden="true",
        )[[]],
        htpy.aside(
            class_="relative w-full max-w-md bg-white shadow-xl h-full overflow-y-auto transform transition-transform duration-300 translate-x-0 border-l border-slate-200",
            role="dialog",
            aria_label=f"Details for {name}",
        )[
            htpy.div(
                class_="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-white sticky top-0 z-10"
            )[
                htpy.h2(class_="text-lg font-semibold text-slate-900")[name],
                htpy.button(
                    class_="rounded-md p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-colors duration-150",
                    aria_label="Close",
                    **close_attrs,
                )["\u00d7"],
            ],
            htpy.div(class_="px-6 py-4 space-y-4")[
                htpy.div(class_="flex items-center gap-2")[badge(state)],
                htpy.dl(class_="space-y-3 text-sm")[
                    htpy.div(class_="flex justify-between")[
                        htpy.dt(class_="text-slate-500")["Type"],
                        htpy.dd(class_="font-medium text-slate-900")[
                            typ.upper() if isinstance(typ, str) else str(typ)
                        ],
                    ],
                    htpy.div(class_="flex justify-between")[
                        htpy.dt(class_="text-slate-500")["Timeout"],
                        htpy.dd(class_="font-mono text-slate-900")[f"{timeout}ms"],
                    ],
                    htpy.div(class_="flex justify-between")[
                        htpy.dt(class_="text-slate-500")["Tools"],
                        htpy.dd(class_="font-mono text-slate-900")[str(tool_count)],
                    ],
                    htpy.div(class_="flex justify-between")[
                        htpy.dt(class_="text-slate-500")["Enabled"],
                        htpy.dd(class_="font-mono text-slate-900")[
                            str(enabled).lower()
                        ],
                    ],
                    (
                        htpy.div(class_="flex flex-col gap-1")[
                            htpy.dt(class_="text-slate-500")["URL"],
                            htpy.dd(class_="font-mono text-slate-900 break-all")[
                                str(url_val)
                            ],
                        ]
                        if url_val
                        else htpy.fragment[[]]
                    ),
                    (
                        htpy.div(class_="flex flex-col gap-1")[
                            htpy.dt(class_="text-slate-500")["Command"],
                            htpy.dd(class_="font-mono text-slate-900 break-all")[
                                command_str
                            ],
                        ]
                        if command_str
                        else htpy.fragment[[]]
                    ),
                    (
                        htpy.div(class_="flex flex-col gap-1")[
                            htpy.dt(class_="text-slate-500")["Resolved Transport"],
                            htpy.dd(class_="font-mono text-slate-900")[str(resolved)],
                        ]
                        if resolved
                        else htpy.fragment[[]]
                    ),
                    (
                        htpy.div(class_="flex flex-col gap-1")[
                            htpy.dt(class_="text-slate-500")["CWD"],
                            htpy.dd(class_="font-mono text-slate-900 break-all")[
                                str(cwd_val)
                            ],
                        ]
                        if cwd_val
                        else htpy.fragment[[]]
                    ),
                    (
                        htpy.div(class_="flex flex-col gap-1")[
                            htpy.dt(class_="text-slate-500")["Headers"],
                            htpy.dd(
                                class_="font-mono text-xs bg-slate-50 p-2 rounded border border-slate-200 overflow-auto"
                            )[headers_text],
                        ]
                        if headers_val is not None
                        else htpy.fragment[[]]
                    ),
                    (
                        htpy.div(class_="flex flex-col gap-1")[
                            htpy.dt(class_="text-slate-500")["Environment"],
                            htpy.dd(
                                class_="font-mono text-xs bg-slate-50 p-2 rounded border border-slate-200 overflow-auto"
                            )[env_text],
                        ]
                        if env_val is not None
                        else htpy.fragment[[]]
                    ),
                ],
                htpy.div(class_="flex flex-wrap gap-2 pt-2")[
                    htpy.button(
                        class_="inline-flex items-center rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 hover:shadow-sm active:scale-95 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all duration-150",
                        **{
                            "hx-patch": patch_url,
                            "hx-vals": json.dumps({"enabled": toggle_val}),
                            "hx-headers": '{"Content-Type":"application/json"}',
                            "hx-target": "#drawer",
                            "hx-swap": "innerHTML",
                        },
                    )[toggle_label],
                    htpy.button(
                        class_="inline-flex items-center rounded-md bg-white border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-400 active:scale-95 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all duration-150",
                        **{
                            "hx-post": refresh_url,
                            "hx-target": "#toast",
                            "hx-swap": "innerHTML",
                        },
                    )["Refresh"],
                    htpy.button(
                        class_="inline-flex items-center rounded-md bg-white border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-400 active:scale-95 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed",
                        **(
                            {
                                "hx-post": reveal_url,
                                "hx-target": "#toast",
                                "hx-swap": "innerHTML",
                                "disabled": "disabled",
                                "title": "Reveal disabled on non-loopback",
                            }
                            if warning_banner
                            else {
                                "hx-post": reveal_url,
                                "hx-target": "#toast",
                                "hx-swap": "innerHTML",
                            }
                        ),
                    )["Reveal"],
                    htpy.button(
                        class_="inline-flex items-center rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 hover:shadow-sm active:scale-95 focus:outline-none focus:ring-2 focus:ring-red-500 transition-all duration-150",
                        **{
                            "hx-delete": delete_url,
                            "hx-confirm": f"Delete server '{name}'? This cannot be undone.",
                            "hx-target": "#server-table-body",
                            "hx-swap": "outerHTML",
                        },
                    )["Delete"],
                ],
                htpy.div(class_="pt-4 border-t border-slate-200")[
                    htpy.h3(class_="text-sm font-semibold text-slate-900 mb-2")[
                        f"Tool signatures ({tool_count})"
                    ],
                    htpy.pre(
                        class_="max-h-64 overflow-auto bg-slate-50 p-3 text-xs font-mono border border-slate-200 rounded"
                    )[pyi_content or "(no tools)"],
                    (
                        htpy.p(class_="text-xs text-amber-600 mt-1")[
                            "truncated (50KB limit)"
                        ]
                        if truncated
                        else htpy.fragment[[]]
                    ),
                ],
            ],
        ],
    ]


def _footer() -> Any:
    return htpy.footer(
        class_="mt-auto border-t border-slate-200 bg-white/80 backdrop-blur py-4 text-center text-xs text-slate-400"
    )[
        htpy.span[
            "MCP Gateway \u2022 v0.7.0 \u2022 local-first \u2014 crafted with dedication"
        ],
    ]


def layout(servers: list[dict[str, Any]], warning_banner: bool = False) -> Any:
    healthy = sum(
        1 for s in servers if s.get("enabled", True) and s.get("tool_count", 0) > 0
    )
    total = len(servers)
    table = htpy.table(class_="min-w-full divide-y divide-slate-200")[
        htpy.thead(class_="bg-slate-50 sticky top-0 z-10")[
            htpy.tr[
                htpy.th(
                    class_="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider"
                )["Name"],
                htpy.th(
                    class_="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider"
                )["Type"],
                htpy.th(
                    class_="px-4 py-3 text-center text-xs font-medium text-slate-500 uppercase tracking-wider"
                )["Tools"],
                htpy.th(
                    class_="px-4 py-3 text-center text-xs font-medium text-slate-500 uppercase tracking-wider"
                )["Timeout"],
                htpy.th(
                    class_="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider"
                )["Enabled"],
                htpy.th(
                    class_="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider"
                )["Actions"],
            ]
        ],
        server_table(servers),
    ]

    warning = (
        htpy.div(
            class_="bg-amber-100 border-l-4 border-amber-500 text-amber-800 p-3 mb-4 rounded transition-colors duration-150",
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
        htpy.body(
            class_="bg-slate-50 text-slate-900 antialiased min-h-screen flex flex-col overflow-y-auto"
        )[
            htpy.div(
                class_="max-w-6xl mx-auto px-4 py-8 pb-12 flex-1 flex flex-col min-h-0 w-full gap-6"
            )[
                htpy.header(class_="flex items-center justify-between mb-2")[
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
                htpy.main(
                    class_="flex-1 flex flex-col space-y-6 min-h-0 gap-6 pb-6 overflow-visible"
                )[
                    htpy.div(
                        class_="bg-white shadow-sm rounded-xl border border-slate-200 overflow-hidden overflow-x-auto transition-shadow duration-150 hover:shadow-md",
                        **{
                            "hx-get": "/dashboard/servers",
                            "hx-trigger": "load",
                            "hx-target": "#server-table-body",
                            "hx-swap": "outerHTML",
                            "hx-indicator": "#global-spinner",
                        },
                    )[table],
                    add_form(),
                    htpy.div(
                        id="drawer",
                        class_="flex-1 min-h-[120px] bg-white border-t border-slate-200 rounded-xl p-4 overflow-auto mt-2",
                    )[[]],
                ],
                htpy.div(
                    id="toast",
                    class_="fixed top-4 right-4 z-50 space-y-2",
                    **{"hx-swap-oob": "true"},
                )[[]],
            ],
            _footer(),
        ],
    ]
