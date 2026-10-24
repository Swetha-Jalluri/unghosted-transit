"""Arrival time and ETA error computation for labeled predictions."""
import logging
import sqlite3
import time
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load config.yaml."""
    config_path = Path("config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def compute_eta_error(pred_ts: int, pred_eta_min: float, actual_arrival_ts: int) -> float:
    """Compute ETA error: actual - predicted in minutes.

    Args:
        pred_ts: Prediction timestamp (POSIX seconds)
        pred_eta_min: Predicted ETA in minutes from pred_ts
        actual_arrival_ts: Actual arrival timestamp (POSIX seconds)

    Returns:
        ETA error in minutes (positive = late, negative = early)
    """
    # Predicted arrival time in seconds
    predicted_arrival_ts = pred_ts + int(pred_eta_min * 60)

    # Error in seconds, then convert to minutes
    error_sec = actual_arrival_ts - predicted_arrival_ts
    error_min = error_sec / 60.0

    return error_min


def record_arrivals(db: sqlite3.Connection) -> int:
    """Compute arrival time and ETA error for all SERVED labels.

    For each SERVED label, find the actual vehicle arrival time from veh_snap
    and record the ETA error compared to the prediction.

    Args:
        db: Database connection

    Returns:
        Number of arrival records created
    """
    cursor = db.cursor()
    recorded_count = 0

    try:
        # Get all SERVED labels that haven't been recorded yet
        cursor.execute(
            """
            SELECT l.trip_id, l.stop_id
            FROM labels l
            WHERE l.label = 'SERVED'
            AND (l.trip_id, l.stop_id) NOT IN (SELECT trip_id, stop_id FROM arrivals)
            """
        )

        served_labels = cursor.fetchall()

        for trip_id, stop_id in served_labels:
            # Get the prediction for this (trip_id, stop_id)
            cursor.execute(
                """
                SELECT ts, app_eta_min, stop_sequence
                FROM pred_snap
                WHERE trip_id = ? AND stop_id = ?
                ORDER BY ts ASC
                LIMIT 1
                """,
                (trip_id, stop_id),
            )

            pred_row = cursor.fetchone()
            if not pred_row:
                logger.warning(f"No prediction found for ({trip_id}, {stop_id})")
                continue

            pred_ts, pred_eta_min, pred_stop_seq = pred_row

            # Get the actual vehicle arrival time from veh_snap
            # Look for the first vehicle record that reaches or passes this stop
            cursor.execute(
                """
                SELECT ts, vehicle_timestamp, stop_sequence, current_status
                FROM veh_snap
                WHERE trip_id = ? AND ts > ?
                ORDER BY ts ASC
                """,
                (trip_id, pred_ts),
            )

            veh_records = cursor.fetchall()

            actual_arrival_ts = None

            for veh_ts, vehicle_timestamp, veh_stop_seq, current_status in veh_records:
                # Vehicle has reached or passed the stop
                if veh_stop_seq is not None and pred_stop_seq is not None:
                    if veh_stop_seq >= pred_stop_seq:
                        # Use vehicle_timestamp if available, else use veh_ts
                        actual_arrival_ts = vehicle_timestamp if vehicle_timestamp > 0 else veh_ts
                        break

            if actual_arrival_ts is None:
                logger.debug(
                    f"Could not find actual arrival time for ({trip_id}, {stop_id})"
                )
                continue

            # Compute ETA error
            eta_error = compute_eta_error(pred_ts, pred_eta_min, actual_arrival_ts)

            # Record arrival
            cursor.execute(
                """
                INSERT INTO arrivals
                (trip_id, stop_id, actual_arrival_ts, predicted_arrival_ts, eta_error_min, ts_recorded)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    trip_id,
                    stop_id,
                    actual_arrival_ts,
                    pred_ts + int(pred_eta_min * 60),
                    eta_error,
                    int(time.time()),
                ),
            )

            recorded_count += 1

        db.commit()
        logger.info(f"Recorded {recorded_count} arrival metrics")

    except Exception as e:
        logger.error(f"Error during record_arrivals: {e}")
        db.rollback()
        raise

    return recorded_count
