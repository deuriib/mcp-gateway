"""Shared test fixtures."""

import io
import sys

import pytest

from mcp_gway.models import MCPServerConfig


@pytest.fixture(autouse=True)
def _restore_stderr():
    orig_stderr = sys.__stderr__
    orig_stdout = sys.__stdout__
    # If previous test left wrapped streams, restore
    if isinstance(sys.stderr, io.TextIOWrapper) and hasattr(sys.stderr, "_original_fd"):
        try:
            if getattr(sys.stderr, "_original_fd", -1) == -1:
                sys.stderr = orig_stderr
        except Exception:
            sys.stderr = orig_stderr
    if isinstance(sys.stdout, io.TextIOWrapper) and hasattr(sys.stdout, "_original_fd"):
        try:
            if getattr(sys.stdout, "_original_fd", -1) == -1:
                sys.stdout = orig_stdout
        except Exception:
            sys.stdout = orig_stdout
    yield
    if isinstance(sys.stderr, io.TextIOWrapper) and hasattr(sys.stderr, "_original_fd"):
        try:
            if getattr(sys.stderr, "_original_fd", -1) == -1:
                sys.stderr = orig_stderr
        except Exception:
            sys.stderr = orig_stderr
    if isinstance(sys.stdout, io.TextIOWrapper) and hasattr(sys.stdout, "_original_fd"):
        try:
            if getattr(sys.stdout, "_original_fd", -1) == -1:
                sys.stdout = orig_stdout
        except Exception:
            sys.stdout = orig_stdout


@pytest.fixture
def http_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="testserver",
        type="remote",
        url="http://localhost:3001/mcp",
    )


@pytest.fixture
def stdio_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="teststdio",
        type="local",
        command=["echo", "hello"],
    )
