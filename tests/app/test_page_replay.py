"""AppTest examples for the Replay scaffolding (``app/replay.py``).

These are example-based (not property) tests that drive the replay controls
through ``streamlit.testing.v1.AppTest``. They run offline: ``core.service``
is never called for real; ``app.replay.get_replay_window`` is stubbed with a
known window before the script runs, and the snapshot renderer passed to
``render_replay`` is a small stub that records or signals success/failure.

A tiny wrapper function is handed to ``AppTest.from_function``; it imports
Streamlit and ``app.replay`` locally (AppTest re-executes the wrapper source as
a fresh script, so only its local imports and module-level patches are visible)
and calls ``app.replay.render_replay`` with the stub. The stub for
``get_replay_window`` is installed with ``patch.object`` on the ``app.replay``
module *before* ``at.run()`` so the patched reference is in place when the
script executes.

Covered:
- Slider bounds come straight from the window (R4.1).
- Hindsight badge text surfaces in the rendered card markdown (R4.6).
- A bad window disables the controls and shows "replay data is unavailable"
  (R4.13).
- A snapshot that fails to load stops playback, keeps the last good data and
  shows "snapshot could not be loaded" (R4.14).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

import app.replay as replay
from app.replay import (
    KEY_LAST_OK_TS,
    KEY_REPLAY_PLAYING,
    KEY_REPLAY_TS,
    MSG_SNAPSHOT_FAILED,
    MSG_WINDOW_UNAVAILABLE,
)
from core.contracts import ReplayWindow

# A known, well-formed replay window reused across the good-path tests.
WIN_START = 1_700_000_000
WIN_END = 1_700_000_600
WIN_STEP = 60
WIN_SNAPSHOTS = 11


def _window(mode: str = "demo") -> ReplayWindow:
    """A valid replay window spanning 10 steps of 60 s each."""
    return ReplayWindow(
        start=WIN_START,
        end=WIN_END,
        step_sec=WIN_STEP,
        n_snapshots=WIN_SNAPSHOTS,
    )


# ---------------------------------------------------------------------------
# Harness wrappers. AppTest.from_function re-runs the wrapper *source* as a
# fresh script, so each wrapper imports what it needs locally and relies on the
# module-level patch of app.replay.get_replay_window installed by the test.
# ---------------------------------------------------------------------------
def _harness_ok() -> None:
    """Render replay with a snapshot renderer that always succeeds."""
    import app.replay as replay

    replay.render_replay(lambda ts: True)


def _harness_served_badge() -> None:
    """Render a 'served' prediction card inside the replay snapshot."""
    import app.replay as replay
    from app.components import status_card

    def render_snapshot(at_ts: int) -> bool:
        status_card(
            title="Route 66",
            status="unreliable",
            headline="Realistically 3-7 min",
            why="prediction looked shaky",
            chance=0.42,
            chance_n=12,
            chance_method="empirical",
            realistic_eta_min=[3, 7],
            outcome="served",
            replay_ts=at_ts,
            app_eta_min=5,
        )
        return True

    replay.render_replay(render_snapshot)


def _harness_vanished_badge() -> None:
    """Render a 'vanished' prediction card inside the replay snapshot."""
    import app.replay as replay
    from app.components import status_card

    def render_snapshot(at_ts: int) -> bool:
        status_card(
            title="Route 1",
            status="unreliable",
            headline="Realistically 1-2 min",
            why="disappeared from the feed",
            chance=0.1,
            chance_n=8,
            chance_method="empirical",
            realistic_eta_min=[1, 2],
            outcome="vanished",
            replay_ts=at_ts,
            app_eta_min=4,
        )
        return True

    replay.render_replay(render_snapshot)


def _harness_snapshot_fails() -> None:
    """Render replay with a snapshot renderer that always fails."""
    import app.replay as replay

    replay.render_replay(lambda ts: False)


# ---------------------------------------------------------------------------
# R4.1 - slider bounds come from get_replay_window.
# ---------------------------------------------------------------------------
class TestSliderBounds:
    def test_slider_min_max_step_match_window(self):
        """Validates: Requirements 4.1"""
        with patch.object(replay, "get_replay_window", _window):
            at = AppTest.from_function(_harness_ok)
            at.run()

        assert not at.exception
        assert len(at.slider) == 1
        bounds = at.slider[0]
        # min == start, max == end, step == step_sec (R4.1). Streamlit stores
        # the numeric slider bounds as floats.
        assert bounds.min == float(WIN_START)
        assert bounds.max == float(WIN_END)
        assert bounds.step == float(WIN_STEP)

    def test_initial_slider_value_is_start(self):
        """Validates: Requirements 4.1"""
        with patch.object(replay, "get_replay_window", _window):
            at = AppTest.from_function(_harness_ok)
            at.run()

        assert not at.exception
        # The replay clock seeds at start and the slider shows it.
        assert at.session_state[KEY_REPLAY_TS] == WIN_START
        assert at.slider[0].value == float(WIN_START)

    def test_play_control_present_and_enabled(self):
        """Validates: Requirements 4.1"""
        with patch.object(replay, "get_replay_window", _window):
            at = AppTest.from_function(_harness_ok)
            at.run()

        assert not at.exception
        play = [b for b in at.button if b.key == "replay_play"]
        assert len(play) == 1
        assert play[0].disabled is False


# ---------------------------------------------------------------------------
# R4.6 - hindsight badge text surfaces on the rendered card.
# ---------------------------------------------------------------------------
class TestHindsightBadge:
    def _markdown_text(self, at) -> str:
        return " ".join(m.value for m in at.markdown)

    def test_served_outcome_shows_served_badge(self):
        """Validates: Requirements 4.6"""
        with patch.object(replay, "get_replay_window", _window):
            at = AppTest.from_function(_harness_served_badge)
            at.run()

        assert not at.exception
        text = self._markdown_text(at)
        assert "served" in text.lower()

    def test_vanished_outcome_shows_disappeared_badge(self):
        """Validates: Requirements 4.6"""
        with patch.object(replay, "get_replay_window", _window):
            at = AppTest.from_function(_harness_vanished_badge)
            at.run()

        assert not at.exception
        text = self._markdown_text(at)
        # app_eta_min=4 is rounded to N; the badge reads "disappeared N min later".
        assert "disappeared 4 min later" in text

    def test_badge_never_uses_ghost_or_proven(self):
        """Validates: Requirements 4.6"""
        with patch.object(replay, "get_replay_window", _window):
            at = AppTest.from_function(_harness_served_badge)
            at.run()

        assert not at.exception
        text = self._markdown_text(at).lower()
        assert "ghost" not in text
        assert "proven" not in text


# ---------------------------------------------------------------------------
# R4.13 - a bad window disables controls and shows the fixed message.
#
# A window is "bad" when the service call fails, n_snapshots == 0, or end <
# start. All three reach the same disabled-controls branch, so they are checked
# together.
# ---------------------------------------------------------------------------
class TestBadWindow:
    @staticmethod
    def _empty_window(mode: str = "demo") -> ReplayWindow:
        return ReplayWindow(
            start=WIN_START, end=WIN_END, step_sec=WIN_STEP, n_snapshots=0
        )

    @staticmethod
    def _inverted_window(mode: str = "demo") -> ReplayWindow:
        # end earlier than start.
        return ReplayWindow(
            start=WIN_END, end=WIN_START, step_sec=WIN_STEP, n_snapshots=5
        )

    @staticmethod
    def _raising_window(mode: str = "demo") -> ReplayWindow:
        raise RuntimeError("window lookup failed")

    @pytest.mark.parametrize(
        "stub",
        [
            pytest.param(_empty_window.__func__, id="n_snapshots_zero"),
            pytest.param(_inverted_window.__func__, id="end_before_start"),
            pytest.param(_raising_window.__func__, id="call_raises"),
        ],
    )
    def test_bad_window_disables_controls_and_shows_message(self, stub):
        """Validates: Requirements 4.13"""
        with patch.object(replay, "get_replay_window", stub):
            at = AppTest.from_function(_harness_ok)
            at.run()

        # The controls must still render (no crash) with the slider and play
        # disabled, and the fixed message shown (R4.13).
        assert not at.exception
        assert len(at.slider) == 1
        assert at.slider[0].disabled is True
        assert len(at.button) == 1
        assert at.button[0].disabled is True
        warnings = [w.value for w in at.warning]
        assert MSG_WINDOW_UNAVAILABLE in warnings


# ---------------------------------------------------------------------------
# R4.14 - a failed snapshot stops playback, keeps the last good data and shows
# the fixed message.
# ---------------------------------------------------------------------------
class TestSnapshotFailure:
    def test_failed_snapshot_shows_message_and_stops_playback(self):
        """Validates: Requirements 4.14"""
        with patch.object(replay, "get_replay_window", _window):
            at = AppTest.from_function(_harness_snapshot_fails)
            at.run()

        assert not at.exception
        warnings = [w.value for w in at.warning]
        assert MSG_SNAPSHOT_FAILED in warnings
        # Playback is stopped (R4.14).
        assert at.session_state[KEY_REPLAY_PLAYING] is False

    def test_failed_snapshot_keeps_last_good_timestamp(self):
        """Validates: Requirements 4.14"""
        with patch.object(replay, "get_replay_window", _window):
            at = AppTest.from_function(_harness_snapshot_fails)
            at.run()

        assert not at.exception
        # The replay time is restored to the last good timestamp, which on the
        # first render is the window start.
        assert at.session_state[KEY_REPLAY_TS] == at.session_state[KEY_LAST_OK_TS]
        assert at.session_state[KEY_REPLAY_TS] == WIN_START
