"""Service layer for Unghosted contract."""
import json
import sqlite3
import time
import yaml
from datetime import datetime, timezone
from pathlib import Path

from core.bus_trust import compute_realistic_eta_range, compute_status_and_why
from core.contracts import (
    BusPrediction,
    BusTrustResponse,
    ChanceBasis,
    DemoStop,
    DockResult,
    DockTrustResponse,
    Evidence,
    Findings,
    Health,
    LiveDataUnavailable,
    NotFound,
    ReplayWindow,
)
from core.database import get_connection

# Resolve paths relative to repo root (not current working directory)
REPO_ROOT = Path(__file__).resolve().parent.parent

# Load config from repo root
with open(REPO_ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

# Attribution and disclaimer (from product.md)
ATTRIBUTION = [
    "Data: MBTA GTFS-realtime (MassDOT Developers License Agreement);",
    "Bluebikes GBFS (Bluebikes Data License Agreement).",
]
DISCLAIMER = "Unofficial. Not affiliated with or endorsed by MBTA, MassDOT or Bluebikes. For information only."

# Mock data directory (from config.yaml, resolved relative to repo root)
_mock_dir_config = CONFIG.get("mock_dir", "tests/fixtures/mock")
MOCK_DIR = REPO_ROOT / _mock_dir_config

# Database paths
RAW_DB = REPO_ROOT / "data" / "raw.db"
SAMPLE_DB = REPO_ROOT / "data" / "sample.db"


def _load_json(filename: str) -> dict:
    """Load JSON from mock fixtures."""
    path = MOCK_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Mock file not found: {filename}")
    with open(path) as f:
        return json.load(f)


def list_demo_stops() -> list[DemoStop]:
    """List available demo stops from config.yaml with real names from static_load and routes from raw.db."""
    demo_stop_ids = CONFIG.get("demo_stops", [])
    
    # Try to get stops from static_load, fall back to stop_id
    stops_dict = {}
    try:
        from core.static_load import get_stops
        stops_dict = get_stops()
    except Exception:
        pass
    
    demo_stops = []
    
    for stop_id in demo_stop_ids:
        # Get name from static_load.get_stops() (MBTA V3 API) or fall back to stop_id
        stop_name = stops_dict.get(stop_id, {}).get("name")
        if not stop_name:
            stop_name = stop_id
        
        # Get routes from raw.db pred_snap for this stop
        routes = set()
        if RAW_DB.exists():
            try:
                conn = get_connection(RAW_DB)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT DISTINCT route_id FROM pred_snap WHERE stop_id = ?",
                    (stop_id,)
                )
                routes = {row["route_id"] for row in cursor.fetchall()}
                conn.close()
            except (sqlite3.Error, Exception):
                pass
        
        # If no routes found in db, use configured routes
        if not routes:
            routes = set(CONFIG.get("routes", []))
        
        demo_stops.append(
            DemoStop(
                stop_id=stop_id,
                name=stop_name,
                routes=sorted(routes),
            )
        )
    
    return demo_stops


