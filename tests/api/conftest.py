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
