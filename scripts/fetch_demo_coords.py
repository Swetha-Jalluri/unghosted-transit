"""One-time script that fills the DEMO_STOP_COORDS block in app/settings.py.

Run once from the repo root::

    uv run python scripts/fetch_demo_coords.py

For each demo stop (from ``core.service.list_demo_stops()``) it calls the MBTA
V3 API ``GET {base}/stops/{stop_id}`` and reads
``data.attributes.latitude`` / ``longitude``. The base URL comes from
``SETTINGS.mbta_api_base_url``. An optional ``MBTA_API_KEY`` is read from
``.env`` and sent as the ``x-api-key`` header only when present; it is never
printed or logged.

On success it rewrites ONLY the text between the ``# BEGIN DEMO_STOP_COORDS``
and ``# END DEMO_STOP_COORDS`` markers in ``app/settings.py``; every other byte
stays unchanged. On any request failure, or any stop lacking a numeric latitude
or longitude, it exits non-zero with a clear error and writes nothing, leaving
``app/settings.py`` byte-identical.

This script is a one-time tool. No runtime code imports it, and the App, API
and MCP server never call the MBTA API (R11.9, R11.10, R11.11).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Ensure the repo root is importable when run as `python scripts/fetch_demo_coords.py`.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.settings import SETTINGS  # noqa: E402
from core.service import list_demo_stops  # noqa: E402

SETTINGS_PATH = REPO_ROOT / "app" / "settings.py"
BEGIN_MARKER = "# BEGIN DEMO_STOP_COORDS"
END_MARKER = "# END DEMO_STOP_COORDS"

# Request timeout in seconds for each MBTA stop lookup.
_REQUEST_TIMEOUT = 15.0


class FetchError(Exception):
    """Raised when a coordinate cannot be fetched; carries a user-facing message."""


def _coerce_coord(value: object) -> float:
    """Return ``value`` as a float, or raise if it is not a real number.

    Booleans are rejected (``bool`` is a subclass of ``int``) and non-finite
    values (NaN, infinity) are not accepted as coordinates.
    """
    import math

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FetchError("coordinate is not a number")
    coord = float(value)
    if not math.isfinite(coord):
        raise FetchError("coordinate is not finite")
    return coord


def fetch_coords(
    client: httpx.Client, base_url: str, stop_id: str
) -> dict[str, float]:
    """Fetch ``{"lat": ..., "lon": ...}`` for one stop, or raise ``FetchError``.

    Any transport error, non-2xx status, bad JSON, or missing/non-numeric
    coordinate is surfaced as a ``FetchError`` with a clear, key-free message.
    """
    url = f"{base_url.rstrip('/')}/stops/{stop_id}"
    try:
        response = client.get(url, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise FetchError(
            f"request for {stop_id} failed with status {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise FetchError(f"request for {stop_id} failed: {exc}") from exc
    except ValueError as exc:
        raise FetchError(f"response for {stop_id} was not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise FetchError(f"response for {stop_id} was not an object")
    attributes = payload.get("data", {})
    attributes = attributes.get("attributes", {}) if isinstance(attributes, dict) else {}
    if not isinstance(attributes, dict):
        raise FetchError(f"response for {stop_id} has no attributes")

    if "latitude" not in attributes or "longitude" not in attributes:
        raise FetchError(f"stop {stop_id} is missing latitude/longitude")
    try:
        lat = _coerce_coord(attributes["latitude"])
        lon = _coerce_coord(attributes["longitude"])
    except FetchError as exc:
        raise FetchError(f"stop {stop_id}: {exc}") from exc
    return {"lat": lat, "lon": lon}


def render_block(coords: dict[str, dict[str, float]]) -> str:
    """Render the Python literal for the coordinate block (no markers).

    The output reassigns ``_DEMO_STOP_COORDS`` to a sorted, deterministic dict.
    """
    lines = ["_DEMO_STOP_COORDS: dict[str, dict[str, float]] = {"]
    for stop_id in sorted(coords):
        entry = coords[stop_id]
        lines.append(
            f'    {stop_id!r}: {{"lat": {entry["lat"]!r}, "lon": {entry["lon"]!r}}},'
        )
    lines.append("}")
    return "\n".join(lines)


def replace_block(source: str, block_body: str) -> str:
    """Return ``source`` with the text between the markers replaced.

    Only the text between ``# BEGIN DEMO_STOP_COORDS`` and
    ``# END DEMO_STOP_COORDS`` changes; the markers and all other bytes stay
    exactly as they were. Raises ``FetchError`` if the markers are missing or
    out of order.
    """
    begin = source.find(BEGIN_MARKER)
    end = source.find(END_MARKER)
    if begin == -1 or end == -1 or end < begin:
        raise FetchError(
            "could not find the DEMO_STOP_COORDS markers in app/settings.py"
        )
    # Keep everything through the end of the BEGIN marker line, and everything
    # from the END marker onward. Replace only what is strictly between them.
    begin_line_end = source.find("\n", begin)
    if begin_line_end == -1:
        raise FetchError("malformed DEMO_STOP_COORDS begin marker")
    prefix = source[: begin_line_end + 1]
    suffix = source[end:]
    return f"{prefix}{block_body}\n{suffix}"


def main() -> int:
    """Fetch coordinates for every demo stop and rewrite the marked block.

    Returns a process exit code: 0 on success, 1 on any failure (in which case
    ``app/settings.py`` is left byte-identical).
    """
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("MBTA_API_KEY")
    headers = {"x-api-key": api_key} if api_key else {}

    base_url = SETTINGS.mbta_api_base_url
    stops = list_demo_stops()

    coords: dict[str, dict[str, float]] = {}
    try:
        with httpx.Client(headers=headers) as client:
            for stop in stops:
                entry = fetch_coords(client, base_url, stop.stop_id)
                coords[stop.stop_id] = entry
                print(f"{stop.stop_id} lat={entry['lat']} lon={entry['lon']}")
    except FetchError as exc:
        print(f"error: {exc}; app/settings.py left unchanged", file=sys.stderr)
        return 1

    try:
        original = SETTINGS_PATH.read_text(encoding="utf-8")
        updated = replace_block(original, render_block(coords))
    except (OSError, FetchError) as exc:
        print(f"error: {exc}; app/settings.py left unchanged", file=sys.stderr)
        return 1

    if updated != original:
        try:
            SETTINGS_PATH.write_text(updated, encoding="utf-8")
        except OSError as exc:
            print(f"error: could not write app/settings.py: {exc}", file=sys.stderr)
            return 1

    print(f"wrote coordinates for {len(coords)} demo stop(s) to app/settings.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
