"""
Fixtures for MCP protocol tests.

These tests drive the real FastMCP server through an in-memory MCP client, so
they exercise the same code path a host such as Claude Code uses: tool,
resource and prompt registration, JSON-RPC serialisation and FastMCP's own
validation. The unit tests in tests/ call service code directly and cannot
catch framework-level breakage (for example, a prompt return type that the
installed FastMCP version no longer accepts).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastmcp import Client

from src.ssa_disability_claims_openlens.app import create_app


class _NoNetwork:
    """Stand-in for httpx.Client that refuses every request."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("network disabled in mcp_tests")


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite offline and deterministic: live Data.gov search must fail
    and the server must fall back to its static catalog."""
    monkeypatch.setattr(httpx, "Client", _NoNetwork)


@pytest.fixture
async def client() -> AsyncIterator[Client]:
    """An MCP client connected to a fresh server instance over in-memory transport."""
    async with Client(create_app()) as c:
        yield c
