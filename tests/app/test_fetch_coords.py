"""Stub-HTTP tests for scripts/fetch_demo_coords.py.

These tests run fully offline: every HTTP call is served by a fake httpx
response, so no real network request is ever made. They guard the no-write-on-
failure rule for the one-time coordinate script (R11.9, R11.10):

1. On success only the text between the DEMO_STOP_COORDS markers is rewritten;
   the markers and every other byte of the settings file are preserved.
2. A failed request or a missing / non-numeric coordinate leaves the settings
   file byte-identical (nothing is written).
3. The MBTA_API_KEY never appears in anything the script prints.
"""
from __future__ import annotations

import json

import httpx
import pytest

from scripts import fetch_demo_coords
from scripts.fetch_demo_coords import (
    FetchError,
    fetch_coords,
    render_block,
    replace_block,
)


# ---------------------------------------------------------------------------
# A settings-like file with the real markers around an empty coordinate block.
# ---------------------------------------------------------------------------
SETTINGS_TEMPLATE = (
    '"""module docstring stays untouched."""\n'
    "LEADING = 1  # a byte before the block\n"
    "# BEGIN DEMO_STOP_COORDS\n"
    "_DEMO_STOP_COORDS: dict[str, dict[str, float]] = {}\n"
    "# END DEMO_STOP_COORDS\n"
    "TRAILING = 2  # a byte after the block\n"
)


class _FakeResponse:
    """Minimal stand-in for httpx.Response used by fetch_coords."""

    def __init__(self, *, status_code: int = 200, payload=None, transport_error=False):
        self.status_code = status_code
        self._payload = payload
        self._transport_error = transport_error
        # fetch_coords reads exc.response.status_code on an HTTPStatusError.
        self.request = httpx.Request("GET", "https://example.test/stops/x")

    def raise_for_status(self):
        if self._transport_error:
            raise httpx.ConnectError("stubbed connection failure")
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "stubbed status error", request=self.request, response=self
            )

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeClient:
    """Stub httpx.Client that returns canned responses keyed by stop id.

    Records the headers it was created with so a test can assert that the API
    key is carried but never surfaced in output.
    """

    def __init__(self, responses: dict[str, _FakeResponse], headers=None):
        self._responses = responses
        self.headers = dict(headers or {})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, timeout=None):
        stop_id = url.rstrip("/").rsplit("/", 1)[-1]
        if stop_id not in self._responses:
            raise AssertionError(f"unexpected request for {stop_id!r}")
        resp = self._responses[stop_id]
        if resp._transport_error:
            raise httpx.ConnectError("stubbed connection failure")
        return resp


def _ok_payload(lat: float, lon: float) -> dict:
    return {"data": {"attributes": {"latitude": lat, "longitude": lon}}}


def _install_fake_client(monkeypatch, responses):
    """Make httpx.Client(headers=...) return a _FakeClient with those responses."""
    captured = {}

    def _factory(*args, **kwargs):
        client = _FakeClient(responses, headers=kwargs.get("headers"))
        captured["client"] = client
        return client

    monkeypatch.setattr(fetch_demo_coords.httpx, "Client", _factory)
    return captured


# ---------------------------------------------------------------------------
# fetch_coords: the stubbed HTTP boundary.
# ---------------------------------------------------------------------------
class TestFetchCoords:
    def test_success_returns_lat_lon(self):
        client = _FakeClient({"s1": _FakeResponse(payload=_ok_payload(42.3, -71.1))})
        with client as c:
            result = fetch_coords(c, "https://api-v3.mbta.com", "s1")
        assert result == {"lat": 42.3, "lon": -71.1}

    def test_non_2xx_status_raises_fetch_error(self):
        client = _FakeClient({"s1": _FakeResponse(status_code=404)})
        with pytest.raises(FetchError):
            with client as c:
                fetch_coords(c, "https://api-v3.mbta.com", "s1")

    def test_transport_error_raises_fetch_error(self):
        client = _FakeClient({"s1": _FakeResponse(transport_error=True)})
        with pytest.raises(FetchError):
            with client as c:
                fetch_coords(c, "https://api-v3.mbta.com", "s1")

    def test_bad_json_raises_fetch_error(self):
        resp = _FakeResponse(payload=ValueError("not json"))
        client = _FakeClient({"s1": resp})
        with pytest.raises(FetchError):
            with client as c:
                fetch_coords(c, "https://api-v3.mbta.com", "s1")

    def test_missing_coordinate_raises_fetch_error(self):
        resp = _FakeResponse(payload={"data": {"attributes": {"latitude": 42.3}}})
        client = _FakeClient({"s1": resp})
        with pytest.raises(FetchError):
            with client as c:
                fetch_coords(c, "https://api-v3.mbta.com", "s1")

    def test_non_numeric_coordinate_raises_fetch_error(self):
        resp = _FakeResponse(payload=_ok_payload("not-a-number", -71.1))
        client = _FakeClient({"s1": resp})
        with pytest.raises(FetchError):
            with client as c:
                fetch_coords(c, "https://api-v3.mbta.com", "s1")

    def test_boolean_coordinate_rejected(self):
        resp = _FakeResponse(payload=_ok_payload(True, -71.1))
        client = _FakeClient({"s1": resp})
        with pytest.raises(FetchError):
            with client as c:
                fetch_coords(c, "https://api-v3.mbta.com", "s1")


