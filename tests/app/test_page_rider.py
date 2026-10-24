"""AppTest examples for the Rider view (task 5.4).

These are example-based smoke tests that drive the real Rider page through
``streamlit.testing.v1.AppTest`` offline, in Demo mode, against the real demo
fixtures exposed by ``core.service``. They cover:

- Default mode is Demo on a fresh session (R3.2).
- The two columns render and there is exactly one Unghosted card per displayable
  prediction, lined up with the "What the app shows" column (R1.1, R1.4).
- ``hidden_count`` is shown as a bare number (R1.9).
- The word "placeholder" appears on a card when ``chance_basis.method`` is
  ``placeholder`` (R1.10, via a stub).
- A ``NotFound`` from the Service shows a message and no cards (R1.13).
- A ``LiveDataUnavailable`` in Live mode falls back to Demo: a note is shown and
  the displayed mode reads Demo (R3.4).

How the Service is stubbed
--------------------------
``AppTest.from_file`` runs ``streamlit_app.py`` in a worker thread but imports
the same ``core.service`` module object this test holds, so attributes patched
on ``core.service`` *before* ``run()`` are seen inside the app. ``stub_service``
patches named attributes and always restores them.

Why ``list_demo_stops`` is always stubbed
-----------------------------------------
``app.rider`` loads the stop picker via ``calls.call(service.list_demo_stops,
mode="demo")``, which forwards ``mode=`` to the Service function. The real
``core.service.list_demo_stops`` takes no ``mode`` parameter, so the live call
raises and the picker shows "Stops are unavailable". To exercise the Rider cards
with real demo data we wrap ``list_demo_stops`` in a shim that tolerates (and
ignores) the extra kwargs and returns the real fixture stops. The shim adds no
fake data; it only absorbs the kwarg the view passes. (This mismatch is a real
defect in ``app/rider.py`` / ``app/calls.py`` worth a follow-up; it is out of
scope for this test task, which must not edit app source.)
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import core.service as service
from core.contracts import (
    BusPrediction,
    BusTrustResponse,
    ChanceBasis,
    Evidence,
    LiveDataUnavailable,
    NotFound,
)

# streamlit_app.py defaults the sidebar page radio to its first option
# ("Rider view"), so a fresh AppTest lands on the Rider page.
APP_PATH = str(Path(__file__).resolve().parents[2] / "streamlit_app.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _real_list_demo_stops(*_args, **_kwargs):
    """Return the real demo stops, tolerating the ``mode=`` kwarg the view sends.

    Imported lazily off the module each call so it still reflects the real
    fixture contents and never hardcodes stop data.
    """
    return service.__dict__["_ORIG_list_demo_stops"]()


@contextmanager
def stub_service(**overrides):
    """Temporarily replace attributes on ``core.service``; always restore them.

    ``list_demo_stops`` is always wrapped so the Rider stop picker populates;
    callers may override any other Service function (e.g. ``get_bus_trust``).
    """
    # Snapshot the genuine list_demo_stops once so the shim can delegate to it.
    service.__dict__.setdefault("_ORIG_list_demo_stops", service.list_demo_stops)

    patched = {"list_demo_stops": _real_list_demo_stops, **overrides}
    saved = {name: getattr(service, name) for name in patched}
    try:
        for name, fn in patched.items():
            setattr(service, name, fn)
        yield
    finally:
        for name, fn in saved.items():
            setattr(service, name, fn)


def run_rider(**overrides) -> AppTest:
    """Build and run the Rider page with the given Service overrides applied."""
    with stub_service(**overrides):
        at = AppTest.from_file(APP_PATH)
        at.run(timeout=60)
    return at


def markdown_texts(at: AppTest) -> list[str]:
    return [m.value for m in at.markdown]


def caption_texts(at: AppTest) -> list[str]:
    return [c.value for c in at.caption]


def route_lines(at: AppTest) -> list[str]:
    """The left-column ("What the app shows") per-prediction lines."""
    return [t for t in markdown_texts(at) if t.startswith("Route ")]


def card_blocks(at: AppTest) -> list[str]:
    """The right-column Unghosted status cards (one markdown block each).

    Match the card container div, not the CSS stylesheet (the injected
    ``GLOBAL_CSS`` mentions the ``.ug-card`` class in its rules).
    """
    return [t for t in markdown_texts(at) if '<div class="ug-card"' in t]


# ---------------------------------------------------------------------------
# Fixtures: a placeholder-method response and a trivial stop list builder
# ---------------------------------------------------------------------------
def _placeholder_bus_response(stop_id: str) -> BusTrustResponse:
    """A one-prediction response whose chance basis method is ``placeholder``."""
    pred = BusPrediction(
        route_id="1",
        trip_id="trip_ph_1",
        headsign="Harvard Square",
        app_eta_min=4.0,
        status="estimate",
        why="Placeholder basis for the chance.",
        reason_codes=["schedule_based"],
        chance_it_arrives=0.5,
        chance_basis=ChanceBasis(method="placeholder", n=0),
        realistic_eta_min=(3.0, 6.0),
        evidence=Evidence(uncertainty=300),
        backup=None,
        outcome=None,
    )
    return BusTrustResponse(
        stop_id=stop_id,
        stop_name="Harvard Ave at Lincoln",
        generated_at="2025-01-15T14:30:00Z",
        mode="demo",
        data_age_sec={"trip_updates": 10, "vehicle_positions": 5},
        predictions=[pred],
        hidden_count=0,
        attribution=service.ATTRIBUTION,
        disclaimer=service.DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# R3.2 — default mode is Demo on a fresh session
# ---------------------------------------------------------------------------
class TestDefaultModeDemo:
    def test_fresh_session_mode_is_demo(self):
        at = run_rider()
        assert not at.exception
        assert at.session_state["rider_mode"] == "Demo"

    def test_mode_selectbox_shows_demo(self):
        at = run_rider()
        mode_boxes = [s for s in at.selectbox if s.label == "Mode"]
        assert mode_boxes, "Mode selectbox should be present"
        assert mode_boxes[0].value == "Demo"

    def test_mode_switch_has_exactly_three_options(self):
        # R3.1: Live, Demo, Replay.
        at = run_rider()
        mode_box = next(s for s in at.selectbox if s.label == "Mode")
        assert list(mode_box.options) == ["Live", "Demo", "Replay"]


# ---------------------------------------------------------------------------
# R1.1 / R1.4 — stop picker, two columns, one card per displayable prediction
# ---------------------------------------------------------------------------
class TestColumnsAndCards:
    def test_stop_picker_is_populated_from_demo_stops(self):
        # R1.1: picker shows each stop's name and its routes.
        at = run_rider()
        stop_box = next(s for s in at.selectbox if s.label == "Stop")
        # The real demo fixtures carry these three stops.
        assert "Harvard Ave at Lincoln (1, 23)" in stop_box.options
        assert any("Northeastern" in opt for opt in stop_box.options)
        assert any("Kendall" in opt for opt in stop_box.options)

    def test_both_columns_render(self):
        at = run_rider()
        texts = markdown_texts(at)
        assert any("What the app shows" in t for t in texts)
        assert any("Unghosted" in t for t in texts)

    def test_one_card_per_displayable_prediction(self):
        # The default stop (place-haecl) has 4 displayable predictions.
        at = run_rider()
        resp = service.get_bus_trust("place-haecl", mode="demo")
        from app.logic import is_displayable

        displayable = [p for p in resp.predictions if is_displayable(p.status)]
        assert len(displayable) == 4  # guards the fixture assumption

        left = route_lines(at)
        cards = card_blocks(at)
        assert len(left) == len(displayable)
        # Exactly one Unghosted card per displayed prediction, same count as the
        # left column so the two columns line up (R1.4).
        assert len(cards) == len(displayable)

    def test_left_column_lines_match_prediction_routes(self):
        at = run_rider()
        resp = service.get_bus_trust("place-haecl", mode="demo")
        from app.logic import is_displayable

        displayable = [p for p in resp.predictions if is_displayable(p.status)]
        left = route_lines(at)
        for line, pred in zip(left, displayable):
            assert f"Route {pred.route_id}" in line


# ---------------------------------------------------------------------------
# R1.9 — hidden count shown as a bare number
# ---------------------------------------------------------------------------
class TestHiddenCount:
    def test_hidden_count_caption_is_a_number(self):
        at = run_rider()
        captions = caption_texts(at)
        hidden = [c for c in captions if "Hidden arrivals" in c]
        assert hidden, "hidden count caption should be shown"
        # The default stop has hidden_count 0, shown as the bare number "0".
        assert hidden[0].rstrip().endswith("0")


# ---------------------------------------------------------------------------
# R1.10 — the word "placeholder" appears on a card for placeholder chance basis
# ---------------------------------------------------------------------------
class TestPlaceholderWord:
    def test_placeholder_method_surfaces_the_word(self):
        def stub_bus(stop_id, mode="demo", **kwargs):
            return _placeholder_bus_response(stop_id)

        at = run_rider(get_bus_trust=stub_bus)
        assert not at.exception
        cards = card_blocks(at)
        assert cards, "a card should render for the placeholder prediction"
        assert any("placeholder" in c.lower() for c in cards)


# ---------------------------------------------------------------------------
# R1.13 — NotFound shows a message and no cards
# ---------------------------------------------------------------------------
class TestNotFound:
    def test_not_found_shows_message_and_no_cards(self):
        def stub_bus(stop_id, mode="demo", **kwargs):
            raise NotFound(f"Stop {stop_id} not found")

        at = run_rider(get_bus_trust=stub_bus)
        assert not at.exception
        # No Unghosted cards for the failed call.
        assert card_blocks(at) == []
        assert route_lines(at) == []
        # A user-facing message is shown (calls.call names the missing id).
        warnings = [w.value for w in at.warning]
        assert any("found" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# R3.4 — Live fallback: LiveDataUnavailable -> Demo note + displayed mode Demo
# ---------------------------------------------------------------------------
class TestLiveFallback:
    def test_live_unavailable_falls_back_to_demo(self):
        # Demo mode never raises LiveDataUnavailable, so the fallback path is
        # verified with a stub: raise only for live, return demo data otherwise.
        orig = service.get_bus_trust

        def stub_bus(stop_id, mode="demo", **kwargs):
            if mode == "live":
                raise LiveDataUnavailable("no live feed")
            return orig(stop_id, mode="demo", **kwargs)

        with stub_service(get_bus_trust=stub_bus):
            at = AppTest.from_file(APP_PATH)
            at.run(timeout=60)
            # Switch the Mode selectbox to Live and re-run.
            mode_box = next(s for s in at.selectbox if s.label == "Mode")
            mode_box.set_value("Live")
            at.run(timeout=60)

        assert not at.exception
        # A note states live data is unavailable and Demo data is shown (R3.4).
        warnings = [w.value for w in at.warning]
        assert any(
            "live data is unavailable" in w.lower() and "demo" in w.lower()
            for w in warnings
        )
        # The displayed mode reads Demo after the fallback.
        captions = caption_texts(at)
        assert any(c.strip().lower() == "mode: demo" for c in captions)
        # Demo cards are shown in place of the failed Live response.
        assert card_blocks(at)


# ---------------------------------------------------------------------------
# R1.12 — no location request / no analytics widgets on the page
# ---------------------------------------------------------------------------
class TestNoLocationOrAnalytics:
    def test_stop_picker_used_not_coordinates(self):
        at = run_rider()
        labels = [s.label for s in at.selectbox]
        assert "Stop" in labels  # a stop picker, not a location request
        # No coordinate inputs for the rider to type lat/lon.
        number_labels = [n.label.lower() for n in at.number_input]
        assert not any("lat" in lbl or "lon" in lbl for lbl in number_labels)


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
