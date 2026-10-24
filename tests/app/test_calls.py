"""Property tests for exception mapping in ``app.calls.call``.

# Feature: unghosted-demo, Property 10: Service exceptions map to typed outcomes
"""
from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from app.calls import CallResult, call
from core.contracts import LiveDataUnavailable, NotFound

# A sentinel wraps every generated exception message so that an assertion like
# "msg not in result.message" cannot fail because the message happened to be an
# incidental substring of the user-safe text (e.g. an empty string, or "data").
_SENTINEL_OPEN = "\u2063<<MSG:"
_SENTINEL_CLOSE = ">>\u2063"


def _wrap(msg: str) -> str:
    """Wrap a generated message in a sentinel so substring checks are honest."""
    return f"{_SENTINEL_OPEN}{msg}{_SENTINEL_CLOSE}"


# Arbitrary text for exception messages (may be empty, unicode, punctuation...).
_messages = st.text()
# Modes we exercise. "live" is special-cased; the others are ordinary.
_non_live_modes = st.sampled_from(["demo", "replay"])
_any_mode = st.sampled_from(["live", "demo", "replay"])


class _Counter:
    """A callable-call counter shared between a stub and its assertions."""

    def __init__(self) -> None:
        self.count = 0
        self.modes: list[str] = []

    def record(self, mode: str) -> None:
        self.count += 1
        self.modes.append(mode)


# Feature: unghosted-demo, Property 10: Service exceptions map to typed outcomes
@settings(max_examples=150)
@given(msg=_messages, mode=_any_mode)
def test_not_found_maps_to_not_found_without_fallback(msg: str, mode: str) -> None:
    """NotFound -> not_found, never re-raised, never falls back, called once.

    Validates: Requirements 1.13, 2.6, 3.4
    """
    wrapped = _wrap(msg)
    counter = _Counter()

    def stub(resource_id: str, *, mode: str, **_: Any) -> Any:
        counter.record(mode)
        raise NotFound(wrapped)

    result: CallResult[Any] = call(stub, "the-id", mode=mode)

    assert result.kind == "not_found"
    assert result.ok is False
    assert result.value is None
    # NotFound never triggers a Demo fallback, so the stub runs exactly once.
    assert counter.count == 1
    assert result.fell_back is False
    # The exception text never leaks into the user-safe message.
    assert wrapped not in result.message


# Feature: unghosted-demo, Property 10: Service exceptions map to typed outcomes
@settings(max_examples=150)
@given(msg=_messages)
def test_live_unavailable_live_mode_falls_back_to_demo(msg: str) -> None:
    """LiveDataUnavailable in live mode retries in demo; success -> ok+fell_back.

    Validates: Requirements 1.13, 3.5, 3.6
    """
    wrapped = _wrap(msg)
    counter = _Counter()
    marker = object()

    def stub(resource_id: str, *, mode: str, **_: Any) -> Any:
        counter.record(mode)
        if mode == "live":
            raise LiveDataUnavailable(wrapped)
        return marker

    result: CallResult[Any] = call(stub, "the-id", mode="live")

    assert result.kind == "ok"
    assert result.ok is True
    assert result.value is marker
    assert result.fell_back is True
    assert result.mode_shown == "demo"
    # Retried exactly once in demo: live attempt + demo retry.
    assert counter.count == 2
    assert counter.modes == ["live", "demo"]
    assert wrapped not in result.message


# Feature: unghosted-demo, Property 10: Service exceptions map to typed outcomes
@settings(max_examples=150)
@given(msg=_messages)
def test_live_unavailable_live_mode_demo_also_fails(msg: str) -> None:
    """LiveDataUnavailable always raising -> live_unavailable, no leak.

    Validates: Requirements 1.13, 3.4
    """
    wrapped = _wrap(msg)
    counter = _Counter()

    def stub(resource_id: str, *, mode: str, **_: Any) -> Any:
        counter.record(mode)
        raise LiveDataUnavailable(wrapped)

    result: CallResult[Any] = call(stub, "the-id", mode="live")

    assert result.kind == "live_unavailable"
    assert result.ok is False
    assert result.value is None
    assert result.fell_back is False
    assert wrapped not in result.message


# Feature: unghosted-demo, Property 10: Service exceptions map to typed outcomes
@settings(max_examples=150)
@given(msg=_messages, mode=_non_live_modes)
def test_live_unavailable_non_live_mode_no_fallback(msg: str, mode: str) -> None:
    """LiveDataUnavailable outside live mode -> live_unavailable, no fallback.

    Validates: Requirements 1.13, 3.4
    """
    wrapped = _wrap(msg)
    counter = _Counter()

    def stub(resource_id: str, *, mode: str, **_: Any) -> Any:
        counter.record(mode)
        raise LiveDataUnavailable(wrapped)

    result: CallResult[Any] = call(stub, "the-id", mode=mode)

    assert result.kind == "live_unavailable"
    assert result.ok is False
    # No fallback is attempted outside live mode, so the stub runs once.
    assert counter.count == 1
    assert result.fell_back is False
    assert wrapped not in result.message


# Feature: unghosted-demo, Property 10: Service exceptions map to typed outcomes
@settings(max_examples=150)
@given(msg=_messages, mode=_any_mode)
def test_generic_exception_maps_to_error(msg: str, mode: str) -> None:
    """Any other exception -> error, never re-raised, no leak.

    Validates: Requirements 1.13, 2.6
    """
    wrapped = _wrap(msg)

    def stub(resource_id: str, *, mode: str, **_: Any) -> Any:
        raise ValueError(wrapped)

    result: CallResult[Any] = call(stub, "the-id", mode=mode)

    assert result.kind == "error"
    assert result.ok is False
    assert result.value is None
    assert result.fell_back is False
    assert wrapped not in result.message


# Feature: unghosted-demo, Property 10: Service exceptions map to typed outcomes
@settings(max_examples=150)
@given(mode=_any_mode)
def test_ok_passes_value_through(mode: str) -> None:
    """A successful call -> ok, value passed through, mode_shown == mode.

    Validates: Requirements 3.4
    """
    marker = object()

    def stub(resource_id: str, *, mode: str, **_: Any) -> Any:
        return marker

    result: CallResult[Any] = call(stub, "the-id", mode=mode)

    assert result.kind == "ok"
    assert result.ok is True
    assert result.value is marker
    assert result.mode_shown == mode
    assert result.fell_back is False


# Feature: unghosted-demo, Property 10: Service exceptions map to typed outcomes
@settings(max_examples=150)
@given(mode=_any_mode)
def test_no_caching_calls_service_each_time(mode: str) -> None:
    """Calling twice invokes the stub twice: there is no caching (R3.5).

    Validates: Requirements 3.5
    """
    marker = object()
    counter = _Counter()

    def stub(resource_id: str, *, mode: str, **_: Any) -> Any:
        counter.record(mode)
        return marker

    first: CallResult[Any] = call(stub, "the-id", mode=mode)
    second: CallResult[Any] = call(stub, "the-id", mode=mode)

    assert first.kind == "ok"
    assert second.kind == "ok"
    # Two calls, two service invocations: nothing is cached between calls.
    assert counter.count == 2
