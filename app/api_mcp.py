"""API & MCP page.

Explains how other software reaches Unghosted: a REST API for transit app
teams and an MCP server for AI assistants. Reference content only -- no live
endpoints are called here.

Every route and tool shown is built from ``SETTINGS`` (base URL, route paths,
MCP tool names) with one request example each. Example ids and coordinates come
from the first ``list_demo_stops()`` entry and ``SETTINGS.demo_stop_coords``.
Nothing is hardcoded: when a setting or example value is missing, the affected
item is omitted and the missing setting is named instead (R7.2, R7.3, R11.5).
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode

import streamlit as st

from core.service import list_demo_stops

from app.components import page_header
from app.settings import SETTINGS


def _default_mode() -> Optional[str]:
    """Return a mode word for examples, preferring demo, else the first mode."""
    modes = SETTINGS.modes
    if not modes:
        return None
    return "demo" if "demo" in modes else modes[0]


def _first_demo_stop():
    """Return the first demo stop, or ``None`` if the list is unavailable."""
    try:
        stops = list_demo_stops()
    except Exception:
        return None
    return stops[0] if stops else None


def _stop_coords(stop_id: str) -> Optional[dict]:
    """Return {"lat", "lon"} for a stop id from Settings, or ``None``."""
    entry = SETTINGS.demo_stop_coords.get(stop_id)
    if not entry:
        return None
    lat = entry.get("lat")
    lon = entry.get("lon")
    if lat is None or lon is None:
        return None
    return {"lat": lat, "lon": lon}


def _query_for_route(route_key: str, stop) -> tuple[Optional[dict], Optional[str]]:
    """Build the query params for a route example.

    Returns ``(params, missing)``. When ``params`` is ``None`` the example must
    be omitted and ``missing`` names the setting (or source) that was empty.
    Routes that take no parameters return an empty dict and no message.
    """
    if route_key in ("findings", "health", "replay_window"):
        return {}, None

    mode = _default_mode()
    if mode is None:
        return None, "modes"

    if route_key == "bus_trust":
        if stop is None:
            return None, "list_demo_stops()"
        limit = SETTINGS.limit.get("default")
        params = {"stop_id": stop.stop_id, "mode": mode}
        if limit is not None:
            params["limit"] = limit
        return params, None

    if route_key == "nearby_docks":
        if stop is None:
            return None, "list_demo_stops()"
        coords = _stop_coords(stop.stop_id)
        if coords is None:
            return None, "demo_stop_coords"
        params = {
            "lat": coords["lat"],
            "lon": coords["lon"],
            "mode": mode,
        }
        walk = SETTINGS.walk_min.get("default")
        if walk is not None:
            params["walk_min"] = walk
        dock_limit = SETTINGS.dock_limit
        if dock_limit is not None:
            params["limit"] = dock_limit
        return params, None

    if route_key == "dock_trust":
        # A station id is not available from list_demo_stops() or
        # demo_stop_coords, so the example is omitted and the source is named.
        return None, "demo_stop_coords (station id)"

    # Unknown route key: no example, but still name the source gap.
    return None, "api_routes"


def _render_routes(stop) -> None:
    """Document each API route from Settings with one request example."""
    st.subheader("REST API")

    base_url = SETTINGS.api_base_url
    routes = SETTINGS.api_routes

    if not base_url:
        st.warning(
            "Base URL is not configured (Settings `api_base_url` is empty). "
            "Routes and examples are omitted until it is set.",
            icon="⚠️",
        )
        return

    if not routes:
        st.warning(
            "No routes are configured (Settings `api_routes` is empty).",
            icon="⚠️",
        )
        return

    st.caption(f"Base URL from Settings `api_base_url`: {base_url}")

    for route_key, path in routes.items():
        if not path:
            st.warning(
                f"Route `{route_key}` is omitted: Settings "
                f"`api_routes['{route_key}']` is empty.",
                icon="⚠️",
            )
            continue

        st.markdown(f"**`{route_key}`** — `{path}`")

        params, missing = _query_for_route(route_key, stop)
        if params is None:
            st.caption(
                f"Example omitted: missing Settings `{missing}`."
            )
            continue

        query = ("?" + urlencode(params)) if params else ""
        st.code(f"GET {base_url}{path}{query}", language="http")


def _render_tools(stop) -> None:
    """Document each MCP tool from Settings with one request example."""
    st.subheader("MCP server")

    tools = SETTINGS.mcp_tools
    if not tools:
        st.warning(
            "No MCP tools are configured (Settings `mcp_tools` is empty).",
            icon="⚠️",
        )
        return

    st.caption("Read-only tools for AI assistants, named from Settings `mcp_tools`.")

    mode = _default_mode()
    coords = _stop_coords(stop.stop_id) if stop is not None else None

    for tool in tools:
        st.markdown(f"**`{tool}`**")
        example, missing = _tool_example(tool, stop, mode, coords)
        if example is None:
            st.caption(f"Example omitted: missing Settings `{missing}`.")
            continue
        st.code(example, language="python")


def _tool_example(tool: str, stop, mode, coords) -> tuple[Optional[str], Optional[str]]:
    """Build one call example for an MCP tool, or name the missing source."""
    if tool == "list_demo_stops":
        return f"{tool}()", None
    if tool == "todays_findings":
        return f"{tool}()", None

    if mode is None:
        return None, "modes"

    if tool == "check_bus_trust":
        if stop is None:
            return None, "list_demo_stops()"
        limit = SETTINGS.limit.get("default")
        args = f'stop_id="{stop.stop_id}", mode="{mode}"'
        if limit is not None:
            args += f", limit={limit}"
        return f"{tool}({args})", None

    if tool == "check_dock_trust":
        # Needs a station id, not available from the example sources.
        return None, "demo_stop_coords (station id)"

    if tool == "nearby_docks":
        if stop is None:
            return None, "list_demo_stops()"
        if coords is None:
            return None, "demo_stop_coords"
        args = f'lat={coords["lat"]}, lon={coords["lon"]}, mode="{mode}"'
        walk = SETTINGS.walk_min.get("default")
        if walk is not None:
            args += f", walk_min={walk}"
        dock_limit = SETTINGS.dock_limit
        if dock_limit is not None:
            args += f", limit={dock_limit}"
        return f"{tool}({args})", None

    # Unknown tool name: no example, name the source gap.
    return None, "mcp_tools"


def render() -> None:
    page_header("API & MCP")

    st.write(
        "Unghosted is built to be consumed by other software. Transit app teams "
        "use the REST API; AI assistants use the MCP server. Both are read-only "
        "and return the same trust signals shown in the Rider view."
    )

    stop = _first_demo_stop()

    _render_routes(stop)
    _render_tools(stop)

    st.info(
        "Every response includes data age, attribution and sample sizes. "
        "Nothing here claims certainty.",
        icon="ℹ️",
    )
