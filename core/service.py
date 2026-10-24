"""Service layer for Unghosted contract."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.contracts import (
    BusTrustResponse,
    ChanceBasis,
    DemoStop,
    DockResult,
    DockTrustResponse,
    Findings,
    Health,
    NotFound,
    ReplayWindow,
    BusPrediction,
    Evidence,
)

# Attribution and disclaimer (from product.md)
ATTRIBUTION = [
    "Data: MBTA GTFS-realtime (MassDOT Developers License Agreement);",
    "Bluebikes GBFS (Bluebikes Data License Agreement).",
]
DISCLAIMER = "Unofficial. Not affiliated with or endorsed by MBTA, MassDOT or Bluebikes. For information only."

# Mock data directory
MOCK_DIR = Path("tests/fixtures/mock")


def _load_json(filename: str) -> dict:
    """Load JSON from mock fixtures."""
    path = MOCK_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Mock file not found: {filename}")
    with open(path) as f:
        return json.load(f)


def list_demo_stops() -> list[DemoStop]:
    """List available demo stops."""
    data = _load_json("demo_stops.json")
    return [DemoStop(**stop) for stop in data]


def get_bus_trust(
    stop_id: str, mode: str = "demo", limit: int = 5, at_ts: int | None = None
) -> BusTrustResponse:
    """Get bus trust predictions for a stop."""
    # Validate stop exists
    stops = list_demo_stops()
    stop_names = {s.stop_id: s.name for s in stops}
    if stop_id not in stop_names:
        raise NotFound(f"Stop {stop_id} not found")

    # Load bus trust data
    filename = f"bus_trust_{stop_id}.json"
    try:
        data = _load_json(filename)
    except FileNotFoundError:
        raise NotFound(f"Bus trust data for stop {stop_id} not found")

    # Handle replay mode with outcome
    if mode == "replay" and at_ts:
        timeline = _load_json("replay_timeline.json")
        for snapshot in timeline:
            if snapshot["ts"] == at_ts and snapshot["stop_id"] == stop_id:
                # Use replay predictions with outcome
                predictions = [BusPrediction(**p) for p in snapshot["predictions"]]
                data["predictions"] = [p.model_dump() for p in predictions]
                data["generated_at"] = datetime.fromtimestamp(at_ts).isoformat() + "Z"
                break

    # Limit predictions
    data["predictions"] = data["predictions"][:limit]

    # Ensure required fields
    data["mode"] = mode
    data["attribution"] = ATTRIBUTION
    data["disclaimer"] = DISCLAIMER

    response = BusTrustResponse(**data)
    return response


def get_dock_trust(
    station_id: str, walk_min: float = 5, mode: str = "demo", at_ts: int | None = None
) -> DockTrustResponse:
    """Get dock trust for a specific station."""
    docks = _load_json("docks.json")
    dock_dict = {d["station_id"]: d for d in docks}

    if station_id not in dock_dict:
        raise NotFound(f"Station {station_id} not found")

    dock_data = dock_dict[station_id]
    dock = DockResult(**dock_data)

    # Get backups (other docks)
    backups = [
        DockResult(**d)
        for d in docks
        if d["station_id"] != station_id
    ]

    response = DockTrustResponse(
        generated_at=datetime.now().isoformat() + "Z",
        mode=mode,
        walk_min=walk_min,
        dock=dock,
        backups=backups,
        attribution=ATTRIBUTION,
        disclaimer=DISCLAIMER,
    )
    return response


def get_nearby_docks(
    lat: float,
    lon: float,
    walk_min: float = 5,
    limit: int = 3,
    mode: str = "demo",
) -> list[DockResult]:
    """Get nearby docks sorted by distance."""
    docks = _load_json("docks.json")
    dock_results = [DockResult(**d) for d in docks]

    # Simple distance calculation (Haversine approximation)
    def distance_km(lat1, lon1, lat2, lon2):
        import math
        dlat = (lat2 - lat1) * 111
        dlon = (lon2 - lon1) * 111 * math.cos(math.radians(lat1))
        return math.sqrt(dlat**2 + dlon**2)

    # Sort by distance and limit
    sorted_docks = sorted(
        dock_results,
        key=lambda d: distance_km(lat, lon, d.lat, d.lon),
    )
    return sorted_docks[:limit]


def get_findings() -> Findings:
    """Get findings and model calibration."""
    data = _load_json("findings.json")
    findings = Findings(**data)
    return findings


def get_health() -> Health:
    """Get system health snapshot."""
    data = _load_json("health.json")
    health = Health(**data)
    return health


def get_replay_window() -> ReplayWindow:
    """Get replay timeline window."""
    timeline = _load_json("replay_timeline.json")
    start_ts = timeline[0]["ts"]
    end_ts = timeline[-1]["ts"]
    step_sec = 60  # from config.yaml
    n_snapshots = len(timeline)

    replay_window = ReplayWindow(
        start=start_ts,
        end=end_ts,
        step_sec=step_sec,
        n_snapshots=n_snapshots,
    )
    return replay_window