# ---------------------------------------------------------------------------
# replace_block: only the marked block changes; all other bytes preserved.
# ---------------------------------------------------------------------------
class TestReplaceBlock:
    def test_only_marked_block_changes(self):
        body = render_block({"s1": {"lat": 42.3, "lon": -71.1}})
        updated = replace_block(SETTINGS_TEMPLATE, body)

        # Markers survive verbatim.
        assert "# BEGIN DEMO_STOP_COORDS\n" in updated
        assert "# END DEMO_STOP_COORDS\n" in updated

        # Everything before the BEGIN marker line is byte-identical.
        begin = SETTINGS_TEMPLATE.index("# BEGIN DEMO_STOP_COORDS")
        begin_line_end = SETTINGS_TEMPLATE.index("\n", begin) + 1
        assert updated[:begin_line_end] == SETTINGS_TEMPLATE[:begin_line_end]

        # Everything from the END marker onward is byte-identical.
        end = SETTINGS_TEMPLATE.index("# END DEMO_STOP_COORDS")
        assert updated[updated.index("# END DEMO_STOP_COORDS"):] == SETTINGS_TEMPLATE[end:]

        # The new coordinate shows up strictly inside the block.
        assert "'s1': {\"lat\": 42.3, \"lon\": -71.1}" in updated

    def test_missing_markers_raise(self):
        with pytest.raises(FetchError):
            replace_block("no markers here\n", "body")

    def test_out_of_order_markers_raise(self):
        swapped = "# END DEMO_STOP_COORDS\n# BEGIN DEMO_STOP_COORDS\n"
        with pytest.raises(FetchError):
            replace_block(swapped, "body")

    def test_idempotent_render_roundtrip(self):
        coords = {"s2": {"lat": 1.0, "lon": 2.0}, "s1": {"lat": 3.0, "lon": 4.0}}
        once = replace_block(SETTINGS_TEMPLATE, render_block(coords))
        twice = replace_block(once, render_block(coords))
        assert once == twice


