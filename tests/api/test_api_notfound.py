# Feature: unghosted-demo, Property 11: Unknown ids are 404 / not_found, never a crash
"""Property 11 (API part): unknown ids are 404 / not_found, never a crash.

For any id string that is valid in format (passes the ``Query`` constraints) but
unknown to the Service, the bus-trust and dock-trust routes return a 404 whose
body carries ``error == "not_found"`` and names the offending id, and never a
500 or a stack trace (R8.4, R10.6).

The demo Service will not naturally raise ``NotFound`` for every arbitrary
string, so to drive the 404 path deterministically and offline we replace
``core.service.get_bus_trust`` / ``get_dock_trust`` with a stub that raises
``core.contracts.NotFound(id)`` for the generated id. The API's exception
handler turns that into the 404 body; the test checks only the delivery layer's
behavior, not the demo data.

A function-scoped fixture cannot be reused across Hypothesis examples (it would
trip ``FailedHealthCheck``), so each generated id builds a fresh app and client
inside a context manager, mirroring ``spied_client`` in ``conftest.py``.

**Validates: Requirements 8.4, 10.6**
"""
from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient
from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from api.main import create_app
from app.settings import SETTINGS
from core import service
from core.contracts import NotFound

# Route paths come from Settings (no hardcoded paths).
ROUTES = SETTINGS.api_routes
BUS_TRUST = ROUTES["bus_trust"]
DOCK_TRUST = ROUTES["dock_trust"]

# Ids that are valid in format: non-empty (so they pass ``min_length=1``) and
# with no slash, so the path-plus-query shape is well formed. They are unknown
# to the Service by construction because the stub raises NotFound for all of
# them.
_ID_STRINGS = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cc", "Cs", "Zl", "Zp"),
        blacklist_characters="/?#&=",
    ),
    min_size=1,
    max_size=24,
).map(lambda s: s.strip()).filter(lambda s: len(s) >= 1)


@contextmanager
def _notfound_client(func_name: str, bad_id: str):
    """Yield a ``TestClient`` whose ``func_name`` service call raises NotFound.

    Replaces ``core.service.<func_name>`` with a stub that raises
    ``NotFound(bad_id)`` regardless of arguments, builds a fresh app and client,
    and restores the original on exit. A standalone context manager (not a
    fixture) so it can be used inside a ``@given`` body, giving every generated
    id a clean app.
    """
    original = getattr(service, func_name)

    def _raise(*_args, **_kwargs):
        raise NotFound(bad_id)

    setattr(service, func_name, _raise)
    try:
        app = create_app()
        with TestClient(app) as test_client:
            yield test_client
    finally:
        setattr(service, func_name, original)


def _assert_not_found(response, bad_id: str) -> None:
    """Assert a 404 ``not_found`` body that names the id and leaks no detail."""
    assert response.status_code == 404, (
        f"expected 404, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body["error"] == "not_found", f"unexpected error code: {body}"
    # The id must appear in the human-readable message.
    assert bad_id in body["message"], (
        f"id {bad_id!r} not named in message {body['message']!r}"
    )
    # Never a 500 / stack trace: no traceback markers in the body text.
    text = response.text
    assert "Traceback" not in text, f"stack trace leaked: {text}"
    assert "internal_error" not in text, f"mapped to 500: {text}"


class TestBusTrustUnknownId:
    """Unknown stop ids on bus-trust map to a 404 that names the id."""

    @hyp_settings(max_examples=100)
    @given(stop_id=_ID_STRINGS)
    def test_unknown_stop_id_is_404(self, stop_id):
        """bus-trust with an unknown stop_id -> 404 not_found naming the id."""
        with _notfound_client("get_bus_trust", stop_id) as client:
            resp = client.get(BUS_TRUST, params={"stop_id": stop_id})
            _assert_not_found(resp, stop_id)


class TestDockTrustUnknownId:
    """Unknown station ids on dock-trust map to a 404 that names the id."""

    @hyp_settings(max_examples=100)
    @given(station_id=_ID_STRINGS)
    def test_unknown_station_id_is_404(self, station_id):
        """dock-trust with an unknown station_id -> 404 not_found naming the id."""
        with _notfound_client("get_dock_trust", station_id) as client:
            resp = client.get(DOCK_TRUST, params={"station_id": station_id})
            _assert_not_found(resp, station_id)
