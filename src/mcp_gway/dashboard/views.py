"""htpy views for dashboard - polished minimalista Swiss infra."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

import htpy
from markupsafe import Markup

_DIALOG_ID = "server-dialog"
_DIALOG_TARGET = f"#{_DIALOG_ID}"
_CLOSE_ATTRS: dict[str, str] = {
    "hx-get": "/dashboard/close",
    "hx-target": _DIALOG_TARGET,
    "hx-swap": "innerHTML",
}
_BASE_BADGE = (
    "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium "
    "transition-colors duration-200"
)
_BADGE_COLORS: dict[str, str] = {
    "healthy": "bg-emerald-50 border-emerald-200 text-emerald-700",
    "disabled": "bg-slate-100 border-slate-200 text-slate-600",
    "unreachable": "bg-amber-50 border-amber-200 text-amber-700",
}
_DOT_COLORS: dict[str, str] = {
    "healthy": "bg-emerald-500",
    "disabled": "bg-slate-400",
    "unreachable": "bg-amber-500",
}


def _icon(name: str, cls: str = "h-4 w-4", aria_hidden: str = "true") -> Any:
    icons: dict[str, str] = {
        "server": '<path d="M5 12H3a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1v-4a1 1 0 0 0-1-1zM19 8H3a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1zM5 8H3a1 1 0 0 0-1 1v0a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1v0a1 1 0 0 0-1-1z"/>',
        "plug": '<path d="M12 2a3 3 0 0 0-3 3v3H7a2 2 0 0 0-2 2v4a2 2 0 0 0 2 2h2v3a3 3 0 0 0 6 0v-3h2a2 2 0 0 0 2-2v-4a2 2 0 0 0-2-2h-2V5a3 3 0 0 0-3-3z"/>',
        "plus": '<path d="M12 5v14M5 12h14"/>',
        "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
        "layers": '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>',
        "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
        "alert": '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
        "zap": '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
    }
    inner = icons.get(name, icons["server"])
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


def badge(state: str | bool) -> Any:
    if isinstance(state, bool):
        state = "healthy" if state else "disabled"
    normalized = str(state).lower()
    if normalized == "healthy":
        color = _BADGE_COLORS["healthy"]
        dot = _DOT_COLORS["healthy"]
        label = "healthy"
    elif normalized == "disabled":
        color = _BADGE_COLORS["disabled"]
        dot = _DOT_COLORS["disabled"]
        label = "disabled"
    elif normalized == "unreachable":
        color = _BADGE_COLORS["unreachable"]
        dot = _DOT_COLORS["unreachable"]
        label = "unreachable"
    else:
        color = _BADGE_COLORS["disabled"]
        dot = _DOT_COLORS["disabled"]
        label = normalized
    cls = f"{_BASE_BADGE} {color}"
    return htpy.span(class_=cls, role="status", aria_label=f"status {label}")[
        htpy.span(
            class_=f"h-1.5 w-1.5 rounded-full {dot} animate-pulse", aria_hidden="true"
        )[[]],
        label,
    ]


def empty_state() -> Any:
    return htpy.div(
        class_="flex flex-col items-center justify-center py-14 text-center animate-in fade-in duration-300"
    )[
        htpy.div(
            class_="mb-5 rounded-2xl bg-gradient-to-b from-slate-50 to-white border border-slate-200 p-5 shadow-sm"
        )[
            htpy.span(
                class_="flex items-center justify-center h-10 w-10 rounded-xl bg-white border border-slate-200 text-slate-400 shadow-sm"
            )[_icon("plug", cls="h-5 w-5"),],
        ],
        htpy.p(class_="text-sm font-semibold tracking-tight text-slate-900 mb-1")[
            "No servers configured"
        ],
        htpy.p(class_="text-sm text-slate-500 mb-1 max-w-sm leading-relaxed")[
            "Connect a remote MCP endpoint or a local process to get started. Takes 15 seconds."
        ],
        htpy.p(class_="text-xs text-slate-400 mb-6")[
            "Tip: try remote first — you can switch to local later"
        ],
        htpy.a(
            href="#add-form",
            class_="inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-black hover:shadow-md active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2 transition-all duration-200 min-h-11",
        )[
            _icon("plus", cls="h-4 w-4"),
            "Add your first server",
        ],
    ]


def server_row(server: dict[str, Any], idx: int = 0) -> Any:
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
    type_label = typ.upper() if isinstance(typ, str) else str(typ)
    type_chip = (
        "bg-sky-50 text-sky-700 border-sky-200"
        if type_label == "REMOTE"
        else "bg-zinc-50 text-zinc-700 border-zinc-200"
    )
    return htpy.tr(
        class_="group transition-all duration-200 hover:bg-slate-50/80 cursor-pointer border-b border-slate-100 last:border-0 animate-row",
        style=f"animation-delay:{idx * 28}ms",
        **{
            "hx-get": detail_url,
            "hx-target": _DIALOG_TARGET,
            "hx-swap": "innerHTML",
            "hx-indicator": "#global-spinner",
            "data-name": name.lower(),
        },
    )[
        htpy.td(class_="px-4 py-3.5")[
            htpy.div(class_="flex items-center gap-3")[
                htpy.span(
                    class_="hidden sm:flex h-8 w-8 items-center justify-center rounded-lg bg-white border border-slate-200 text-slate-500 shadow-sm group-hover:border-slate-300 group-hover:shadow transition-all duration-200"
                )[_icon("server", cls="h-4 w-4"),],
                htpy.div(class_="flex flex-col")[
                    htpy.span(
                        class_="font-mono text-sm font-medium tracking-tight text-slate-900"
                    )[name],
                    htpy.span(class_="text-xs text-slate-400 sm:hidden")[
                        f"{type_label} • {tool_count} tools"
                    ],
                ],
            ]
        ],
        htpy.td(class_="hidden sm:table-cell px-4 py-3.5")[
            htpy.span(
                class_=f"inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium tracking-wide {type_chip}"
            )[type_label],
        ],
        htpy.td(class_="hidden sm:table-cell px-4 py-3.5 text-center")[
            htpy.span(
                class_="inline-flex items-center justify-center min-w-7 h-7 rounded-full bg-slate-900 text-white text-xs font-mono font-medium"
            )[str(tool_count)],
        ],
        htpy.td(class_="hidden md:table-cell px-4 py-3.5 text-center")[
            htpy.span(class_="font-mono text-xs text-slate-500 tabular-nums")[
                f"{timeout}ms"
            ],
        ],
        htpy.td(class_="px-4 py-3.5")[badge(state),],
        htpy.td(class_="px-4 py-3.5")[
            htpy.div(class_="flex items-center gap-1 justify-end")[
                htpy.button(
                    class_="inline-flex items-center justify-center rounded-full bg-white border border-slate-200 h-9 px-3 text-xs font-medium text-slate-700 hover:bg-slate-900 hover:text-white hover:border-slate-900 active:scale-95 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-1 transition-all duration-200 h-9",
                    aria_label=f"View {name}",
                    **{
                        "hx-get": detail_url,
                        "hx-target": _DIALOG_TARGET,
                        "hx-swap": "innerHTML",
                        "hx-indicator": "#global-spinner",
                    },
                )["View"],
                htpy.button(
                    class_="hidden sm:inline-flex items-center justify-center rounded-full bg-white border border-slate-200 h-9 px-3 text-xs font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 active:scale-95 focus:outline-none focus:ring-2 focus:ring-slate-900 transition-all duration-200 h-9",
                    aria_label=f"{toggle_label} {name}",
                    **{
                        "hx-patch": patch_url,
                        "hx-vals": json.dumps({"enabled": toggle_val}),
                        "hx-headers": '{"Content-Type":"application/json"}',
                        "hx-target": "#server-table-body",
                        "hx-swap": "outerHTML",
                    },
                )[toggle_label],
                htpy.button(
                    class_="inline-flex items-center justify-center rounded-full bg-white border border-slate-200 h-8 w-8 text-slate-400 hover:bg-red-50 hover:text-red-600 hover:border-red-200 active:scale-95 focus:outline-none focus:ring-2 focus:ring-red-500 transition-all duration-200",
                    aria_label=f"Delete {name}",
                    **{
                        "hx-delete": delete_url,
                        "hx-confirm": f"Delete server '{name}'? This cannot be undone.",
                        "hx-target": "#server-table-body",
                        "hx-swap": "outerHTML",
                    },
                )[htpy.span(aria_hidden="true")["×"]],
            ]
        ],
    ]


def server_table(servers: list[dict[str, Any]]) -> Any:
    if not servers:
        return htpy.tbody(id="server-table-body")[
            htpy.tr[htpy.td(colspan="6", class_="px-4 py-6")[empty_state()]]
        ]
    rows = [server_row(s, i) for i, s in enumerate(servers)]
    return htpy.tbody(id="server-table-body")[rows]


def add_form() -> Any:
    return htpy.section(
        id="add-server-section",
        class_="bg-white shadow-sm rounded-2xl border border-slate-200 overflow-hidden transition-shadow duration-200 hover:shadow-md",
    )[
        htpy.div(
            class_="px-6 py-5 border-b border-slate-100 flex items-center justify-between"
        )[
            htpy.div(class_="flex items-center gap-3")[
                htpy.span(
                    class_="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 text-white shadow-sm"
                )[_icon("plus", cls="h-4 w-4"),],
                htpy.div[
                    htpy.h2(
                        class_="text-sm font-semibold tracking-tight text-slate-900"
                    )["Add Server"],
                    htpy.p(class_="text-xs text-slate-500")[
                        "Remote URL or local command — choose one"
                    ],
                ],
            ],
            htpy.span(
                class_="hidden sm:inline-flex items-center gap-1.5 text-xs text-slate-400"
            )[
                htpy.span(class_="h-1.5 w-1.5 rounded-full bg-emerald-500")[[]],
                "local-first • masked ***",
            ],
        ],
        htpy.form(
            id="add-form",
            method="post",
            action="/api/servers",
            class_="p-6 space-y-5",
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
                        class_="block text-xs font-medium tracking-wide text-slate-700 mb-1.5",
                        for_="field-name",
                    )["Name *"],
                    htpy.input(
                        id="field-name",
                        name="name",
                        placeholder="my_server",
                        required=True,
                        autocomplete="off",
                        class_="w-full rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 text-sm font-mono transition-all duration-200 placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900 hover:border-slate-300 hover:bg-white min-h-11",
                    ),
                    htpy.p(class_="mt-1 text-xs text-slate-400")[
                        "a-z, 0-9, underscore only"
                    ],
                ],
                htpy.div[
                    htpy.label(
                        class_="block text-xs font-medium tracking-wide text-slate-700 mb-1.5",
                        for_="field-type",
                    )["Type *"],
                    htpy.div(class_="relative")[
                        htpy.select(
                            id="field-type",
                            name="type",
                            required=True,
                            class_="w-full appearance-none rounded-xl border border-slate-200 bg-slate-50/50 px-3.5 py-2.5 pr-10 text-sm font-medium transition-all duration-200 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900 hover:border-slate-300 hover:bg-white min-h-11",
                        )[
                            htpy.option(value="remote", selected=True)[
                                "remote  — HTTP / SSE"
                            ],
                            htpy.option(value="local")["local  — stdio command"],
                        ],
                        htpy.span(
                            class_="pointer-events-none absolute inset-y-0 right-3 flex items-center text-slate-400"
                        )["▾"],
                    ],
                ],
            ],
            htpy.div(id="group-url")[
                htpy.label(
                    class_="block text-xs font-medium tracking-wide text-slate-700 mb-1.5",
                    for_="field-url",
                )["URL (remote)"],
                htpy.input(
                    id="field-url",
                    name="url",
                    type="url",
                    placeholder="https://example.com/mcp",
                    class_="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-mono transition-all duration-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900 hover:border-slate-300 min-h-11",
                ),
            ],
            htpy.div(id="group-command", class_="hidden")[
                htpy.label(
                    class_="block text-xs font-medium tracking-wide text-slate-700 mb-1.5",
                    for_="field-command",
                )["Command (local)"],
                htpy.input(
                    id="field-command",
                    name="command",
                    placeholder="npx -y my-mcp",
                    class_="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-mono transition-all duration-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900 hover:border-slate-300 min-h-11",
                ),
                htpy.p(class_="mt-1 text-xs text-slate-400")[
                    "Executed locally — ensure trusted command"
                ],
            ],
            htpy.details(
                class_="group rounded-xl border border-slate-200 bg-slate-50/50 open:bg-white transition-colors duration-200"
            )[
                htpy.summary(
                    class_="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-medium text-slate-700 hover:text-slate-900"
                )[
                    htpy.span(class_="flex items-center gap-2")[
                        htpy.span(
                            class_="text-slate-400 group-open:rotate-90 transition-transform duration-200"
                        )["›"],
                        "Advanced — headers & environment",
                    ],
                    htpy.span(class_="text-xs font-normal text-slate-400")[
                        "optional JSON"
                    ],
                ],
                htpy.div(class_="grid grid-cols-1 md:grid-cols-2 gap-4 px-4 pb-4 pt-1")[
                    htpy.div[
                        htpy.label(
                            class_="block text-xs font-medium text-slate-600 mb-1.5",
                            for_="field-headers",
                        )["Headers (JSON)"],
                        htpy.textarea(
                            id="field-headers",
                            name="headers",
                            placeholder='{"Authorization": "Bearer ***"}',
                            rows="2",
                            class_="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-mono transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900 hover:border-slate-300",
                        )[[]],
                    ],
                    htpy.div[
                        htpy.label(
                            class_="block text-xs font-medium text-slate-600 mb-1.5",
                            for_="field-env",
                        )["Environment (JSON)"],
                        htpy.textarea(
                            id="field-env",
                            name="environment",
                            placeholder='{"FOO": "***"}',
                            rows="2",
                            class_="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-mono transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900 hover:border-slate-300",
                        )[[]],
                    ],
                ],
            ],
            htpy.div(class_="flex flex-wrap items-center gap-3 pt-2")[
                htpy.button(
                    type="submit",
                    class_="inline-flex items-center justify-center gap-2 rounded-full bg-slate-900 px-6 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-black hover:shadow-md active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2 transition-all duration-200 min-h-11",
                )[
                    _icon("plus", cls="h-4 w-4"),
                    "Add Server",
                ],
                htpy.span(
                    id="add-spinner",
                    class_="htmx-indicator opacity-0 transition-opacity duration-200 inline-flex items-center gap-2 text-xs text-slate-500",
                )[
                    htpy.span(
                        class_="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-slate-900"
                    )[[]],
                    "Discovering tools…",
                ],
                htpy.span(class_="text-xs text-slate-400 hidden sm:inline")[
                    "Auto-discovers tools via streamable-http → SSE"
                ],
            ],
        ],
        htpy.script[
            Markup("""
