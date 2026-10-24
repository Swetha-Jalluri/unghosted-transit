# Feature: unghosted-demo, Property 9: Invalid input never reaches the Service
"""Property 9 (MCP part): invalid input never reaches the Service.

For any MCP tool call with a missing required parameter or an out-of-bound
value, the tool returns an ``invalid_input`` error result naming the offending
field, and a spy on ``core.service`` records zero calls.

Each tool in ``mcp_server.tools`` validates its inputs through ``app.validation``
before any Service call, so a rejected call must both return
``{"ok": False, "error": {"code": "invalid_input", "field": ...}}`` naming the
field and leave the Service untouched (R9.3).

**Validates: Requirements 9.3**
"""
from __future__ import annotations

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.settings import SETTINGS
from mcp_server.tools import (
    check_bus_trust,
    check_dock_trust,
    nearby_docks,
)
from tests.mcp.conftest import spied_service

# Bounds come from Settings (no hardcoded limits).
_LIMIT_MIN = SETTINGS.limit["min"]
_LIMIT_MAX = SETTINGS.limit["max"]
_WALK_MIN = SETTINGS.walk_min["min"]
_WALK_MAX = SETTINGS.walk_min["max"]

# A value that is never one of the configured modes.
_BAD_MODES = st.text(min_size=1, max_size=12).filter(lambda m: m not in SETTINGS.modes)

# Out-of-bound integer limits (outside [min, max]).
_BAD_LIMITS = st.integers(min_value=-1000, max_value=1000).filter(
    lambda n: n < _LIMIT_MIN or n > _LIMIT_MAX
)

# Out-of-bound walk_min values.
_BAD_WALK_MINS = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
).filter(lambda w: w < _WALK_MIN or w > _WALK_MAX)

# Latitudes outside the fixed geographic range -90..90.
_BAD_LATS = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
).filter(lambda v: v < -90.0 or v > 90.0)

# Longitudes outside the fixed geographic range -180..180.
_BAD_LONS = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e7, max_value=1e7
).filter(lambda v: v < -180.0 or v > 180.0)

# Ids that fail validation: empty/whitespace-only or longer than 64 chars.
# validate_id trims surrounding whitespace before measuring length, so the
# over-long branch uses non-whitespace characters only; otherwise a 65-char
# string ending in whitespace could trim down to a valid length.
_NON_WS_TEXT = st.text(
    alphabet=st.characters(
        min_codepoint=33, max_codepoint=126, blacklist_characters="\x7f"
    ),
    min_size=65,
    max_size=200,
)
_BAD_IDS = st.one_of(
    st.sampled_from(["", " ", "   ", "\t", "\n"]),
    _NON_WS_TEXT,
)

# Negative at_ts values (a negative POSIX second is invalid).
_NEGATIVE_AT_TS = st.integers(min_value=-1_000_000, max_value=-1)

# Non-integer at_ts values: floats-with-fraction, strings and booleans.
_NON_INT_AT_TS = st.one_of(
    st.floats(allow_nan=False, allow_infinity=False, min_value=0.1, max_value=1e6).filter(
        lambda f: f != int(f)
    ),
    st.text(alphabet="abcdef .:-", min_size=1, max_size=8),
    st.booleans(),
)

# Booleans supplied where a number is expected.
_BOOLEANS = st.booleans()


def _assert_invalid(result, spy, field):
    """Assert an ``invalid_input`` result naming ``field``, with no service calls."""
    assert result["ok"] is False, f"expected failure, got: {result}"
    error = result["error"]
    assert error["code"] == "invalid_input", (
        f"expected invalid_input, got {error['code']}: {result}"
    )
    assert error.get("field") == field, (
        f"expected field {field!r}, got {error.get('field')!r}: {result}"
    )
    # The Service must never be reached for a rejected call.
    assert spy.count == 0, f"service was called on invalid input: {spy.names()}"


