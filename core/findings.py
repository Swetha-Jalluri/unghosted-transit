"""Compute findings from labels and poll log."""
import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from core.contracts import Findings, ModelInfo, EvalInfo, RateRow

logger = logging.getLogger(__name__)

# Resolve paths relative to repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DB = REPO_ROOT / "data" / "raw.db"
RAW_SNAPSHOT_DB = REPO_ROOT / "data" / "raw_snapshot.db"
LABELS_DB = REPO_ROOT / "data" / "labels.db"


def load_config() -> dict:
    """Load config.yaml."""
    config_path = REPO_ROOT / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def _create_snapshot(timeout_sec: int = 30) -> None:
    """Create a read-only snapshot of raw.db using SQLite backup API.
    
    This avoids database locks by copying raw.db to raw_snapshot.db
    while the collector may be writing. Uses sqlite3's backup API with timeout.
    
    Args:
        timeout_sec: Timeout for establishing backup connection (default 30s).
    """
    if not RAW_DB.exists():
        return
    
    try:
        # Set timeout on source connection to avoid hangs
        src = sqlite3.connect(str(RAW_DB), timeout=timeout_sec)
        dst = sqlite3.connect(str(RAW_SNAPSHOT_DB), timeout=timeout_sec)
        
        try:
            # Perform backup
            with dst:
                src.backup(dst)
            logger.info(f"Created snapshot at {RAW_SNAPSHOT_DB}")
        finally:
            src.close()
            dst.close()
    except sqlite3.OperationalError as e:
        logger.error(f"Failed to create snapshot: {e}")
        raise


