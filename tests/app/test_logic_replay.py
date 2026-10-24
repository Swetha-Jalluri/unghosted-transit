"""Property tests for the replay-advance presentation logic (owner B).

# Feature: unghosted-demo, Property 6: Replay advance is bounded and terminates
"""
from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic import next_replay_ts


# Generate a replay window with start <= current <= end and step >= 1.
@st.composite
def _replay_states(draw):
    start = draw(st.integers(min_value=-1_000_000, max_value=1_000_000))
    # Keep the window width bounded so iterating to the end stays cheap; the
    # termination property holds for any width, so a bounded span is enough.
    width = draw(st.integers(min_value=0, max_value=100_000))
    end = start + width
    current = draw(st.integers(min_value=start, max_value=end))
    # Bias step to include small values (step=1 exercises the longest walk) and
    # large values (step > width exercises immediate clamping to end).
    step = draw(st.integers(min_value=1, max_value=width + 1))
    return start, current, end, step


# Feature: unghosted-demo, Property 6: Replay advance is bounded and terminates
# Validates: Requirements 4.3, 4.4
# deadline disabled: iteration time scales with the generated window width.
@settings(max_examples=200, deadline=None)
@given(_replay_states())
def test_replay_advance_is_bounded_and_terminates(state):
    """A single advance stays in range, steps by exactly ``step`` until it
    would pass ``end``, and reports finished exactly at ``end``; iterating from
    ``start`` reaches ``end`` in the bounded number of steps."""
    start, current, end, step = state

    nxt, finished = next_replay_ts(current, start, end, step)

    # Result is within [current, end].
    assert current <= nxt <= end

    # Advances by exactly step unless that would pass end (clamped to end).
    assert nxt == min(current + step, end)

    # finished reports exactly when the result has reached end.
    assert finished == (nxt >= end)
    assert finished == (nxt == end)

    # Iterating from start reaches end in a finite, bounded number of steps.
    expected_steps = math.ceil((end - start) / step)
    pos = start
    steps = 0
    done = pos >= end
    while not done:
        pos, done = next_replay_ts(pos, start, end, step)
        steps += 1
        # Guard against a non-terminating loop (also bounds the test).
        assert steps <= expected_steps
    assert pos == end
    assert steps == expected_steps
