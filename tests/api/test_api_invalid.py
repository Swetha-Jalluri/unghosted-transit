# Feature: unghosted-demo, Property 9: Invalid input never reaches the Service
"""Property 9 (API part): invalid input never reaches the Service.

For any API request with a missing required parameter or an out-of-bound value,
the API returns 422 with a body that names each offending parameter, and a spy
on ``core.service`` records zero calls.

FastAPI validates query parameters against the ``Query`` bounds (from Settings)
and the ``mode`` ``Literal`` before the handler body runs, so a rejected request
must both produce a 422 whose ``params`` names the offending parameter(s) and
leave the Service untouched (R8.3).

**Validates: Requirements 8.3**
"""
from __future__ import annotations

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.settings import SETTINGS
from tests.api.conftest import spied_client

# Route paths and bounds come from Settings (no hardcoded paths or limits).
ROUTES = SETTINGS.api_routes
BUS_TRUST = ROUTES["bus_trust"]
DOCK_TRUST = ROUTES["dock_trust"]
NEARBY_DOCKS = ROUTES["nearby_docks"]

_LIMIT_MIN = SETTINGS.limit["min"]
_LIMIT_MAX = SETTINGS.limit["max"]
_WALK_MIN = SETTINGS.walk_min["min"]
_WALK_MAX = SETTINGS.walk_min["max"]

# A value that is never one of the configured modes.
_BAD_MODES = st.text(min_size=1, max_size=12).filter(lambda m: m not in SETTINGS.modes)


def _assert_rejected(response, spy, expected_params):
    """Assert a 422 whose body names each expected parameter, with no service calls."""
    assert response.status_code == 422, (
        f"expected 422, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body["error"] == "validation_error"
    named = set(body.get("params", []))
    for param in expected_params:
        assert param in named, (
            f"expected {param!r} named in params {named}; body={body}"
        )
    # The Service must never be reached for a rejected request.
    assert spy.count == 0, f"service was called on invalid input: {spy.names()}"


class TestMissingRequiredParams:
    """Missing required query parameters are rejected before the Service."""

    def test_bus_trust_missing_stop_id(self, client, service_spy):
        """bus-trust without stop_id -> 422 naming stop_id, no service call."""
        resp = client.get(BUS_TRUST)
        _assert_rejected(resp, service_spy, {"stop_id"})

    def test_dock_trust_missing_station_id(self, client, service_spy):
        """dock-trust without station_id -> 422 naming station_id."""
        resp = client.get(DOCK_TRUST)
        _assert_rejected(resp, service_spy, {"station_id"})

    def test_nearby_docks_missing_lat_and_lon(self, client, service_spy):
        """nearby-docks without lat and lon -> 422 naming both."""
        resp = client.get(NEARBY_DOCKS)
        _assert_rejected(resp, service_spy, {"lat", "lon"})

    def test_nearby_docks_missing_lon(self, client, service_spy):
        """nearby-docks with lat only -> 422 naming lon."""
        resp = client.get(NEARBY_DOCKS, params={"lat": 42.36})
        _assert_rejected(resp, service_spy, {"lon"})


class TestOutOfBoundValues:
    """Out-of-bound query values are rejected before the Service."""

    @hyp_settings(max_examples=100)
    @given(mode=_BAD_MODES)
    def test_bus_trust_bad_mode(self, mode):
        """bus-trust with a mode outside Settings.modes -> 422 naming mode."""
        with spied_client() as (client, spy):
            resp = client.get(BUS_TRUST, params={"stop_id": "place-x", "mode": mode})
            _assert_rejected(resp, spy, {"mode"})

    @hyp_settings(max_examples=100)
    @given(
        limit=st.integers().filter(lambda n: n < _LIMIT_MIN or n > _LIMIT_MAX)
    )
    def test_bus_trust_limit_out_of_bounds(self, limit):
        """bus-trust with limit outside [min, max] -> 422 naming limit."""
        with spied_client() as (client, spy):
            resp = client.get(
                BUS_TRUST, params={"stop_id": "place-x", "limit": limit}
            )
            _assert_rejected(resp, spy, {"limit"})

    @hyp_settings(max_examples=100)
    @given(
        walk_min=st.floats(
            allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
        ).filter(lambda w: w < _WALK_MIN or w > _WALK_MAX)
    )
    def test_dock_trust_walk_min_out_of_bounds(self, walk_min):
        """dock-trust with walk_min outside [min, max] -> 422 naming walk_min."""
        with spied_client() as (client, spy):
            resp = client.get(
                DOCK_TRUST, params={"station_id": "s-1", "walk_min": walk_min}
            )
            _assert_rejected(resp, spy, {"walk_min"})

    @hyp_settings(max_examples=100)
    @given(
        lat=st.floats(
            allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
        ).filter(lambda v: v < -90.0 or v > 90.0)
    )
    def test_nearby_docks_lat_out_of_range(self, lat):
        """nearby-docks with lat outside -90..90 -> 422 naming lat."""
        with spied_client() as (client, spy):
            resp = client.get(NEARBY_DOCKS, params={"lat": lat, "lon": 0.0})
            _assert_rejected(resp, spy, {"lat"})

    @hyp_settings(max_examples=100)
    @given(
        lon=st.floats(
            allow_nan=False, allow_infinity=False, min_value=-1e7, max_value=1e7
        ).filter(lambda v: v < -180.0 or v > 180.0)
    )
    def test_nearby_docks_lon_out_of_range(self, lon):
        """nearby-docks with lon outside -180..180 -> 422 naming lon."""
        with spied_client() as (client, spy):
            resp = client.get(NEARBY_DOCKS, params={"lat": 0.0, "lon": lon})
            _assert_rejected(resp, spy, {"lon"})

    @hyp_settings(max_examples=100)
    @given(
        at_ts=st.one_of(
            # Non-numeric text (letters, symbols, whitespace): never an int.
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz .,:-_/",
                min_size=1,
                max_size=8,
            ).filter(lambda s: not s.strip().lstrip("+-").isdigit()),
            # A decimal with a guaranteed non-zero fractional digit, so it can
            # never be read as an integer (e.g. "42.37"), kept small enough to
            # format without scientific notation.
            st.builds(
                lambda whole, frac: f"{whole}.{frac}",
                st.integers(min_value=0, max_value=1_000_000),
                st.integers(min_value=1, max_value=99),
            ),
        )
    )
    def test_bus_trust_at_ts_non_integer(self, at_ts):
        """bus-trust with a non-integer at_ts -> 422 naming at_ts."""
        with spied_client() as (client, spy):
            resp = client.get(
                BUS_TRUST, params={"stop_id": "place-x", "at_ts": at_ts}
            )
            _assert_rejected(resp, spy, {"at_ts"})
