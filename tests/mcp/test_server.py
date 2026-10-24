# Feature: unghosted-demo, Task 11.7: MCP server registration unit tests
"""Unit tests for the FastMCP server in ``mcp_server.server``.

These check the registration contract rather than tool bodies (those are
covered by the property tests in this package):

1. The server registers *exactly* the five tools from ``SETTINGS.mcp_tools``,
   with names equal to that tuple (R9.1 - Settings owns the names).
2. Every registered tool is read-only: the five names are exactly the
   read-only set, each tool's underlying function comes from
   ``mcp_server.tools``, and no create/update/delete tool exists (R9.8).
3. An in-memory smoke call through ``fastmcp.Client`` against the server
   instance returns an ok-shaped result for a read tool.

``fastmcp`` (4.1.3) exposes ``FastMCP.list_tools()`` and ``Client`` as async
APIs. ``pytest-asyncio`` is not a project dependency, so the async work is
driven with ``asyncio.run`` inside ordinary synchronous tests (no new plugin,
no new dependency).

**Validates: Requirements 9.1, 9.8**
"""
from __future__ import annotations

import asyncio

from fastmcp import Client

from app.settings import SETTINGS
from mcp_server.server import mcp

# Verbs that would indicate a mutating tool. None of these may appear in a
# registered tool name: the server is read-only (R9.8).
_WRITE_VERBS = ("create", "update", "delete", "write", "set", "add", "remove")


def _list_tools() -> list:
    """Return the server's registered Tool objects (async bridged to sync)."""
    return asyncio.run(mcp.list_tools())


def test_registers_exactly_five_tools() -> None:
    """The server registers exactly five tools (R9.1)."""
    tools = _list_tools()
    assert len(tools) == 5, [t.name for t in tools]
    assert len(SETTINGS.mcp_tools) == 5


def test_tool_names_match_settings() -> None:
    """Registered tool names equal ``SETTINGS.mcp_tools`` exactly (R9.1).

    Order-independent: Settings owns the names and the server must expose that
    exact set, no more and no less.
    """
    names = {t.name for t in _list_tools()}
    assert names == set(SETTINGS.mcp_tools)


def test_all_tools_are_read_only() -> None:
    """No registered tool is a write tool (R9.8).

    The five names are exactly the read-only set from Settings, no name
    contains a mutating verb, and each tool's underlying function is one of the
    plain functions defined in ``mcp_server.tools``.
    """
    tools = _list_tools()
    names = {t.name for t in tools}

    # Exactly the read-only Settings set, nothing extra.
    assert names == set(SETTINGS.mcp_tools)

    for tool in tools:
        lowered = tool.name.lower()
        assert not any(verb in lowered for verb in _WRITE_VERBS), (
            f"tool {tool.name!r} name suggests a write operation"
        )
        # Bodies live in mcp_server.tools; nothing is registered from elsewhere.
        assert tool.fn.__module__ == "mcp_server.tools", (
            f"tool {tool.name!r} is backed by {tool.fn.__module__}, "
            "not mcp_server.tools"
        )


def test_in_memory_client_smoke_call() -> None:
    """An in-memory client call to a read tool returns an ok result.

    Uses ``fastmcp.Client`` with the in-memory transport (passing the server
    instance directly). Calls ``list_demo_stops`` and asserts a successful,
    ok-shaped envelope with a list payload.
    """

    async def _run():
        async with Client(mcp) as client:
            listed = await client.list_tools()
            assert {t.name for t in listed} == set(SETTINGS.mcp_tools)

            result = await client.call_tool("list_demo_stops", {})
            assert result.is_error is False
            return result.data

    data = asyncio.run(_run())

    # Envelope shape from mcp_server.tools._ok.
    assert isinstance(data, dict)
    assert data["ok"] is True
    assert isinstance(data["data"], list)
    assert isinstance(data["attribution"], list) and data["attribution"]
    assert isinstance(data["disclaimer"], str) and data["disclaimer"]
