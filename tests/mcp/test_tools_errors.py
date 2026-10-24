# Feature: unghosted-demo, Property 12: Service failures are mapped without leaking detail
"""Property 12 (MCP part): service failures are mapped without leaking detail.

For any exception message text, when the Service raises ``LiveDataUnavailable``
the MCP tool returns a ``live_unavailable`` error result that suggests demo
mode; when it raises any other exception the tool returns an ``internal_error``
result. In both cases the result contains neither the exception text nor a stack
trace (no ``Traceback`` marker, no source path), and the tool keeps accepting
calls afterwards (R9.5, R9.6).

The tool functions in ``mcp_server.tools`` do ``from core import service`` and
call ``service.get_bus_trust(...)`` at call time, so each generated message
replaces ``core.service.get_bus_trust`` with a stub that raises the chosen
exception. The tool's ``except LiveDataUnavailable`` / ``except Exception``
branch turns that into the typed error dict; the test checks only the tool's
delivery behavior, not the demo data.

A function-scoped fixture cannot be reused across Hypothesis examples, so the
stub is installed inside a standalone context manager and the original restored
on exit, mirroring the API errors test and ``conftest.spied_service``.

Each generated message is wrapped in a distinctive sentinel marker on both
sides, so a verbatim echo of the exception text (whole or partial) would surface
the marker in the result. A fixed generic error message can never contain the
marker, so asserting the marker's absence tests the real property (the exception
text is not leaked) without false positives from short message characters that
happen to also occur in the fixed error text.

**Validates: Requirements 9.5, 9.6**
"""
from __future__ import annotations

import json
from contextlib import contextmanager

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from core import service
from core.contracts import LiveDataUnavailable
from mcp_server.tools import check_bus_trust

# A known-good demo stop, used to prove the tool keeps accepting calls after an
# error was mapped (R9.6). Taken from the demo stops fixture.
_VALID_STOP_ID = "place-haecl"


@contextmanager
def _failing_service(exc: BaseException):
    """Make ``core.service.get_bus_trust`` raise ``exc``.

    Replaces the attribute on the ``core.service`` module object (which the tool
    resolves at call time) with a stub that raises regardless of arguments, and
    restores the original on exit. A standalone context manager so it can be
    used inside a ``@given`` body, giving every generated message a clean stub.
    """
    original = service.get_bus_trust

    def _raise(*_args, **_kwargs):
        raise exc

    service.get_bus_trust = _raise
    try:
        yield
    finally:
        service.get_bus_trust = original


# A distinctive marker wrapped around every generated message. If a tool ever
# echoed the raised exception's text into the result, this marker would appear.
# A fixed generic message can never contain it, so asserting its absence tests
# the real property without false positives from incidental substrings.
_LEAK_MARKER = "ZZ_UNGHOSTED_LEAK_MARKER_ZZ"


def _result_text(result: dict) -> str:
    """Serialize the whole result dict to text for leak scanning."""
    return json.dumps(result, default=str)


def _assert_no_leak(result: dict, marked_message: str) -> None:
    """Assert the result leaks neither the exception text nor a stack trace.

    ``marked_message`` is the exact text the exception was raised with; it
    carries ``_LEAK_MARKER`` on both sides, so any verbatim echo of the
    exception text (whole or around the marker) would surface the marker.
    """
    text = _result_text(result)
    assert _LEAK_MARKER not in text, (
        f"exception message leaked into result: {text!r}"
    )
    assert marked_message not in text, (
        f"exception message leaked into result: {text!r}"
    )
    # No stack-trace markers or source file paths.
    assert "Traceback" not in text, f"stack trace leaked: {text!r}"
    assert ".py" not in text, f"source path leaked: {text!r}"
    assert 'File "' not in text, f"traceback frame leaked: {text!r}"


def _assert_valid_call_works() -> None:
    """A subsequent valid demo call still succeeds (server keeps accepting).

    Called after the failing stub is restored (outside the ``with`` block), so
    this exercises the tool's normal path and proves it kept accepting calls
    rather than crashing or being left in a broken state (R9.6).
    """
    again = check_bus_trust(stop_id=_VALID_STOP_ID, mode="demo")
    assert again["ok"] is True, f"tool stopped accepting calls: {again}"


# Inner message text spans plausible exception content: letters, digits,
# punctuation, path-like and traceback-looking fragments. The marker is added
# around it so a naive echo of the message would be detectable.
_INNER = st.text(
    alphabet=st.characters(
        min_codepoint=32, max_codepoint=126, blacklist_categories=("Cs",)
    ),
    min_size=0,
    max_size=120,
)
_MESSAGES = _INNER.map(lambda s: f"{_LEAK_MARKER}{s}{_LEAK_MARKER}")


class TestLiveUnavailableMaps:
    """``LiveDataUnavailable`` -> live_unavailable suggesting demo, no leak."""

    @hyp_settings(max_examples=100)
    @given(message=_MESSAGES)
    def test_live_unavailable(self, message):
        """LiveDataUnavailable(msg) -> live_unavailable error mentioning demo;
        msg text not leaked; tool keeps accepting calls."""
        with _failing_service(LiveDataUnavailable(message)):
            result = check_bus_trust(stop_id=_VALID_STOP_ID, mode="demo")

        assert result["ok"] is False, f"expected failure, got: {result}"
        error = result["error"]
        assert error["code"] == "live_unavailable", (
            f"expected live_unavailable, got {error['code']}: {result}"
        )
        # The message suggests demo mode as an alternative (R9.5).
        assert "demo" in error["message"].lower(), (
            f"message does not mention demo mode: {error['message']!r}"
        )
        _assert_no_leak(result, message)
        # After the stub is restored, the tool still accepts calls (R9.6).
        _assert_valid_call_works()


class TestOtherExceptionMaps:
    """Any non-typed exception -> internal_error, no leak, keeps serving."""

    @hyp_settings(max_examples=100)
    @given(message=_MESSAGES)
    def test_generic_exception(self, message):
        """Exception(msg) -> internal_error; msg text not leaked, no traceback;
        tool keeps accepting calls."""
        with _failing_service(Exception(message)):
            result = check_bus_trust(stop_id=_VALID_STOP_ID, mode="demo")

        assert result["ok"] is False, f"expected failure, got: {result}"
        error = result["error"]
        assert error["code"] == "internal_error", (
            f"expected internal_error, got {error['code']}: {result}"
        )
        _assert_no_leak(result, message)
        # After the stub is restored, the tool still accepts calls (R9.6).
        _assert_valid_call_works()

    @hyp_settings(max_examples=100)
    @given(message=_MESSAGES)
    def test_runtime_error(self, message):
        """RuntimeError(msg) -> internal_error; msg text not leaked, no
        traceback; tool keeps accepting calls."""
        with _failing_service(RuntimeError(message)):
            result = check_bus_trust(stop_id=_VALID_STOP_ID, mode="demo")

        assert result["ok"] is False, f"expected failure, got: {result}"
        error = result["error"]
        assert error["code"] == "internal_error", (
            f"expected internal_error, got {error['code']}: {result}"
        )
        _assert_no_leak(result, message)
        # After the stub is restored, the tool still accepts calls (R9.6).
        _assert_valid_call_works()
