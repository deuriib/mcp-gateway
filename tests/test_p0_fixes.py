"""P0 fixes tests - SSRF validation on MCPServerConfig."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_gway.models import MCPServerConfig


def test_ssrf_169_blocked():
    with pytest.raises((ValidationError, ValueError)):
        MCPServerConfig(name="bad", type="remote", url="http://169.254.169.254/mcp")
    with pytest.raises((ValidationError, ValueError)):
        MCPServerConfig(name="bad2", type="remote", url="http://10.0.0.1/mcp")
    # CR/LF still blocked
    with pytest.raises((ValidationError, ValueError)):
        MCPServerConfig(name="bad3", type="remote", url="http://127.0.0.1/mcp\r\n")
    # valid public should pass
    cfg = MCPServerConfig(name="ok", type="remote", url="https://example.com/mcp")
    assert cfg.url == "https://example.com/mcp"
