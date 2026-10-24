"""Shared constants and styling for the Unghosted app.

Product rules enforced here:
- Always show the status word, never color alone.
- Every page shows attribution and the disclaimer.
- No logos, no analytics, no location requests.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Branding (text only, no logos / brand marks)
# ---------------------------------------------------------------------------
APP_TITLE = "Unghosted"
APP_SUBTITLE = "A trust layer for transit apps"
APP_TAGLINE = "Apps tell you when. We tell you whether."

# ---------------------------------------------------------------------------
# Required legal text (kept identical to the product + contract rules)
# ---------------------------------------------------------------------------
DISCLAIMER = (
    "Unofficial. Not affiliated with or endorsed by MBTA, MassDOT or Bluebikes. "
    "For information only."
)

ATTRIBUTION = (
    "Data: MBTA GTFS-realtime (MassDOT Developers License Agreement); "
    "Bluebikes GBFS (Bluebikes Data License Agreement)."
)

# ---------------------------------------------------------------------------
# Status vocabulary. The word is primary; color is a secondary cue only.
# confirmed = green, estimate = amber, unreliable = red.
# "hidden" is never rendered as a card (never shown to riders).
# ---------------------------------------------------------------------------
STATUS_STYLES: dict[str, dict[str, str]] = {
    "confirmed": {
        "label": "Confirmed",
        "color": "#1F9D55",   # green
        "bg": "#E8F6EF",
        "icon": "✓",
    },
    "estimate": {
        "label": "Estimate",
        "color": "#B7791F",   # amber
        "bg": "#FBF3E2",
        "icon": "≈",
    },
    "unreliable": {
        "label": "Unreliable",
        "color": "#C53030",   # red
        "bg": "#FBEAEA",
        "icon": "!",
    },
}


def status_style(status: str) -> dict[str, str]:
    """Return the style dict for a status, falling back to a neutral style."""
    return STATUS_STYLES.get(
        status,
        {"label": status.title(), "color": "#4A5568", "bg": "#EDF2F7", "icon": "?"},
    )


# ---------------------------------------------------------------------------
# Global CSS injected once per page.
# ---------------------------------------------------------------------------
GLOBAL_CSS = """
<style>
.block-container { padding-top: 2.2rem; max-width: 980px; }

.ug-hero h1 { margin-bottom: 0.1rem; font-weight: 800; letter-spacing: -0.5px; }
.ug-hero .ug-subtitle { font-size: 1.05rem; color: #4A5568; margin: 0; }
.ug-hero .ug-tagline { font-size: 1.15rem; font-weight: 600; color: #2563EB; margin-top: 0.35rem; }

.ug-card {
    border-radius: 12px;
    padding: 1rem 1.15rem;
    margin-bottom: 0.85rem;
    border: 1px solid rgba(0,0,0,0.06);
}
.ug-card .ug-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
}
.ug-card .ug-route {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1A1F2B;
}
.ug-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.3px;
    text-transform: uppercase;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    border: 1px solid currentColor;
}
.ug-card .ug-why { color: #3A4252; margin: 0.5rem 0 0.35rem; }
.ug-card .ug-meta { font-size: 0.85rem; color: #5A6473; }
.ug-card .ug-backup {
    margin-top: 0.6rem;
    padding-top: 0.55rem;
    border-top: 1px dashed rgba(0,0,0,0.12);
    font-size: 0.88rem;
    color: #3A4252;
}

.ug-footer {
    margin-top: 2.5rem;
    padding-top: 1rem;
    border-top: 1px solid rgba(0,0,0,0.08);
    font-size: 0.78rem;
    color: #6B7280;
    line-height: 1.5;
}
.ug-footer .ug-disclaimer { font-weight: 600; color: #4A5568; }
</style>
"""
