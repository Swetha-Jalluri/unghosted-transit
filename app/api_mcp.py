"""API & MCP page.

Explains how other software reaches Unghosted: a REST API for transit app
teams and an MCP server for AI assistants. Reference content only -- no live
endpoints are called here.
"""
from __future__ import annotations

import streamlit as st

from app.components import footer, page_header


def render() -> None:
    page_header("API & MCP")

    st.write(
        "Unghosted is built to be consumed by other software. Transit app teams "
        "use the REST API; AI assistants use the MCP server. Both are read-only "
        "and return the same trust signals shown in the Rider view."
    )

    st.subheader("REST API (/v1)")
    st.caption("Illustrative endpoints — preview only, not live yet.")
    st.code(
        """# Bus trust for a stop
GET /v1/bus-trust?stop_id=place-kencl&mode=demo&limit=5

# Dock trust for a station
GET /v1/dock-trust?station_id=station_kencl&walk_min=5&mode=demo

# Nearby docks (stop picker coordinates, never a location request)
GET /v1/nearby-docks?lat=42.3626&lon=-71.0915&walk_min=5&limit=3

# Aggregate findings and system health
GET /v1/findings
GET /v1/health""",
        language="http",
    )

    st.subheader("MCP server")
    st.caption("Read-only tools for AI assistants — preview only.")
    st.markdown(
        """
- `get_bus_trust(stop_id, mode, limit, at_ts)`
- `get_dock_trust(station_id, walk_min, mode, at_ts)`
- `get_nearby_docks(lat, lon, walk_min, limit, mode, at_ts)`
- `get_findings()`
- `get_health()`
- `get_replay_window()`
        """
    )

    st.info(
        "Every response includes data age, attribution and sample sizes. "
        "Nothing here claims certainty.",
        icon="ℹ️",
    )

    footer()
