"""Service-call wrapper with typed results and Live-to-Demo fallback.

The Streamlit views call the Service only through :func:`call`, which turns the
Service's exceptions into a :class:`CallResult`. This keeps exception text out
of the UI, gives every view a single place to read the mode actually shown, and
implements the one visible fallback rule: a ``LiveDataUnavailable`` raised while
``mode == "live"`` retries once in ``"demo"`` and reports ``fell_back=True``.

No caching happens here on purpose: choosing Live again re-requests the Service
(R3.5). ``at_ts`` is forwarded to the Service only when it is not ``None`` so we
do not pass it to functions that have no such parameter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, Literal, Optional, TypeVar

from core.contracts import LiveDataUnavailable, NotFound

T = TypeVar("T")

CallKind = Literal["ok", "not_found", "live_unavailable", "error"]


@dataclass(frozen=True)
class CallResult(Generic[T]):
    """Typed outcome of a single Service call.

    Attributes:
        ok: True only when the Service returned a value (including a Demo
            fallback value after a Live failure).
        value: The Service return value, or ``None`` when the call did not
            succeed.
        kind: One of ``ok``, ``not_found``, ``live_unavailable``, ``error``.
        mode_shown: The mode of the data actually displayed. After a Live to
            Demo fallback this is ``"demo"``.
        fell_back: True when a Live request failed and Demo data is shown.
        message: User-safe text. Never contains exception detail.
        missing_id: The id that was not found, for ``not_found`` messages.
    """

    ok: bool
    value: Optional[T]
    kind: CallKind
    mode_shown: str
    fell_back: bool
    message: str
    missing_id: Optional[str]


def _first_id(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Optional[str]:
    """Best-effort id for a NotFound message, without exception text.

    The Service's trust functions take the resource id as the first positional
    argument (``stop_id`` / ``station_id``). We surface it so the view can name
    the missing id; nothing from the exception itself is used.
    """
    for key in ("stop_id", "station_id"):
        if key in kwargs and isinstance(kwargs[key], str):
            return kwargs[key]
    if args and isinstance(args[0], str):
        return args[0]
    return None


def call(fn: Callable[..., T], *args: Any, mode: str, **kwargs: Any) -> CallResult[T]:
    """Call ``fn(*args, mode=mode, **kwargs)`` and map exceptions to a result.

    - ``NotFound`` -> ``kind="not_found"``, no fallback, selected mode kept.
    - ``LiveDataUnavailable`` with ``mode == "live"`` -> retry once in ``"demo"``;
      on success return ``fell_back=True, mode_shown="demo"``. In any other mode
      (or if the Demo retry also fails) return ``kind="live_unavailable"``.
    - Any other exception -> ``kind="error"`` with a generic, user-safe message.

    ``at_ts`` is forwarded only when it is not ``None`` so functions without an
    ``at_ts`` parameter are never passed one.
    """
    # Drop at_ts entirely when None so we never pass it to functions that have
    # no such parameter (e.g. get_nearby_docks).
    if kwargs.get("at_ts", "unset") is None:
        kwargs = {k: v for k, v in kwargs.items() if k != "at_ts"}

    try:
        value = fn(*args, mode=mode, **kwargs)
        return CallResult(
            ok=True,
            value=value,
            kind="ok",
            mode_shown=mode,
            fell_back=False,
            message="",
            missing_id=None,
        )
    except NotFound:
        missing_id = _first_id(args, kwargs)
        if missing_id:
            message = f"No data found for '{missing_id}'."
        else:
            message = "No data found for that selection."
        return CallResult(
            ok=False,
            value=None,
            kind="not_found",
            mode_shown=mode,
            fell_back=False,
            message=message,
            missing_id=missing_id,
        )
    except LiveDataUnavailable:
        if mode == "live":
            try:
                value = fn(*args, mode="demo", **kwargs)
                return CallResult(
                    ok=True,
                    value=value,
                    kind="ok",
                    mode_shown="demo",
                    fell_back=True,
                    message="Live data is unavailable. Showing Demo data.",
                    missing_id=None,
                )
            except Exception:
                # The Demo retry failed too (including another NotFound or
                # LiveDataUnavailable); report Live as unavailable without
                # leaking exception detail.
                return CallResult(
                    ok=False,
                    value=None,
                    kind="live_unavailable",
                    mode_shown="live",
                    fell_back=False,
                    message="Live data is unavailable right now.",
                    missing_id=None,
                )
        return CallResult(
            ok=False,
            value=None,
            kind="live_unavailable",
            mode_shown=mode,
            fell_back=False,
            message="Live data is unavailable right now.",
            missing_id=None,
        )
    except Exception:
        return CallResult(
            ok=False,
            value=None,
            kind="error",
            mode_shown=mode,
            fell_back=False,
            message="Something went wrong. Please try again.",
            missing_id=None,
        )