def _get_connection(db_path: Path) -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _initialize_labels_db() -> None:
    """Initialize labels.db with enriched labels table (idempotent)."""
    db_path = LABELS_DB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = _get_connection(db_path)
    cursor = conn.cursor()
    
    # Create labels table with enriched columns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            trip_id TEXT NOT NULL,
            stop_id TEXT NOT NULL,
            label TEXT NOT NULL,
            route_id TEXT,
            uncertainty_bucket TEXT,
            has_vehicle INTEGER,
            first_status TEXT,
            first_status_10min TEXT,
            ts_labeled INTEGER,
            PRIMARY KEY (trip_id, stop_id)
        )
    """)
    
    # Add missing columns if they don't exist (schema migration)
    cursor.execute("PRAGMA table_info(labels)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if "first_status_10min" not in columns:
        try:
            cursor.execute("ALTER TABLE labels ADD COLUMN first_status_10min TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
    
    conn.commit()
    conn.close()


def _compute_labels_from_raw(config: dict | None = None) -> int:
    """Compute labels from raw.db snapshots and save enriched data to labels.db.
    
    For each labeled prediction (SERVED or VANISHED), stores:
    - route_id, uncertainty bucket, has_vehicle (measured at FIRST SIGHTING), 
      first_status, first_status_10min (from bus_trust)
    
    Only labels predictions whose predicted arrival time is > 5 minutes in the past.
    
    Returns:
        Number of labels created
    """
    if config is None:
        config = load_config()
    
    if not RAW_DB.exists():
        logger.warning(f"raw.db not found at {RAW_DB}")
        return 0
    
    # Initialize labels.db
    _initialize_labels_db()
    
    from core.bus_trust import compute_status_and_why
    
    raw_conn = _get_connection(RAW_DB)
    labels_conn = _get_connection(LABELS_DB)
    
    raw_cursor = raw_conn.cursor()
    labels_cursor = labels_conn.cursor()
    
    now_ts = int(time.time())
    five_min_ago = now_ts - 300
    labeled_count = 0
    
    try:
        # Get all predictions whose arrival is > 5 min in the past
        raw_cursor.execute("""
            SELECT DISTINCT trip_id, stop_id
            FROM pred_snap
            WHERE ts + (app_eta_min * 60) < ?
            ORDER BY trip_id, stop_id
        """, (five_min_ago,))
        
        predictions_to_label = raw_cursor.fetchall()
        logger.info(f"Found {len(predictions_to_label)} predictions to label")
        
        for pred_row in predictions_to_label:
            trip_id = pred_row[0]
            stop_id = pred_row[1]
            
            # Get the earliest (first sighting) prediction for this (trip, stop) pair
            raw_cursor.execute("""
                SELECT ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
                       schedule_relationship, revenue, headsign
                FROM pred_snap
                WHERE trip_id = ? AND stop_id = ?
                ORDER BY ts ASC
                LIMIT 1
            """, (trip_id, stop_id))
            
            pred = raw_cursor.fetchone()
            if not pred:
                continue
            
            pred_ts = pred[0]
            pred_route_id = pred[2]
            pred_eta_sec = int(pred[4] * 60)
            pred_arrival_time = pred_ts + pred_eta_sec
            uncertainty = pred[5]
            
            # Compute uncertainty bucket
            uncertainty_bucket = "missing"
            if uncertainty is not None:
                if uncertainty < 300:
                    uncertainty_bucket = "<300"
                elif uncertainty == 300:
                    uncertainty_bucket = "300"
                elif uncertainty == 301:
                    uncertainty_bucket = "301"
            
            # FIX 1: has_vehicle measured AT FIRST SIGHTING only
            # Query vehicle records AT OR BEFORE first sighting timestamp
            raw_cursor.execute("""
                SELECT ts, trip_id, route_id, stop_sequence, current_status,
                       vehicle_timestamp, vehicle_id
                FROM veh_snap
                WHERE trip_id = ? AND ts <= ?
                ORDER BY ts DESC
                LIMIT 1
            """, (trip_id, pred_ts))
            
            first_sighting_veh = raw_cursor.fetchone()
            has_vehicle_at_first_sighting = 1 if first_sighting_veh and first_sighting_veh[6] else 0
            
            # If trip was marked CANCELED, label as CANCELED
            if pred[6] in ("CANCELED", "SKIPPED"):
                label = "CANCELED"
                first_status = "unreliable"
                first_status_10min = None
            else:
                # Check vehicle history for arrival (AFTER first sighting)
                raw_cursor.execute("""
                    SELECT ts, trip_id, route_id, stop_sequence, current_status,
                           vehicle_timestamp, vehicle_id
                    FROM veh_snap
                    WHERE trip_id = ? AND ts > ?
                    ORDER BY ts DESC
                """, (trip_id, pred_ts))
                
                veh_records = raw_cursor.fetchall()
                
                # Check if vehicle reached this stop (SERVED)
                label = "OPEN"
                
                if veh_records:
                    # Check if any vehicle record indicates arrival
                    for veh in veh_records:
                        vehicle_timestamp = veh[5]
                        
                        # If vehicle_timestamp is close to predicted arrival time, consider SERVED
                        if vehicle_timestamp and vehicle_timestamp > 0:
                            time_diff = abs(vehicle_timestamp - pred_arrival_time)
                            if time_diff <= 60:  # Within 1 minute
                                label = "SERVED"
                                break
                    
                    # Check for VANISHED (vehicle was tracked but disappeared)
                    if label == "OPEN" and veh_records:
                        last_veh = veh_records[-1]  # Oldest vehicle record
                        veh_ts = last_veh[5]
                        
                        if veh_ts and veh_ts > 0:
                            time_since_vehicle = pred_arrival_time - veh_ts
                            vanish_margin = config.get("thresholds", {}).get("vanish_margin_s", 120)
                            
                            if time_since_vehicle > vanish_margin:
                                # Vehicle disappeared before arrival
                                label = "VANISHED"
                
                # If prediction is still in feed, mark as OPEN
                if label == "OPEN":
                    raw_cursor.execute("""
                        SELECT COUNT(*) FROM pred_snap
                        WHERE trip_id = ? AND stop_id = ? AND ts > ?
                    """, (trip_id, stop_id, pred_ts))
                    newer_preds = raw_cursor.fetchone()[0]
                    if newer_preds > 0:
                        label = "OPEN"
                
                # Compute first_status using bus_trust at first sighting
                location_age_sec = None
                vehicle_id = None
                current_status = None
                
                if first_sighting_veh:
                    vehicle_id = first_sighting_veh[6]
                    location_age_sec = pred_ts - first_sighting_veh[5] if first_sighting_veh[5] else None
                    current_status = first_sighting_veh[4]
                
                evidence = {
                    "uncertainty": uncertainty,
                    "vehicle_id": vehicle_id,
                    "location_age_sec": location_age_sec,
                }
                
                pred_dict = {
                    "route_id": pred_route_id,
                    "trip_id": trip_id,
                    "app_eta_min": pred[4],
                    "revenue": pred[7],
                    "schedule_relationship": pred[6],
                    "current_status": current_status,
                    "headsign": pred[8],
                }
                
                status, _, _, _ = compute_status_and_why(pred_dict, evidence)
                first_status = status if status is not None else "estimate"
                
                # FIX 2: Compute first_status_10min at 10+ minutes before predicted arrival
                # Query predictions at or after (pred_arrival_time - 600 seconds)
                ten_min_before_arrival = pred_arrival_time - 600
                
                raw_cursor.execute("""
                    SELECT ts, route_id, app_eta_min, uncertainty, schedule_relationship, 
                           revenue, headsign
                    FROM pred_snap
                    WHERE trip_id = ? AND stop_id = ? AND ts >= ?
                    ORDER BY ts DESC
                    LIMIT 1
                """, (trip_id, stop_id, ten_min_before_arrival))
                
                pred_10min = raw_cursor.fetchone()
                first_status_10min = None
                
                if pred_10min:
                    # Find vehicle record at this earlier prediction time
                    pred_10min_ts = pred_10min[0]
                    
                    raw_cursor.execute("""
                        SELECT ts, vehicle_timestamp, vehicle_id, current_status
                        FROM veh_snap
                        WHERE trip_id = ? AND ts <= ?
                        ORDER BY ts DESC
                        LIMIT 1
                    """, (trip_id, pred_10min_ts))
                    
                    veh_10min = raw_cursor.fetchone()
                    veh_id_10min = None
                    veh_ts_10min = None
                    status_10min = None
                    
                    if veh_10min:
                        veh_ts_10min = veh_10min[1]
                        veh_id_10min = veh_10min[2]
                        status_10min = veh_10min[3]
                    
                    location_age_10min = pred_10min_ts - veh_ts_10min if veh_ts_10min else None
                    
                    evidence_10min = {
                        "uncertainty": pred_10min[3],
                        "vehicle_id": veh_id_10min,
                        "location_age_sec": location_age_10min,
                    }
                    
                    pred_dict_10min = {
                        "route_id": pred_10min[1],
                        "trip_id": trip_id,
                        "app_eta_min": pred_10min[2],
                        "revenue": pred_10min[5],
                        "schedule_relationship": pred_10min[4],
                        "current_status": status_10min,
                        "headsign": pred_10min[6],
                    }
                    
                    status_10min_val, _, _, _ = compute_status_and_why(pred_dict_10min, evidence_10min)
                    first_status_10min = status_10min_val if status_10min_val is not None else "estimate"
            
            # Insert enriched label into labels.db
            labels_cursor.execute(
                """
                INSERT OR IGNORE INTO labels 
                (trip_id, stop_id, label, route_id, uncertainty_bucket, has_vehicle, first_status, first_status_10min, ts_labeled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (trip_id, stop_id, label, pred_route_id, uncertainty_bucket, 
                 has_vehicle_at_first_sighting, first_status, first_status_10min, int(time.time()))
            )
            labeled_count += 1
        
        labels_conn.commit()
        logger.info(f"Labeled {labeled_count} predictions in labels.db")
    
    except Exception as e:
        logger.error(f"Error computing labels: {e}")
        labels_conn.rollback()
        raise
    
    finally:
        raw_conn.close()
        labels_conn.close()
    
    return labeled_count


