"""Shared fixtures for the REST API tests.

Provides a ``TestClient`` built from ``api.main.create_app`` and a spy over the
``core.service`` functions that ``api.main`` calls. ``api.main`` does
``from core import service`` and invokes ``service.get_bus_trust(...)`` etc. at
request time, so the spy replaces the attributes on the ``core.service`` module
object; every handler then resolves to the spy on each call.

The spy lets a test assert that a rejected request (missing or out-of-bound
parameter) never reaches the Service: FastAPI validates query parameters before
the handler body runs, so a 422 must coincide with zero recorded calls (R8.3).
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core import service
from core.contracts import (
    BusPrediction,
    BusTrustResponse,
    ChanceBasis,
    DemoStop,
    Evidence,
    NotFound,
)

# The service functions the API delegates to. These are the only names the
# routes in ``api.main`` call, so the spy needs to cover exactly these.
_SERVICE_FUNCS = (
    "list_demo_stops",
    "get_bus_trust",
    "get_dock_trust",
    "get_nearby_docks",
    "get_findings",
    "get_health",
    "get_replay_window",
)


@dataclass
class ServiceSpy:
    """Records every call made to a wrapped ``core.service`` function.

    ``calls`` holds ``(name, args, kwargs)`` tuples in call order. ``count`` is
    the total number of recorded calls across all wrapped functions.
    """

    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Total recorded calls across all wrapped service functions."""
        return len(self.calls)

    def names(self) -> list[str]:
        """Names of the service functions that were called, in order."""
        return [name for name, _args, _kwargs in self.calls]

    def reset(self) -> None:
        """Forget all recorded calls."""
        self.calls.clear()


@pytest.fixture
def service_spy(monkeypatch: pytest.MonkeyPatch) -> ServiceSpy:
    """Replace each ``core.service`` function with a recording wrapper.

    The wrapper records the call then delegates to the real function, so routes
    that legitimately reach the Service still behave normally while a test can
    assert ``service_spy.count == 0`` for input that should be rejected before
    the Service is reached. ``monkeypatch`` restores the originals after the
    test.
    """
    spy = ServiceSpy()

    def _make_wrapper(name: str, original):
        def _wrapper(*args, **kwargs):
            spy.calls.append((name, args, kwargs))
            return original(*args, **kwargs)

        return _wrapper

    for func_name in _SERVICE_FUNCS:
        original = getattr(service, func_name)
        monkeypatch.setattr(service, func_name, _make_wrapper(func_name, original))

    return spy


# ---------------------------------------------------------------------------
# Fixed contract-model bus data.
#
# A's real demo Service answers ``get_bus_trust`` with its own live demo stops
# and raises ``NotFound`` for them in demo mode, so content/shape tests must not
# depend on it. These helpers build fixed ``DemoStop`` / ``BusTrustResponse``
# contract models and a context manager that monkeypatches ``core.service`` to
# serve them. Ids and names live only here (fixed test data), never asserted as
# literals in the test bodies: tests read them back from these builders.
# ---------------------------------------------------------------------------

# Fixed demo stops the patched Service exposes. Arbitrary but valid ids/names.
_FIXED_DEMO_STOPS = (
    DemoStop(stop_id="fixed-stop-a", name="Fixed Stop A", routes=["1", "23"]),
    DemoStop(stop_id="fixed-stop-b", name="Fixed Stop B", routes=["39"]),
)


def fixed_demo_stops() -> list[DemoStop]:
    """Return a fresh copy of the fixed demo stops the patched Service serves."""
    return [s.model_copy(deep=True) for s in _FIXED_DEMO_STOPS]


