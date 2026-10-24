"""Plain, read-only MCP tool functions over ``core.service``.

Each function validates its inputs through :mod:`app.validation` *before* any
Service call, then returns a plain dict. These functions never raise: every
failure path (bad input, unknown id, live data unavailable, or any unexpected
error) is turned into a typed error dict so the FastMCP server in
``mcp_server/server.py`` can register them directly and keep serving (R9.1-9.8,
R10.9).

Result shapes
-------------
Success::

    {"ok": True,
     "data": <model_dump or list of model_dump>,
     "data_age_sec": {...},
     "attribution": [<ATTRIBUTION string>],
     "disclaimer": DISCLAIMER}

Error::

    {"ok": False,
     "error": {"code": "invalid_input" | "not_found" | "live_unavailable"
                       | "internal_error",
               "field"?: str,
               "message": str}}

``data_age_sec`` rules (from the design):
- bus tools use ``BusTrustResponse.data_age_sec``;
- dock tools use ``{"docks": <last_reported_age_sec>}`` (``None`` when absent);
- ``list_demo_stops`` and ``todays_findings`` report ``{}`` because the Service
  reports no age for them (findings carry their own ``generated_at``).

Legal text comes from :mod:`app.settings` (single source): ``ATTRIBUTION`` is a
single string shown in a one-element list, ``DISCLAIMER`` is the standard
sentence. These functions perform no writes (read-only, R9.8).
"""
from __future__ import annotations

from typing import Any, Optional

from app.settings import ATTRIBUTION, DISCLAIMER, SETTINGS
from app.validation import (
    InvalidInput,
    validate_at_ts,
    validate_id,
    validate_int_in,
    validate_mode,
    validate_number_in,
    validate_lat,
    validate_lon,
)
from core import service
from core.contracts import LiveDataUnavailable, NotFound


def _ok(data: Any, data_age_sec: dict[str, Any]) -> dict[str, Any]:
    """Build a success envelope with the shared legal text."""
    return {
        "ok": True,
        "data": data,
        "data_age_sec": data_age_sec,
        "attribution": [ATTRIBUTION],
        "disclaimer": DISCLAIMER,
    }


def _error(code: str, message: str, field: Optional[str] = None) -> dict[str, Any]:
    """Build an error envelope. ``field`` is included only when given."""
    error: dict[str, Any] = {"code": code, "message": message}
    if field is not None:
        error["field"] = field
    return {"ok": False, "error": error}


def _invalid(exc: InvalidInput) -> dict[str, Any]:
    """Map an :class:`InvalidInput` to an ``invalid_input`` error dict.

    Names the offending field and the allowed range/values (R9.3).
    """
    return _error(
        "invalid_input",
        f"Invalid {exc.field}: allowed {exc.allowed}.",
        field=exc.field,
    )


def _not_found(resource: str, resource_id: str) -> dict[str, Any]:
    """Map a missing resource to a ``not_found`` error dict, naming the id."""
    return _error("not_found", f"No {resource} found for '{resource_id}'.")


def _live_unavailable() -> dict[str, Any]:
    """Map a live-data failure to a ``live_unavailable`` error dict.

    Suggests demo mode, as the design requires (R9.6).
    """
    return _error(
        "live_unavailable",
        "Live data is unavailable right now. Try mode 'demo'.",
    )


def _internal_error() -> dict[str, Any]:
    """Map any unexpected failure to a generic ``internal_error`` dict.

    Carries no trace or exception text; the server keeps serving (R9.6).
    """
    return _error("internal_error", "Something went wrong. Please try again.")


def _dock_age(last_reported_age_sec: Optional[int]) -> dict[str, Any]:
    """data_age_sec for dock tools: ``{"docks": <age or None>}``."""
    return {"docks": last_reported_age_sec}


def list_demo_stops() -> dict[str, Any]:
    """Return the demo stops as a list of plain dicts.

    No inputs to validate; the Service reports no age, so ``data_age_sec`` is
    ``{}``.
    """
    try:
        stops = service.list_demo_stops()
    except Exception:
        return _internal_error()
    data = [stop.model_dump() for stop in stops]
    return _ok(data, {})


