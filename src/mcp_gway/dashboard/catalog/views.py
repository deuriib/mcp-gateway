"""htpy views for catalog bounded context - Swiss minimalista infra."""

from __future__ import annotations

from typing import Any

import htpy
from markupsafe import Markup

from mcp_gway.catalog.models import CatalogEntry

_STYLE_HIDDEN = "hidden"
_DIALOG_ID = "server-dialog"
_DIALOG_TARGET = f"#{_DIALOG_ID}"
_CLOSE_ATTRS: dict[str, str] = {
    "hx-get": "/dashboard/close",
    "hx-target": _DIALOG_TARGET,
    "hx-swap": "innerHTML",
}


def _icon(name: str, cls: str = "h-4 w-4", aria_hidden: str = "true") -> Any:
    icons: dict[str, str] = {
        "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
        "layers": '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>',
        "alert": '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
        "plus": '<path d="M12 5v14M5 12h14"/>',
        "plug": '<path d="M12 2a3 3 0 0 0-3 3v3H7a2 2 0 0 0-2 2v4a2 2 0 0 0 2 2h2v3a3 3 0 0 0 6 0v-3h2a2 2 0 0 0 2-2v-4a2 2 0 0 0-2-2h-2V5a3 3 0 0 0-3-3z"/>',
        "external": '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
    }
    inner = icons.get(name, icons["layers"])
    return htpy.svg(
        class_=cls,
        viewBox="0 0 24 24",
        fill="none",
        stroke="currentColor",
        stroke_width="1.75",
        stroke_linecap="round",
        stroke_linejoin="round",
        aria_hidden=aria_hidden,
    )[Markup(inner)]


def _badge_type(t: str) -> Any:
    label = t.upper()
    chip = (
        "bg-sky-50 text-sky-700 border-sky-200"
        if label == "REMOTE"
        else "bg-zinc-50 text-zinc-700 border-zinc-200"
    )
    return htpy.span(
        class_=f"inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium tracking-wide {chip}"
    )[label]


def catalog_card(entry: CatalogEntry | dict[str, Any]) -> Any:
    if isinstance(entry, dict):
        eid = entry.get("id", entry.get("name", ""))
        title = entry.get("title", eid)
        desc = entry.get("description", "")
        typ = entry.get("type", "remote")
        tags = entry.get("tags", [])
        truncated = entry.get("truncated", False)
    else:
        eid = entry.id
        title = entry.title or entry.name
        desc = entry.description
        typ = entry.type
        tags = entry.tags
        truncated = entry.truncated
    desc_text = desc[:220]
    if truncated and len(desc) >= 50000 or truncated:
        desc_text += " ... truncated"
    install_url = f"/api/catalog/{eid}/install"
    detail_url = f"/dashboard/catalog/{eid}"
    return htpy.div(
        class_="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm hover:shadow-md hover:border-slate-300 transition-all duration-200 flex flex-col gap-3",
        role="article",
        aria_label=title,
    )[
        htpy.div(class_="flex items-start justify-between gap-3")[
            htpy.h3(
                class_="font-semibold text-sm tracking-tight text-slate-900 leading-snug"
            )[title],
            _badge_type(typ),
        ],
        htpy.p(
            class_="text-xs leading-relaxed text-slate-500 line-clamp-3 min-h-[2.6rem]"
        )[desc_text or "No description"],
        htpy.div(class_="flex flex-wrap gap-1.5")[
            *[
                htpy.span(
                    class_="inline-flex items-center rounded-full bg-slate-100 border border-slate-200 px-2.5 py-0.5 text-xs font-medium text-slate-600"
                )[t]
                for t in tags[:6]
            ]
            if tags
            else [htpy.span(class_="text-xs text-slate-400")["no tags"]]
        ],
        htpy.div(
            class_="flex items-center gap-2 mt-auto pt-2 border-t border-slate-50"
        )[
            htpy.a(
                href=detail_url,
                class_="inline-flex items-center justify-center rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 active:scale-95 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-1 transition-all duration-200 min-h-8",
                aria_label=f"View {title}",
                **{
                    "hx-get": detail_url,
                    "hx-target": _DIALOG_TARGET,
                    "hx-swap": "innerHTML",
                    "hx-indicator": "#global-spinner",
                },
            )["View"],
            htpy.button(
                class_="inline-flex items-center cursor-pointer justify-center rounded-full bg-slate-900 px-3.5 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-black hover:shadow active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-1 transition-all duration-200 min-h-8 gap-1.5",
                aria_label=f"Add {title}",
                **{
                    "hx-post": install_url,
                    "hx-target": "#server-table-body",
                    "hx-swap": "outerHTML",
                    "hx-indicator": "#global-spinner",
                },
            )[_icon("plus", cls="h-3 w-3"), "Add"],
        ],
    ]