(function(){
  const sel=document.getElementById('field-type');
  const urlG=document.getElementById('group-url');
  const cmdG=document.getElementById('group-command');
  if(!sel||!urlG||!cmdG) return;
  function sync(){
    const isLocal=sel.value==='local';
    urlG.classList.toggle('hidden', isLocal);
    cmdG.classList.toggle('hidden', !isLocal);
  }
  sel.addEventListener('change', sync);
  sync();
  const q=document.getElementById('server-filter');
  if(q){
    q.addEventListener('input', function(){
      const v=this.value.toLowerCase();
      document.querySelectorAll('tr[data-name]').forEach(function(tr){
        tr.style.display = tr.getAttribute('data-name').includes(v) ? '' : 'none';
      });
    });
  }
  document.addEventListener('click', function(e){
    const b=e.target.closest('.copy-btn');
    if(!b) return;
    const pre=b.closest('div').nextElementSibling;
    if(pre && navigator.clipboard){ navigator.clipboard.writeText(pre.textContent).then(()=>{const t=b.textContent; b.textContent='Copied!'; setTimeout(()=>b.textContent=t,1200)}); }
  });
})();""")
        ],
    ]


def add_modal() -> Any:
    return add_form()


def drawer_error(message: str, status: int = 404) -> Any:
    cls = (
        "bg-red-50 border border-red-200 text-red-800 p-4 rounded-xl"
        if status >= 500
        else "bg-amber-50 border border-amber-200 text-amber-800 p-4 rounded-xl"
    )
    return htpy.aside(
        class_="relative w-full max-w-md bg-white shadow-2xl h-full overflow-y-auto ml-auto transform transition-all duration-300 translate-x-0 border-l border-slate-200 flex flex-col",
        role="region",
        aria_label="Error",
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
                **_CLOSE_ATTRS,
            )["×"],
        ],
        htpy.div(class_="p-6")[htpy.div(class_=cls)[message]],
    ]


def _drawer_header(name: str) -> Any:
    return htpy.div(
        class_="flex items-start justify-between gap-4 px-6 py-5 border-b border-slate-100 bg-white sticky top-0 z-10"
    )[
        htpy.div(class_="min-w-0 flex-1")[
            htpy.div(class_="flex items-center gap-2 mb-1")[
                htpy.span(
                    class_="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white"
                )[_icon("server", cls="h-4 w-4")],
                htpy.h2(
                    class_="text-base font-semibold tracking-tight text-slate-900 truncate"
                )[name],
            ],
            htpy.p(class_="text-xs text-slate-500")[
                "Server detail • inspect tools & config"
            ],
        ],
        htpy.button(
            class_="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 hover:bg-slate-900 hover:text-white focus:outline-none focus:ring-2 focus:ring-slate-900 transition-colors duration-200",
            aria_label="Close",
            **_CLOSE_ATTRS,
        )["×"],
    ]


def _drawer_metadata(server: dict[str, Any]) -> Any:
    typ = server.get("type", "")
    timeout = server.get("timeout", 5000)
    enabled = server.get("enabled", True)
    tool_count = server.get("tool_count", 0)
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

    def kv(label: str, value: str, mono: bool = True, break_all: bool = False) -> Any:
        return htpy.div(
            class_="flex items-center justify-between gap-4 py-2.5 border-b border-slate-50 last:border-0"
        )[
            htpy.dt(class_="text-xs font-medium tracking-wide text-slate-500 shrink-0")[
                label
            ],
            htpy.dd(
                class_=(
                    "font-mono text-xs text-slate-900 "
                    if mono
                    else "text-xs text-slate-900 "
                )
                + ("break-all text-right" if break_all else "text-right")
            )[value],
        ]

    return htpy.dl(
        class_="rounded-xl border border-slate-200 bg-slate-50/50 divide-y divide-slate-100 overflow-hidden"
    )[
        kv("Type", typ.upper() if isinstance(typ, str) else str(typ), mono=False),
        kv("Timeout", f"{timeout}ms"),
        kv("Tools", str(tool_count)),
        kv("Enabled", str(enabled).lower(), mono=False),
        (
            htpy.div(class_="px-4 py-3")[
                htpy.dt(class_="text-xs font-medium tracking-wide text-slate-500 mb-1")[
                    "URL"
                ],
                htpy.dd(
                    class_="font-mono text-xs text-slate-900 break-all bg-white border border-slate-200 rounded-lg px-3 py-2"
                )[str(url_val)],
            ]
            if url_val
            else htpy.fragment[[]]
        ),
        (
            htpy.div(class_="px-4 py-3")[
                htpy.dt(class_="text-xs font-medium tracking-wide text-slate-500 mb-1")[
                    "Command"
                ],
                htpy.dd(
                    class_="font-mono text-xs text-slate-900 break-all bg-white border border-slate-200 rounded-lg px-3 py-2"
                )[command_str],
            ]
            if command_str
            else htpy.fragment[[]]
        ),
        (
            htpy.div(class_="px-4 py-3")[
                htpy.dt(class_="text-xs font-medium tracking-wide text-slate-500 mb-1")[
                    "Resolved Transport"
                ],
                htpy.dd(class_="font-mono text-xs text-slate-900")[str(resolved)],
            ]
            if resolved
            else htpy.fragment[[]]
        ),
        (
            htpy.div(class_="px-4 py-3")[
                htpy.dt(class_="text-xs font-medium tracking-wide text-slate-500 mb-1")[
                    "CWD"
                ],
                htpy.dd(
                    class_="font-mono text-xs text-slate-900 break-all bg-white border border-slate-200 rounded-lg px-3 py-2"
                )[str(cwd_val)],
            ]
            if cwd_val
            else htpy.fragment[[]]
        ),
        (
            htpy.div(class_="px-4 py-3")[
                htpy.dt(class_="text-xs font-medium tracking-wide text-slate-500 mb-1")[
                    "Headers"
                ],
                htpy.dd(
                    class_="font-mono text-xs bg-white p-3 rounded-lg border border-slate-200 overflow-auto max-h-32"
                )[headers_text],
            ]
            if headers_val is not None
            else htpy.fragment[[]]
        ),
        (
            htpy.div(class_="px-4 py-3")[
                htpy.dt(class_="text-xs font-medium tracking-wide text-slate-500 mb-1")[
                    "Environment"
                ],
                htpy.dd(
                    class_="font-mono text-xs bg-white p-3 rounded-lg border border-slate-200 overflow-auto max-h-32"
                )[env_text],
            ]
            if env_val is not None
            else htpy.fragment[[]]
        ),
    ]


def _drawer_actions(server: dict[str, Any], warning_banner: bool) -> Any:
    name = server.get("name", "")
    enabled = server.get("enabled", True)
    quoted = urllib.parse.quote(name, safe="")
    toggle_val = not enabled
    toggle_label = "Disable" if enabled else "Enable"
    patch_url = f"/api/servers/{quoted}"
    refresh_url = f"/api/servers/{quoted}/refresh"
    reveal_url = f"/api/servers/{quoted}/reveal"
    delete_url = f"/api/servers/{quoted}"
    return htpy.div(class_="flex flex-wrap gap-2")[
        htpy.button(
            class_="inline-flex items-center justify-center rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-black hover:shadow-sm active:scale-95 focus:outline-none focus:ring-2 focus:ring-slate-900 transition-all duration-200 min-h-11",
            **{
                "hx-patch": patch_url,
                "hx-vals": json.dumps({"enabled": toggle_val}),
                "hx-headers": '{"Content-Type":"application/json"}',
                "hx-target": _DIALOG_TARGET,
                "hx-swap": "innerHTML",
            },
        )[toggle_label],
        htpy.button(
            class_="inline-flex items-center justify-center rounded-full bg-white border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 active:scale-95 focus:outline-none focus:ring-2 focus:ring-slate-900 transition-all duration-200 min-h-11",
            **{
                "hx-post": refresh_url,
                "hx-target": "#toast",
                "hx-swap": "innerHTML",
            },
        )["Refresh"],
        htpy.button(
            class_="inline-flex items-center justify-center rounded-full bg-white border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 active:scale-95 focus:outline-none focus:ring-2 focus:ring-slate-900 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 min-h-11",
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
            class_="inline-flex items-center justify-center rounded-full bg-white border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 hover:border-red-300 active:scale-95 focus:outline-none focus:ring-2 focus:ring-red-500 transition-all duration-200 min-h-11",
            **{
                "hx-delete": delete_url,
                "hx-confirm": f"Delete server '{name}'? This cannot be undone.",
                "hx-target": "#server-table-body",
                "hx-swap": "outerHTML",
            },
        )["Delete"],
    ]


def _tool_panel(tool_count: Any, pyi_content: str, truncated: bool) -> Any:
    return htpy.div(class_="rounded-xl border border-slate-200 overflow-hidden")[
        htpy.div(
            class_="flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-200"
        )[
            htpy.h3(
                class_="text-xs font-semibold tracking-wide uppercase text-slate-700 flex items-center gap-2"
            )[
                _icon("layers", cls="h-3.5 w-3.5"),
                f"Tool signatures ({tool_count})",
            ],
            htpy.button(
                class_="inline-flex items-center gap-1 rounded-full bg-white border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors duration-200 copy-btn",
                aria_label="Copy tool signatures",
                **{"data-copy-target": "tool-pre"},
            )["Copy"],
            htpy.span(class_="hidden")[[]],
        ],
        htpy.pre(
            class_="max-h-72 overflow-auto bg-white p-4 text-xs font-mono leading-relaxed text-slate-800"
        )[pyi_content or "(no tools — add will try streamable-http → SSE)"],
        (
            htpy.p(
                class_="px-4 py-2 text-xs text-amber-700 bg-amber-50 border-t border-amber-200 flex items-center gap-1.5"
            )[_icon("alert", cls="h-3.5 w-3.5"), "truncated (50KB limit)"]
            if truncated
            else htpy.fragment[[]]
        ),
    ]


def server_drawer(
    server: dict[str, Any],
    pyi_content: str,
    truncated: bool,
    warning_banner: bool = False,
) -> Any:
    name = server.get("name", "")
    tool_count = server.get("tool_count", 0)
    enabled = server.get("enabled", True)
    if not enabled:
        state = "disabled"
    elif isinstance(tool_count, int) and tool_count == 0:
        state = "unreachable"
    else:
        state = "healthy"
    return htpy.aside(
        class_="relative w-full max-w-md bg-white shadow-2xl h-full overflow-y-auto ml-auto transform transition-all duration-300 translate-x-0 border-l border-slate-200 flex flex-col",
        role="region",
        aria_label=f"Details for {name}",
    )[
        _drawer_header(name),
        htpy.div(class_="px-6 py-5 space-y-5 flex-1")[
            htpy.div(class_="flex items-center gap-2")[badge(state)],
            _drawer_metadata(server),
            _drawer_actions(server, warning_banner),
            _tool_panel(tool_count, pyi_content, truncated),
        ],
    ]


def _footer() -> Any:
    return htpy.footer(
        class_="mt-auto border-t border-slate-200 bg-white/80 backdrop-blur py-4 text-center"
    )[
        htpy.div(
            class_="flex items-center justify-center gap-2 text-xs text-slate-400"
        )[
            htpy.span(class_="h-1 w-1 rounded-full bg-slate-300")[[]],
            htpy.span["MCP Gateway • v0.7.0 • local-first — crafted with dedication"],
            htpy.span(class_="h-1 w-1 rounded-full bg-slate-300")[[]],
        ],
    ]


def _stats(servers: list[dict[str, Any]]) -> Any:
    healthy = sum(
        1 for s in servers if s.get("enabled", True) and s.get("tool_count", 0) > 0
    )
    total = len(servers)
    disabled = sum(1 for s in servers if not s.get("enabled", True))
    unreachable = sum(
        1 for s in servers if s.get("enabled", True) and s.get("tool_count", 0) == 0
    )
    stat_styles = {
        "Total": ("bg-slate-100 text-slate-900", "layers"),
        "Healthy": ("bg-emerald-50 text-emerald-600", "activity"),
        "Disabled": ("bg-slate-100 text-slate-500", "server"),
        "Unreachable": ("bg-amber-50 text-amber-600", "alert"),
    }
    vals = {
        "Total": (str(total), f"{total} servers"),
        "Healthy": (str(healthy), f"{healthy}/{total} ok"),
        "Disabled": (str(disabled), f"{disabled} off"),
        "Unreachable": (str(unreachable), "0 tools"),
    }
    return htpy.div(class_="grid grid-cols-2 lg:grid-cols-4 gap-3")[
        *[
            htpy.div(
                class_="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm hover:shadow-md hover:border-slate-300 transition-all duration-200 group"
            )[
                htpy.div(class_="flex items-center justify-between mb-2")[
                    htpy.span(
                        class_="text-xs font-medium tracking-widest uppercase text-slate-500"
                    )[label],
                    htpy.span(
                        class_=f"flex h-7 w-7 items-center justify-center rounded-lg {stat_styles[label][0]} group-hover:scale-105 transition-transform duration-200"
                    )[_icon(stat_styles[label][1], cls="h-3.5 w-3.5"),],
                ],
                htpy.div(class_="flex items-baseline gap-2")[
                    htpy.span(
                        class_="text-2xl font-semibold tracking-tight text-slate-900 tabular-nums"
                    )[vals[label][0]],
                    htpy.span(class_="text-xs text-slate-400")[vals[label][1]],
                ],
            ]
            for label in ["Total", "Healthy", "Disabled", "Unreachable"]
        ]
    ]


def layout(servers: list[dict[str, Any]], warning_banner: bool = False) -> Any:
    healthy = sum(
        1 for s in servers if s.get("enabled", True) and s.get("tool_count", 0) > 0
    )
    total = len(servers)
    table = htpy.table(class_="min-w-full divide-y divide-slate-100")[
        htpy.thead(class_="bg-slate-50/80 backdrop-blur sticky top-0 z-10")[
            htpy.tr[
                htpy.th(
                    class_="px-4 py-3 text-left text-xs font-medium tracking-widest uppercase text-slate-500"
                )["Server"],
                htpy.th(
                    class_="hidden sm:table-cell px-4 py-3 text-left text-xs font-medium tracking-widest uppercase text-slate-500"
                )["Type"],
                htpy.th(
                    class_="hidden sm:table-cell px-4 py-3 text-center text-xs font-medium tracking-widest uppercase text-slate-500"
                )["Tools"],
                htpy.th(
                    class_="hidden md:table-cell px-4 py-3 text-center text-xs font-medium tracking-widest uppercase text-slate-500"
                )["Timeout"],
                htpy.th(
                    class_="px-4 py-3 text-left text-xs font-medium tracking-widest uppercase text-slate-500"
                )["Status"],
                htpy.th(
                    class_="px-4 py-3 text-right text-xs font-medium tracking-widest uppercase text-slate-500"
                )["Actions"],
            ]
        ],
        server_table(servers),
    ]

    warning = (
        htpy.div(
            class_="flex items-center gap-3 bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-2xl shadow-sm",
            role="alert",
        )[
            htpy.span(
                class_="flex h-8 w-8 items-center justify-center rounded-full bg-amber-100 text-amber-700"
            )[_icon("alert", cls="h-4 w-4")],
            htpy.div(class_="flex-1")[
                htpy.p(class_="text-sm font-medium")[
                    "Dashboard exposed on non-loopback"
                ],
                htpy.p(class_="text-xs opacity-80")[
                    "Set MCP_GWAY_ALLOW_REMOTE=1 — secrets reveal disabled"
                ],
            ],
        ]
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
            htpy.meta(name="color-scheme", content="light"),
            htpy.title["MCP Gateway Dashboard"],
            htpy.link(rel="stylesheet", href="/static/tailwind.css"),
            htpy.script(src="/static/htmx.min.js")[[]],
            htpy.script(src="/static/dialog.js")[[]],
            htpy.style[
                Markup("""
