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
# Required legal text. Single source of truth is app.settings; theme only
# re-exports so existing imports (components.py) keep working unchanged.
# ---------------------------------------------------------------------------
from app.settings import ATTRIBUTION, DISCLAIMER  # noqa: E402,F401  (re-export)

# ---------------------------------------------------------------------------
# Status vocabulary. The word is primary; color is a secondary cue only.
# confirmed = green, estimate = amber, unreliable = red.
# "hidden" is never rendered as a card (never shown to riders).
#
# Colors are tuned for a Jet Black (#0A0A0A) background: bright, high-contrast
# (WCAG AA) foregrounds with a faint translucent fill. The unreliable red
# (#FF5C57, a warm orange-red) is deliberately kept a different hue from the
# Neon Rose accent (#FF2D95, a magenta pink) so the two are never confused.
# ---------------------------------------------------------------------------
STATUS_STYLES: dict[str, dict[str, str]] = {
    "confirmed": {
        "label": "Confirmed",
        "color": "#3DD68C",            # green (bright on black)
        "bg": "rgba(61,214,140,0.10)",
        "icon": "✓",
    },
    "estimate": {
        "label": "Estimate",
        "color": "#F5B544",            # amber
        "bg": "rgba(245,181,68,0.10)",
        "icon": "≈",
    },
    "unreliable": {
        "label": "Unreliable",
        "color": "#FF5C57",            # red — warm, distinct from Neon Rose
        "bg": "rgba(255,92,87,0.10)",
        "icon": "!",
    },
}


def status_style(status: str) -> dict[str, str]:
    """Return the style dict for a status, falling back to a neutral style."""
    return STATUS_STYLES.get(
        status,
        {
            "label": status.title(),
            "color": "#9AA3B2",
            "bg": "rgba(154,163,178,0.10)",
            "icon": "?",
        },
    )


# ---------------------------------------------------------------------------
# Global CSS injected once per page.
#
# Futuristic editorial landing look on Jet Black:
#   - Space Grotesk display font for the oversized headline, Inter for body
#     (loaded from Google Fonts, with system fallbacks).
#   - Oversized "Unghosted" headline with tight tracking and a Cerulean Blue ->
#     Neon Rose gradient.
#   - Small uppercase nav-style labels, generous whitespace, thin dividers.
#   - Dark rounded cards with a subtle glowing border.
# All foreground text meets WCAG AA contrast on #0A0A0A.
# ---------------------------------------------------------------------------
GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {
    --ug-bg: #0A0A0A;
    --ug-panel: #141416;
    --ug-text: #ECECEC;
    --ug-muted: #9AA3B2;
    --ug-cerulean: #007BA7;
    --ug-cerulean-bright: #29A8D6;
    --ug-rose: #FF2D95;
    --ug-line: rgba(255,255,255,0.08);
    --ug-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --ug-display: 'Space Grotesk', 'Inter', -apple-system, 'Segoe UI', sans-serif;
}

html, body, [class*="css"], .stApp {
    font-family: var(--ug-sans);
    color: var(--ug-text);
}
.stApp { background: var(--ug-bg); }

.block-container {
    padding-top: 3rem;
    padding-bottom: 3rem;
    max-width: 1020px;
}

/* --- Sidebar --------------------------------------------------------- */
section[data-testid="stSidebar"] {
    background: #0D0D0F;
    border-right: 1px solid var(--ug-line);
}
section[data-testid="stSidebar"] h3 {
    font-family: var(--ug-display);
    letter-spacing: -0.5px;
    font-weight: 700;
}

/* --- Hero headline --------------------------------------------------- */
.ug-hero { margin-bottom: 0.4rem; }
.ug-hero h1 {
    font-family: var(--ug-display);
    font-size: clamp(3.4rem, 9vw, 6rem);
    line-height: 0.95;
    font-weight: 700;
    letter-spacing: -0.045em;
    margin: 0 0 0.35rem;
    background: linear-gradient(100deg, var(--ug-cerulean) 0%, var(--ug-cerulean-bright) 42%, var(--ug-rose) 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    color: var(--ug-rose); /* fallback for browsers without text-fill */
}
.ug-hero .ug-subtitle {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.26em;
    font-weight: 600;
    color: var(--ug-muted);
    margin: 0;
}
.ug-hero .ug-tagline {
    font-size: 1.2rem;
    font-weight: 500;
    color: var(--ug-text);
    margin-top: 0.9rem;
    max-width: 48ch;
}

/* small uppercase nav-style label under the hero (st.caption) */
.ug-hero + div [data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
    text-transform: uppercase;
    letter-spacing: 0.22em;
    font-size: 0.72rem;
    color: var(--ug-muted);
}

/* --- Thin divider lines ---------------------------------------------- */
hr, [data-testid="stDivider"] {
    border: none;
    border-top: 1px solid var(--ug-line);
}

/* Section subheaders in editorial uppercase */
h2, h3 {
    font-family: var(--ug-display);
    letter-spacing: -0.01em;
    font-weight: 600;
}

/* --- Cards ----------------------------------------------------------- */
.ug-card {
    position: relative;
    border-radius: 16px;
    padding: 1.15rem 1.3rem;
    margin-bottom: 1rem;
    background: var(--ug-panel);
    border: 1px solid var(--ug-line);
    box-shadow:
        0 0 0 1px rgba(0,123,167,0.12),
        0 0 22px -6px rgba(0,123,167,0.35);
    transition: box-shadow 0.25s ease, border-color 0.25s ease;
}
.ug-card:hover {
    border-color: rgba(0,123,167,0.45);
    box-shadow:
        0 0 0 1px rgba(0,123,167,0.25),
        0 0 30px -4px rgba(0,123,167,0.5);
}
.ug-card .ug-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
}
.ug-card .ug-route {
    font-family: var(--ug-display);
    font-size: 1.1rem;
    font-weight: 600;
    letter-spacing: -0.01em;
    color: var(--ug-text);
}
.ug-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding: 0.24rem 0.7rem;
    border-radius: 999px;
    border: 1px solid currentColor;
    background: rgba(255,255,255,0.03);
}
.ug-card .ug-why { color: var(--ug-text); margin: 0.6rem 0 0.35rem; }
.ug-card .ug-why strong { color: #FFFFFF; }
.ug-card .ug-meta { font-size: 0.84rem; color: var(--ug-muted); line-height: 1.55; }
.ug-card .ug-backup {
    margin-top: 0.7rem;
    padding-top: 0.6rem;
    border-top: 1px dashed var(--ug-line);
    font-size: 0.88rem;
    color: #C9CFDA;
}

/* --- Footer ---------------------------------------------------------- */
.ug-footer {
    margin-top: 3rem;
    padding-top: 1.1rem;
    border-top: 1px solid var(--ug-line);
    font-size: 0.76rem;
    color: var(--ug-muted);
    line-height: 1.6;
}
.ug-footer .ug-disclaimer { font-weight: 600; color: #C9CFDA; }
</style>
"""
