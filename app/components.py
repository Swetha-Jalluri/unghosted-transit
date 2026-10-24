"""Reusable UI components for the Unghosted app.

All components are presentation-only. They take plain dicts so they can later
be fed by core.service responses without changing their signatures.
"""
from __future__ import annotations

import html
from typing import Any, Optional, Sequence

import streamlit as st

from app.logic import fmt_metric, format_chance, hindsight_badge
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


def realistic_range_text(realistic_eta_min: Optional[Sequence[float]]) -> Optional[str]:
    """Format a ``[low, high]`` realistic ETA range as ``"3-7 min"``.

    Returns ``None`` when the range is missing or malformed so the caller can
    omit the line entirely. A low value equal to the high value renders as a
    single figure (e.g. ``"5 min"``).
    """
    if not realistic_eta_min or len(realistic_eta_min) != 2:
        return None
    low, high = realistic_eta_min
    low_text = fmt_metric(low)
    high_text = fmt_metric(high)
    if low_text == "not available" or high_text == "not available":
        return None
    if low_text == high_text:
        return f"{low_text} min"
    return f"{low_text}-{high_text} min"


def chance_text(
    chance: Optional[float],
    n: int,
    method: str,
) -> str:
    """Format a chance line for a card using the shared logic helper.

    The ``placeholder`` method surfaces the word "placeholder" so unmeasured
    numbers are never shown as measured (R1.5, R1.10). Delegates to
    ``app.logic.format_chance`` so the wording stays in one place.
    """
    return format_chance(chance, n, method)


def status_card(
    *,
    title: str,
    status: str,
    headline: str,
    why: str,
    chance: Optional[float] = None,
    chance_n: Optional[int] = None,
    chance_method: Optional[str] = None,
    realistic_eta_min: Optional[Sequence[float]] = None,
    meta_lines: Optional[list[str]] = None,
    backup_text: Optional[str] = None,
    outcome: Optional[str] = None,
    replay_ts: Optional[float] = None,
    app_eta_min: Optional[float] = None,
) -> None:
    """Render a reusable status card.

    The Status_Label word is ALWAYS shown (never color alone). Chance text, the
    realistic ETA range, the backup line and the replay hindsight badge are all
    optional and only render when the relevant data is supplied.

    Parameters
    ----------
    title: primary identifier (e.g. "Route 66 -> Dudley Station" or a dock name)
    status: one of "confirmed" | "estimate" | "unreliable"
    headline: the main value line (e.g. an ETA range or usable-bikes range)
    why: short plain-language explanation
    chance: 0..1 probability; ``None`` reads "chance unavailable"
    chance_n: sample size shown with the chance (always displayed when chance
        text is rendered)
    chance_method: chance basis method ("model" | "empirical" | "placeholder");
        the placeholder method adds the word "placeholder" to the chance line
    realistic_eta_min: optional ``[low, high]`` realistic ETA range in minutes
    meta_lines: optional extra detail lines (data age, sample size, evidence)
    backup_text: optional backup suggestion line
    outcome: optional replay outcome ("served" | "vanished" | "canceled" |
        "open"); drives the hindsight badge
    replay_ts: optional replay timestamp, used to compute the vanished badge
    app_eta_min: optional app ETA in minutes, used to compute the vanished badge
    """
    s = status_style(status)

    range_text = realistic_range_text(realistic_eta_min)
    range_html = ""
    if range_text:
        range_html = (
            f'<div class="ug-meta">Realistic: {html.escape(range_text)}</div>'
        )

    chance_html = ""
    if chance_n is not None and chance_method is not None:
        chance_line = chance_text(chance, chance_n, chance_method)
        chance_html = (
            f'<div class="ug-meta">Chance: {html.escape(chance_line)}</div>'
        )

    meta_html = ""
    if meta_lines:
        meta_html = "<br>".join(html.escape(line) for line in meta_lines)
        meta_html = f'<div class="ug-meta">{meta_html}</div>'

    badge_html = ""
    badge_text = hindsight_badge(outcome, replay_ts, app_eta_min)
    if badge_text:
        badge_html = (
            f'<div class="ug-meta">Hindsight: '
            f'<strong>{html.escape(badge_text)}</strong></div>'
        )

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
            {range_html}
            {chance_html}
            {meta_html}
            {badge_html}
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


def placeholder_label(label: str, is_placeholder: bool) -> str:
    """Return ``label`` with the word "placeholder" appended when requested.

    When ``is_placeholder`` is true every table, chart and metric label must
    carry the word "placeholder" so unmeasured figures are never read as
    measured results (R5.8). Already-placeholder labels are left unchanged.
    """
    if is_placeholder and "placeholder" not in label.lower():
        return f"{label} (placeholder)"
    return label


def small_metric(
    label: str,
    value: Any,
    *,
    is_placeholder: bool = False,
    help_text: Optional[str] = None,
) -> None:
    """Render a single metric with a placeholder-aware label.

    ``value`` is passed through ``app.logic.fmt_metric`` so ``None`` reads
    "not available" and zero stays "0". When ``is_placeholder`` is true the
    word "placeholder" is added to the label (R5.8, R6.2).
    """
    display_value = value if isinstance(value, str) else fmt_metric(value)
    st.metric(
        label=placeholder_label(label, is_placeholder),
        value=display_value,
        help=help_text,
    )


def small_table(
    title: str,
    rows: Sequence[dict[str, Any]],
    *,
    is_placeholder: bool = False,
    empty_text: str = "no data",
) -> None:
    """Render a small table with a placeholder-aware caption.

    ``rows`` is a sequence of plain dicts (column name to value). An empty
    sequence renders ``empty_text`` instead of a table. When ``is_placeholder``
    is true the word "placeholder" is added to the table title (R5.8).
    """
    st.caption(placeholder_label(title, is_placeholder))
    if not rows:
        st.write(empty_text)
        return
    st.table(list(rows))


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