def get_bus_trust(
    stop_id: str, mode: str = "demo", limit: int = 5, at_ts: int | None = None
) -> BusTrustResponse:
    """Get bus trust predictions for a stop.
    
    Args:
        stop_id: Stop ID (any stop that has predictions in the latest poll).
        mode: "live" (current feeds), "demo" (sample.db or mocks), "replay" (mock timeline).
        limit: Max predictions to return.
        at_ts: Replay timestamp (POSIX seconds).
    
    Returns:
        BusTrustResponse with predictions, hidden_count, and metadata.
    
    Raises:
        NotFound: If stop_id has no predictions in latest poll.
        LiveDataUnavailable: If live mode and feeds fail.
    """
    # Demo mode: read latest snapshot from raw.db or fall back to mocks
    if mode == "demo":
        # Try to read from raw.db first
        if RAW_DB.exists():
            try:
                conn = get_connection(RAW_DB)
                cursor = conn.cursor()
                
                # Get latest poll timestamp and data ages
                cursor.execute(
                    "SELECT ts, data_age_trip_updates, data_age_vehicle_positions FROM poll_log ORDER BY ts DESC LIMIT 1"
                )
                latest_poll = cursor.fetchone()
                if latest_poll:
                    poll_ts = latest_poll["ts"]
                    data_age_sec = {}
                    if latest_poll["data_age_trip_updates"] is not None:
                        data_age_sec["trip_updates"] = latest_poll["data_age_trip_updates"]
                    if latest_poll["data_age_vehicle_positions"] is not None:
                        data_age_sec["vehicle_positions"] = latest_poll["data_age_vehicle_positions"]
                else:
                    poll_ts = None
                    data_age_sec = {}
                
                # Get stop name from static_load or use stop_id as fallback
                try:
                    from core.static_load import get_stops
                    stops_dict = get_stops()
                    stop_name = stops_dict.get(stop_id, {}).get("name")
                except Exception:
                    stops_dict = {}
                    stop_name = None
                
                if not stop_name:
                    stop_name = stop_id
                
                # Get latest predictions for this stop with all vehicle data
                # First get predictions with vehicle_id from trip updates if available
                cursor.execute("""
                    SELECT DISTINCT p.route_id, p.trip_id, p.app_eta_min, p.uncertainty, 
                                    p.schedule_relationship, p.revenue, p.headsign,
                                    v.current_status, v.vehicle_timestamp, v.vehicle_id
                    FROM pred_snap p
                    LEFT JOIN veh_snap v ON p.trip_id = v.trip_id AND v.ts = (
                        SELECT MAX(ts) FROM veh_snap WHERE trip_id = p.trip_id
                    )
                    WHERE p.stop_id = ? AND p.ts = (
                        SELECT MAX(ts) FROM pred_snap WHERE stop_id = ?
                    )
                    ORDER BY p.trip_id
                """, (stop_id, stop_id))
                
                rows = cursor.fetchall()
                conn.close()
                
                if rows:
                    # Predictions already deduplicated by query (one per trip from latest poll)
                    predictions_data = rows
                    
                    predictions = []
                    hidden_count = 0
                    
                    # Score each prediction
                    for row in predictions_data[:limit * 2]:  # Get more to filter hidden
                        route_id = row["route_id"]
                        trip_id = row["trip_id"]
                        app_eta_min = row["app_eta_min"]
                        uncertainty = row["uncertainty"]
                        schedule_relationship = row["schedule_relationship"]
                        revenue = row["revenue"]
                        headsign = row["headsign"]
                        
                        # Build evidence from vehicle data
                        vehicle_id = row["vehicle_id"]
                        current_status = row["current_status"]
                        vehicle_timestamp = row["vehicle_timestamp"]
                        
                        # Calculate location age from vehicle timestamp
                        location_age_sec = None
                        if poll_ts and vehicle_timestamp:
                            location_age_sec = poll_ts - vehicle_timestamp
                        
                        evidence = Evidence(
                            uncertainty=uncertainty,
                            vehicle_id=vehicle_id,
                            location_age_sec=location_age_sec,
                        )
                        
                        # Build prediction dict for scoring
                        pred_dict = {
                            "route_id": route_id,
                            "trip_id": trip_id,
                            "app_eta_min": app_eta_min,
                            "revenue": revenue,
                            "schedule_relationship": schedule_relationship,
                            "current_status": current_status,
                            "headsign": headsign,
                        }
                        
                        # Compute status and why using bus_trust engine
                        status, why, reason_codes, chance_it_arrives = compute_status_and_why(
                            pred_dict,
                            {
                                "uncertainty": uncertainty,
                                "vehicle_id": vehicle_id,
                                "location_age_sec": location_age_sec,
                            },
                        )
                        
                        # Check if hidden (chance_it_arrives is None)
                        if chance_it_arrives is None:
                            hidden_count += 1
                            continue
                        
                        # Compute realistic ETA range
                        realistic_eta_min = compute_realistic_eta_range(
                            app_eta_min, status, evidence, uncertainty
                        )
                        
                        # Create prediction with computed status
                        pred = BusPrediction(
                            route_id=route_id,
                            trip_id=trip_id,
                            headsign=headsign,
                            app_eta_min=app_eta_min,
                            status=status,
                            why=why,
                            reason_codes=reason_codes,
                            chance_it_arrives=chance_it_arrives,
                            chance_basis=ChanceBasis(method="placeholder", n=0),
                            realistic_eta_min=realistic_eta_min,
                            evidence=evidence,
                        )
                        predictions.append(pred)
                    
                    # Trim to limit
                    predictions = predictions[:limit]
                    
                    if predictions:
                        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                        response = BusTrustResponse(
                            stop_id=stop_id,
                            stop_name=stop_name,
                            generated_at=generated_at,
                            mode=mode,
                            data_age_sec=data_age_sec,
                            predictions=predictions,
                            hidden_count=hidden_count,
                            attribution=ATTRIBUTION,
                            disclaimer=DISCLAIMER,
                        )
                        return response
                    else:
                        # No predictions found for this stop
                        raise NotFound(f"No predictions for stop {stop_id}")
            
            except (sqlite3.Error, Exception):
                # Fall through to mocks if db read fails
                pass
        
        # Fall back to mock data
        try:
            data = _load_json(f"bus_trust_{stop_id}.json")
            data["mode"] = mode
            data["attribution"] = ATTRIBUTION
            data["disclaimer"] = DISCLAIMER
            data["predictions"] = data["predictions"][:limit]
            response = BusTrustResponse(**data)
            return response
        except FileNotFoundError:
            raise NotFound(f"No bus trust data for stop {stop_id}")
    
    # Live mode: fetch from feeds and compute trust scores (not yet implemented)
    elif mode == "live":
        raise LiveDataUnavailable("Live mode not yet implemented")
    
    # Replay mode: use mock timeline
    elif mode == "replay":
        try:
            timeline = _load_json("replay_timeline.json")
            for snapshot in timeline:
                if snapshot.get("ts") == at_ts and snapshot.get("stop_id") == stop_id:
                    predictions = [BusPrediction(**p) for p in snapshot.get("predictions", [])]
                    generated_at = datetime.fromtimestamp(at_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
                    # Get stop name for replay
                    try:
                        from core.static_load import get_stops
                        stops_dict = get_stops()
                        stop_name = stops_dict.get(stop_id, {}).get("name")
                    except Exception:
                        stop_name = None
                    if not stop_name:
                        stop_name = stop_id
                    response = BusTrustResponse(
                        stop_id=stop_id,
                        stop_name=stop_name,
                        generated_at=generated_at,
                        mode=mode,
                        data_age_sec={},
                        predictions=predictions[:limit],
                        hidden_count=snapshot.get("hidden_count", 0),
                        attribution=ATTRIBUTION,
                        disclaimer=DISCLAIMER,
                    )
                    return response
            raise NotFound(f"No replay data for stop {stop_id} at {at_ts}")
        except FileNotFoundError:
            raise NotFound("Replay timeline not found")
    
    else:
        raise NotFound(f"Unknown mode: {mode}")


def get_dock_trust(
    station_id: str, walk_min: float = 5, mode: str = "demo", at_ts: int | None = None
) -> DockTrustResponse:
    """Get dock trust for a specific station."""
    # For demo mode, use mock docks data
    try:
        docks = _load_json("docks.json")
    except FileNotFoundError:
        raise NotFound("Dock data not found")
    
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
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
    """Get findings and model calibration.
    
    When raw.db exists: generates findings from real logged data (is_placeholder=false).
    When raw.db missing: uses mock findings (is_placeholder=true).
    
    Never returns cached artifacts/findings.json when raw.db exists.
    Always writes real findings to artifacts/findings.json when raw.db exists.
    """
    from core.findings import generate_findings, save_findings
    
    # If raw.db exists, always compute and return real findings
    if RAW_DB.exists():
        findings = generate_findings(is_placeholder=False)
        save_findings(findings)
        return findings
    
    # raw.db missing: fall back to mock (is_placeholder=true)
    try:
        data = _load_json("findings.json")
        findings = Findings(**data)
        return findings
    except FileNotFoundError:
        # If no mock either, generate empty findings as placeholder
        findings = generate_findings(is_placeholder=True)
        return findings


def get_health() -> Health:
    """Get system health snapshot from poll_log (read-only).
    
    Returns health status including:
    - Last poll timestamp
    - Polls in last hour
    - Success rate
    - Row counts per table
    - Data age per feed
    - Available modes
    - Model method
    
    Computes only from data/raw.db poll_log and row counts (read-only).
    Falls back to mock health.json only if raw.db does not exist.
    """
    health_data = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "last_poll_ts": None,
        "polls_last_hour": 0,
        "poll_success_rate": None,
        "rows": {"pred": 0, "veh": 0, "dock": 0},
        "data_age_sec": {},
        "modes": {"demo": True, "live": False, "replay": True},
        "model_method": "placeholder",  # Until model training exists
    }
    
    # Try to read from raw.db (read-only)
    if RAW_DB.exists():
        try:
            conn = get_connection(RAW_DB)
            cursor = conn.cursor()
            
            # Get last poll timestamp and recent poll count
            cursor.execute("SELECT COUNT(*) as count FROM poll_log WHERE success = 1")
            success_count = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM poll_log")
            total_count = cursor.fetchone()["count"]
            
            # Get polls in last hour
            now_ts = int(time.time())
            hour_ago_ts = now_ts - 3600
            cursor.execute(
                "SELECT COUNT(*) as count FROM poll_log WHERE ts > ?",
                (hour_ago_ts,)
            )
            polls_last_hour = cursor.fetchone()["count"]
            
            # Get last poll timestamp and data ages
            cursor.execute("SELECT ts, data_age_trip_updates, data_age_vehicle_positions, data_age_docks FROM poll_log ORDER BY ts DESC LIMIT 1")
            last_poll = cursor.fetchone()
            
            if last_poll:
                health_data["last_poll_ts"] = last_poll["ts"]
                if last_poll["data_age_trip_updates"] is not None:
                    health_data["data_age_sec"]["trip_updates"] = last_poll["data_age_trip_updates"]
                if last_poll["data_age_vehicle_positions"] is not None:
                    health_data["data_age_sec"]["vehicle_positions"] = last_poll["data_age_vehicle_positions"]
                if last_poll["data_age_docks"] is not None:
                    health_data["data_age_sec"]["docks"] = last_poll["data_age_docks"]
            
            # Calculate success rate
            if total_count > 0:
                health_data["poll_success_rate"] = success_count / total_count
            
            health_data["polls_last_hour"] = polls_last_hour
            
            # Get row counts
            cursor.execute("SELECT COUNT(*) as count FROM pred_snap")
            health_data["rows"]["pred"] = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM veh_snap")
            health_data["rows"]["veh"] = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM dock_snap")
            health_data["rows"]["dock"] = cursor.fetchone()["count"]
            
            conn.close()
            return Health(**health_data)
        
        except (sqlite3.Error, Exception):
            # If database access fails, fall through to mock
            pass
    
    # Fall back to mock data only if raw.db does not exist or is inaccessible
    try:
        data = _load_json("health.json")
        health_data.update(data)
    except FileNotFoundError:
        pass
    
    return Health(**health_data)


def get_replay_window() -> ReplayWindow:
    """Get replay timeline window."""
    timeline = _load_json("replay_timeline.json")
    start_ts = timeline[0]["ts"]
    end_ts = timeline[-1]["ts"]
    step_sec = CONFIG.get("replay", {}).get("step_sec", 60)
    n_snapshots = len(timeline)

    replay_window = ReplayWindow(
        start=start_ts,
        end=end_ts,
        step_sec=step_sec,
        n_snapshots=n_snapshots,
    )
    return replay_window
