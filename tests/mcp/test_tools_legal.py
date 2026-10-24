# Feature: unghosted-demo, Property 13: Successful API and MCP responses carry the legal text
"""Property 13 (MCP part): successful MCP tool calls carry the legal text.

For any valid MCP tool call on demo data, the answer includes both the
Attribution and the Disclaimer strings and a ``data_age_sec`` entry for each
source the Service reports.

Each tool in ``mcp_server.tools`` wraps its success in a common envelope built
by ``_ok``: ``attribution`` is ``[ATTRIBUTION]`` and ``disclaimer`` is
``DISCLAIMER`` (both from :mod:`app.settings`, the single source). The
``data_age_sec`` shape follows the tool type (from the design):

- bus tools report ``BusTrustResponse.data_age_sec``;
- dock tools report ``{"docks": <last_reported_age_sec or None>}``;
- ``list_demo_stops`` and ``todays_findings`` report ``{}`` because the Service
  reports no age for them.

The property is driven over real demo ids: stop ids come from
``core.service.list_demo_stops()`` and a valid station id / coordinate comes
from ``core.service.get_nearby_docks(...)``. Health and replay-window are not
MCP tools and so are out of scope here.

**Validates: Requirements 9.7, 10.7**
"""
from __future__ import annotations

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.settings import ATTRIBUTION, DISCLAIMER
from core import service
from mcp_server.tools import (
    check_bus_trust,
    check_dock_trust,
    list_demo_stops,
    nearby_docks,
    todays_findings,
)
from tests.mcp.conftest import fixed_bus_service, fixed_demo_stops

# Fixed demo stop ids for the bus property. A's real demo Service raises
# ``NotFound`` for bus-trust in demo mode, so the bus tool is exercised against
# fixed contract models installed by ``fixed_bus_service``; ids are read from
# that fixed stop list (no hardcoded ids in the test).
_DEMO_STOP_IDS = [stop.stop_id for stop in fixed_demo_stops()]

# A valid station id and its coordinate, discovered through the Service exactly
# as the task prescribes: ask get_nearby_docks for the nearest dock and reuse
# its id/lat/lon. Centre the search on the first demo dock's own coordinate so
# the result is deterministic and real.
_ALL_DOCKS = service.get_nearby_docks(0.0, 0.0, limit=50)
_DEMO_STATION_ID = _ALL_DOCKS[0].station_id
_DEMO_LAT = _ALL_DOCKS[0].lat
_DEMO_LON = _ALL_DOCKS[0].lon

# Strategy over the real demo stop ids.
_STOP_IDS = st.sampled_from(_DEMO_STOP_IDS)


def _assert_legal(result) -> None:
    """Assert a successful envelope carries both legal strings and an age dict.

    ``attribution`` must contain ``ATTRIBUTION`` (the tools emit the single
    joined string in a one-element list), ``disclaimer`` must equal
    ``DISCLAIMER`` exactly, and ``data_age_sec`` must be present as a dict.
    """
    assert result["ok"] is True, f"expected success, got: {result}"
    attribution = result["attribution"]
    assert isinstance(attribution, list), f"attribution not a list: {attribution!r}"
    assert attribution == [ATTRIBUTION], (
        f"attribution should be [ATTRIBUTION], got: {attribution!r}"
    )
    assert ATTRIBUTION in attribution, f"ATTRIBUTION missing: {attribution!r}"
    assert result["disclaimer"] == DISCLAIMER, (
        f"disclaimer should equal DISCLAIMER, got: {result['disclaimer']!r}"
    )
    assert "data_age_sec" in result, f"data_age_sec missing: {result}"
    assert isinstance(result["data_age_sec"], dict), (
        f"data_age_sec not a dict: {result['data_age_sec']!r}"
    )


class TestBusTrustLegal:
    """check_bus_trust carries the legal text and the service's age map."""

    @hyp_settings(max_examples=100)
    @given(stop_id=_STOP_IDS)
    def test_legal_text_and_bus_data_age(self, stop_id):
        """A valid demo bus call carries both strings and the service age map.

        The age map must equal the response's own ``data_age_sec`` (bus tools
        forward ``BusTrustResponse.data_age_sec`` unchanged).
        """
        with fixed_bus_service():
            result = check_bus_trust(stop_id=stop_id, mode="demo")
            _assert_legal(result)
            expected_age = dict(
                service.get_bus_trust(stop_id, mode="demo").data_age_sec
            )
        assert result["data_age_sec"] == expected_age, (
            f"bus data_age_sec should match the service response, "
            f"got {result['data_age_sec']!r} vs {expected_age!r}"
        )


class TestDockTrustLegal:
    """check_dock_trust carries the legal text and a ``docks`` age entry."""

    @hyp_settings(max_examples=100)
    @given(walk_min=st.floats(min_value=1.0, max_value=30.0, allow_nan=False, allow_infinity=False))
    def test_legal_text_and_dock_data_age(self, walk_min):
        """A valid demo dock call carries both strings and a ``docks`` age key.

        Dock tools report ``{"docks": <last_reported_age_sec or None>}``, so the
        age dict must have exactly the ``docks`` key equal to the station's
        reported age.
        """
        result = check_dock_trust(station_id=_DEMO_STATION_ID, walk_min=walk_min, mode="demo")
        _assert_legal(result)
        age = result["data_age_sec"]
        assert set(age.keys()) == {"docks"}, f"dock age keys should be {{'docks'}}: {age!r}"
        expected = service.get_dock_trust(
            _DEMO_STATION_ID, walk_min=walk_min, mode="demo"
        ).dock.last_reported_age_sec
        assert age["docks"] == expected, (
            f"docks age should match the station report, got {age['docks']!r} vs {expected!r}"
        )


class TestNearbyDocksLegal:
    """nearby_docks carries the legal text and a ``docks`` age entry."""

    @hyp_settings(max_examples=100)
    @given(limit=st.integers(min_value=1, max_value=20))
    def test_legal_text_and_nearby_data_age(self, limit):
        """A valid demo nearby call carries both strings and a ``docks`` age key.

        The age uses the first returned dock's reported age; the key set is
        exactly ``{"docks"}``.
        """
        result = nearby_docks(lat=_DEMO_LAT, lon=_DEMO_LON, limit=limit, mode="demo")
        _assert_legal(result)
        age = result["data_age_sec"]
        assert set(age.keys()) == {"docks"}, f"dock age keys should be {{'docks'}}: {age!r}"
        docks = service.get_nearby_docks(_DEMO_LAT, _DEMO_LON, limit=limit, mode="demo")
        expected = docks[0].last_reported_age_sec if docks else None
        assert age["docks"] == expected, (
            f"docks age should match the first dock, got {age['docks']!r} vs {expected!r}"
        )


class TestFindingsAndStopsLegal:
    """todays_findings and list_demo_stops carry the legal text with empty age."""

    def test_findings_legal_text_and_empty_age(self):
        """todays_findings carries both strings and an empty ``data_age_sec``."""
        result = todays_findings()
        _assert_legal(result)
        assert result["data_age_sec"] == {}, (
            f"findings data_age_sec should be empty, got: {result['data_age_sec']!r}"
        )

    def test_demo_stops_legal_text_and_empty_age(self):
        """list_demo_stops carries both strings and an empty ``data_age_sec``."""
        result = list_demo_stops()
        _assert_legal(result)
        assert result["data_age_sec"] == {}, (
            f"stops data_age_sec should be empty, got: {result['data_age_sec']!r}"
        )
