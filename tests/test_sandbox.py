"""Tests for Starlark sandbox execution."""

import pytest

from mcp_gway.sandbox import StarlarkSandbox


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
