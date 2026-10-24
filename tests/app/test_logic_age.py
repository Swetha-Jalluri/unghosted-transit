"""Property tests for data-age round-trip formatting in ``app.logic``.

# Feature: unghosted-demo, Property 4: Data-age round trip
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic import format_age, parse_age

# One week in seconds, the upper bound of the age input space (R1.11, R10.5).
_MAX_AGE_SEC = 604_800

# Seconds-per-unit for each display unit that format_age can emit.
_UNIT_SECONDS = {"s": 1, "min": 60, "h": 3600, "d": 86400}


# Feature: unghosted-demo, Property 4: Data-age round trip
@settings(max_examples=200)
@given(age=st.integers(min_value=0, max_value=_MAX_AGE_SEC))
def test_age_round_trip_within_one_display_unit(age: int) -> None:
    """parse_age(format_age(age)) is within one display unit of age.

    format_age floors to the largest fitting unit, so the parsed value is the
    lower bound of that bucket: ``0 <= age - back < unit``.

    Validates: Requirements 1.11, 10.5
    """
    text = format_age(age)
    back = parse_age(text)

    assert back is not None, f"parse_age failed to round-trip {text!r}"

    # Determine the display unit shown in the formatted text.
    unit = text.split()[1]
    assert unit in _UNIT_SECONDS, f"unexpected unit in {text!r}"
    unit_seconds = _UNIT_SECONDS[unit]

    # Floored bucket: back is the lower bound, so the gap is in [0, unit).
    assert back <= age
    assert age - back < unit_seconds


# Feature: unghosted-demo, Property 4: Data-age round trip
def test_format_age_none_is_unknown() -> None:
    """format_age(None) reads "unknown" and parse_age round-trips it to None.

    Validates: Requirements 1.11, 10.5
    """
    assert format_age(None) == "unknown"
    assert parse_age("unknown") is None