def make_bus_trust_response(stop_id: str, mode: str = "demo") -> BusTrustResponse:
    """Build a fixed, valid ``BusTrustResponse`` for ``stop_id``.

    Carries the Service's own legal text (``service.ATTRIBUTION`` list and
    ``service.DISCLAIMER``) so legal-text assertions hold without hardcoding the
    strings, two displayable predictions, and one hidden arrival.
    """
    predictions = [
        BusPrediction(
            route_id="1",
            trip_id="fixed-trip-1",
            headsign="Downtown",
            app_eta_min=5.0,
            status="confirmed",
            why="Vehicle is in transit and reporting.",
            reason_codes=["vehicle_reporting"],
            chance_it_arrives=0.92,
            chance_basis=ChanceBasis(method="empirical", n=40),
            realistic_eta_min=(4.0, 7.0),
            evidence=Evidence(uncertainty=60, vehicle_id="veh-1", location_age_sec=15),
            backup=None,
            outcome=None,
        ),
        BusPrediction(
            route_id="23",
            trip_id="fixed-trip-2",
            headsign="Crosstown",
            app_eta_min=9.0,
            status="estimate",
            why="Schedule-based; no vehicle assigned yet.",
            reason_codes=["schedule_based"],
            chance_it_arrives=0.6,
            chance_basis=ChanceBasis(method="model", n=12),
            realistic_eta_min=(7.0, 13.0),
            evidence=Evidence(uncertainty=300),
            backup=None,
            outcome=None,
        ),
    ]
    return BusTrustResponse(
        stop_id=stop_id,
        stop_name=f"Stop {stop_id}",
        generated_at="2026-01-01T00:00:00Z",
        mode=mode,
        data_age_sec={"trip_updates": 12, "vehicle_positions": 8},
        predictions=predictions,
        hidden_count=1,
        attribution=list(service.ATTRIBUTION),
        disclaimer=service.DISCLAIMER,
    )


@contextmanager
def fixed_bus_service():
    """Monkeypatch ``core.service`` bus functions to serve fixed contract models.

    ``list_demo_stops`` returns :func:`fixed_demo_stops`; ``get_bus_trust``
    returns :func:`make_bus_trust_response` for any known fixed stop id and
    raises ``NotFound`` for anything else (so error paths still exercise real
    behavior). Other Service functions are untouched, so dock/findings/health
    continue to use A's real demo data. Originals are restored on exit.
    """
    known = {s.stop_id for s in _FIXED_DEMO_STOPS}
    originals = {
        "list_demo_stops": service.list_demo_stops,
        "get_bus_trust": service.get_bus_trust,
    }

    def _list_demo_stops(*_args, **_kwargs):
        return fixed_demo_stops()

    def _get_bus_trust(stop_id, mode="demo", limit=5, at_ts=None):
        if stop_id not in known:
            raise NotFound(f"Stop {stop_id} not found")
        return make_bus_trust_response(stop_id, mode=mode)

    service.list_demo_stops = _list_demo_stops
    service.get_bus_trust = _get_bus_trust
    try:
        yield
    finally:
        for name, fn in originals.items():
            setattr(service, name, fn)


@pytest.fixture
def client() -> TestClient:
    """A ``TestClient`` over a fresh app, exercising the API offline.

    Requests run in-process against the ASGI app with no network or live feeds;
    routes default to demo mode, so any call that does reach the Service uses
    the committed demo data rather than live feeds.
    """
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@contextmanager
def spied_client():
    """Yield a fresh ``(client, ServiceSpy)`` pair with the service spied.

    A standalone context manager (not a pytest fixture) so it can be used
    inside the body of a ``@given`` property test: each ``with`` block builds a
    new app, ``TestClient`` and spy, and restores the original ``core.service``
    functions on exit. This gives every generated input a clean spy, which a
    function-scoped fixture cannot do because Hypothesis does not reset fixtures
    between examples.

    Example::

        with spied_client() as (client, spy):
            resp = client.get(...)
            assert spy.count == 0
    """
    spy = ServiceSpy()
    originals = {name: getattr(service, name) for name in _SERVICE_FUNCS}

    def _make_wrapper(name: str, original):
        def _wrapper(*args, **kwargs):
            spy.calls.append((name, args, kwargs))
            return original(*args, **kwargs)

        return _wrapper

    for func_name, original in originals.items():
        setattr(service, func_name, _make_wrapper(func_name, original))

    try:
        app = create_app()
        with TestClient(app) as test_client:
            yield test_client, spy
    finally:
        for func_name, original in originals.items():
            setattr(service, func_name, original)
