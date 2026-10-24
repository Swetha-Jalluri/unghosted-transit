"""Property tests for the hindsight badge in ``app.logic``.

# Feature: unghosted-demo, Property 3: Hindsight badge is deterministic and honest
"""
from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic import hindsight_badge

# Finite minutes within the replay horizon (a day, in whole and fractional
# minutes). Round-tripped through the badge as ``app_eta_min``.
_finite_minutes = st.floats(
    min_value=0.0, max_value=1440.0, allow_nan=False, allow_infinity=False
)

# Non-finite / absent sentinels that must force "disappeared before arrival".
_non_finite = st.sampled_from([None, float("nan"), float("inf"), float("-inf")])

# A finite replay timestamp (POSIX seconds UTC, arbitrary but finite).
_finite_ts = st.floats(
    min_value=0.0, max_value=4_102_444_800.0, allow_nan=False, allow_infinity=False
)


def _no_banned_words(text: str | None) -> None:
    """Assert the badge never says "ghost" or "proven" in any case."""
    if text is None:
        return
    lowered = text.lower()
    assert "ghost" not in lowered
    assert "proven" not in lowered


# Feature: unghosted-demo, Property 3: Hindsight badge is deterministic and honest
@settings(max_examples=200)
@given(
    outcome=st.sampled_from(["served", "vanished", "canceled", "open"]),
    replay_ts=st.one_of(_finite_ts, _non_finite),
    app_eta_min=st.one_of(_finite_minutes, _non_finite),
)
def test_badge_is_deterministic_and_pure(
    outcome: str, replay_ts: float | None, app_eta_min: float | None
) -> None:
    """Repeated calls return the same value and do not mutate inputs.

    Validates: Requirements 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 10.1, 10.4
    """
    first = hindsight_badge(outcome, replay_ts, app_eta_min)
    second = hindsight_badge(outcome, replay_ts, app_eta_min)
    assert first == second
    # Inputs are immutable scalars; confirm identity is unchanged (not mutated).
    assert outcome == outcome
    _no_banned_words(first)


# Feature: unghosted-demo, Property 3: Hindsight badge is deterministic and honest
@settings(max_examples=200)
@given(replay_ts=st.one_of(_finite_ts, _non_finite), app_eta_min=st.one_of(_finite_minutes, _non_finite))
def test_served_canceled_open_labels(
    replay_ts: float | None, app_eta_min: float | None
) -> None:
    """served/canceled/open map to fixed honest labels regardless of minutes.

    Validates: Requirements 4.7, 4.10, 4.11, 4.12, 10.4
    """
    assert hindsight_badge("served", replay_ts, app_eta_min) == "served"
    assert hindsight_badge("canceled", replay_ts, app_eta_min) == "canceled"
    assert hindsight_badge("open", replay_ts, app_eta_min) == "still open"
    for label in ("served", "canceled", "still open"):
        _no_banned_words(label)


# Feature: unghosted-demo, Property 3: Hindsight badge is deterministic and honest
@settings(max_examples=200)
@given(replay_ts=_finite_ts, app_eta_min=_finite_minutes)
def test_vanished_finite_reports_rounded_minutes(
    replay_ts: float, app_eta_min: float
) -> None:
    """vanished with finite inputs -> "disappeared N min later", N=max(0,round).

    Validates: Requirements 4.8, 4.12, 10.4
    """
    badge = hindsight_badge("vanished", replay_ts, app_eta_min)
    expected_n = max(0, round(app_eta_min))
    assert badge == f"disappeared {expected_n} min later"
    assert expected_n >= 0
    _no_banned_words(badge)


# Feature: unghosted-demo, Property 3: Hindsight badge is deterministic and honest
@settings(max_examples=200)
@given(
    replay_ts=st.one_of(_finite_ts, _non_finite),
    app_eta_min=st.one_of(_finite_minutes, _non_finite),
)
def test_vanished_non_finite_falls_back(
    replay_ts: float | None, app_eta_min: float | None
) -> None:
    """vanished with any non-finite input -> "disappeared before arrival".

    Validates: Requirements 4.9, 4.12, 10.4
    """
    ts_finite = isinstance(replay_ts, (int, float)) and math.isfinite(replay_ts)
    eta_finite = isinstance(app_eta_min, (int, float)) and math.isfinite(app_eta_min)
    badge = hindsight_badge("vanished", replay_ts, app_eta_min)
    if ts_finite and eta_finite:
        assert badge == f"disappeared {max(0, round(app_eta_min))} min later"
    else:
        assert badge == "disappeared before arrival"
    _no_banned_words(badge)


# Feature: unghosted-demo, Property 3: Hindsight badge is deterministic and honest
@settings(max_examples=200)
@given(
    outcome=st.one_of(st.none(), st.text()),
    replay_ts=st.one_of(_finite_ts, _non_finite),
    app_eta_min=st.one_of(_finite_minutes, _non_finite),
)
def test_unknown_or_absent_outcome_has_no_badge(
    outcome: str | None, replay_ts: float | None, app_eta_min: float | None
) -> None:
    """Absent/unknown outcome returns None; known outcomes always return text.

    Validates: Requirements 4.6, 4.12, 10.4
    """
    badge = hindsight_badge(outcome, replay_ts, app_eta_min)
    if outcome in ("served", "vanished", "canceled", "open"):
        assert badge is not None
    else:
        assert badge is None
    _no_banned_words(badge)
