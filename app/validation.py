"""Pure input validators shared by the MCP tools and the Rider walk-minutes input.

Each validator returns the cleaned value or raises :class:`InvalidInput`, which
carries the offending field name and a human-readable description of the allowed
range or values. The module performs no I/O, clock reads, randomness or
mutation, so it can be property-tested directly (Property 8).

Numeric bounds are supplied by the caller from ``app.settings.SETTINGS`` (for
example ``SETTINGS.walk_min["min"]`` / ``["max"]`` and ``SETTINGS.limit``), so no
bound is hardcoded here. Latitude and longitude bounds are the fixed geographic
ranges (-90..90 and -180..180) required by Requirements 2.5, 8.3 and 9.2.

Booleans are always rejected where a number is expected: ``bool`` is a subclass
of ``int`` in Python, and ``True``/``False`` are not valid numeric inputs.
"""
from __future__ import annotations

from numbers import Real

# Fixed geographic bounds (degrees). Not configurable; defined by the coordinate
# system, not by Settings.
_LAT_MIN = -90.0
_LAT_MAX = 90.0
_LON_MIN = -180.0
_LON_MAX = 180.0

# Id length bounds (characters, after trimming whitespace).
_ID_MIN_LEN = 1
_ID_MAX_LEN = 64


class InvalidInput(Exception):
    """Raised when an input fails validation.

    Attributes
    ----------
    field:
        The name of the offending input field.
    allowed:
        A human-readable description of the allowed range or values.
    """

    def __init__(self, field: str, allowed: str) -> None:
        self.field = field
        self.allowed = allowed
        super().__init__(f"{field}: allowed {allowed}")


def _is_real_number(value: object) -> bool:
    """Return True for a genuine real number, rejecting booleans.

    ``bool`` is a subclass of ``int`` so ``True``/``False`` would otherwise pass
    as numbers; they are rejected explicitly.
    """
    if isinstance(value, bool):
        return False
    return isinstance(value, Real)


def validate_id(value: object, field: str = "id") -> str:
    """Return a trimmed id string of 1 to 64 characters, else raise.

    A non-string, or a string that is empty or longer than 64 characters after
    trimming surrounding whitespace, is rejected.
    """
    allowed = f"non-empty string of {_ID_MIN_LEN} to {_ID_MAX_LEN} characters"
    if not isinstance(value, str):
        raise InvalidInput(field, allowed)
    trimmed = value.strip()
    if not (_ID_MIN_LEN <= len(trimmed) <= _ID_MAX_LEN):
        raise InvalidInput(field, allowed)
    return trimmed


def validate_mode(value: object, modes, field: str = "mode") -> str:
    """Return ``value`` when it is one of ``modes``, else raise.

    ``modes`` is the allowed collection (``SETTINGS.modes``).
    """
    allowed = "one of " + ", ".join(str(m) for m in modes)
    if not isinstance(value, str) or value not in modes:
        raise InvalidInput(field, allowed)
    return value


def validate_int_in(
    value: object, minimum: int, maximum: int, field: str = "value"
) -> int:
    """Return ``value`` as an int within ``[minimum, maximum]``, else raise.

    Booleans and non-integer values are rejected. Bounds come from the caller
    (Settings), not from this module.
    """
    allowed = f"integer in {minimum} to {maximum}"
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidInput(field, allowed)
    if not (minimum <= value <= maximum):
        raise InvalidInput(field, allowed)
    return value


def validate_number_in(
    value: object, minimum: float, maximum: float, field: str = "value"
) -> float:
    """Return ``value`` as a float within ``[minimum, maximum]``, else raise.

    Booleans and non-numeric values are rejected. Bounds come from the caller
    (Settings), not from this module.
    """
    allowed = f"number in {minimum} to {maximum}"
    if not _is_real_number(value):
        raise InvalidInput(field, allowed)
    number = float(value)
    if not (minimum <= number <= maximum):
        raise InvalidInput(field, allowed)
    return number


def validate_lat(value: object, field: str = "lat") -> float:
    """Return ``value`` as a latitude in -90 to 90, else raise."""
    try:
        return validate_number_in(value, _LAT_MIN, _LAT_MAX, field)
    except InvalidInput:
        raise InvalidInput(field, f"number in {_LAT_MIN} to {_LAT_MAX}") from None


def validate_lon(value: object, field: str = "lon") -> float:
    """Return ``value`` as a longitude in -180 to 180, else raise."""
    try:
        return validate_number_in(value, _LON_MIN, _LON_MAX, field)
    except InvalidInput:
        raise InvalidInput(field, f"number in {_LON_MIN} to {_LON_MAX}") from None


def validate_at_ts(value: object, field: str = "at_ts") -> int:
    """Return ``value`` as a non-negative integer POSIX timestamp, else raise.

    Only used when ``at_ts`` is supplied; callers pass ``None`` through
    untouched rather than calling this validator.
    """
    allowed = "non-negative integer POSIX seconds"
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidInput(field, allowed)
    if value < 0:
        raise InvalidInput(field, allowed)
    return value
