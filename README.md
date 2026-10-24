# Unghosted
Unghosted: a trust layer for transit apps

## Usage

Everything runs through `uv`; dependencies live in `pyproject.toml` and `uv.lock`. From the repo root:

```bash
uv sync
uv run streamlit run streamlit_app.py
uv run uvicorn api.main:app --reload
uv run python -m mcp_server.server
uv run pytest -q
```

The demo stop coordinates are fetched once with `uv run python scripts/fetch_demo_coords.py`.

## API

FastAPI service under the `/v1` prefix. Unauthenticated and read-only.

- `GET /v1/bus-trust` — bus-trust predictions for a stop (`stop_id` required; optional `mode`, `limit`, `at_ts`). Returns a `BusTrustResponse`.
- `GET /v1/dock-trust` — dock-trust for a station (`station_id` required; optional `walk_min`, `mode`, `at_ts`). Returns a `DockTrustResponse`.
- `GET /v1/nearby-docks` — nearby docks for a point (`lat`, `lon` required; optional `walk_min`, `limit`, `mode`, `at_ts`). Returns an envelope wrapping a list of `DockResult`.
- `GET /v1/findings` — measured vanish rates and model quality. Returns an envelope wrapping `Findings`.
- `GET /v1/health` — data-collection health snapshot. Returns a `Health`.
- `GET /v1/replay-window` — the logged time window for replay mode. Returns a `ReplayWindow`.

Errors use one JSON shape `{"error", "message", "params"}`: 422 `validation_error` (names each offending parameter), 404 `not_found`, 503 `live_unavailable`, 500 `internal_error`.

Example response for `GET /v1/health`:

```json
{
  "generated_at": "2025-01-15T14:30:00Z",
  "last_poll_ts": 1737018600,
  "polls_last_hour": 82,
  "poll_success_rate": 0.976,
  "rows": { "pred": 3247, "veh": 1842, "dock": 512 },
  "data_age_sec": { "trip_updates": 12, "vehicle_positions": 8, "docks": 45 },
  "modes": { "demo": true, "live": false, "replay": true },
  "model_method": "logistic_regression"
}
```

## MCP tools

Read-only tools over `core.service`. Each validates its inputs first and
returns `{ok, data, data_age_sec, attribution, disclaimer}` on success or
`{ok: False, error: {code, field?, message}}` on failure; none ever raises.

- `list_demo_stops()` — list the demo stops (`stop_id`, `name`, `routes`).
- `check_bus_trust(stop_id, mode="demo", limit=5, at_ts=None)` — bus trust predictions for a stop.
- `check_dock_trust(station_id, walk_min=5, mode="demo", at_ts=None)` — dock trust for one station plus backups.
- `nearby_docks(lat, lon, walk_min=5, limit=3, mode="demo", at_ts=None)` — nearby docks for a coordinate.
- `todays_findings()` — current findings and model calibration.
