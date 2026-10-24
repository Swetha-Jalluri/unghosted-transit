"""Property tests for the pure input validators in ``app.validation``.

# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
"""
from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.settings import SETTINGS
from app.validation import (
    InvalidInput,
    validate_at_ts,
    validate_id,
    validate_int_in,
    validate_lat,
    validate_lon,
    validate_number_in,
)

# Fixed geographic bounds (degrees), as required by R2.5 and R9.2. These are the
# coordinate-system bounds the validators enforce, not configurable settings.
_LAT_MIN, _LAT_MAX = -90.0, 90.0
_LON_MIN, _LON_MAX = -180.0, 180.0

# Id length bounds (characters, after trimming).
_ID_MIN_LEN, _ID_MAX_LEN = 1, 64

# Integer bounds pulled from Settings so nothing is hardcoded (R9.2). The limit
# block is the integer-bounded input the service accepts.
_INT_MIN = SETTINGS.limit["min"]
_INT_MAX = SETTINGS.limit["max"]

# Float bounds pulled from Settings (walk minutes).
_NUM_MIN = float(SETTINGS.walk_min["min"])
_NUM_MAX = float(SETTINGS.walk_min["max"])


# Finite real numbers (floats and ints), excluding NaN/inf which are not valid
# bounded inputs. Booleans are drawn separately and must always be rejected.
_finite_floats = st.floats(allow_nan=False, allow_infinity=False)
_reals = st.one_of(st.integers(), _finite_floats)

# Values that are never valid numbers/ints: strings, None, booleans, sequences.
_non_numeric = st.one_of(
    st.text(),
    st.none(),
    st.booleans(),
    st.lists(st.integers()),
)


# ---------------------------------------------------------------------------
# validate_number_in
# ---------------------------------------------------------------------------
# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
@settings(max_examples=300)
@given(value=_reals)
def test_number_in_accepts_iff_within_range(value: float) -> None:
    """validate_number_in accepts a real value iff it is inside [min, max].

    Validates: Requirements 2.4, 9.2
    """
    inside = _NUM_MIN <= value <= _NUM_MAX
    if inside:
        result = validate_number_in(value, _NUM_MIN, _NUM_MAX, field="walk_min")
        assert math.isclose(result, float(value))
    else:
        with pytest.raises(InvalidInput) as exc:
            validate_number_in(value, _NUM_MIN, _NUM_MAX, field="walk_min")
        assert exc.value.field == "walk_min"


# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
@settings(max_examples=100)
@given(value=_non_numeric)
def test_number_in_rejects_non_numbers_and_booleans(value: object) -> None:
    """validate_number_in rejects booleans and non-numeric values, naming field.

    Validates: Requirements 2.4, 9.2
    """
    with pytest.raises(InvalidInput) as exc:
        validate_number_in(value, _NUM_MIN, _NUM_MAX, field="walk_min")
    assert exc.value.field == "walk_min"


# ---------------------------------------------------------------------------
# validate_int_in
# ---------------------------------------------------------------------------
# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
@settings(max_examples=300)
@given(value=st.integers())
def test_int_in_accepts_iff_within_range(value: int) -> None:
    """validate_int_in accepts an int iff it is inside [min, max].

    Validates: Requirements 2.4, 9.2
    """
    inside = _INT_MIN <= value <= _INT_MAX
    if inside:
        assert validate_int_in(value, _INT_MIN, _INT_MAX, field="limit") == value
    else:
        with pytest.raises(InvalidInput) as exc:
            validate_int_in(value, _INT_MIN, _INT_MAX, field="limit")
        assert exc.value.field == "limit"


# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
@settings(max_examples=100)
@given(value=st.one_of(st.booleans(), _finite_floats, st.text(), st.none()))
def test_int_in_rejects_booleans_and_non_ints(value: object) -> None:
    """validate_int_in rejects booleans, floats and non-integers, naming field.

    Validates: Requirements 2.4, 9.2
    """
    with pytest.raises(InvalidInput) as exc:
        validate_int_in(value, _INT_MIN, _INT_MAX, field="limit")
    assert exc.value.field == "limit"