@keyframes rowIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.animate-row{animation:rowIn 320ms cubic-bezier(.16,1,.3,1) both}
@media (prefers-reduced-motion: reduce){.animate-row{animation:none!important}}
.htmx-indicator{opacity:0;transition:opacity 200ms}
.htmx-request .htmx-indicator,.htmx-request.htmx-indicator{opacity:1}
::selection{background:#0F172A;color:#fff}
""")
            ],
        ],
        htpy.body(
            class_="bg-slate-50 text-slate-900 antialiased min-h-screen flex flex-col overflow-y-auto selection:bg-slate-900 selection:text-white"
        )[
            htpy.header(
                class_="sticky top-0 z-20 backdrop-blur-xl bg-white/75 border-b border-slate-200"
            )[
                htpy.div(
                    class_="max-w-6xl mx-auto px-4 py-3.5 flex items-center justify-between gap-4"
                )[
                    htpy.div(class_="flex items-center gap-3 min-w-0")[
                        htpy.span(
                            class_="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 text-white shadow-sm"
                        )[_icon("layers", cls="h-5 w-5")],
                        htpy.div(class_="min-w-0")[
                            htpy.h1(
                                class_="text-sm font-semibold tracking-tight text-slate-900 leading-none"
                            )["MCP Gateway"],
                            htpy.p(class_="text-xs text-slate-500 hidden sm:block")[
                                "Local dashboard • single process"
                            ],
                        ],
                        htpy.span(
                            class_="hidden md:inline-flex items-center rounded-full bg-slate-900 text-white px-2.5 py-0.5 text-xs font-medium tracking-wide"
                        )["v0.7.0"],
                    ],
                    htpy.div(class_="flex items-center gap-2 sm:gap-3")[
                        htpy.div(
                            class_="hidden sm:flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1.5 shadow-sm"
                        )[
                            htpy.span(
                                class_="h-2 w-2 rounded-full bg-emerald-500 animate-pulse",
                                aria_hidden="true",
                            )[[]],
                            htpy.span(
                                class_="text-xs font-medium tabular-nums text-slate-700"
                            )[f"{healthy}/{total} healthy" if total else "0 servers"],
                        ],
                        health_badge,
                        htpy.span(
                            id="global-spinner",
                            class_="htmx-indicator inline-flex items-center gap-1.5 text-xs text-slate-500",
                        )[
                            htpy.span(
                                class_="h-3 w-3 animate-spin rounded-full border-2 border-slate-200 border-t-slate-900"
                            )[[]],
                            htpy.span(class_="hidden sm:inline")["Loading…"],
                        ],
                    ],
                ],
            ],
            htpy.div(
                class_="max-w-6xl mx-auto px-4 py-6 pb-12 flex-1 flex flex-col min-h-0 w-full gap-6"
            )[
                warning,
                _stats(servers),
                htpy.main(
                    class_="flex-1 flex flex-col space-y-6 min-h-0 gap-6 pb-6 overflow-visible"
                )[
                    htpy.div(
                        class_="bg-white shadow-sm rounded-2xl border border-slate-200 overflow-hidden transition-shadow duration-200 hover:shadow-md flex flex-col",
                    )[
                        htpy.div(
                            class_="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 sm:px-6 py-4 border-b border-slate-100 bg-slate-50/50"
                        )[
                            htpy.h2(
                                class_="text-sm font-semibold tracking-tight text-slate-900 flex items-center gap-2"
                            )[
                                _icon("server", cls="h-4 w-4 text-slate-400"),
                                "Servers",
                                htpy.span(
                                    class_="ml-1 rounded-full bg-slate-900 text-white px-2 py-0.5 text-xs font-medium"
                                )[str(total)],
                            ],
                            htpy.div(class_="flex items-center gap-2")[
                                htpy.div(class_="relative")[
                                    htpy.input(
                                        id="server-filter",
                                        placeholder="Filter by name…",
                                        class_="w-full sm:w-56 rounded-full border border-slate-200 bg-white pl-9 pr-3 py-2 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900 transition-all duration-200",
                                    ),
                                    htpy.span(
                                        class_="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                                    )[_icon("search", cls="h-4 w-4")],
                                ],
                            ],
                        ],
                        htpy.div(
                            class_="overflow-x-auto",
                            **{
                                "hx-get": "/dashboard/servers",
                                "hx-trigger": "load",
                                "hx-target": "#server-table-body",
                                "hx-swap": "outerHTML",
                                "hx-indicator": "#global-spinner",
                            },
                        )[table],
                    ],
                    add_form(),
                    htpy.dialog(
                        id=_DIALOG_ID,
                        class_="m-0 p-0 max-w-none w-screen h-screen max-h-none bg-transparent backdrop:bg-slate-900/30 backdrop:backdrop-blur-sm open:flex open:justify-end border-0",
                    )[[]],
                ],
                htpy.div(
                    id="toast",
                    class_="fixed top-4 right-4 z-50 space-y-2 max-w-sm",
                    **{"hx-swap-oob": "true"},
                )[[]],
            ],
            _footer(),
        ],
    ]
