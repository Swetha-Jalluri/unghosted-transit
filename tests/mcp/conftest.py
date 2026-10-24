"""Shared fixtures for the MCP tool tests.

Provides a spy over the ``core.service`` functions that ``mcp_server.tools``
calls. The tool functions do ``from core import service`` and invoke
``service.get_bus_trust(...)`` etc. at call time, so the spy replaces the
attributes on the ``core.service`` module object; every tool then resolves to
the spy on each call.

The spy lets a test assert that a rejected call (missing required parameter or
out-of-bound value) never reaches the Service: each tool validates its inputs
through ``app.validation`` before any Service call, so an ``invalid_input``
result must coincide with zero recorded calls (R9.3).
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest

from core import service
from core.contracts import (
    BusPrediction,
    BusTrustResponse,
    ChanceBasis,
    DemoStop,
    Evidence,
    NotFound,
)

# The service functions the MCP tools delegate to. These are the only names
# ``mcp_server.tools`` calls, so the spy needs to cover exactly these.
_SERVICE_FUNCS = (
    "list_demo_stops",
    "get_bus_trust",
    "get_dock_trust",
    "get_nearby_docks",
    "get_findings",
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

    The wrapper records the call then delegates to the real function, so tools
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
# serve them. Ids/names live only here (fixed test data), never asserted as
# literals in test bodies: tests read them back from these builders.
# ---------------------------------------------------------------------------

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
    ``service.DISCLAIMER``) and a non-empty ``data_age_sec`` so the legal-text
    and data-age assertions hold without hardcoding any string.
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
    returns :func:`make_bus_trust_response` for a known fixed stop id and raises
    ``NotFound`` otherwise. Other Service functions are untouched, so dock /
    findings tools keep using A's real demo data. Originals restored on exit.
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


@contextmanager
def spied_service():
    """Yield a fresh :class:`ServiceSpy` with ``core.service`` spied.

    A standalone context manager (not a pytest fixture) so it can be used
    inside the body of a ``@given`` property test: each ``with`` block installs
    recording wrappers over ``core.service`` and restores the originals on exit.
    This gives every generated input a clean spy, which a function-scoped
    fixture cannot do because Hypothesis does not reset fixtures between
    examples.

    Example::

        with spied_service() as spy:
            result = check_bus_trust(stop_id="place-x", mode="nope")
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
        yield spy
    finally:
        for func_name, original in originals.items():
            setattr(service, func_name, original)
