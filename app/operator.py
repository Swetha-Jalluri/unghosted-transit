"""Operator view.

For bikeshare operations and MBTA/city analysts: aggregate reliability
findings, the least reliable docks, and model calibration at a glance.

Placeholder content only -- no data calls yet. Numbers shown are illustrative
and marked as a preview, never presented as measured results.
"""
from __future__ import annotations

import streamlit as st

from app.components import footer, page_header, status_card


def render() -> None:
    page_header("Operator view")

    st.warning(
        "Preview only. These figures are illustrative placeholders, not measured "
        "findings. Real numbers come from logged data once wired in.",
        icon="⚠️",
    )

    st.subheader("Reliability at a glance")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Labeled arrivals", "—")
    c2.metric("Served", "—")
    c3.metric("Disappeared before arrival", "—")
    c4.metric("Canceled", "—")

    st.subheader("Least reliable docks")
    status_card(
        title="Bluebikes Mission",
        status="unreliable",
        headline="Often empty on arrival",
        why="High drain rate and aged data at peak hours (preview).",
        meta_lines=["Metric: placeholder", "Sample size: placeholder"],
    )
    status_card(
        title="Bluebikes Harvard",
        status="estimate",
        headline="Usually has bikes",
        why="Moderate turnover; watch during morning rush (preview).",
        meta_lines=["Metric: placeholder", "Sample size: placeholder"],
    )

    st.subheader("Model calibration")
    st.caption(
        "Calibration curve and ETA-range hit rate will render here once findings "
        "are available. We never claim certainty — every output carries its "
        "sample size and method."
    )
    st.empty()

    footer()
