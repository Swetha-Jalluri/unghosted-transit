"""Label assignment for historical predictions."""
import logging
import sqlite3
import time
from typing import Optional
from pathlib import Path

import yaml

from core import database

logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load config.yaml."""
    config_path = Path("config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def assign_label(
    pred: dict,
    veh_history: list[dict],
    pred_history: list[dict],
    config: dict,
) -> str:
    """Assign label to a prediction: SERVED | VANISHED | CANCELED | OPEN.

    Args:
        pred: Single prediction record from pred_snap
        veh_history: List of vehicle records for this trip after the prediction
        pred_history: List of prediction records for this (trip, stop) after the prediction
        config: Configuration dict

    Returns:
        Label string: "SERVED", "VANISHED", "CANCELED", or "OPEN"
    """
    # If schedule_relationship is CANCELED/SKIPPED, label as CANCELED
    if pred.get("schedule_relationship") in ("CANCELED", "SKIPPED"):
        return "CANCELED"

    # Check if prediction is still in feed (has newer pred_history records)
    # If there are predictions after this one, trip is still OPEN
    if pred_history and len(pred_history) > 0:
        # Check if most recent prediction still has schedule_relationship != CANCELED
        latest_pred = pred_history[-1]  # Most recent (sorted by ts descending)
        if latest_pred.get("schedule_relationship") not in ("CANCELED", "SKIPPED"):
            return "OPEN"

    # Check vehicle history for arrival
    if veh_history:
        # SERVED if vehicle reached/passed stop or prediction stayed within 1 min
        # Vehicle current_stop_sequence >= pred stop_sequence means vehicle reached it
        pred_ts = pred.get("ts")
        pred_eta_sec = int(pred.get("app_eta_min", 0) * 60)
        pred_arrival_time = pred_ts + pred_eta_sec
        pred_stop_seq = pred.get("stop_sequence")

        for veh_record in veh_history:
            veh_stop_seq = veh_record.get("stop_sequence")

            # If both have stop_sequence and vehicle is at or past this stop, label SERVED
            if veh_stop_seq is not None and pred_stop_seq is not None:
                if veh_stop_seq >= pred_stop_seq:
                    return "SERVED"

            # Check if vehicle timestamp shows it arrived near prediction time
            veh_ts = veh_record.get("vehicle_timestamp", 0)
            if veh_ts > 0:
                time_diff = abs(veh_ts - pred_arrival_time)
                if time_diff <= 60:  # Within 1 minute
                    return "SERVED"

    # VANISHED: disappeared > 2 min before arrival with no vehicle reached
    # This happens when vehicle was present but then disappeared from feed
    # before reaching the stop
    if veh_history:
        # Check if last vehicle record is > vanish_margin_s before predicted arrival
        last_veh = veh_history[-1]
        veh_ts = last_veh.get("vehicle_timestamp", 0)

        if veh_ts > 0:
            pred_ts = pred.get("ts")
            pred_eta_sec = int(pred.get("app_eta_min", 0) * 60)
            pred_arrival_time = pred_ts + pred_eta_sec

            time_since_vehicle_seen = pred_arrival_time - veh_ts
            vanish_margin = config.get("thresholds", {}).get("vanish_margin_s", 120)

            if time_since_vehicle_seen > vanish_margin:
                return "VANISHED"

    # Default to OPEN if still in feed
    return "OPEN"


def flicker_filter(
    history: list[dict],
    ts: int,
    config: dict,
) -> bool:
    """Flicker logic: suppress label until prediction is old enough or vehicle confirmed.

    Returns True if label should be suppressed (not yet reliable).

    Args:
        history: List of prediction records for this (trip, stop), sorted by ts descending
        ts: Current timestamp
        config: Configuration dict

    Returns:
        True if label should be suppressed; False if ready to label
    """
    if not history:
        return True

    # Get most recent prediction
    latest_pred = history[0]
    pred_ts = latest_pred.get("ts", ts)
    pred_eta_min = latest_pred.get("app_eta_min", 0)

    # Suppress label until prediction is old enough (passed its ETA by some margin)
    # Or until we have a vehicle confirmation
    eta_age_sec = ts - (pred_ts + int(pred_eta_min * 60))

    # Use stale_location_s as flicker threshold (2 minutes default)
    flicker_threshold = config.get("thresholds", {}).get("stale_location_s", 120)

    return eta_age_sec < flicker_threshold


def label_predictions(
    db: sqlite3.Connection,
    window: tuple[int, int],
    config: Optional[dict] = None,
) -> int:
    """Assign labels to all predictions in a time window.

    Args:
        db: Database connection
        window: (start_ts, end_ts) POSIX seconds
        config: Configuration dict (if None, loads from config.yaml)

    Returns:
        Number of labels created
    """
    if config is None:
        config = load_config()

    start_ts, end_ts = window
    cursor = db.cursor()
    labeled_count = 0

    try:
        # Get all predictions in the window (not yet labeled)
        cursor.execute(
            """
            SELECT DISTINCT trip_id, stop_id FROM pred_snap
            WHERE ts BETWEEN ? AND ?
            AND (trip_id, stop_id) NOT IN (SELECT trip_id, stop_id FROM labels)
            ORDER BY trip_id, stop_id
            """,
            (start_ts, end_ts),
        )

        predictions_to_label = cursor.fetchall()

        for pred_row in predictions_to_label:
            trip_id = pred_row[0]
            stop_id = pred_row[1]

            # Get the prediction record from the window
            cursor.execute(
                """
                SELECT ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
                       schedule_relationship, revenue, headsign, stop_sequence
                FROM pred_snap
                WHERE trip_id = ? AND stop_id = ? AND ts BETWEEN ? AND ?
                ORDER BY ts
                """,
                (trip_id, stop_id, start_ts, end_ts),
            )

            pred_records = cursor.fetchall()
            if not pred_records:
                continue

            # Take the earliest prediction in the window
            pred = {
                "ts": pred_records[0][0],
                "stop_id": pred_records[0][1],
                "route_id": pred_records[0][2],
                "trip_id": pred_records[0][3],
                "app_eta_min": pred_records[0][4],
                "uncertainty": pred_records[0][5],
                "schedule_relationship": pred_records[0][6],
                "revenue": bool(pred_records[0][7]),
                "headsign": pred_records[0][8],
                "stop_sequence": pred_records[0][9],
            }

            pred_ts = pred["ts"]

            # Get vehicle history after this prediction
            cursor.execute(
                """
                SELECT ts, trip_id, route_id, stop_sequence, current_status,
                       vehicle_timestamp, vehicle_id
                FROM veh_snap
                WHERE trip_id = ? AND ts > ?
                ORDER BY ts DESC
                """,
                (trip_id, pred_ts),
            )

            veh_records = cursor.fetchall()
            veh_history = [
                {
                    "ts": r[0],
                    "trip_id": r[1],
                    "route_id": r[2],
                    "stop_sequence": r[3],
                    "current_status": r[4],
                    "vehicle_timestamp": r[5],
                    "vehicle_id": r[6],
                }
                for r in veh_records
            ]

            # Get prediction history after this prediction
            cursor.execute(
                """
                SELECT ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
                       schedule_relationship, revenue, headsign, stop_sequence
                FROM pred_snap
                WHERE trip_id = ? AND stop_id = ? AND ts > ?
                ORDER BY ts DESC
                """,
                (trip_id, stop_id, pred_ts),
            )

            pred_records_after = cursor.fetchall()
            pred_history = [
                {
                    "ts": r[0],
                    "stop_id": r[1],
                    "route_id": r[2],
                    "trip_id": r[3],
                    "app_eta_min": r[4],
                    "uncertainty": r[5],
                    "schedule_relationship": r[6],
                    "revenue": bool(r[7]),
                    "headsign": r[8],
                    "stop_sequence": r[9],
                }
                for r in pred_records_after
            ]

            # Check flicker filter
            # Combine all predictions for this (trip, stop) for flicker check
            cursor.execute(
                """
                SELECT ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
                       schedule_relationship, revenue, headsign, stop_sequence
                FROM pred_snap
                WHERE trip_id = ? AND stop_id = ?
                ORDER BY ts DESC
                """,
                (trip_id, stop_id),
            )

            all_pred_records = cursor.fetchall()
            all_pred_history = [
                {
                    "ts": r[0],
                    "stop_id": r[1],
                    "route_id": r[2],
                    "trip_id": r[3],
                    "app_eta_min": r[4],
                    "uncertainty": r[5],
                    "schedule_relationship": r[6],
                    "revenue": bool(r[7]),
                    "headsign": r[8],
                    "stop_sequence": r[9],
                }
                for r in all_pred_records
            ]

            if flicker_filter(all_pred_history, end_ts, config):
                continue

            # Assign label
            label = assign_label(pred, veh_history, pred_history, config)

            # Store label
            cursor.execute(
                """
                INSERT INTO labels (trip_id, stop_id, label, ts_labeled)
                VALUES (?, ?, ?, ?)
                """,
                (trip_id, stop_id, label, int(time.time())),
            )

            labeled_count += 1

        db.commit()
        logger.info(f"Labeled {labeled_count} predictions in window {start_ts}-{end_ts}")

    except Exception as e:
        logger.error(f"Error during label_predictions: {e}")
        db.rollback()
        raise

    return labeled_count


def propagate_canceled(
    db: sqlite3.Connection,
    config: Optional[dict] = None,
) -> int:
    """Propagate CANCELED labels from any stop of a trip to all stops.

    Args:
        db: Database connection
        config: Configuration dict (if None, loads from config.yaml)

    Returns:
        Number of labels updated to CANCELED
    """
    if config is None:
        config = load_config()

    cursor = db.cursor()
    updated_count = 0

    try:
        # Find trips with any CANCELED label
        cursor.execute(
            """
            SELECT DISTINCT trip_id FROM labels
            WHERE label = 'CANCELED'
            """
        )

        canceled_trips = cursor.fetchall()

        for (trip_id,) in canceled_trips:
            # Update all labels for this trip to CANCELED if not already
            cursor.execute(
                """
                UPDATE labels
                SET label = 'CANCELED'
                WHERE trip_id = ? AND label != 'CANCELED'
                """,
                (trip_id,),
            )

            updated_count += cursor.rowcount

        db.commit()
        logger.info(f"Propagated CANCELED to {updated_count} labels")

    except Exception as e:
        logger.error(f"Error during propagate_canceled: {e}")
        db.rollback()
        raise

    return updated_count
