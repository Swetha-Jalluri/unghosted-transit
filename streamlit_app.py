"""Unghosted — Streamlit app entry point.

"A trust layer for transit apps. Apps tell you when. We tell you whether."

Run from the repo root:
    uv run streamlit run streamlit_app.py

Pages live in app/. This file only wires up page config and navigation.
Placeholder content only — no data calls yet.
"""
from __future__ import annotations

import streamlit as st

from app import about, api_mcp, operator, rider
from app.components import footer
from app.theme import APP_SUBTITLE, APP_TITLE

st.set_page_config(
    page_title=f"{APP_TITLE} — {APP_SUBTITLE}",
    page_icon="🚦",
    layout="centered",
    initial_sidebar_state="expanded",
    menu_items={"About": APP_SUBTITLE},
)

PAGES = {
    "Rider view": rider.render,
    "Operator view": operator.render,
    "API & MCP": api_mcp.render,
    "About": about.render,
}


def main() -> None:
    # Session default: start in Demo mode (sample data, no live feeds).
    st.session_state.setdefault("rider_mode", "Demo")

    with st.sidebar:
        st.markdown(f"### {APP_TITLE}")
        st.caption(APP_SUBTITLE)
        choice = st.radio("Go to", list(PAGES.keys()), label_visibility="collapsed")

    # Render the selected page, then always render the footer — including error
    # states — so Disclaimer and Attribution appear on every page (R3.2, R7.1).
    try:
        PAGES[choice]()
    finally:
        footer()


if __name__ == "__main__":
    main()
