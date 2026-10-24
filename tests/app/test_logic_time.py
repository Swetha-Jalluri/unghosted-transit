"""Property test for New York time formatting (owner B).

# Feature: unghosted-demo, Property 5: New York times carry a zone abbreviation
Validates: Requirements 4.5
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic import format_ny_time

# POSIX range covering the epoch (1970) through ~2100, so every instant falls
# inside the EST/EDT era for America/New_York (no legacy LMT offset).
_TS_MIN = 0
_TS_MAX = 4_102_444_800  # 2100-01-01 00:00:00 UTC


def _real_ny_abbrev(ts: int) -> str:
    """The actual America/New_York zone abbreviation at this instant."""
    return (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        .astimezone(ZoneInfo("America/New_York"))
        .strftime("%Z")
    )


# Property 5: New York times carry a zone abbreviation.
@settings(max_examples=200)
@given(ts=st.integers(min_value=_TS_MIN, max_value=_TS_MAX))
def test_ny_time_carries_matching_zone_abbreviation(ts: int) -> None:
    text = format_ny_time(ts)

    # The abbreviation is always one of the two valid New York zones...
    assert text.endswith("EST") or text.endswith("EDT")

    # ...and it matches the real zone offset at that instant.
    expected = _real_ny_abbrev(ts)
    assert text.endswith(expected), f"{text!r} should end with {expected!r}"


def test_none_reads_unknown() -> None:
    assert format_ny_time(None) == "unknown"
