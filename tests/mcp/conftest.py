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
