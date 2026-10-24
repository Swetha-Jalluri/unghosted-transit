"""AppTest examples for the static pages and the shared footer.

These drive the real Streamlit app (``streamlit_app.py``) a page at a time with
``streamlit.testing.v1.AppTest`` and assert on the rendered output. Everything
runs offline: the static pages (About, API & MCP) make no Service data call,
and the data-backed pages (Rider, Operator) still render the footer even when
their Service call fails in the test environment, which is exactly what R7.1 /
R7.8 require.

Covered:
- R7.1: the Disclaimer and Attribution appear word for word (imported from
  ``app.settings``) on every page, in every nav selection.
- R7.4: the About page has labeled Guardrails, Evals, Observability, Honest
  limits and Roadmap sections, and the Roadmap names AWS.
- R7.5: the About page lists confirmed / estimate / unreliable / hidden and
  states that ``hidden`` is never shown to users.
- R7.3: the API & MCP page omits an example and names the missing setting when
  a Settings value is empty (the ``demo_stop_coords`` block is empty by
  default), substituting no hardcoded value.
- R4.12: the "ghost"/"proven" prohibition. R4.12 scopes this to the
  Hindsight_Badge ("SHALL NOT use the words 'ghost' or 'proven' ... in any
  badge"). The static pages render no badge, so no badge can carry those words.
  The About page deliberately QUOTES the two words in prose to say what
  Unghosted does NOT claim ("we say 'disappeared before arrival', never
  'proven ghost'") and to state that user-facing text never uses them. Those
  two mentions are the point of the principle, not a violation, so the test
  pins them to their sanctioned sentences rather than banning the substrings
  outright (which would be a false failure). See ``test_about_*`` below.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.settings import ATTRIBUTION, DISCLAIMER

# Whole-word matcher for the two banned words. Word boundaries are essential:
# the brand name "Unghosted" contains the substring "ghost" but is NOT the word
# "ghost", so a naive substring scan would raise a false alarm on every page.
_GHOST_OR_PROVEN = re.compile(r"\b(ghost|proven)\b", re.IGNORECASE)

ROOT = Path(__file__).resolve().parents[2]
APP_PATH = str(ROOT / "streamlit_app.py")

# Nav options exactly as wired in streamlit_app.PAGES.
PAGES = ["Rider view", "Operator view", "API & MCP", "About"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _run_page(page: str) -> AppTest:
    """Run the app and switch the nav to ``page`` via the sidebar radio.

    A fresh ``AppTest`` starts on the default page (Rider view); selecting the
    radio value and re-running renders the requested page, with the footer
    always drawn by ``main()`` afterwards.
    """
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=60)
    # ``at.exception`` is an ElementList: empty (falsy) means no uncaught
    # exception. It is never ``None``, so test for emptiness, not identity.
    assert not at.exception, f"app raised on first run: {list(at.exception)}"
    if page != at.radio[0].value:
        at.radio[0].set_value(page).run(timeout=60)
    assert not at.exception, f"app raised rendering {page!r}: {list(at.exception)}"
    return at


def _all_text(at: AppTest) -> str:
    """Concatenate every text-bearing element rendered on the page.

    Pulls markdown, captions, subheaders, headers, titles, writes, info,
    warning, error and code blocks so a word-for-word substring check sees
    everything the page actually shows.
    """
    parts: list[str] = []
    for group in (
        at.markdown,
        at.caption,
        at.subheader,
        at.header,
        at.title,
        at.info,
        at.warning,
        at.error,
        at.success,
    ):
        parts.extend(el.value for el in group)
    # ``code`` blocks are only present on some pages; guard defensively.
    try:
        parts.extend(el.value for el in at.code)
    except Exception:  # pragma: no cover - element absent on a page
        pass
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# R7.1 - Disclaimer and Attribution on every page, word for word
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("page", PAGES)
def test_disclaimer_and_attribution_on_every_page(page: str) -> None:
    """Footer legal text appears verbatim on every page (R7.1, R7.8).

    The strings are imported from ``app.settings`` (the single source), so this
    also guards against the footer drifting from the canonical glossary text.
    The data-backed pages render their footer even when their Service call
    fails in the test environment, which is the behaviour R7.8 asks for.
    """
    at = _run_page(page)
    text = _all_text(at)
    assert DISCLAIMER in text, f"Disclaimer missing on {page!r}"
    assert ATTRIBUTION in text, f"Attribution missing on {page!r}"


# ---------------------------------------------------------------------------
# R7.4 - About page labeled sections + AWS roadmap
# ---------------------------------------------------------------------------
def test_about_has_all_labeled_sections() -> None:
    """About shows Guardrails, Evals, Observability, Honest limits, Roadmap."""
    at = _run_page("About")
    headings = {s.value.strip() for s in at.subheader}
    for required in ("Guardrails", "Evals", "Observability", "Honest limits", "Roadmap"):
        assert required in headings, f"About missing section {required!r}"


def test_about_roadmap_names_aws() -> None:
    """The roadmap names AWS in at least one item (R7.4)."""
    at = _run_page("About")
    text = _all_text(at)
    assert "AWS" in text, "Roadmap does not name AWS"


# ---------------------------------------------------------------------------
# R7.5 - Four statuses listed, hidden never shown
# ---------------------------------------------------------------------------
def test_about_lists_all_four_statuses() -> None:
    """All four status words appear on the About page (R7.5)."""
    at = _run_page("About")
    text = _all_text(at).lower()
    for status in ("confirmed", "estimate", "unreliable", "hidden"):
        assert status in text, f"status {status!r} not listed on About"


def test_about_states_hidden_is_never_shown() -> None:
    """About states that the hidden status is never shown to users (R7.5)."""
    at = _run_page("About")
    text = _all_text(at).lower()
    assert "never shown" in text, "About does not say hidden is never shown"


# ---------------------------------------------------------------------------
# R4.12 - no "ghost"/"proven" in any badge; About prose mentions are sanctioned
# ---------------------------------------------------------------------------
def test_static_pages_render_no_badge_elements() -> None:
    """R4.12 bans "ghost"/"proven" in a Hindsight_Badge.

    Static pages render no status or hindsight badges at all. A rendered badge
    is a ``<span class="ug-badge" ...>WORD</span>`` produced only by the Rider
    cards; the ``.ug-badge`` *style rule* in the injected global CSS is a
    definition, not a badge. We assert no badge SPAN is present, so no badge on
    a static page can carry either banned word in the first place.
    """
    badge_span = re.compile(r'<span[^>]*class="ug-badge"')
    for page in ("About", "API & MCP"):
        at = _run_page(page)
        text = _all_text(at)
        assert not badge_span.search(text), f"unexpected badge span on {page!r}"


def test_static_page_prose_has_no_ghost_or_proven_word() -> None:
    """No ordinary prose on the API & MCP page uses the banned words.

    The API & MCP page carries no "what we don't say" principle, so neither
    whole word should appear anywhere in its text (ignoring the brand name
    "Unghosted", which the whole-word matcher already excludes).
    """
    at = _run_page("API & MCP")
    text = _all_text(at)
    hit = _GHOST_OR_PROVEN.search(text)
    assert hit is None, f"API & MCP page uses the word {hit.group(0)!r}"


def test_about_ghost_proven_only_in_sanctioned_prose() -> None:
    """The About page only uses "ghost"/"proven" to say what we do NOT claim.

    R4.12 prohibits the words in a badge, not in prose. The About principle
    deliberately quotes them ('we say "disappeared before arrival", never
    "proven ghost"') and the Guardrails section states user-facing text never
    uses them. Both are the intended message. This test confirms every mention
    lives inside one of those two sanctioned lines, so the words never leak into
    an ordinary claim on the page.
    """
    at = _run_page("About")
    # Sanctioned lines (lower-cased) that are allowed to carry the words. Each
    # is a "what we don't say" statement, which is the point of the principle.
    sanctioned_markers = (
        'never *"proven ghost"*',  # Principles bullet (markdown emphasis)
        'the words "ghost" or "proven"',  # Guardrails sentence
    )
    # st.write text lands in at.markdown, so markdown + caption + info covers
    # every prose element the About page renders. Whole-word matching keeps the
    # brand name "Unghosted" from registering as the word "ghost".
    offenders: list[str] = []
    for el in list(at.markdown) + list(at.caption) + list(at.info):
        value = el.value
        if _GHOST_OR_PROVEN.search(value):
            low = value.lower()
            if not any(marker in low for marker in sanctioned_markers):
                offenders.append(value)
    assert not offenders, (
        "About page uses the word 'ghost'/'proven' outside the sanctioned "
        f"'what we don't say' lines: {offenders!r}"
    )


# ---------------------------------------------------------------------------
# R7.3 - API & MCP omits examples and names the missing setting
# ---------------------------------------------------------------------------
def test_api_mcp_omits_examples_and_names_missing_setting() -> None:
    """With ``demo_stop_coords`` empty (its default), examples that need a

    station id or coordinates are omitted and the missing Settings source is
    named, with no hardcoded value substituted (R7.3, R11.5).
    """
    at = _run_page("API & MCP")
    captions = [c.value for c in at.caption]
    omissions = [c for c in captions if c.startswith("Example omitted:")]
    assert omissions, "expected at least one omitted example on API & MCP"
    # Every omission names a Settings source rather than silently dropping it.
    assert any("demo_stop_coords" in c for c in omissions), (
        f"omission message does not name the missing setting: {omissions!r}"
    )


def test_api_mcp_documents_routes_and_tools_from_settings() -> None:
    """Routes and tools are documented from Settings, with the base URL shown.

    This pins the page to Settings-sourced content (R7.2) so the omission test
    above is meaningful: the page really is driven by Settings, not stubs.
    """
    at = _run_page("API & MCP")
    text = _all_text(at)
    from app.settings import SETTINGS

    assert SETTINGS.api_base_url in text, "base URL from Settings not shown"
    for path in SETTINGS.api_routes.values():
        assert path in text, f"route path {path!r} not documented"
    for tool in SETTINGS.mcp_tools:
        assert tool in text, f"MCP tool {tool!r} not documented"
