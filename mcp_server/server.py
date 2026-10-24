"""FastMCP server exposing the five read-only Unghosted tools.

This is a thin registration layer. The tool bodies live in
:mod:`mcp_server.tools` as plain functions that never raise and return dicts;
here we register them on a :class:`fastmcp.FastMCP` instance under the exact
names from ``SETTINGS.mcp_tools`` (R9.1). Nothing registered here writes, so the
server is read-only (R9.8).

FastMCP API note (version pinned in ``uv.lock``): a tool is built with
``Tool.from_function(fn, name=...)`` and registered with ``mcp.add_tool(tool)``.
``from_function`` takes the public ``name`` so the wire-level tool name is
decoupled from the Python function name, letting Settings own the names.

Run with ``uv run python -m mcp_server.server``.
"""
from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.tools import Tool

from app.settings import SETTINGS
from mcp_server import tools

# The five read-only tool functions, in the order Settings lists their names.
# Settings owns the names (R9.1); this module owns only the pairing to bodies.
_TOOL_FUNCTIONS = (
    tools.list_demo_stops,
    tools.check_bus_trust,
    tools.check_dock_trust,
    tools.nearby_docks,
    tools.todays_findings,
)


def build_server() -> FastMCP:
    """Create the FastMCP server with exactly the five Settings tools.

    Names come from ``SETTINGS.mcp_tools`` (never hardcoded here); each name is
    paired, in order, with the matching plain function in ``mcp_server.tools``.
    Guards against drift between the Settings names and the tool functions.
    """
    names = SETTINGS.mcp_tools
    if len(names) != len(_TOOL_FUNCTIONS):
        raise ValueError(
            "SETTINGS.mcp_tools lists "
            f"{len(names)} names but {len(_TOOL_FUNCTIONS)} tool functions are "
            "defined; they must match one-to-one."
        )

    mcp = FastMCP("Unghosted")
    for name, fn in zip(names, _TOOL_FUNCTIONS):
        mcp.add_tool(Tool.from_function(fn, name=name))
    return mcp


# Module-level instance so tests and `-m` runs share one server.
mcp = build_server()


def main() -> None:
    """Start the MCP server (blocking)."""
    mcp.run()


if __name__ == "__main__":
    main()
