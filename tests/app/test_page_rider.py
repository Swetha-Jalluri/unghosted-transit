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

Why the Service is stubbed with fixed contract models
-----------------------------------------------------
``app.rider`` loads the stop picker via ``calls.call(service.list_demo_stops,
mode="demo")`` and then renders ``get_bus_trust(stop_id, mode="demo")``. A's
real demo Service exposes its own live demo stops and raises ``NotFound`` for
bus-trust in demo mode, so a content/shape test must not depend on it. Instead
these tests install fixed, valid contract models (``DemoStop`` list and a
``BusTrustResponse`` built in :func:`_fixed_bus_response`) over ``core.service``
and assert against those fixtures, reading ids/names back from them rather than
hardcoding any value. ``list_demo_stops`` is wrapped in a shim that tolerates
(and ignores) the ``mode=`` kwarg the view forwards.
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
    DemoStop,
    Evidence,
    LiveDataUnavailable,
    NotFound,
)

# streamlit_app.py defaults the sidebar page radio to its first option
# ("Rider view"), so a fresh AppTest lands on the Rider page.
APP_PATH = str(Path(__file__).resolve().parents[2] / "streamlit_app.py")


# ---------------------------------------------------------------------------
# Fixed contract-model demo data (not A's live demo data).
#
# Ids/names live only here as fixed test data; assertions read them back from
# these fixtures instead of hardcoding literals.
# ---------------------------------------------------------------------------
_FIXED_DEMO_STOPS = (
    DemoStop(stop_id="fixed-stop-a", name="Fixed Stop A", routes=["1", "23"]),
    DemoStop(stop_id="fixed-stop-b", name="Fixed Stop B", routes=["39"]),
)

# The default stop the Rider picker lands on is the first option; keep a handle
# so tests can rebuild the exact response the page renders for it.
_DEFAULT_STOP = _FIXED_DEMO_STOPS[0]


def _fixed_demo_stops(*_args, **_kwargs):
    """Return fresh copies of the fixed demo stops, ignoring any ``mode=`` kwarg."""
    return [s.model_copy(deep=True) for s in _FIXED_DEMO_STOPS]


def _fixed_bus_response(stop_id: str, mode: str = "demo", **_kwargs) -> BusTrustResponse:
    """Build a fixed, valid ``BusTrustResponse`` with four displayable predictions.

    Statuses are all displayable (confirmed/estimate/unreliable) so the Rider
    renders one card per prediction; ``hidden_count`` is a bare number. Carries
    the Service's own legal text so the page's disclaimer/attribution render.
    """
    specs = [
        ("1", "confirmed", 0.9),
        ("23", "estimate", 0.6),
        ("39", "unreliable", 0.3),
        ("57", "estimate", 0.5),
    ]
    predictions = [
        BusPrediction(
            route_id=route,
            trip_id=f"fixed-trip-{i}",
            headsign="Downtown",
            app_eta_min=float(3 + i),
            status=status,
            why="Fixed prediction for the Rider view test.",
            reason_codes=["vehicle_reporting"],
            chance_it_arrives=chance,
            chance_basis=ChanceBasis(method="empirical", n=30),
            realistic_eta_min=(float(2 + i), float(5 + i)),
            evidence=Evidence(uncertainty=60),
            backup=None,
            outcome=None,
        )
        for i, (route, status, chance) in enumerate(specs)
    ]
    return BusTrustResponse(
        stop_id=stop_id,
        stop_name=f"Stop {stop_id}",
        generated_at="2026-01-01T00:00:00Z",
        mode=mode,
        data_age_sec={"trip_updates": 10, "vehicle_positions": 5},
        predictions=predictions,
        hidden_count=0,
        attribution=service.ATTRIBUTION,
        disclaimer=service.DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@contextmanager
def stub_service(**overrides):
    """Temporarily replace attributes on ``core.service``; always restore them.

    ``list_demo_stops`` and ``get_bus_trust`` default to the fixed contract
    models above so the Rider renders deterministic data offline; callers may
    override either (or any other Service function).
    """
    patched = {
        "list_demo_stops": _fixed_demo_stops,
        "get_bus_trust": _fixed_bus_response,
        **overrides,
    }
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
        # R1.1: picker shows each stop's name and its routes. Options are
        # derived from the fixed demo stops, not hardcoded strings.
        at = run_rider()
        stop_box = next(s for s in at.selectbox if s.label == "Stop")
        for stop in _FIXED_DEMO_STOPS:
            expected = f"{stop.name} ({', '.join(stop.routes)})"
            assert expected in stop_box.options, (
                f"picker missing option {expected!r}; got {list(stop_box.options)!r}"
            )

    def test_both_columns_render(self):
        at = run_rider()
        texts = markdown_texts(at)
        assert any("What the app shows" in t for t in texts)
        assert any("Unghosted" in t for t in texts)

    def test_one_card_per_displayable_prediction(self):
        # The default stop renders the fixed response (four displayable
        # predictions). The expected count is derived from that fixture.
        at = run_rider()
        resp = _fixed_bus_response(_DEFAULT_STOP.stop_id, mode="demo")
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
        resp = _fixed_bus_response(_DEFAULT_STOP.stop_id, mode="demo")
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
        # verified with a stub: raise only for live, return the fixed demo
        # response otherwise.
        def stub_bus(stop_id, mode="demo", **kwargs):
            if mode == "live":
                raise LiveDataUnavailable("no live feed")
            return _fixed_bus_response(stop_id, mode="demo")

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
