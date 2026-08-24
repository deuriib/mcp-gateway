"""Tests for Starlark sandbox execution."""

import pytest

from mcp_gway.sandbox import SandboxTimeoutError, StarlarkSandbox


def test_execute_simple_expression():
    sandbox = StarlarkSandbox()
    result = sandbox.execute("result = 2 + 3")
    assert result == 5


def test_execute_string_operations():
    sandbox = StarlarkSandbox()
    assert sandbox.execute('result = "hello " + "world"') == "hello world"


def test_execute_list_comprehension():
    sandbox = StarlarkSandbox()
    assert sandbox.execute("result = [x * 2 for x in [1, 2, 3]]") == [2, 4, 6]


def test_execute_with_injected_object():
    sandbox = StarlarkSandbox()

    class MockServer:
        def search(self, query=""):
            return {"items": [{"title": f"Result for {query}"}]}

    sandbox.inject_server("youtube", MockServer())
    result = sandbox.execute('result = youtube.search(query="test")')
    assert result["items"][0]["title"] == "Result for test"


def test_execute_syntax_error():
    sandbox = StarlarkSandbox()
    with pytest.raises(Exception):
        sandbox.execute("def broken(")


def test_execute_undefined_variable_error():
    sandbox = StarlarkSandbox()
    with pytest.raises(Exception):
        sandbox.execute("result = nonexistent_var")


# --- Timeout Tests ---


def test_execute_slow_callback_raises_timeout():
    """Injected Python callback that sleeps should be killed by timeout."""
    import time

    class SlowServer:
        def slow_method(self):
            time.sleep(10)
            return "done"

    sandbox = StarlarkSandbox()
    sandbox.inject_server("slow", SlowServer())
    with pytest.raises(SandboxTimeoutError):
        sandbox.execute("result = slow.slow_method()", timeout=0.5)


def test_execute_fast_callback_completes_within_timeout():
    """Fast injected callback should not be affected by generous timeout."""

    class FastServer:
        def fast_method(self):
            return 42

    sandbox = StarlarkSandbox()
    sandbox.inject_server("fast", FastServer())
    result = sandbox.execute("result = fast.fast_method()", timeout=5.0)
    assert result == 42


def test_execute_timeout_error_message_includes_details():
    """Timeout error should be descriptive enough for debugging."""
    import time

    class Blocker:
        def block(self):
            time.sleep(10)

    sandbox = StarlarkSandbox()
    sandbox.inject_server("b", Blocker())
    with pytest.raises(SandboxTimeoutError, match="timed out"):
        sandbox.execute("result = b.block()", timeout=0.3)


def test_default_timeout_is_reasonable():
    """Default timeout should be 30 seconds, not infinite."""
    import inspect

    sig = inspect.signature(StarlarkSandbox.execute)
    assert sig.parameters["timeout"].default == 30.0


# --- Hyphenated tool name tests ---


def test_execute_with_hyphenated_method():
    """Methods with hyphens (like query-docs) should work via sanitized names."""
    from mcp_gway.sandbox import _sanitize_identifier

    assert _sanitize_identifier("query-docs") == "query_docs"
    assert _sanitize_identifier("resolve-library-id") == "resolve_library_id"
    assert _sanitize_identifier("memory_smart_search") == "memory_smart_search"
    assert _sanitize_identifier("123tool") == "_123tool"

    class Context7Server:
        pass

    def query_docs(self, library_id="", query=""):
        return {"answer": f"Docs for {library_id}: {query}"}

    setattr(Context7Server, "query-docs", query_docs)

    sandbox = StarlarkSandbox()
    sandbox.inject_server("context7", Context7Server())
    # Should work because hyphens are sanitized to underscores
    result = sandbox.execute(
        'result = context7.query_docs(library_id="react", query="hooks")'
    )
    assert result["answer"] == "Docs for react: hooks"


def test_inject_server_with_hyphenated_methods():
    """Server struct with hyphenated method names should be injectable."""
    from mcp_gway.sandbox import _sanitize_identifier

    class MyServer:
        pass

    def query_docs(self, q=""):
        return q

    def resolve_library_id(self, lib=""):
        return lib

    setattr(MyServer, "query-docs", query_docs)
    setattr(MyServer, "resolve-library-id", resolve_library_id)

    sandbox = StarlarkSandbox()
    sandbox.inject_server("context7", MyServer())

    # Verify sanitized names are valid identifiers
    proxy = sandbox._modules["context7"]
    for attr_name in dir(proxy):
        if attr_name.startswith("_"):
            continue
        safe = _sanitize_identifier(attr_name)
        assert safe.isidentifier(), f"'{safe}' is not a valid identifier"


def test_sanitize_identifier_edge_cases():
    """Test various edge cases for identifier sanitization."""
    from mcp_gway.sandbox import _sanitize_identifier

    assert _sanitize_identifier("simple") == "simple"
    assert _sanitize_identifier("with-dash") == "with_dash"
    assert _sanitize_identifier("with.dot") == "with_dot"
    assert _sanitize_identifier("with space") == "with_space"
    assert _sanitize_identifier("with@special#chars!") == "with_special_chars_"
    assert _sanitize_identifier("") == ""
    assert _sanitize_identifier("_private") == "_private"
    assert _sanitize_identifier("3start") == "_3start"


# --- print() no-op tests ---


def test_print_noop_does_not_fail():
    """Scripts using print() should not raise Variable 'print' not found."""
    sandbox = StarlarkSandbox()
    result = sandbox.execute('print("hello"); result = 42')
    assert result == 42


def test_print_noop_with_multiple_args():
    """print() with multiple positional args should be silently ignored."""
    sandbox = StarlarkSandbox()
    result = sandbox.execute('print("a", "b", "c"); result = 1')
    assert result == 1


def test_print_noop_with_kwargs():
    """print() with keyword args (e.g. end, sep) should be silently ignored."""
    sandbox = StarlarkSandbox()
    result = sandbox.execute('print("x", end=""); result = 99')
    assert result == 99


def test_print_noop_returns_none():
    """print() should return None so assignments like x = print(...) work."""
    sandbox = StarlarkSandbox()
    result = sandbox.execute("x = print('test'); result = x")
    assert result is None