def catalog_grid(
    entries: list[CatalogEntry | dict[str, Any]],
    q: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Any:
    if not entries:
        return catalog_empty(q, stale=bool(meta and meta.get("stale")))
    cards = [catalog_card(e) for e in entries]
    meta_total = meta.get("total") if isinstance(meta, dict) else len(entries)
    stale = bool(meta and meta.get("stale"))
    header = htpy.div(class_="flex items-center justify-between mb-3")[
        htpy.p(class_="text-xs text-slate-500")[
            f"{meta_total} result{'s' if meta_total != 1 else ''}"
            + (f' for "{q}"' if q else "")
        ],
        htpy.span(
            class_="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium border "
            + (
                "bg-amber-50 border-amber-200 text-amber-700"
                if stale
                else "bg-emerald-50 border-emerald-200 text-emerald-700"
            )
        )["stale" if stale else "live"]
        if meta is not None
        else htpy.fragment[[]],
    ]
    return htpy.div(id="catalog-grid", class_="flex flex-col gap-3")[
        header,
        htpy.div(
            class_="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
        )[cards],
    ]


def catalog_empty(q: str | None, stale: bool = False) -> Any:
    msg = "No matches" if q else "No catalog available offline"
    sub = (
        f'No results for "{q}" - try another term'
        if q
        else "Remote catalog unreachable and no cached data. Check connection or try Refresh."
    )
    badge = (
        htpy.span(
            class_="inline-flex items-center rounded-full bg-amber-50 border border-amber-200 text-amber-700 px-2.5 py-0.5 text-xs font-medium"
        )["stale"]
        if stale
        else htpy.fragment[[]]
    )
    return htpy.div(
        id="catalog-grid",
        class_="flex flex-col items-center justify-center py-16 text-center gap-3",
        role="status",
        aria_live="polite",
    )[
        htpy.div(
            class_="mb-2 rounded-2xl bg-gradient-to-b from-slate-50 to-white border border-slate-200 p-5 shadow-sm"
        )[
            htpy.span(
                class_="flex items-center justify-center h-10 w-10 rounded-xl bg-white border border-slate-200 text-slate-400 shadow-sm mx-auto"
            )[_icon("search", cls="h-5 w-5"),],
        ],
        htpy.div(class_="flex items-center gap-2")[
            htpy.p(class_="text-sm font-semibold tracking-tight text-slate-900")[msg],
            badge,
        ],
        htpy.p(class_="text-sm text-slate-500 max-w-sm leading-relaxed")[sub],
        htpy.p(class_="text-xs text-slate-400")[
            "Tip: catalog is cached locally - stale data shown with amber badge"
        ]
        if stale
        else htpy.fragment[[]],
    ]


def catalog_drawer(
    entry: CatalogEntry | dict[str, Any], warning_banner: bool = False
) -> Any:
    if isinstance(entry, dict):
        eid = entry.get("id", "")
        title = entry.get("title", eid)
        desc = entry.get("description", "")
        typ = entry.get("type", "")
        url = entry.get("url")
        command = entry.get("command")
        tags = entry.get("tags", [])
        docs = entry.get("docsUrl") or entry.get("docs_url")
        truncated = entry.get("truncated", False)
    else:
        eid = entry.id
        title = entry.title or entry.name
        desc = entry.description
        typ = entry.type
        url = entry.url
        command = entry.command
        tags = entry.tags
        docs = entry.docsUrl
        truncated = entry.truncated
    cmd_str = (
        " ".join(command)
        if isinstance(command, list)
        else str(command)
        if command
        else ""
    )
    banner = (
        htpy.div(
            class_="mx-6 mt-4 flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-800 px-3 py-2.5 text-xs rounded-xl",
            role="alert",
        )[_icon("alert", cls="h-4 w-4"), "dashboard exposed - local only on 127.0.0.1"]
        if warning_banner
        else htpy.fragment[[]]
    )
    desc_html = desc + (" ... truncated" if truncated else "")
    install_url = f"/api/catalog/{eid}/install"
    detail_label = url or cmd_str or ""
    return htpy.aside(
        class_="relative w-full max-w-md bg-white shadow-2xl h-full max-h-[100dvh] overflow-y-auto overscroll-y-contain ml-auto border-l border-slate-200 flex flex-col focus:outline-none",
        role="region",
        aria_label="Catalog detail",
        tabindex="-1",
    )[
        htpy.div(
            class_="flex items-start justify-between gap-4 px-6 py-5 border-b border-slate-100 bg-white sticky top-0 z-10"
        )[
            htpy.div(class_="flex items-center gap-3 min-w-0")[
                htpy.span(
                    class_="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 text-white shadow-sm shrink-0"
                )[_icon("layers", cls="h-4 w-4"),],
                htpy.div(class_="min-w-0 flex-1")[
                    htpy.h2(
                        class_="text-base font-semibold tracking-tight text-slate-900 truncate"
                    )[title],
                    htpy.p(class_="text-xs text-slate-500")[f"{typ} - {eid}"],
                ],
            ],
            htpy.button(
                class_="flex h-9 w-9 shrink-0 items-center cursor-pointer justify-center rounded-full bg-slate-100 text-slate-500 hover:bg-slate-900 hover:text-white focus:outline-none focus:ring-2 focus:ring-slate-900 transition-colors duration-200",
                aria_label="Close",
                title="Close drawer",
                **_CLOSE_ATTRS,
            )["x"],
        ],
        banner,
        htpy.div(class_="p-6 flex flex-col gap-5 overflow-y-auto")[
            htpy.div(class_="rounded-xl border border-slate-200 bg-slate-50/50 p-4")[
                htpy.p(class_="text-sm leading-relaxed text-slate-700")[
                    desc_html or "No description"
                ],
                htpy.p(class_="text-xs text-amber-700 mt-2 flex items-center gap-1")[
                    _icon("alert", cls="h-3 w-3"),
                    "... truncated - see docs for full description",
                ]
                if truncated
                else htpy.fragment[[]],
            ],
            htpy.dl(
                class_="rounded-xl border border-slate-200 bg-white divide-y divide-slate-100 overflow-hidden"
            )[
                htpy.div(class_="flex items-center justify-between gap-4 py-3 px-4")[
                    htpy.dt(class_="text-xs font-medium tracking-wide text-slate-500")[
                        "Type"
                    ],
                    htpy.dd(class_="text-xs font-medium")[_badge_type(typ)],
                ],
                htpy.div(class_="px-4 py-3")[
                    htpy.dt(
                        class_="text-xs font-medium tracking-wide text-slate-500 mb-1.5"
                    )["URL" if url else "Command"],
                    htpy.dd(
                        class_="font-mono text-xs text-slate-900 break-all bg-slate-50 border border-slate-200 rounded-lg px-3 py-2"
                    )[detail_label or "-"],
                ],
                htpy.div(class_="px-4 py-3")[
                    htpy.dt(
                        class_="text-xs font-medium tracking-wide text-slate-500 mb-1.5"
                    )["Tags"],
                    htpy.dd(class_="flex flex-wrap gap-1.5")[
                        *[
                            htpy.span(
                                class_="inline-flex items-center rounded-full bg-slate-100 border border-slate-200 px-2.5 py-0.5 text-xs font-medium text-slate-600"
                            )[t]
                            for t in tags
                        ]
                        if tags
                        else [htpy.span(class_="text-xs text-slate-400")["no tags"]]
                    ],
                ],
            ],
            htpy.a(
                href=docs,
                target="_blank",
                rel="noopener noreferrer",
                class_="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-700 underline underline-offset-4",
            )[_icon("external", cls="h-3 w-3"), docs]
            if docs
            else htpy.fragment[[]],
            htpy.div(class_="flex gap-2 pt-2")[
                htpy.button(
                    class_="inline-flex flex-1 items-center cursor-pointer justify-center gap-1.5 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-black hover:shadow-md active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2 transition-all duration-200 min-h-11",
                    aria_label=f"Add {title} to gateway",
                    **{
                        "hx-post": install_url,
                        "hx-target": "#server-table-body",
                        "hx-swap": "outerHTML",
                        "hx-indicator": "#global-spinner",
                    },
                )[_icon("plus", cls="h-4 w-4"), "Add"],
                htpy.a(
                    href=f"/dashboard/catalog/{eid}",
                    class_="inline-flex items-center justify-center rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 active:scale-95 focus:outline-none focus:ring-2 focus:ring-slate-900 transition-all duration-200 min-h-11",
                )["Permalink"],
            ],
            htpy.p(class_="text-xs text-slate-400 leading-relaxed")[
                "Install reuses Registry.add + discovery - no catalog write until Add. Duplicates return 409."
            ],
        ],
    ]


def drawer_error(message: str, status: int = 404) -> Any:
    cls = (
        "bg-red-50 border border-red-200 text-red-800 p-4 rounded-xl"
        if status >= 500
        else "bg-amber-50 border border-amber-200 text-amber-800 p-4 rounded-xl"
    )
    return htpy.aside(
        class_="relative w-full max-w-md bg-white shadow-2xl h-full max-h-[100dvh] overflow-y-auto overscroll-y-contain ml-auto transform transition-all duration-300 translate-x-0 border-l border-slate-200 flex flex-col focus:outline-none",
        role="region",
        aria_label="Error",
        tabindex="-1",
    )[
        htpy.div(
            class_="flex items-center justify-between px-6 py-4 border-b border-slate-100 sticky top-0 bg-white z-10"
        )[
            htpy.h2(class_="text-sm font-semibold tracking-tight text-slate-900")[
                "Error"
            ],
            htpy.button(
                class_="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-500 hover:bg-slate-900 hover:text-white focus:outline-none focus:ring-2 focus:ring-slate-900 transition-colors duration-200",
                aria_label="Close",
                title="Close drawer",
                **_CLOSE_ATTRS,
            )["x"],
        ],
        htpy.div(class_="p-6")[htpy.div(class_=cls, role="alert")[message]],
    ]


def catalog_layout(
    entries: list[CatalogEntry | dict[str, Any]],
    q: str | None = None,
    meta: dict[str, Any] | None = None,
    warning_banner: bool = False,
) -> Any:
    banner = (
        htpy.div(
            class_="max-w-6xl mx-auto mb-4 flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 text-sm rounded-xl shadow-sm",
            role="alert",
        )[
            _icon("alert", cls="h-4 w-4 shrink-0"),
            "dashboard exposed - serving on non-loopback (set MCP_GWAY_ALLOW_REMOTE=1 to allow)",
        ]
        if warning_banner
        else htpy.fragment[[]]
    )
    search_val = q or ""
    grid = catalog_grid(entries, q, meta)
    stale = bool(meta and meta.get("stale"))
    toast_init = (
        htpy.div(
            class_="bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-xl text-sm"
        )["Catalog offline - showing cached"]
        if stale
        else htpy.fragment[[]]
    )
    return htpy.html(lang="en")[
        htpy.head[
            htpy.meta(charset="utf-8"),
            htpy.meta(name="viewport", content="width=device-width, initial-scale=1"),
            htpy.title["Catalog - MCP Gateway"],
            htpy.link(rel="stylesheet", href="/static/tailwind.css"),
            htpy.script(src="/static/htmx.min.js"),
        ],
        htpy.body(class_="bg-slate-50 min-h-screen antialiased")[
            htpy.div(id="global-spinner", class_="htmx-indicator")[[]],
            htpy.header(class_="max-w-6xl mx-auto px-4 pt-6")[
                htpy.div(
                    class_="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6"
                )[
                    htpy.div(class_="flex items-center gap-3")[
                        htpy.span(
                            class_="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-white shadow-sm"
                        )[_icon("layers", cls="h-5 w-5"),],
                        htpy.div[
                            htpy.h1(
                                class_="text-xl font-semibold tracking-tight text-slate-900 leading-none"
                            )["Catalog"],
                            htpy.p(class_="text-xs text-slate-500 mt-1")[
                                "Curated Bifrost registry - 1-click Add, stale-while-revalidate"
                            ],
                        ],
                    ],
                    htpy.a(
                        href="/dashboard",
                        class_="inline-flex items-center justify-center rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 active:scale-95 focus:outline-none focus:ring-2 focus:ring-slate-900 transition-all duration-200",
                    )["<- Back to Dashboard"],
                ],
                banner,
            ],
            htpy.main(class_="max-w-6xl mx-auto px-4 pb-10")[
                htpy.div(
                    class_="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 sm:p-5 mb-6"
                )[
                    htpy.label(
                        for_="catalog-search",
                        class_="block text-xs font-medium tracking-wide text-slate-700 mb-1.5",
                    )["Search catalog"],
                    htpy.div(class_="relative")[
                        htpy.span(
                            class_="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400"
                        )[_icon("search", cls="h-4 w-4"),],
                        htpy.input(
                            id="catalog-search",
                            type="search",
                            name="q",
                            value=search_val,
                            placeholder="Search by name, title or tag... (e.g. git, postgres)",
                            autocomplete="off",
                            aria_label="Search catalog",
                            class_="w-full rounded-xl border border-slate-200 bg-slate-50/50 pl-10 pr-3 py-2.5 text-sm transition-all duration-200 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900 hover:border-slate-300 hover:bg-white min-h-11",
                            **{
                                "hx-get": "/dashboard/catalog",
                                "hx-target": "#catalog-grid",
                                "hx-swap": "outerHTML",
                                "hx-trigger": "keyup changed delay:300ms",
                                "hx-indicator": "#global-spinner",
                            },
                        ),
                    ],
                    htpy.p(class_="mt-1.5 text-xs text-slate-400")[
                        "Filters O(n) substring, case-insensitive - no page reload"
                    ],
                ],
                grid,
            ],
            htpy.div(
                id="server-dialog",
                class_="fixed inset-0 z-40 hidden has-[aside]:block has-[aside]:bg-black/20",
                aria_live="polite",
            )[[]],
            htpy.div(
                id="toast",
                class_="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm",
                aria_live="polite",
                aria_atomic="true",
            )[toast_init],
            htpy.div(id="catalog-meta", class_="hidden", aria_hidden="true")[
                str(meta) if meta else ""
            ]
            if False
            else htpy.fragment[[]],
        ],
    ]
