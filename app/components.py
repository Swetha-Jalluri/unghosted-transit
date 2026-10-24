"""Reusable UI components for the Unghosted app.

All components are presentation-only. They take plain dicts so they can later
be fed by core.service responses without changing their signatures.
"""
from __future__ import annotations

import html
from typing import Optional

import streamlit as st

from app.theme import (
    APP_SUBTITLE,
    APP_TAGLINE,
    APP_TITLE,
    ATTRIBUTION,
    DISCLAIMER,
    GLOBAL_CSS,
    status_style,
)


def inject_css() -> None:
    """Inject global CSS once per page render."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def page_header(page_name: str) -> None:
    """Render the shared hero header (text only, no logos)."""
    inject_css()
    st.markdown(
        f"""
        <div class="ug-hero">
            <h1>{html.escape(APP_TITLE)}</h1>
            <p class="ug-subtitle">{html.escape(APP_SUBTITLE)}</p>
            <p class="ug-tagline">{html.escape(APP_TAGLINE)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(page_name)
    st.divider()


def status_badge_html(status: str) -> str:
    """Return HTML for a status badge that ALWAYS shows the status word.

    Color is a secondary cue only; the word is required so the status is never
    communicated by color alone.
    """
    s = status_style(status)
    return (
        f'<span class="ug-badge" style="color:{s["color"]};">'
        f'{s["icon"]} {html.escape(s["label"])}'
        f"</span>"
    )


def status_card(
    *,
    title: str,
    status: str,
    headline: str,
    why: str,
    meta_lines: Optional[list[str]] = None,
    backup_text: Optional[str] = None,
) -> None:
    """Render a reusable status card.

    Parameters
    ----------
    title: primary identifier (e.g. "Route 66 -> Dudley Station" or a dock name)
    status: one of "confirmed" | "estimate" | "unreliable"
    headline: the main value line (e.g. an ETA range or usable-bikes range)
    why: short plain-language explanation
    meta_lines: optional extra detail lines (data age, sample size, evidence)
    backup_text: optional backup suggestion line
    """
    s = status_style(status)
    meta_html = ""
    if meta_lines:
        meta_html = "<br>".join(html.escape(line) for line in meta_lines)
        meta_html = f'<div class="ug-meta">{meta_html}</div>'

    backup_html = ""
    if backup_text:
        backup_html = (
            f'<div class="ug-backup">Backup: {html.escape(backup_text)}</div>'
        )

    st.markdown(
        f"""
        <div class="ug-card" style="background:{s["bg"]};">
            <div class="ug-card-head">
                <span class="ug-route">{html.escape(title)}</span>
                {status_badge_html(status)}
            </div>
            <div class="ug-why"><strong>{html.escape(headline)}</strong></div>
            <div class="ug-why">{html.escape(why)}</div>
            {meta_html}
            {backup_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_legend() -> None:
    """Render a small legend showing every status word with its color cue."""
    cols = st.columns(3)
    for col, status in zip(cols, ("confirmed", "estimate", "unreliable")):
        with col:
            st.markdown(status_badge_html(status), unsafe_allow_html=True)


def footer() -> None:
    """Render the required footer on every page: attribution + disclaimer."""
    st.markdown(
        f"""
        <div class="ug-footer">
            <div>{html.escape(ATTRIBUTION)}</div>
            <div class="ug-disclaimer">{html.escape(DISCLAIMER)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