class TestBusTrustInvalid:
    """check_bus_trust rejects bad input before the Service."""

    @hyp_settings(max_examples=100)
    @given(stop_id=_BAD_IDS)
    def test_bad_stop_id(self, stop_id):
        """Empty or over-long stop_id -> invalid_input naming stop_id."""
        with spied_service() as spy:
            result = check_bus_trust(stop_id=stop_id)
            _assert_invalid(result, spy, "stop_id")

    @hyp_settings(max_examples=100)
    @given(mode=_BAD_MODES)
    def test_bad_mode(self, mode):
        """mode outside Settings.modes -> invalid_input naming mode."""
        with spied_service() as spy:
            result = check_bus_trust(stop_id="place-x", mode=mode)
            _assert_invalid(result, spy, "mode")

    @hyp_settings(max_examples=100)
    @given(limit=_BAD_LIMITS)
    def test_limit_out_of_bounds(self, limit):
        """limit outside [min, max] -> invalid_input naming limit."""
        with spied_service() as spy:
            result = check_bus_trust(stop_id="place-x", limit=limit)
            _assert_invalid(result, spy, "limit")

    @hyp_settings(max_examples=100)
    @given(limit=_BOOLEANS)
    def test_boolean_limit(self, limit):
        """A boolean limit (number expected) -> invalid_input naming limit."""
        with spied_service() as spy:
            result = check_bus_trust(stop_id="place-x", limit=limit)
            _assert_invalid(result, spy, "limit")

    @hyp_settings(max_examples=100)
    @given(at_ts=_NEGATIVE_AT_TS)
    def test_negative_at_ts(self, at_ts):
        """Negative at_ts -> invalid_input naming at_ts."""
        with spied_service() as spy:
            result = check_bus_trust(stop_id="place-x", at_ts=at_ts)
            _assert_invalid(result, spy, "at_ts")

    @hyp_settings(max_examples=100)
    @given(at_ts=_NON_INT_AT_TS)
    def test_non_integer_at_ts(self, at_ts):
        """Non-integer at_ts -> invalid_input naming at_ts."""
        with spied_service() as spy:
            result = check_bus_trust(stop_id="place-x", at_ts=at_ts)
            _assert_invalid(result, spy, "at_ts")


class TestDockTrustInvalid:
    """check_dock_trust rejects bad input before the Service."""

    @hyp_settings(max_examples=100)
    @given(station_id=_BAD_IDS)
    def test_bad_station_id(self, station_id):
        """Empty or over-long station_id -> invalid_input naming station_id."""
        with spied_service() as spy:
            result = check_dock_trust(station_id=station_id)
            _assert_invalid(result, spy, "station_id")

    @hyp_settings(max_examples=100)
    @given(walk_min=_BAD_WALK_MINS)
    def test_walk_min_out_of_bounds(self, walk_min):
        """walk_min outside [min, max] -> invalid_input naming walk_min."""
        with spied_service() as spy:
            result = check_dock_trust(station_id="s-1", walk_min=walk_min)
            _assert_invalid(result, spy, "walk_min")

    @hyp_settings(max_examples=100)
    @given(walk_min=_BOOLEANS)
    def test_boolean_walk_min(self, walk_min):
        """A boolean walk_min (number expected) -> invalid_input naming walk_min."""
        with spied_service() as spy:
            result = check_dock_trust(station_id="s-1", walk_min=walk_min)
            _assert_invalid(result, spy, "walk_min")

    @hyp_settings(max_examples=100)
    @given(mode=_BAD_MODES)
    def test_bad_mode(self, mode):
        """mode outside Settings.modes -> invalid_input naming mode."""
        with spied_service() as spy:
            result = check_dock_trust(station_id="s-1", mode=mode)
            _assert_invalid(result, spy, "mode")


class TestNearbyDocksInvalid:
    """nearby_docks rejects bad input before the Service."""

    @hyp_settings(max_examples=100)
    @given(lat=_BAD_LATS)
    def test_lat_out_of_range(self, lat):
        """lat outside -90..90 -> invalid_input naming lat."""
        with spied_service() as spy:
            result = nearby_docks(lat=lat, lon=0.0)
            _assert_invalid(result, spy, "lat")

    @hyp_settings(max_examples=100)
    @given(lon=_BAD_LONS)
    def test_lon_out_of_range(self, lon):
        """lon outside -180..180 -> invalid_input naming lon."""
        with spied_service() as spy:
            result = nearby_docks(lat=0.0, lon=lon)
            _assert_invalid(result, spy, "lon")

    @hyp_settings(max_examples=100)
    @given(lat=_BOOLEANS)
    def test_boolean_lat(self, lat):
        """A boolean lat (number expected) -> invalid_input naming lat."""
        with spied_service() as spy:
            result = nearby_docks(lat=lat, lon=0.0)
            _assert_invalid(result, spy, "lat")

    @hyp_settings(max_examples=100)
    @given(walk_min=_BAD_WALK_MINS)
    def test_walk_min_out_of_bounds(self, walk_min):
        """walk_min outside [min, max] -> invalid_input naming walk_min."""
        with spied_service() as spy:
            result = nearby_docks(lat=0.0, lon=0.0, walk_min=walk_min)
            _assert_invalid(result, spy, "walk_min")

    @hyp_settings(max_examples=100)
    @given(limit=_BAD_LIMITS)
    def test_limit_out_of_bounds(self, limit):
        """limit outside [min, max] -> invalid_input naming limit."""
        with spied_service() as spy:
            result = nearby_docks(lat=0.0, lon=0.0, limit=limit)
            _assert_invalid(result, spy, "limit")
