# Feature: unghosted-demo, Property 15: CORS only for listed origins
"""Property 15: CORS only for listed origins.

For any ``Origin`` header and any configured origin list, the API returns CORS
allow headers if and only if the origin is in the list; with an empty list it
returns none.

``api.main.create_app`` reads ``SETTINGS.cors_origins`` at app-build time and
adds ``CORSMiddleware`` only when that list is non-empty (no wildcard origin,
no credentials). The middleware is wired when the app is built, so a test must
set the configured origins *before* calling ``create_app()``. ``Settings`` is a
frozen dataclass, so we build a variant with ``dataclasses.replace`` and patch
the module-level ``SETTINGS`` reference that ``api.main`` reads
(``api.main.SETTINGS``), then build a fresh app and ``TestClient`` per scenario.

Route targets come from ``SETTINGS.api_routes`` (no hardcoded paths). Starlette's
``CORSMiddleware`` echoes the request ``Origin`` back in
``access-control-allow-origin`` for an allowed origin (both on a simple GET that
carries an ``Origin`` header and on an ``OPTIONS`` preflight); for a disallowed
origin, or when no middleware is installed, that header is absent.

**Validates: Requirements 8.9**
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace

from fastapi.testclient import TestClient
from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

import api.main as api_main
from app.settings import SETTINGS

# A real route path to aim requests at, read from Settings (no hardcoded path).
_HEALTH_ROUTE = SETTINGS.api_routes["health"]

# The header Starlette's CORSMiddleware sets to echo an allowed origin.
_ALLOW_ORIGIN = "access-control-allow-origin"

# A small pool of plausible origins used to build configured lists and to probe
# with. Keeping them distinct lets "in the list" and "not in the list" be
# decided by simple membership.
_ORIGIN_POOL = [
    "https://app.example.com",
    "https://trusted.example.org",
    "http://localhost:3000",
    "https://partner.transit.app",
    "https://rider.example.net",
    "https://ops.example.io",
]

_origins = st.sampled_from(_ORIGIN_POOL)
_origin_lists = st.lists(_origins, min_size=1, max_size=4, unique=True)


@contextmanager
def cors_client(origins):
    """Yield a fresh ``TestClient`` whose configured CORS origins are ``origins``.

    ``Settings`` is frozen, so a variant is built with ``dataclasses.replace``.
    ``api.main.create_app`` reads the module-level ``SETTINGS`` at build time, so
    the variant must replace ``api.main.SETTINGS`` *before* ``create_app()``;
    this context manager restores the original on exit. It is a standalone
    context manager (not a pytest fixture) so it can be used inside the body of a
    ``@given`` property test, where function-scoped fixtures are not reset
    between generated examples.
    """
    patched = replace(SETTINGS, cors_origins=list(origins))
    original = api_main.SETTINGS
    api_main.SETTINGS = patched
    try:
        app = api_main.create_app()
        with TestClient(app) as test_client:
            yield test_client
    finally:
        api_main.SETTINGS = original


def _get_with_origin(client: TestClient, origin: str):
    """Issue a simple GET carrying an ``Origin`` header."""
    return client.get(_HEALTH_ROUTE, headers={"Origin": origin})


def _preflight(client: TestClient, origin: str):
    """Issue a CORS preflight ``OPTIONS`` for a GET from ``origin``."""
    return client.options(
        _HEALTH_ROUTE,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )


class TestCorsWithConfiguredList:
    """A non-empty configured list: allow headers iff the Origin is listed."""

    @hyp_settings(max_examples=100)
    @given(data=st.data())
    def test_allow_header_iff_origin_listed(self, data):
        """Allow-origin header appears exactly when the probed Origin is listed."""
        origins = data.draw(_origin_lists)
        probe = data.draw(_origins)

        with cors_client(origins) as client:
            resp = _get_with_origin(client, probe)
            header = resp.headers.get(_ALLOW_ORIGIN)
            if probe in origins:
                # Allowed: the origin is echoed back verbatim (no wildcard).
                assert header == probe, (
                    f"listed origin {probe!r} should be echoed, got {header!r}"
                )
                assert header != "*", "wildcard origin must never be used"
            else:
                # Not listed: no allow-origin header at all.
                assert header is None, (
                    f"unlisted origin {probe!r} must get no allow-origin, "
                    f"got {header!r}"
                )

    @hyp_settings(max_examples=100)
    @given(data=st.data())
    def test_preflight_allow_header_iff_origin_listed(self, data):
        """Preflight OPTIONS echoes a listed origin and withholds an unlisted one."""
        origins = data.draw(_origin_lists)
        probe = data.draw(_origins)

        with cors_client(origins) as client:
            resp = _preflight(client, probe)
            header = resp.headers.get(_ALLOW_ORIGIN)
            if probe in origins:
                assert header == probe, (
                    f"listed origin {probe!r} should be echoed on preflight, "
                    f"got {header!r}"
                )
                assert header != "*", "wildcard origin must never be used"
            else:
                assert header is None, (
                    f"unlisted origin {probe!r} must get no allow-origin on "
                    f"preflight, got {header!r}"
                )

    def test_no_credentials_header_for_allowed_origin(self):
        """An allowed origin never receives allow-credentials (credentials off)."""
        origins = ["https://app.example.com"]
        with cors_client(origins) as client:
            resp = _get_with_origin(client, origins[0])
            assert resp.headers.get(_ALLOW_ORIGIN) == origins[0]
            assert "access-control-allow-credentials" not in resp.headers


class TestCorsWithEmptyList:
    """An empty configured list: no CORS allow headers for any origin."""

    @hyp_settings(max_examples=100)
    @given(origin=_origins)
    def test_get_never_gets_allow_header(self, origin):
        """With no configured origins, a GET with any Origin gets no allow header."""
        with cors_client([]) as client:
            resp = _get_with_origin(client, origin)
            assert resp.headers.get(_ALLOW_ORIGIN) is None, (
                f"empty list must yield no allow-origin, got "
                f"{resp.headers.get(_ALLOW_ORIGIN)!r} for {origin!r}"
            )

    @hyp_settings(max_examples=100)
    @given(origin=_origins)
    def test_preflight_never_gets_allow_header(self, origin):
        """With no configured origins, a preflight gets no allow-origin header."""
        with cors_client([]) as client:
            resp = _preflight(client, origin)
            assert resp.headers.get(_ALLOW_ORIGIN) is None, (
                f"empty list must yield no allow-origin on preflight, got "
                f"{resp.headers.get(_ALLOW_ORIGIN)!r} for {origin!r}"
            )
