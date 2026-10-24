"""Replay scaffolding for the Rider view (owner B).

Replay mode lets a user scrub a time slider over logged snapshots and, with
play, step through them automatically. This module owns only the *scaffolding*:
the time window, the slider, the play/pause control, the advancing clock and
the error handling. It does not render bus or dock cards itself -- that wiring
lives in ``app/rider.py`` (task 6.2), which calls :func:`render_replay` with a
callback that fetches and draws the cards for a given ``at_ts``.

Design rules implemented here (R4.1-R4.5, R4.13, R4.14):

- The window comes from ``core.service.get_replay_window()`` through
  ``app.calls.call``: the slider spans ``start`` (min) to ``end`` (max) in steps
  of ``step_sec``, starting at ``start``.
- Playing uses a Streamlit fragment created dynamically so ``run_every`` can be
  switched on while playing and off while paused:
  ``tick = step_sec / SETTINGS.replay_play_speed`` real seconds per step.
- The clock advances with ``logic.next_replay_ts`` and stops exactly at ``end``.
- All shown times use ``logic.format_ny_time`` (NY zone abbreviation always
  shown).
- A snapshot that fails to load stops playback, keeps the last good data and
  shows "snapshot could not be loaded".
- A bad window (call fails, ``n_snapshots == 0`` or ``end < start``) disables the
  slider and play and shows "replay data is unavailable".

Session keys (per design): ``replay_ts``, ``replay_playing``,
``last_ok_replay_ts``.
"""
from __future__ import annotations

from typing import Callable, Optional

import streamlit as st

from app.calls import call
from app.logic import format_ny_time, next_replay_ts
from app.settings import SETTINGS
from core.service import get_replay_window

# Session-state keys (kept in one place so rider.py can reuse them).
KEY_REPLAY_TS = "replay_ts"
KEY_REPLAY_PLAYING = "replay_playing"
KEY_LAST_OK_TS = "last_ok_replay_ts"

# User-facing messages (fixed wording the tests and design rely on).
MSG_WINDOW_UNAVAILABLE = "replay data is unavailable"
MSG_SNAPSHOT_FAILED = "snapshot could not be loaded"

# A callback that renders bus/dock cards for one snapshot timestamp. It returns
# True on success and False when the snapshot could not be loaded, so replay can
# stop playback and keep the last good data. rider.py supplies this in task 6.2.
SnapshotRenderer = Callable[[int], bool]


def _window_is_bad(result) -> bool:
    """Return True when the replay window cannot drive a usable slider.

    A window is bad when the service call failed, it reports no snapshots, or
    its end precedes its start (R4.13, R4.14).
    """
    if not result.ok or result.value is None:
        return True
    window = result.value
    if window.n_snapshots <= 0:
        return True
    if window.end < window.start:
        return True
    return False


def _init_session(start: int) -> None:
    """Seed replay session keys on first use, clamped to a known start."""
    if KEY_REPLAY_TS not in st.session_state:
        st.session_state[KEY_REPLAY_TS] = start
    if KEY_REPLAY_PLAYING not in st.session_state:
        st.session_state[KEY_REPLAY_PLAYING] = False
    if KEY_LAST_OK_TS not in st.session_state:
        st.session_state[KEY_LAST_OK_TS] = st.session_state[KEY_REPLAY_TS]


def _clamp(ts: int, start: int, end: int) -> int:
    """Clamp a timestamp into the inclusive ``[start, end]`` window."""
    return max(start, min(end, ts))


def render_replay(render_snapshot: Optional[SnapshotRenderer] = None) -> None:
    """Render the replay controls and drive ``render_snapshot`` for each tick.

    Parameters
    ----------
    render_snapshot:
        Callback that draws the bus/dock cards for a given ``at_ts`` and returns
        True on success, False if the snapshot could not be loaded. When
        ``None`` (e.g. before task 6.2 wires it in), only the controls and the
        selected time are shown. The callback must not itself mutate the replay
        session keys.
    """
    result = call(get_replay_window, mode="replay")

    # Bad window: disable the controls and say so, nothing else to drive.
    if _window_is_bad(result):
        st.slider("Replay time", min_value=0, max_value=1, value=0, disabled=True)
        st.button("Play", disabled=True, key="replay_play_disabled")
        st.warning(MSG_WINDOW_UNAVAILABLE)
        return

    window = result.value
    start, end, step = window.start, window.end, window.step_sec

    _init_session(start)

    # Keep any externally set replay_ts inside the window.
    st.session_state[KEY_REPLAY_TS] = _clamp(
        int(st.session_state[KEY_REPLAY_TS]), start, end
    )

    playing = bool(st.session_state[KEY_REPLAY_PLAYING])

    # real seconds between automatic steps while playing.
    speed = SETTINGS.replay_play_speed or 1
    tick = step / speed

    def replay_body() -> None:
        # 1. If playing, advance the clock first and stop at the end.
        if st.session_state.get(KEY_REPLAY_PLAYING):
            current = int(st.session_state[KEY_REPLAY_TS])
            nxt, finished = next_replay_ts(current, start, end, step)
            st.session_state[KEY_REPLAY_TS] = nxt
            if finished:
                st.session_state[KEY_REPLAY_PLAYING] = False

        ts = int(st.session_state[KEY_REPLAY_TS])

        # 2. Fetch and render the snapshot. On failure: stop playback, restore
        #    the last good time and show the fixed message (R4.14).
        ok = True
        if render_snapshot is not None:
            try:
                ok = render_snapshot(ts)
            except Exception:
                ok = False
        if not ok:
            st.session_state[KEY_REPLAY_PLAYING] = False
            st.session_state[KEY_REPLAY_TS] = int(
                st.session_state.get(KEY_LAST_OK_TS, ts)
            )
            st.warning(MSG_SNAPSHOT_FAILED)
        else:
            st.session_state[KEY_LAST_OK_TS] = ts

        # 3. Controls. The slider is bound to replay_ts; play toggles playback.
        shown_ts = int(st.session_state[KEY_REPLAY_TS])
        st.caption(f"Showing snapshot at {format_ny_time(shown_ts)}")
        st.slider(
            "Replay time",
            min_value=start,
            max_value=end,
            value=shown_ts,
            step=step,
            key=KEY_REPLAY_TS,
            format="%d",
            help=(
                f"{format_ny_time(start)} to {format_ny_time(end)} "
                f"(New York time)"
            ),
        )

        label = "Pause" if st.session_state.get(KEY_REPLAY_PLAYING) else "Play"
        if st.button(label, key="replay_play"):
            st.session_state[KEY_REPLAY_PLAYING] = not st.session_state.get(
                KEY_REPLAY_PLAYING
            )
            st.rerun()

        # 4. When play just finished, rerun once to drop run_every from the
        #    fragment so it stops ticking.
        if playing and not st.session_state.get(KEY_REPLAY_PLAYING):
            st.rerun()

    # Create the fragment dynamically so run_every is only set while playing.
    frag = st.fragment(run_every=tick if playing else None)(replay_body)
    frag()
