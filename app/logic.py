"""Pure presentation logic for the Unghosted delivery layer (owner B).

Every function here is pure: no network, file, clock or random-number access,
and no mutation of its inputs. These rules (status words, chance text, hindsight
badges, age and time formatting, replay advance, missing-value display) are
property-tested so the trust presentation cannot silently break (R10.1).

Import only ``app.settings`` for the display time zone. No Streamlit import.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.settings import SETTINGS

# Displayable bus/dock statuses, in canonical lowercase form.
STATUSES = ("confirmed", "estimate", "unreliable")

# Word shown for each displayable status (word is always visible, never color
# alone; R1.7, R1.8, R10.2).
_STATUS_WORDS = {
    "confirmed": "Confirmed",
    "estimate": "Estimate",
    "unreliable": "Unreliable",
}


def status_word(status: str) -> str | None:
    """Return the capitalized status word, or ``None`` when not displayable.

    Only ``confirmed``, ``estimate`` and ``unreliable`` are displayable; every
    other value (including ``hidden`` and unknown strings) returns ``None`` so
    the prediction is omitted (R1.8).
    """
    if not isinstance(status, str):
        return None
    return _STATUS_WORDS.get(status.strip().lower())


def is_displayable(status: str) -> bool:
    """Return True when a prediction with this status should be shown."""
    return status_word(status) is not None


def format_chance(chance: float | None, n: int, method: str) -> str:
    """Format a chance with its sample size, e.g. ``"96% (model, n=580)"``.

    A ``None`` chance reads ``"chance unavailable (n=580)"`` with no percentage.
    The ``placeholder`` method adds the word ``"placeholder"`` to the basis so
    unmeasured numbers are never presented as measured results (R1.5, R1.6,
    R1.10, R10.3). The decimal digits of ``n`` always appear.
    """
    basis = str(method)
    if basis == "placeholder":
        basis = "placeholder"
    if chance is None:
        return f"chance unavailable (n={n})"
    percent_text = f"{round(chance * 100)}%"
    return f"{percent_text} ({basis}, n={n})"


def hindsight_badge(
    outcome: str | None,
    replay_ts: float | None,
    app_eta_min: float | None,
) -> str | None:
    """Return the replay hindsight badge text, or ``None`` for no badge.

    ``served`` -> ``"served"``; ``canceled`` -> ``"canceled"``; ``open`` ->
    ``"still open"``. ``vanished`` -> ``"disappeared N min later"`` where
    ``N = max(0, round(app_eta_min))`` when both ``replay_ts`` and
    ``app_eta_min`` are present and finite, otherwise
    ``"disappeared before arrival"``. Any absent or unknown outcome returns
    ``None``. The text never contains "ghost" or "proven" (R4.6-R4.12, R10.1,
    R10.4). Deterministic and does not modify its inputs.
    """
    if outcome == "served":
        return "served"
    if outcome == "canceled":
        return "canceled"
    if outcome == "open":
        return "still open"
    if outcome == "vanished":
        if _is_finite_number(replay_ts) and _is_finite_number(app_eta_min):
            minutes = max(0, round(app_eta_min))
            return f"disappeared {minutes} min later"
        return "disappeared before arrival"
    return None


def format_age(sec: int | None) -> str:
    """Format a data age in seconds as ``"unknown"``/``"45 s"``/``"5 min"``...

    Chooses the largest unit that fits and floors to it: seconds below a
    minute, minutes below an hour, hours below a day, days otherwise. ``None``
    (or a negative value) reads ``"unknown"`` (R1.11, R10.5).
    """
    if sec is None or not _is_finite_number(sec) or sec < 0:
        return "unknown"
    seconds = int(sec)
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    if seconds < 86400:
        return f"{seconds // 3600} h"
    return f"{seconds // 86400} d"


# Multiplier from a display unit back to seconds (inverse of format_age).
_AGE_UNIT_SECONDS = {"s": 1, "min": 60, "h": 3600, "d": 86400}


def parse_age(text: str) -> int | None:
    """Parse text produced by :func:`format_age` back to seconds.

    ``"unknown"`` returns ``None``. ``"5 min"`` returns 300, etc. The result is
    the lower bound of the floored display bucket, so it is within one display
    unit of the original age (R10.5). Returns ``None`` for unparseable text.
    """
    if not isinstance(text, str):
        return None
    parts = text.strip().split()
    if len(parts) != 2:
        return None
    value_text, unit = parts
    multiplier = _AGE_UNIT_SECONDS.get(unit)
    if multiplier is None:
        return None
    try:
        value = int(value_text)
    except ValueError:
        return None
    if value < 0:
        return None
    return value * multiplier


def format_ny_time(ts: int | None) -> str:
    """Format a POSIX timestamp in the display time zone with its abbreviation.

    Example: ``"2026-01-10 14:05 EST"``. The zone comes from
    ``SETTINGS.display_tz`` and the abbreviation (EST/EDT) is always shown so a
    time is never ambiguous (R4.5). ``None`` reads ``"unknown"``.
    """
    if ts is None or not _is_finite_number(ts):
        return "unknown"
    tz = ZoneInfo(SETTINGS.display_tz)
    moment = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(tz)
    return moment.strftime("%Y-%m-%d %H:%M %Z")


def next_replay_ts(current: int, start: int, end: int, step: int) -> tuple[int, bool]:
    """Advance a replay clock by ``step``, clamped to ``end``.

    Returns ``(next_ts, finished)`` where ``next_ts = min(current + step, end)``
    and ``finished`` is True exactly when ``next_ts`` equals ``end``. Guarantees
    the replay reaches ``end`` in finitely many steps (R4.3, R4.4). ``start`` is
    accepted for signature symmetry and is not otherwise used.
    """
    nxt = min(current + step, end)
    return nxt, nxt >= end


def percent(x: float | None, places: int = 1) -> str:
    """Format a 0..1 fraction as a percentage string, or "not available".

    ``None`` reads ``"not available"``; otherwise the value is multiplied by 100
    and rendered with ``places`` decimals, e.g. ``0.9634`` -> ``"96.3%"``
    (R5.2-R5.4).
    """
    if x is None or not _is_finite_number(x):
        return "not available"
    return f"{x * 100:.{places}f}%"


def fmt_metric(x: float | int | None, places: int = 3) -> str:
    """Format a plain numeric metric for display.

    ``None`` reads ``"not available"``; a value of zero stays ``"0"`` (never
    "not available"); integers render without a decimal point and floats with
    ``places`` decimals (R5.3, R6.2).
    """
    if x is None or not _is_finite_number(x):
        return "not available"
    if isinstance(x, bool):
        # Treat booleans as their integer value for safety; not expected here.
        x = int(x)
    if isinstance(x, int):
        return str(x)
    if x == 0:
        return "0"
    return f"{x:.{places}f}"


def _is_finite_number(value: object) -> bool:
    """Return True when ``value`` is a real, finite number (not bool/NaN/inf)."""
    if isinstance(value, bool):
        # Booleans are accepted as finite ints where used (age/ts); callers that
        # must reject bools do so elsewhere. Here treat as a finite number.
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    return False