def generate_findings(
    db: sqlite3.Connection | None = None,
    model: object | None = None,
    is_placeholder: bool = False,
    config: dict | None = None,
) -> Findings:
    """Generate findings from labels and poll log.

    Args:
        db: Database connection (if None, uses labels.db). For testing compatibility.
        model: Trained model object (if any)
        is_placeholder: True if demo or insufficient data
        config: Configuration dict (if None, loads from config.yaml)

    Returns:
        Findings object with all metrics
    """
    if config is None:
        config = load_config()
    
    # FIX 3: Recompute labels on every call from fresh snapshot
    # This ensures totals grow over time as new data arrives
    # Skip if raw.db is busy (being written by collector)
    if RAW_DB.exists():
        try:
            _compute_labels_from_raw(config)
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                logger.debug("raw.db is locked; skipping label recomputation")
            else:
                logger.warning(f"Could not recompute labels: {e}")
    
    # Create snapshot of raw.db to avoid locks
    has_raw_db = RAW_DB.exists()
    if has_raw_db:
        try:
            _create_snapshot(timeout_sec=30)
        except sqlite3.OperationalError as e:
            logger.warning(f"Could not create snapshot: {e}; continuing with limited metrics")
    
    # Use labels.db if no db provided
    if db is None:
        db = _get_connection(LABELS_DB)
        should_close = True
    else:
        should_close = False

    cursor = db.cursor()
    now = int(datetime.now().timestamp())
    now_iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    try:
        # ========== Get label totals ==========
        cursor.execute(
            """
            SELECT label, COUNT(*) as count
            FROM labels
            GROUP BY label
            """
        )
        label_counts = {row[0]: row[1] for row in cursor.fetchall()}
        total_labeled = sum(label_counts.values())

        totals = {
            "labeled": total_labeled,
            "served": label_counts.get("SERVED", 0),
            "vanished": label_counts.get("VANISHED", 0),
            "canceled": label_counts.get("CANCELED", 0),
        }

        # ========== Determine sample label ==========
        # Most common label
        sample_label = max(label_counts.keys(), key=lambda k: label_counts[k]) if label_counts else "OPEN"

        # ========== Get window from poll_log (read from snapshot if available) ==========
        window_row = None
        if has_raw_db and RAW_SNAPSHOT_DB.exists():
            try:
                raw_conn = _get_connection(RAW_SNAPSHOT_DB)
                raw_cursor = raw_conn.cursor()
                
                raw_cursor.execute(
                    """
                    SELECT MIN(ts), MAX(ts) FROM poll_log WHERE success = 1
                    """
                )
                window_row = raw_cursor.fetchone()
                raw_conn.close()
            except sqlite3.OperationalError:
                window_row = None
        
        if window_row and window_row[0] and window_row[1]:
            window_start = window_row[0]
            window_end = window_row[1]
        else:
            # Fallback: use label timestamps
            cursor.execute(
                """
                SELECT MIN(ts_labeled), MAX(ts_labeled) FROM labels
                """
            )
            ts_row = cursor.fetchone()
            if ts_row and ts_row[0] and ts_row[1]:
                window_start = ts_row[0]
                window_end = ts_row[1]
            else:
                window_start = now
                window_end = now

        window = {"start": window_start, "end": window_end}

        # ========== Fetch first-sighting data in one query ==========
        # For each (trip_id, stop_id), get MIN(ts) and associated fields
        first_sightings = {}  # (trip_id, stop_id) -> {ts, route_id, uncertainty, schedule_rel, revenue}
        
        if has_raw_db and RAW_SNAPSHOT_DB.exists():
            try:
                raw_conn = _get_connection(RAW_SNAPSHOT_DB)
                raw_cursor = raw_conn.cursor()
                
                # Use MIN(ts) subquery to get first sighting per (trip_id, stop_id)
                raw_cursor.execute("""
                    SELECT p1.trip_id, p1.stop_id, p1.ts, p1.route_id, p1.uncertainty, 
                           p1.schedule_relationship, p1.revenue
                    FROM pred_snap p1
                    WHERE (p1.trip_id, p1.stop_id, p1.ts) IN (
                        SELECT trip_id, stop_id, MIN(ts)
                        FROM pred_snap
                        GROUP BY trip_id, stop_id
                    )
                """)
                
                for row in raw_cursor.fetchall():
                    trip_id, stop_id, ts, route_id, uncertainty, schedule_rel, revenue = row
                    first_sightings[(trip_id, stop_id)] = {
                        "ts": ts,
                        "route_id": route_id,
                        "uncertainty": uncertainty,
                        "schedule_relationship": schedule_rel,
                        "revenue": revenue,
                    }
                
                raw_conn.close()
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not fetch first sightings: {e}")

        # ========== Vanish rates by status ==========
        vanish_by_status = []
        if total_labeled > 0 and first_sightings:
            try:
                cursor.execute(
                    """
                    SELECT trip_id, stop_id, label, first_status
                    FROM labels
                    WHERE label IN ('SERVED', 'VANISHED')
                    """
                )
                label_rows = cursor.fetchall()
                
                status_label_map = {}  # status_name -> {vanished, total}
                
                for trip_id, stop_id, label, first_status in label_rows:
                    key = (trip_id, stop_id)
                    if key not in first_sightings:
                        continue
                    
                    # Use first_status from labels table
                    if first_status not in status_label_map:
                        status_label_map[first_status] = {"vanished": 0, "total": 0}
                    
                    status_label_map[first_status]["total"] += 1
                    if label == "VANISHED":
                        status_label_map[first_status]["vanished"] += 1
                
                for status, counts in status_label_map.items():
                    if counts["total"] > 0:
                        vanish_rate = counts["vanished"] / counts["total"]
                        vanish_by_status.append(
                            RateRow(group=status, rate=vanish_rate, n=counts["total"])
                        )
            except Exception as e:
                logger.warning(f"Could not compute vanish_by_status: {e}")

        # ========== Vanish rates by status_10min (FIX 2) ==========
        vanish_by_status_10min = []
        if total_labeled > 0 and first_sightings:
            try:
                cursor.execute(
                    """
                    SELECT trip_id, stop_id, label, first_status_10min
                    FROM labels
                    WHERE label IN ('SERVED', 'VANISHED') AND first_status_10min IS NOT NULL
                    """
                )
                label_rows = cursor.fetchall()
                
                status_10min_map = {}  # status_name -> {vanished, total}
                
                for trip_id, stop_id, label, first_status_10min in label_rows:
                    key = (trip_id, stop_id)
                    if key not in first_sightings:
                        continue
                    
                    if first_status_10min not in status_10min_map:
                        status_10min_map[first_status_10min] = {"vanished": 0, "total": 0}
                    
                    status_10min_map[first_status_10min]["total"] += 1
                    if label == "VANISHED":
                        status_10min_map[first_status_10min]["vanished"] += 1
                
                for status, counts in status_10min_map.items():
                    if counts["total"] > 0:
                        vanish_rate = counts["vanished"] / counts["total"]
                        vanish_by_status_10min.append(
                            RateRow(group=status, rate=vanish_rate, n=counts["total"])
                        )
            except Exception as e:
                logger.warning(f"Could not compute vanish_by_status_10min: {e}")

        # ========== Vanish rates by uncertainty ==========
        vanish_by_uncertainty = []
        if total_labeled > 0 and first_sightings:
            try:
                cursor.execute(
                    """
                    SELECT trip_id, stop_id, label, has_vehicle
                    FROM labels
                    WHERE label IN ('SERVED', 'VANISHED')
                    """
                )
                label_rows = cursor.fetchall()
                
                unc_vehicle_map = {}  # (unc_bucket, has_vehicle) -> {vanished, total}
                
                for trip_id, stop_id, label, has_vehicle_db in label_rows:
                    key = (trip_id, stop_id)
                    if key not in first_sightings:
                        continue
                    
                    first = first_sightings[key]
                    uncertainty = first["uncertainty"]
                    # FIX 1: Use has_vehicle from labels table (measured at first sighting)
                    has_vehicle = has_vehicle_db
                    
                    # Compute uncertainty bucket
                    if uncertainty is None:
                        unc_bucket = "missing"
                    elif uncertainty < 300:
                        unc_bucket = "<300"
                    elif uncertainty == 300:
                        unc_bucket = "300"
                    elif uncertainty == 301:
                        unc_bucket = "301"
                    else:
                        unc_bucket = ">301"
                    
                    key = (unc_bucket, has_vehicle)
                    if key not in unc_vehicle_map:
                        unc_vehicle_map[key] = {"vanished": 0, "total": 0}
                    
                    unc_vehicle_map[key]["total"] += 1
                    if label == "VANISHED":
                        unc_vehicle_map[key]["vanished"] += 1
                
                for (unc_bucket, has_vehicle), counts in unc_vehicle_map.items():
                    if counts["total"] > 0:
                        vanish_rate = counts["vanished"] / counts["total"]
                        group_name = f"{unc_bucket}_vehicle={bool(has_vehicle)}"
                        vanish_by_uncertainty.append(
                            RateRow(group=group_name, rate=vanish_rate, n=counts["total"])
                        )
            except Exception as e:
                logger.warning(f"Could not compute vanish_by_uncertainty: {e}")

        # ========== Vanish rates by route ==========
        vanish_by_route = []
        if total_labeled > 0 and first_sightings:
            try:
                cursor.execute(
                    """
                    SELECT trip_id, stop_id, label
                    FROM labels
                    WHERE label IN ('SERVED', 'VANISHED')
                    """
                )
                label_rows = cursor.fetchall()
                
                route_map = {}  # route_id -> {vanished, total}
                
                for trip_id, stop_id, label in label_rows:
                    key = (trip_id, stop_id)
                    if key not in first_sightings:
                        continue
                    
                    first = first_sightings[key]
                    route_id = first["route_id"]
                    
                    if route_id is None:
                        continue
                    
                    if route_id not in route_map:
                        route_map[route_id] = {"vanished": 0, "total": 0}
                    
                    route_map[route_id]["total"] += 1
                    if label == "VANISHED":
                        route_map[route_id]["vanished"] += 1
                
                for route_id, counts in route_map.items():
                    if counts["total"] > 0:
                        vanish_rate = counts["vanished"] / counts["total"]
                        vanish_by_route.append(
                            RateRow(group=route_id, rate=vanish_rate, n=counts["total"])
                        )
            except Exception as e:
                logger.warning(f"Could not compute vanish_by_route: {e}")

        # ========== ETA range hit rate ==========
        # Note: eta_range_hit requires arrival data (observed vs predicted ETA ranges)
        # If arrivals table doesn't exist, leave n=0 (don't invent data)
        eta_range_hit_data = {
            "range_hit": 0,
            "single_eta_hit": 0,
            "n": 0,
        }

        # ========== Least reliable docks ==========
        # Skip for now; requires dock data
        least_reliable_docks = []

        # ========== Model info ==========
        # Determine method: placeholder if is_placeholder flag or insufficient labels
        should_be_placeholder = is_placeholder or total_labeled < config.get("thresholds", {}).get("min_labels", 300)
        model_method = "placeholder" if should_be_placeholder else ("model" if model else "empirical")
        
        model_info = ModelInfo(
            method=model_method,
            auc=None,
            brier=None,
            n_labels=total_labeled,
        )

        # ========== Calibration bins ==========
        calibration_bins = []

        # ========== Eval info ==========
        eval_info = EvalInfo(
            holdout_window=None,
            n_train=total_labeled,
            n_test=0,
        )

        # ========== Create Findings ==========
        findings = Findings(
            generated_at=now_iso,
            sample_label=sample_label,
            window=window,
            totals=totals,
            vanish_by_status=vanish_by_status,
            vanish_by_uncertainty=vanish_by_uncertainty,
            vanish_by_route=vanish_by_route,
            vanish_by_status_10min=vanish_by_status_10min if vanish_by_status_10min else None,
            eta_range_hit=eta_range_hit_data,
            least_reliable_docks=least_reliable_docks,
            model=model_info,
            calibration=calibration_bins,
            eval=eval_info,
            is_placeholder=should_be_placeholder,
        )

        return findings
    
    finally:
        if should_close:
            db.close()


def save_findings(findings: Findings, output_path: Path = Path("artifacts/findings.json")) -> None:
    """Save findings to JSON file.

    Args:
        findings: Findings object
        output_path: Path to save to
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(findings.model_dump(), f, indent=2, default=str)

    logger.info(f"Saved findings to {output_path}")
