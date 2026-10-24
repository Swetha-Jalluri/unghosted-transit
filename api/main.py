"""FastAPI application for the Unghosted REST API (``/v1``).

A thin, unauthenticated, read-only layer over ``core.service``. Every route is
one service call wrapped in error handling; no business logic lives here.

Design points (see .kiro/specs/unghosted-demo/design.md "API"):

* Route paths come from ``SETTINGS.api_routes`` (no hardcoded paths).
* Query bounds come from Settings (``limit``, ``walk_min``) and the fixed
  geographic ranges for ``lat``/``lon``; ``mode`` is a ``Literal`` of
  ``SETTINGS.modes``. FastAPI validates these before the handler body runs, so
  the Service is never called on bad input (R8.3).
* ``bus-trust``, ``dock-trust``, ``health`` and ``replay-window`` return the
  matching ``core.contracts`` model unchanged (R8.7). ``findings`` and
  ``nearby-docks`` wrap their payload in :class:`~api.models.Envelope` so the
  legal text travels with them (R8.8).
* Errors share one JSON shape (:class:`~api.models.ErrorBody`): 422
  ``validation_error`` naming each offending parameter, 404 ``not_found``
  naming the id, 503 ``live_unavailable``, 500 ``internal_error`` with generic
  text only (no stack trace, file path or exception text) (R8.3-R8.6).
* CORS allow headers are added only when ``SETTINGS.cors_origins`` is non-empty;
  no wildcard origin and no credentials (R8.9).

The documented service gap (R12.2) that ``get_nearby_docks`` has no ``at_ts``
parameter is honored here: the route accepts ``at_ts`` for a uniform interface
but does not forward it, rather than working around the gap.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.settings import ATTRIBUTION, DISCLAIMER, SETTINGS
from api.models import Envelope, ErrorBody
from core import service
from core.contracts import (
    BusTrustResponse,
    DockResult,
    DockTrustResponse,
    Findings,
    Health,
    LiveDataUnavailable,
    NotFound,
    ReplayWindow,
)

# ---------------------------------------------------------------------------
# Bounds pulled from Settings once (no hardcoded limits). lat/lon use the fixed
# geographic ranges required by R8.3.
# ---------------------------------------------------------------------------
_LIMIT_MIN = SETTINGS.limit["min"]
_LIMIT_MAX = SETTINGS.limit["max"]
_LIMIT_DEFAULT = SETTINGS.limit["default"]
_WALK_MIN = SETTINGS.walk_min["min"]
_WALK_MAX = SETTINGS.walk_min["max"]
_WALK_DEFAULT = SETTINGS.walk_min["default"]
_LAT_MIN, _LAT_MAX = -90.0, 90.0
_LON_MIN, _LON_MAX = -180.0, 180.0

# ``mode`` as a Literal of the three modes. FastAPI rejects anything else with a
# 422 before the handler runs. Built from SETTINGS.modes to avoid a second
# source of truth.
Mode = Literal[SETTINGS.modes]  # type: ignore[valid-type]

_DEMO_DEFAULT: str = "demo"


def _error_response(status: int, error: str, message: str,
                    params: Optional[list[str]] = None) -> JSONResponse:
    """Build a JSON error response with the shared :class:`ErrorBody` shape.

    ``params`` is emitted only when provided (422), via ``exclude_none`` so the
    key is absent otherwise.
    """
    body = ErrorBody(error=error, message=message, params=params)
    return JSONResponse(status_code=status, content=body.model_dump(exclude_none=True))


def create_app() -> FastAPI:
    """Build and return the FastAPI application.

    Registers the six ``/v1`` routes, the exception handlers that map service
    and validation errors to the shared body, and CORS middleware only when
    origins are configured.
    """
    app = FastAPI(
        title="Unghosted API",
        description=(
            "Unofficial transit trust layer. Unauthenticated and read-only by "
            "design (public derived demo data)."
        ),
        version="1",
    )

    routes = SETTINGS.api_routes

    # -- Exception handlers -------------------------------------------------
    # Validation (422): name each offending parameter. The Service is never
    # reached because FastAPI runs this before the handler body (R8.3).
    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        params: list[str] = []
        for err in exc.errors():
            # loc is like ("query", "stop_id"); take the parameter name.
            loc = err.get("loc", ())
            name = next(
                (str(part) for part in reversed(loc)
                 if part not in ("query", "path", "body", "header", "cookie")),
                None,
            )
            if name and name not in params:
                params.append(name)
        return _error_response(
            422, "validation_error",
            "one or more parameters are missing or out of range", params,
        )

    # NotFound (404): name the id. The exception message carries the id text.
    @app.exception_handler(NotFound)
    async def _on_not_found(request: Request, exc: NotFound) -> JSONResponse:
        message = str(exc) or "the requested id was not found"
        return _error_response(404, "not_found", message)

    # LiveDataUnavailable (503): generic live-unavailable text.
    @app.exception_handler(LiveDataUnavailable)
    async def _on_live_unavailable(
        request: Request, exc: LiveDataUnavailable
    ) -> JSONResponse:
        return _error_response(503, "live_unavailable", "live data is unavailable")

    # Any other exception (500): generic text only, no detail leaked (R8.6).
    @app.exception_handler(Exception)
    async def _on_internal_error(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(500, "internal_error", "an internal error occurred")

    # -- Routes -------------------------------------------------------------
    @app.get(routes["bus_trust"], response_model=BusTrustResponse)
    def bus_trust(
        stop_id: str = Query(..., min_length=1),
        mode: Mode = Query(_DEMO_DEFAULT),
        limit: int = Query(_LIMIT_DEFAULT, ge=_LIMIT_MIN, le=_LIMIT_MAX),
        at_ts: Optional[int] = Query(None, ge=0),
    ) -> BusTrustResponse:
        """Return bus-trust predictions for a stop (contract model unchanged)."""
        return service.get_bus_trust(stop_id, mode=mode, limit=limit, at_ts=at_ts)

    @app.get(routes["dock_trust"], response_model=DockTrustResponse)
    def dock_trust(
        station_id: str = Query(..., min_length=1),
        walk_min: float = Query(_WALK_DEFAULT, ge=_WALK_MIN, le=_WALK_MAX),
        mode: Mode = Query(_DEMO_DEFAULT),
        at_ts: Optional[int] = Query(None, ge=0),
    ) -> DockTrustResponse:
        """Return dock-trust for a station (contract model unchanged)."""
        return service.get_dock_trust(
            station_id, walk_min=walk_min, mode=mode, at_ts=at_ts
        )

    @app.get(routes["nearby_docks"], response_model=Envelope[list[DockResult]])
    def nearby_docks(
        lat: float = Query(..., ge=_LAT_MIN, le=_LAT_MAX),
        lon: float = Query(..., ge=_LON_MIN, le=_LON_MAX),
        walk_min: float = Query(_WALK_DEFAULT, ge=_WALK_MIN, le=_WALK_MAX),
        limit: int = Query(SETTINGS.dock_limit, ge=_LIMIT_MIN, le=_LIMIT_MAX),
        mode: Mode = Query(_DEMO_DEFAULT),
        at_ts: Optional[int] = Query(None, ge=0),
    ) -> Envelope[list[DockResult]]:
        """Return nearby docks wrapped in the legal-text envelope.

        ``at_ts`` is accepted for a uniform interface but not forwarded:
        ``get_nearby_docks`` has no ``at_ts`` parameter (documented gap R12.2),
        and the delivery layer does not work around it.
        """
        docks = service.get_nearby_docks(
            lat, lon, walk_min=walk_min, limit=limit, mode=mode
        )
        return Envelope[list[DockResult]](data=docks)

    @app.get(routes["findings"], response_model=Envelope[Findings])
    def findings() -> Envelope[Findings]:
        """Return findings wrapped in the legal-text envelope."""
        return Envelope[Findings](data=service.get_findings())

    @app.get(routes["health"], response_model=Health)
    def health() -> Health:
        """Return the health snapshot (contract model unchanged)."""
        return service.get_health()

    @app.get(routes["replay_window"], response_model=ReplayWindow)
    def replay_window() -> ReplayWindow:
        """Return the replay window (contract model unchanged)."""
        return service.get_replay_window()

    # -- CORS ---------------------------------------------------------------
    # Only add the middleware when origins are configured; never a wildcard and
    # never with credentials (R8.9). With an empty list, no CORS headers are
    # returned for any origin.
    if SETTINGS.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(SETTINGS.cors_origins),
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    return app


# Module-level app for ``uv run uvicorn api.main:app --reload``.
app = create_app()
