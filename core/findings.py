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
LABELS_DB = REPO_ROOT / "data" / "labels.db"


def load_config() -> dict:
    """Load config.yaml."""
    config_path = REPO_ROOT / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            trip_id TEXT NOT NULL,
            stop_id TEXT NOT NULL,
            label TEXT NOT NULL,
            route_id TEXT,
            uncertainty_bucket TEXT,
            has_vehicle INTEGER,
            first_status TEXT,
            ts_labeled INTEGER,
            PRIMARY KEY (trip_id, stop_id)
        )
    """)
    conn.commit()
    conn.close()


def _compute_labels_from_raw(config: dict | None = None) -> int:
    """Compute labels from raw.db snapshots and save enriched data to labels.db.
    
    For each labeled prediction (SERVED or VANISHED), stores:
    - route_id, uncertainty bucket, has_vehicle, first_status (from bus_trust)
    
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
            
            # Skip if already labeled
            labels_cursor.execute(
                "SELECT label FROM labels WHERE trip_id = ? AND stop_id = ?",
                (trip_id, stop_id)
            )
            if labels_cursor.fetchone():
                continue
            
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
            
            # If trip was marked CANCELED, label as CANCELED
            if pred[6] in ("CANCELED", "SKIPPED"):
                label = "CANCELED"
                first_status = "unreliable"
                has_vehicle = False
            else:
                # Check vehicle history for arrival
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
                has_vehicle = False
                
                if veh_records:
                    has_vehicle = True
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
                # Get vehicle data at first sighting
                location_age_sec = None
                vehicle_id = None
                current_status = None
                
                if veh_records:
                    # Use most recent vehicle record at or before first pred
                    first_vehicle = veh_records[-1]  # Oldest (closest in time to pred)
                    vehicle_id = first_vehicle[6]
                    location_age_sec = pred_ts - first_vehicle[5] if first_vehicle[5] else None
                    current_status = first_vehicle[4]
                
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
            
            # Insert enriched label into labels.db
            labels_cursor.execute(
                """
                INSERT OR IGNORE INTO labels 
                (trip_id, stop_id, label, route_id, uncertainty_bucket, has_vehicle, first_status, ts_labeled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (trip_id, stop_id, label, pred_route_id, uncertainty_bucket, 
                 int(has_vehicle), first_status, int(time.time()))
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
    
    # Ensure labels are computed (only when raw.db exists)
    if RAW_DB.exists():
        _compute_labels_from_raw(config)
    
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

        # ========== Get window from poll_log (read from raw.db) ==========
        if RAW_DB.exists():
            raw_conn = _get_connection(RAW_DB)
            raw_cursor = raw_conn.cursor()
            
            raw_cursor.execute(
                """
                SELECT MIN(ts), MAX(ts) FROM poll_log WHERE success = 1
                """
            )
            window_row = raw_cursor.fetchone()
            raw_conn.close()
        else:
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

        # ========== Vanish rates by status ==========
        vanish_by_status = []
        if total_labeled > 0:
            # Get vanished count
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM labels
                WHERE label = 'VANISHED'
                """
            )
            vanished_row = cursor.fetchone()
            if vanished_row and vanished_row[0] > 0:
                vanished_count = vanished_row[0]
                vanish_rate = vanished_count / total_labeled
                vanish_by_status.append(
                    RateRow(group="VANISHED", rate=vanish_rate, n=vanished_count)
                )

        # ========== Vanish rates by uncertainty ==========
        # This requires joining with pred_snap, so we'll skip if no raw.db
        vanish_by_uncertainty = []

        # ========== Vanish rates by route ==========
        # This also requires pred_snap data; skip for now
        vanish_by_route = []

        # ========== ETA range hit rate ==========
        # Skip for now; arrivals table may not exist
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