def check_bus_trust(
    stop_id: Any,
    mode: Any = "demo",
    limit: Any = 5,
    at_ts: Any = None,
) -> dict[str, Any]:
    """Return bus trust for ``stop_id`` after validating every input.

    ``data_age_sec`` is the response's own ``data_age_sec`` map.
    """
    try:
        stop_id = validate_id(stop_id, field="stop_id")
        mode = validate_mode(mode, SETTINGS.modes, field="mode")
        limit = validate_int_in(
            limit, SETTINGS.limit["min"], SETTINGS.limit["max"], field="limit"
        )
        if at_ts is not None:
            at_ts = validate_at_ts(at_ts, field="at_ts")
    except InvalidInput as exc:
        return _invalid(exc)

    try:
        response = service.get_bus_trust(
            stop_id, mode=mode, limit=limit, at_ts=at_ts
        )
    except NotFound:
        return _not_found("stop", stop_id)
    except LiveDataUnavailable:
        return _live_unavailable()
    except Exception:
        return _internal_error()

    return _ok(response.model_dump(), dict(response.data_age_sec))


def check_dock_trust(
    station_id: Any,
    walk_min: Any = 5,
    mode: Any = "demo",
    at_ts: Any = None,
) -> dict[str, Any]:
    """Return dock trust for ``station_id`` after validating every input.

    ``data_age_sec`` uses the returned dock's ``last_reported_age_sec``
    (``None`` when absent).
    """
    try:
        station_id = validate_id(station_id, field="station_id")
        walk_min = validate_number_in(
            walk_min,
            SETTINGS.walk_min["min"],
            SETTINGS.walk_min["max"],
            field="walk_min",
        )
        mode = validate_mode(mode, SETTINGS.modes, field="mode")
        if at_ts is not None:
            at_ts = validate_at_ts(at_ts, field="at_ts")
    except InvalidInput as exc:
        return _invalid(exc)

    try:
        response = service.get_dock_trust(
            station_id, walk_min=walk_min, mode=mode, at_ts=at_ts
        )
    except NotFound:
        return _not_found("station", station_id)
    except LiveDataUnavailable:
        return _live_unavailable()
    except Exception:
        return _internal_error()

    return _ok(
        response.model_dump(),
        _dock_age(response.dock.last_reported_age_sec),
    )


def nearby_docks(
    lat: Any,
    lon: Any,
    walk_min: Any = 5,
    limit: Any = 3,
    mode: Any = "demo",
    at_ts: Any = None,
) -> dict[str, Any]:
    """Return nearby docks for a coordinate after validating every input.

    The Service's ``get_nearby_docks`` has no ``at_ts`` parameter, so a supplied
    ``at_ts`` is validated but not forwarded. ``data_age_sec`` uses the first
    returned dock's ``last_reported_age_sec`` (``None`` when empty or absent).
    """
    try:
        lat = validate_lat(lat, field="lat")
        lon = validate_lon(lon, field="lon")
        walk_min = validate_number_in(
            walk_min,
            SETTINGS.walk_min["min"],
            SETTINGS.walk_min["max"],
            field="walk_min",
        )
        limit = validate_int_in(
            limit, SETTINGS.limit["min"], SETTINGS.limit["max"], field="limit"
        )
        mode = validate_mode(mode, SETTINGS.modes, field="mode")
        if at_ts is not None:
            validate_at_ts(at_ts, field="at_ts")
    except InvalidInput as exc:
        return _invalid(exc)

    try:
        docks = service.get_nearby_docks(
            lat, lon, walk_min=walk_min, limit=limit, mode=mode
        )
    except NotFound:
        return _not_found("dock", f"{lat},{lon}")
    except LiveDataUnavailable:
        return _live_unavailable()
    except Exception:
        return _internal_error()

    data = [dock.model_dump() for dock in docks]
    first_age = docks[0].last_reported_age_sec if docks else None
    return _ok(data, _dock_age(first_age))


def todays_findings() -> dict[str, Any]:
    """Return today's findings as a plain dict.

    No inputs to validate; the Service reports no age (findings carry their own
    ``generated_at``), so ``data_age_sec`` is ``{}``.
    """
    try:
        findings = service.get_findings()
    except LiveDataUnavailable:
        return _live_unavailable()
    except Exception:
        return _internal_error()
    return _ok(findings.model_dump(), {})
