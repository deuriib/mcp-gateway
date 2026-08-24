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
