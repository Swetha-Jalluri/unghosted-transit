"""Rider view.

What a rider sees: for a chosen stop, which arrivals are trustworthy, a
realistic time range instead of one number, and a backup when things look bad.

Placeholder content only -- no data calls yet. A stop picker is used instead of
any location request.
"""
from __future__ import annotations

import streamlit as st

from app.components import footer, page_header, status_card, status_legend

# Placeholder-only sample stops (mirrors the shape of core DemoStop; no data call).
_SAMPLE_STOPS = {
    "Kendall/MIT": "place-kencl",
    "Harvard Ave at Lincoln": "place-haecl",
    "Northeastern Entrance": "place-neast",
}

# Placeholder-only cards. These stand in for a future BusTrustResponse.
_SAMPLE_PREDICTIONS = [
    {
        "title": "Route 66 → Dudley Station",
        "status": "confirmed",
        "headline": "Realistically 5.5–6.7 min",
        "why": "Vehicle on route, tracking close to schedule.",
        "meta_lines": [
            "Chance it arrives: 96% (model, n=580)",
            "App says: 6 min · evidence: vehicle assigned, location 5s old",
        ],
        "backup_text": None,
    },
    {
        "title": "Route 66 → Dudley Station",
        "status": "estimate",
        "headline": "Realistically 17–24 min",
        "why": "Scheduled prediction with no vehicle assigned yet; typical reliability.",
        "meta_lines": [
            "Chance it arrives: 75% (empirical, n=410)",
            "App says: 20 min · evidence: schedule-based",
        ],
        "backup_text": None,
    },
    {
        "title": "Route 111 → Dudley Station",
        "status": "unreliable",
        "headline": "Realistically 20–45 min",
        "why": "Stalled or missing signal; this one has disappeared before arrival on days like this.",
        "meta_lines": [
            "Chance it arrives: 40% (empirical, n=75)",
            "App says: 32 min · evidence: stalled, location 200s old",
        ],
        "backup_text": "Bluebikes Kendall — 1 min walk, bike likely (82%).",
    },
]


def render() -> None:
    page_header("Rider view")

    st.write(
        "Pick a stop to see whether each arrival is trustworthy. We show a "
        "realistic time range, not a single number, and the status word is "
        "always spelled out."
    )

    col_pick, col_mode = st.columns([2, 1])
    with col_pick:
        st.selectbox("Stop", options=list(_SAMPLE_STOPS.keys()), key="rider_stop")
    with col_mode:
        st.selectbox("Mode", options=["demo", "live", "replay"], key="rider_mode")

    st.caption("Preview only — not wired to data yet.")
    status_legend()
    st.write("")

    for pred in _SAMPLE_PREDICTIONS:
        status_card(
            title=pred["title"],
            status=pred["status"],
            headline=pred["headline"],
            why=pred["why"],
            meta_lines=pred["meta_lines"],
            backup_text=pred["backup_text"],
        )

    st.info("Hidden arrivals (non-revenue or invalid) are never shown here.")

    footer()
