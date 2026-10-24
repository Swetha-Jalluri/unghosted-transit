# Feature: unghosted-demo, Property 13: Successful API and MCP responses carry the legal text
"""Property 13 (API part): successful responses carry the legal text.

For any valid request on demo data to bus-trust, dock-trust, nearby-docks or
findings, the API response carries the Attribution and Disclaimer text exactly
(R8.7, R10.7):

* bus-trust / dock-trust return the contract model unchanged, so the response's
  ``attribution`` list joined by a single space equals ``ATTRIBUTION`` (and, as
  a looser guarantee, the joined text contains it), and ``disclaimer`` equals
  ``DISCLAIMER``.
* nearby-docks / findings wrap their payload in the legal-text envelope, so the
  envelope's ``attribution`` list contains ``ATTRIBUTION`` and ``disclaimer``
  equals ``DISCLAIMER``.

Health and replay-window are excluded by the property and are not exercised
here.

The requests use real committed demo data: ids come from
``service.list_demo_stops()`` (bus-trust), the demo docks fixture
(dock-trust), and the demo dock coordinates (nearby-docks); findings takes no
id. No stubbing is needed because the demo Service answers all of these
offline. Route paths and the two Query defaults (``mode``) come from
``SETTINGS`` (no hardcoded paths).

Hypothesis samples over the finite set of valid ids/coordinates; a fresh client
with the service spied is built inside each ``@given`` body via ``spied_client``
so Hypothesis does not reuse a function-scoped fixture (which would trip
``FailedHealthCheck``).

**Validates: Requirements 8.7, 10.7**
"""
from __future__ import annotations

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.settings import ATTRIBUTION, DISCLAIMER, SETTINGS
from core import service
from tests.api.conftest import spied_client

# Route paths come from Settings (no hardcoded paths).
ROUTES = SETTINGS.api_routes
BUS_TRUST = ROUTES["bus_trust"]
DOCK_TRUST = ROUTES["dock_trust"]
NEARBY_DOCKS = ROUTES["nearby_docks"]
FINDINGS = ROUTES["findings"]


def _demo_stop_ids() -> list[str]:
    """Real demo stop ids that bus-trust can answer offline."""
    return [stop.stop_id for stop in service.list_demo_stops()]


def _demo_station_ids() -> list[str]:
    """Real demo station ids that dock-trust can answer offline.

    Driven from a valid nearby-docks response so the ids match the committed
    demo docks without reaching into core fixtures directly.
    """
    with spied_client() as (client, _spy):
        # A lat/lon pair inside the geographic bounds; the demo service returns
        # the full dock list regardless of distance, so any valid pair works.
        resp = client.get(NEARBY_DOCKS, params={"lat": 42.36, "lon": -71.1})
        assert resp.status_code == 200, resp.text
        docks = resp.json()["data"]
    return [dock["station_id"] for dock in docks]


_STOP_IDS = _demo_stop_ids()
_STATION_IDS = _demo_station_ids()

# A handful of valid coordinate pairs inside the fixed geographic range. The
# demo service ignores distance, so these only need to satisfy the Query bounds.
_COORDS = [
    (42.3719, -71.1159),
    (42.3626, -71.0915),
    (0.0, 0.0),
    (-89.9, 179.9),
]


def _assert_contract_legal_text(attribution: list[str], disclaimer: str) -> None:
    """Assert a contract-model response carries the legal text exactly.

    The service attribution list joined by a single space must equal
    ``ATTRIBUTION`` (and, as the looser guarantee the property also allows,
    contain it); the disclaimer must equal ``DISCLAIMER`` word for word.
    """
    assert isinstance(attribution, list) and attribution, (
        f"attribution must be a non-empty list, got {attribution!r}"
    )
    joined = " ".join(attribution)
    assert joined == ATTRIBUTION, (
        f"joined attribution {joined!r} != ATTRIBUTION {ATTRIBUTION!r}"
    )
    assert ATTRIBUTION in joined, "joined attribution does not contain ATTRIBUTION"
    assert disclaimer == DISCLAIMER, (
        f"disclaimer {disclaimer!r} != DISCLAIMER {DISCLAIMER!r}"
    )


def _assert_envelope_legal_text(attribution: list[str], disclaimer: str) -> None:
    """Assert an envelope response carries the legal text exactly.

    The envelope's attribution list must contain ``ATTRIBUTION`` and the
    disclaimer must equal ``DISCLAIMER`` word for word.
    """
    assert isinstance(attribution, list), (
        f"envelope attribution must be a list, got {attribution!r}"
    )
    assert ATTRIBUTION in attribution, (
        f"ATTRIBUTION {ATTRIBUTION!r} not in envelope attribution {attribution!r}"
    )
    assert disclaimer == DISCLAIMER, (
        f"disclaimer {disclaimer!r} != DISCLAIMER {DISCLAIMER!r}"
    )


class TestBusTrustCarriesLegalText:
    """bus-trust returns the contract model with the legal text intact."""

    @hyp_settings(max_examples=100)
    @given(stop_id=st.sampled_from(_STOP_IDS))
    def test_bus_trust_legal_text(self, stop_id):
        """A valid demo bus-trust request carries ATTRIBUTION and DISCLAIMER."""
        with spied_client() as (client, _spy):
            resp = client.get(BUS_TRUST, params={"stop_id": stop_id})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        _assert_contract_legal_text(body["attribution"], body["disclaimer"])


class TestDockTrustCarriesLegalText:
    """dock-trust returns the contract model with the legal text intact."""

    @hyp_settings(max_examples=100)
    @given(station_id=st.sampled_from(_STATION_IDS))
    def test_dock_trust_legal_text(self, station_id):
        """A valid demo dock-trust request carries ATTRIBUTION and DISCLAIMER."""
        with spied_client() as (client, _spy):
            resp = client.get(DOCK_TRUST, params={"station_id": station_id})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        _assert_contract_legal_text(body["attribution"], body["disclaimer"])


class TestNearbyDocksCarriesLegalText:
    """nearby-docks wraps its payload in the legal-text envelope."""

    @hyp_settings(max_examples=100)
    @given(coord=st.sampled_from(_COORDS))
    def test_nearby_docks_legal_text(self, coord):
        """A valid demo nearby-docks request carries ATTRIBUTION and DISCLAIMER."""
        lat, lon = coord
        with spied_client() as (client, _spy):
            resp = client.get(NEARBY_DOCKS, params={"lat": lat, "lon": lon})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        _assert_envelope_legal_text(body["attribution"], body["disclaimer"])


class TestFindingsCarriesLegalText:
    """findings wraps its payload in the legal-text envelope."""

    def test_findings_legal_text(self):
        """A valid demo findings request carries ATTRIBUTION and DISCLAIMER."""
        with spied_client() as (client, _spy):
            resp = client.get(FINDINGS)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        _assert_envelope_legal_text(body["attribution"], body["disclaimer"])
