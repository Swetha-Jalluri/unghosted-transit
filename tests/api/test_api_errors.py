# Feature: unghosted-demo, Property 12: Service failures are mapped without leaking detail
"""Property 12 (API part): service failures are mapped without leaking detail.

For any exception message text, when the Service raises ``LiveDataUnavailable``
the API returns 503 with ``error == "live_unavailable"``; when it raises any
other exception the API returns 500 with ``error == "internal_error"``. In both
cases the response body contains neither the exception text nor a stack trace
(no file path, no ``Traceback`` marker) (R8.5, R8.6).

The test drives the ``bus-trust`` route with a valid request (so validation
passes and the handler reaches the Service) and monkeypatches
``core.service.get_bus_trust`` to raise the generated exception. Routes come
from ``SETTINGS.api_routes`` (no hardcoded paths).

A standalone ``failing_client`` context manager (not a pytest fixture) is used
inside the ``@given`` body, mirroring ``conftest.spied_client``: Hypothesis does
not reset function-scoped fixtures between examples, so each generated input
gets a freshly built app and a cleanly restored ``core.service`` on exit, which
also avoids ``FailedHealthCheck``.

**Validates: Requirements 8.5, 8.6**
"""
from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient
from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from api.main import create_app
from app.settings import SETTINGS
from core import service
from core.contracts import LiveDataUnavailable

# Route paths come from Settings (no hardcoded paths). A valid bus-trust request
# passes validation, so the handler reaches the spied service function.
BUS_TRUST = SETTINGS.api_routes["bus_trust"]
_VALID_PARAMS = {"stop_id": "place-x", "mode": "demo"}


@contextmanager
def failing_client(exc: BaseException):
    """Yield a ``TestClient`` whose ``get_bus_trust`` raises ``exc``.

    ``raise_server_exceptions=False`` lets the app's registered ``Exception``
    handler produce the 500 response instead of the client re-raising, so the
    500 mapping (R8.6) can be asserted. The original ``core.service`` function
    is restored on exit.
    """
    original = service.get_bus_trust

    def _raise(*_args, **_kwargs):
        raise exc

    service.get_bus_trust = _raise
    try:
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        service.get_bus_trust = original


# A distinctive marker wrapped around every generated message. If the API ever
# echoed the raised exception's text into the response, this marker would appear
# in the body. A fixed generic message can never contain it, so asserting the
# marker's absence tests the real property (the exception text is not leaked)
# without false positives from short message characters that happen to also
# occur in the fixed "live data is unavailable" / "an internal error occurred"
# text.
_LEAK_MARKER = "ZZ_UNGHOSTED_LEAK_MARKER_ZZ"


def _assert_no_leak(body_text: str, marked_message: str) -> None:
    """Assert the body leaks neither the exception text nor a stack trace.

    ``marked_message`` is the exact text the exception was raised with. It
    carries ``_LEAK_MARKER`` on both sides, so any verbatim echo of the
    exception text (whole or in part around the marker) would surface the marker
    in the body.
    """
    # The marker (and therefore the raised exception text) must not appear.
    assert _LEAK_MARKER not in body_text, (
        f"exception message leaked into body: {body_text!r}"
    )
    assert marked_message not in body_text, (
        f"exception message leaked into body: {body_text!r}"
    )
    # No stack-trace markers or source file paths.
    assert "Traceback" not in body_text, f"stack trace leaked: {body_text!r}"
    assert ".py" not in body_text, f"source path leaked: {body_text!r}"
    assert "File \"" not in body_text, f"traceback frame leaked: {body_text!r}"


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


class TestLiveUnavailableMapsTo503:
    """``LiveDataUnavailable`` -> 503 live_unavailable, no detail leaked."""

    @hyp_settings(max_examples=100)
    @given(message=_MESSAGES)
    def test_live_unavailable_503(self, message):
        with failing_client(LiveDataUnavailable(message)) as client:
            resp = client.get(BUS_TRUST, params=_VALID_PARAMS)

        assert resp.status_code == 503, (
            f"expected 503, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body["error"] == "live_unavailable", body
        _assert_no_leak(resp.text, message)


class TestOtherExceptionMapsTo500:
    """Any non-typed exception -> 500 internal_error, no detail leaked."""

    @hyp_settings(max_examples=100)
    @given(message=_MESSAGES)
    def test_generic_exception_500(self, message):
        with failing_client(Exception(message)) as client:
            resp = client.get(BUS_TRUST, params=_VALID_PARAMS)

        assert resp.status_code == 500, (
            f"expected 500, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body["error"] == "internal_error", body
        _assert_no_leak(resp.text, message)

    @hyp_settings(max_examples=100)
    @given(message=_MESSAGES)
    def test_runtime_error_500(self, message):
        with failing_client(RuntimeError(message)) as client:
            resp = client.get(BUS_TRUST, params=_VALID_PARAMS)

        assert resp.status_code == 500, (
            f"expected 500, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body["error"] == "internal_error", body
        _assert_no_leak(resp.text, message)