# ---------------------------------------------------------------------------
# main(): the write path against a temp copy of the settings file.
# ---------------------------------------------------------------------------
class TestMain:
    @pytest.fixture
    def settings_file(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.py"
        path.write_text(SETTINGS_TEMPLATE, encoding="utf-8")
        monkeypatch.setattr(fetch_demo_coords, "SETTINGS_PATH", path)
        return path

    @pytest.fixture
    def two_stops(self, monkeypatch):
        class _Stop:
            def __init__(self, stop_id):
                self.stop_id = stop_id

        stops = [_Stop("s1"), _Stop("s2")]
        monkeypatch.setattr(fetch_demo_coords, "list_demo_stops", lambda: stops)
        return stops

    def test_success_writes_only_the_block(self, settings_file, two_stops, monkeypatch):
        responses = {
            "s1": _FakeResponse(payload=_ok_payload(42.1, -71.1)),
            "s2": _FakeResponse(payload=_ok_payload(42.2, -71.2)),
        }
        _install_fake_client(monkeypatch, responses)

        before = settings_file.read_text(encoding="utf-8")
        rc = fetch_demo_coords.main()
        after = settings_file.read_text(encoding="utf-8")

        assert rc == 0
        assert after != before
        # Bytes outside the block are preserved.
        assert after.startswith('"""module docstring stays untouched."""\n')
        assert "LEADING = 1  # a byte before the block\n" in after
        assert "TRAILING = 2  # a byte after the block\n" in after
        assert "# BEGIN DEMO_STOP_COORDS\n" in after
        assert "# END DEMO_STOP_COORDS\n" in after
        # The fetched coordinates are inside the block.
        assert "'s1': {\"lat\": 42.1, \"lon\": -71.1}" in after
        assert "'s2': {\"lat\": 42.2, \"lon\": -71.2}" in after

    def test_failed_request_leaves_file_byte_identical(
        self, settings_file, two_stops, monkeypatch
    ):
        responses = {
            "s1": _FakeResponse(payload=_ok_payload(42.1, -71.1)),
            "s2": _FakeResponse(status_code=500),
        }
        _install_fake_client(monkeypatch, responses)

        before = settings_file.read_bytes()
        rc = fetch_demo_coords.main()
        after = settings_file.read_bytes()

        assert rc == 1
        assert after == before

    def test_missing_coordinate_leaves_file_byte_identical(
        self, settings_file, two_stops, monkeypatch
    ):
        responses = {
            "s1": _FakeResponse(payload=_ok_payload(42.1, -71.1)),
            "s2": _FakeResponse(payload={"data": {"attributes": {"latitude": 42.2}}}),
        }
        _install_fake_client(monkeypatch, responses)

        before = settings_file.read_bytes()
        rc = fetch_demo_coords.main()
        after = settings_file.read_bytes()

        assert rc == 1
        assert after == before

    def test_non_numeric_coordinate_leaves_file_byte_identical(
        self, settings_file, two_stops, monkeypatch
    ):
        responses = {
            "s1": _FakeResponse(payload=_ok_payload(42.1, -71.1)),
            "s2": _FakeResponse(payload=_ok_payload("nope", -71.2)),
        }
        _install_fake_client(monkeypatch, responses)

        before = settings_file.read_bytes()
        rc = fetch_demo_coords.main()
        after = settings_file.read_bytes()

        assert rc == 1
        assert after == before


# ---------------------------------------------------------------------------
# The API key is carried to httpx but never printed.
# ---------------------------------------------------------------------------
class TestApiKeyNeverLeaks:
    @pytest.fixture
    def settings_file(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.py"
        path.write_text(SETTINGS_TEMPLATE, encoding="utf-8")
        monkeypatch.setattr(fetch_demo_coords, "SETTINGS_PATH", path)
        return path

    @pytest.fixture
    def one_stop(self, monkeypatch):
        class _Stop:
            stop_id = "s1"

        monkeypatch.setattr(fetch_demo_coords, "list_demo_stops", lambda: [_Stop()])

    def test_key_sent_as_header_but_absent_from_output(
        self, settings_file, one_stop, monkeypatch, capsys
    ):
        secret = "SUPER-SECRET-KEY-1234567890"
        monkeypatch.setenv("MBTA_API_KEY", secret)
        # Avoid reading any real .env over the environment variable.
        monkeypatch.setattr(fetch_demo_coords, "load_dotenv", lambda *a, **k: None)

        responses = {"s1": _FakeResponse(payload=_ok_payload(42.1, -71.1))}
        captured = _install_fake_client(monkeypatch, responses)

        rc = fetch_demo_coords.main()
        out = capsys.readouterr()

        assert rc == 0
        # The key is carried on the client header...
        assert captured["client"].headers.get("x-api-key") == secret
        # ...but never printed to stdout or stderr.
        assert secret not in out.out
        assert secret not in out.err

    def test_key_absent_from_output_on_failure(
        self, settings_file, one_stop, monkeypatch, capsys
    ):
        secret = "SUPER-SECRET-KEY-1234567890"
        monkeypatch.setenv("MBTA_API_KEY", secret)
        monkeypatch.setattr(fetch_demo_coords, "load_dotenv", lambda *a, **k: None)

        responses = {"s1": _FakeResponse(status_code=403)}
        _install_fake_client(monkeypatch, responses)

        rc = fetch_demo_coords.main()
        out = capsys.readouterr()

        assert rc == 1
        assert secret not in out.out
        assert secret not in out.err
