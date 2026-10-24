# Feature: unghosted-demo, Property 11: Unknown ids are 404 / not_found, never a crash
"""Property 11 (MCP part): unknown ids are not_found, never a crash.

For any id string that is valid in format (1 to 64 characters after trimming, so
it passes ``validate_id``) but unknown to the Service, the MCP bus/dock tools
(``check_bus_trust``, ``check_dock_trust``) return a ``not_found`` result naming
the id, never raise, and keep accepting calls afterwards (R9.4, R10.9).

The demo Service will not naturally raise ``NotFound`` for every arbitrary
string, so to drive the not_found path deterministically and offline we replace
``core.service.get_bus_trust`` / ``get_dock_trust`` with a stub that raises
``core.contracts.NotFound(id)`` for the generated id. The tool's ``except
NotFound`` branch turns that into the error dict; the test checks only the
tool's delivery behavior, not the demo data.

``validate_id`` trims surrounding whitespace before measuring length and returns
the trimmed value, and ``tools._not_found`` names that trimmed id in the
message, so the generated id is compared in its trimmed form. A function-scoped
fixture cannot be reused across Hypothesis examples, so each generated id
installs its stub inside a context manager and restores the original on exit,
mirroring the API notfound test and ``conftest.spied_service``.

**Validates: Requirements 9.4, 10.9**
"""
from __future__ import annotations

from contextlib import contextmanager

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.validation import validate_id
from core import service
from core.contracts import NotFound
from mcp_server.tools import check_bus_trust, check_dock_trust

# Format-valid ids: strings whose trimmed form is 1 to 64 non-whitespace-bounded
# characters, so they pass ``validate_id`` and reach the Service. Build from a
# non-whitespace alphabet (so stripping cannot shrink the length) sized 1..64.
_UNKNOWN_IDS = st.text(
    alphabet=st.characters(
        min_codepoint=33, max_codepoint=126, blacklist_characters="\x7f"
    ),
    min_size=1,
    max_size=64,
)


@contextmanager
def _notfound_service(func_name: str, bad_id: str):
    """Make ``core.service.<func_name>`` raise ``NotFound(bad_id)``.

    Replaces the attribute on the ``core.service`` module object (which the
    tools resolve at call time) with a stub that raises regardless of arguments,
    and restores the original on exit. A standalone context manager so it can be
    used inside a ``@given`` body, giving every generated id a clean stub.
    """
    original = getattr(service, func_name)

    def _raise(*_args, **_kwargs):
        raise NotFound(bad_id)

    setattr(service, func_name, _raise)
    try:
        yield
    finally:
        setattr(service, func_name, original)


def _assert_not_found(result, bad_id: str) -> None:
    """Assert a ``not_found`` error dict naming the id, with no leaked detail."""
    assert result["ok"] is False, f"expected failure, got: {result}"
    error = result["error"]
    assert error["code"] == "not_found", (
        f"expected not_found, got {error['code']}: {result}"
    )
    # The trimmed id must appear in the human-readable message.
    assert bad_id in error["message"], (
        f"id {bad_id!r} not named in message {error['message']!r}"
    )
    # Never mapped to an internal error / crash.
    assert error["code"] != "internal_error", f"mapped to internal_error: {result}"


class TestBusTrustUnknownId:
    """Unknown stop ids on check_bus_trust map to not_found and keep serving."""

    @hyp_settings(max_examples=100)
    @given(stop_id=_UNKNOWN_IDS)
    def test_unknown_stop_id_is_not_found(self, stop_id):
        """Unknown stop_id -> not_found naming the id; tool never raises and
        keeps accepting calls afterwards."""
        trimmed = validate_id(stop_id, field="stop_id")
        with _notfound_service("get_bus_trust", trimmed):
            # The tool must not raise; it returns a typed error dict.
            result = check_bus_trust(stop_id=stop_id)
            _assert_not_found(result, trimmed)
            # A subsequent call still works: the tool kept accepting calls.
            again = check_bus_trust(stop_id=stop_id)
            _assert_not_found(again, trimmed)


class TestDockTrustUnknownId:
    """Unknown station ids on check_dock_trust map to not_found and keep serving."""

    @hyp_settings(max_examples=100)
    @given(station_id=_UNKNOWN_IDS)
    def test_unknown_station_id_is_not_found(self, station_id):
        """Unknown station_id -> not_found naming the id; tool never raises and
        keeps accepting calls afterwards."""
        trimmed = validate_id(station_id, field="station_id")
        with _notfound_service("get_dock_trust", trimmed):
            result = check_dock_trust(station_id=station_id)
            _assert_not_found(result, trimmed)
            again = check_dock_trust(station_id=station_id)
            _assert_not_found(again, trimmed)
