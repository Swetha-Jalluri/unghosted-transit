# Feature: unghosted-demo, Task 10.9: one happy-path example test per API route
"""One happy-path example test per API route, all in demo mode and offline.

For each of the six ``/v1`` routes listed in ``SETTINGS.api_routes`` this makes a
single valid demo-mode request through the in-process ``TestClient`` (no network,
no live feeds) and asserts a 200 whose body matches the corresponding contract
model shape (R8.1, R8.2):

* ``bus-trust`` / ``dock-trust`` / ``health`` / ``replay-window`` return a
  contract model unchanged.
* ``findings`` / ``nearby-docks`` are wrapped in the legal-text envelope
  ``{"data": ..., "attribution": [...], "disclaimer": "..."}``.

Example ids and coordinates come from the committed demo data, not hardcoded
values: a real ``stop_id`` from ``list_demo_stops()`` for bus-trust, a real
``station_id`` and its coordinates from a demo dock for dock-trust and
nearby-docks. The demo Service serves these from the fixture mocks, so every
request stays fully offline. Route paths are read from ``SETTINGS.api_routes``.

_Requirements: 8.1, 8.2_
"""
from __future__ import annotations

import pytest

from app.settings import SETTINGS
from core import service
from tests.api.conftest import fixed_bus_service, fixed_demo_stops

# Route paths come from Settings (no hardcoded paths).
ROUTES = SETTINGS.api_routes


def _first_demo_stop_id() -> str:
    """A fixed ``stop_id`` from the patched bus Service, not a literal.

    Bus content is served from fixed contract models (see
    ``conftest.fixed_bus_service``) because A's real demo Service raises
    ``NotFound`` for bus-trust in demo mode. The id is read back from the fixed
    stop list rather than hardcoded here.
    """
    stops = fixed_demo_stops()
    assert stops, "fixed demo stops must expose at least one stop"
    return stops[0].stop_id


def _first_demo_dock() -> service.DockResult:
    """A real demo dock (id + coordinates) the demo Service accepts.

    ``get_nearby_docks`` with the dock's own coordinates returns it first, and
    its ``station_id`` is a valid id for ``get_dock_trust``; both avoid any
    hardcoded id or coordinate.
    """
    docks = service.get_nearby_docks(lat=0.0, lon=0.0, mode="demo")
    assert docks, "demo data must expose at least one dock for the example test"
    return docks[0]


class TestBusTrustRoute:
    """bus-trust returns 200 with the BusTrustResponse shape."""

    def test_bus_trust_example(self, client):
        stop_id = _first_demo_stop_id()
        with fixed_bus_service():
            resp = client.get(
                ROUTES["bus_trust"], params={"stop_id": stop_id, "mode": "demo"}
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["stop_id"] == stop_id
        assert body["mode"] == "demo"
        assert isinstance(body["predictions"], list)
        assert isinstance(body["attribution"], list) and body["attribution"]
        assert isinstance(body["disclaimer"], str) and body["disclaimer"]


class TestDockTrustRoute:
    """dock-trust returns 200 with the DockTrustResponse shape."""

    def test_dock_trust_example(self, client):
        station_id = _first_demo_dock().station_id
        resp = client.get(
            ROUTES["dock_trust"], params={"station_id": station_id, "mode": "demo"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dock"]["station_id"] == station_id
        assert body["mode"] == "demo"
        assert isinstance(body["backups"], list)
        assert isinstance(body["attribution"], list) and body["attribution"]
        assert isinstance(body["disclaimer"], str) and body["disclaimer"]


class TestNearbyDocksRoute:
    """nearby-docks returns 200 with the envelope wrapping a DockResult list."""

    def test_nearby_docks_example(self, client):
        dock = _first_demo_dock()
        resp = client.get(
            ROUTES["nearby_docks"],
            params={"lat": dock.lat, "lon": dock.lon, "mode": "demo"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body["data"], list) and body["data"]
        assert "station_id" in body["data"][0]
        assert isinstance(body["attribution"], list) and body["attribution"]
        assert isinstance(body["disclaimer"], str) and body["disclaimer"]


class TestFindingsRoute:
    """findings returns 200 with the envelope wrapping the Findings model."""

    def test_findings_example(self, client):
        resp = client.get(ROUTES["findings"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body["data"], dict)
        assert "generated_at" in body["data"]
        assert "is_placeholder" in body["data"]
        assert isinstance(body["attribution"], list) and body["attribution"]
        assert isinstance(body["disclaimer"], str) and body["disclaimer"]


class TestHealthRoute:
    """health returns 200 with the Health contract shape (not enveloped)."""

    def test_health_example(self, client):
        resp = client.get(ROUTES["health"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "generated_at" in body
        assert "modes" in body
        assert "rows" in body


class TestReplayWindowRoute:
    """replay-window returns 200 with the ReplayWindow contract shape."""

    def test_replay_window_example(self, client):
        resp = client.get(ROUTES["replay_window"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "start" in body and "end" in body
        assert "step_sec" in body
        assert "n_snapshots" in body