# ---------------------------------------------------------------------------
# validate_lat / validate_lon
# ---------------------------------------------------------------------------
# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
@settings(max_examples=300)
@given(value=_reals)
def test_lat_accepts_iff_within_90(value: float) -> None:
    """validate_lat accepts a real value iff -90 <= v <= 90.

    Validates: Requirements 2.5, 9.2
    """
    inside = _LAT_MIN <= value <= _LAT_MAX
    if inside:
        assert math.isclose(validate_lat(value), float(value))
    else:
        with pytest.raises(InvalidInput) as exc:
            validate_lat(value)
        assert exc.value.field == "lat"


# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
@settings(max_examples=300)
@given(value=_reals)
def test_lon_accepts_iff_within_180(value: float) -> None:
    """validate_lon accepts a real value iff -180 <= v <= 180.

    Validates: Requirements 2.5, 9.2
    """
    inside = _LON_MIN <= value <= _LON_MAX
    if inside:
        assert math.isclose(validate_lon(value), float(value))
    else:
        with pytest.raises(InvalidInput) as exc:
            validate_lon(value)
        assert exc.value.field == "lon"


# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
@settings(max_examples=100)
@given(value=_non_numeric)
def test_lat_lon_reject_non_numbers_and_booleans(value: object) -> None:
    """validate_lat/validate_lon reject booleans and non-numbers, naming field.

    Validates: Requirements 2.5, 9.2
    """
    with pytest.raises(InvalidInput) as exc_lat:
        validate_lat(value)
    assert exc_lat.value.field == "lat"

    with pytest.raises(InvalidInput) as exc_lon:
        validate_lon(value)
    assert exc_lon.value.field == "lon"


# ---------------------------------------------------------------------------
# validate_at_ts
# ---------------------------------------------------------------------------
# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
@settings(max_examples=300)
@given(value=st.integers())
def test_at_ts_accepts_iff_non_negative_int(value: int) -> None:
    """validate_at_ts accepts an int iff it is non-negative.

    Validates: Requirements 9.2
    """
    if value >= 0:
        assert validate_at_ts(value) == value
    else:
        with pytest.raises(InvalidInput) as exc:
            validate_at_ts(value)
        assert exc.value.field == "at_ts"


# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
@settings(max_examples=100)
@given(value=st.one_of(st.booleans(), _finite_floats, st.text(), st.none()))
def test_at_ts_rejects_booleans_and_non_ints(value: object) -> None:
    """validate_at_ts rejects booleans, floats and non-integers, naming field.

    Validates: Requirements 9.2
    """
    with pytest.raises(InvalidInput) as exc:
        validate_at_ts(value, field="at_ts")
    assert exc.value.field == "at_ts"


# ---------------------------------------------------------------------------
# validate_id
# ---------------------------------------------------------------------------
# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
@settings(max_examples=300)
@given(value=st.text())
def test_id_accepts_iff_trimmed_length_in_bounds(value: str) -> None:
    """validate_id accepts a string iff its trimmed length is in [1, 64].

    Validates: Requirements 9.2
    """
    trimmed = value.strip()
    inside = _ID_MIN_LEN <= len(trimmed) <= _ID_MAX_LEN
    if inside:
        assert validate_id(value, field="stop_id") == trimmed
    else:
        with pytest.raises(InvalidInput) as exc:
            validate_id(value, field="stop_id")
        assert exc.value.field == "stop_id"


# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
@settings(max_examples=100)
@given(value=st.one_of(st.integers(), st.booleans(), st.none(), _finite_floats))
def test_id_rejects_non_strings(value: object) -> None:
    """validate_id rejects any non-string value, naming the field.

    Validates: Requirements 9.2
    """
    with pytest.raises(InvalidInput) as exc:
        validate_id(value, field="stop_id")
    assert exc.value.field == "stop_id"


# Feature: unghosted-demo, Property 8: Bounds validators accept exactly the allowed range
@settings(max_examples=100)
@given(
    pad=st.integers(min_value=0, max_value=10),
    over=st.integers(min_value=1, max_value=50),
)
def test_id_rejects_over_64_characters(pad: int, over: int) -> None:
    """A string whose trimmed length exceeds 64 is rejected, naming the field.

    Validates: Requirements 9.2
    """
    core = "x" * (_ID_MAX_LEN + over)
    value = (" " * pad) + core + (" " * pad)
    with pytest.raises(InvalidInput) as exc:
        validate_id(value, field="stop_id")
    assert exc.value.field == "stop_id"
