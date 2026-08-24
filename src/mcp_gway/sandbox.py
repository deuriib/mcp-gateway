"""Starlark sandbox for safe code execution."""

from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

import starlark as sl


class SandboxTimeoutError(Exception):
    """Raised when code execution exceeds the timeout."""


class StarlarkSandbox:
    def __init__(self) -> None:
        self.globals = sl.Globals.extended_by([sl.LibraryExtension.StructType])
        self._modules: dict[str, object] = {}

    def inject_server(self, name: str, server_proxy: object) -> None:
        self._modules[name] = server_proxy

    def execute(self, code: str, timeout: float = 30.0) -> object:
        mod = sl.Module()
        preamble_lines: list[str] = []

        for name, proxy in self._modules.items():
            methods: list[str] = []
            for attr_name in dir(proxy):
                if attr_name.startswith("_"):
                    continue
                attr_val = getattr(proxy, attr_name, None)
                if callable(attr_val) or (inspect.isfunction(attr_val)):
                    callable_name = f"{name}_{attr_name}"
                    mod.add_callable(callable_name, attr_val)
                    methods.append(f"{attr_name} = {callable_name}")

            if methods:
                fields = ", ".join(methods)
                preamble_lines.append(f"{name} = struct({fields})")

        full_code = "\n".join(preamble_lines) + "\n" + code if preamble_lines else code

        def _run() -> object:
            ast = sl.parse("code.star", full_code)
            sl.eval(mod, ast, self.globals)
            try:
                return mod["result"]
            except (KeyError, Exception):
                raise RuntimeError(
                    "Code did not assign to 'result' variable. "
                    "Assign your output to 'result' to return it."
                )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeoutError:
                raise SandboxTimeoutError(
                    f"Code execution timed out after {timeout}s. "
                    "Avoid infinite loops or long-running operations."
                )
