"""Scheduled data collection and storage."""
import logging
import sqlite3
import time
import random
from pathlib import Path
from typing import Optional

import yaml

from core import feeds, database

logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load config.yaml."""
    config_path = Path("config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def initialize_db() -> None:
    """Create data/raw.db schema."""
    db_path = Path("data") / "raw.db"
    database.initialize_db(db_path)
    
    # Set WAL mode for better concurrent access
    db = database.get_connection(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.close()
    
    logger.info(f"Initialized database at {db_path}")


def insert_pred_snap(db: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert pred_snap records (append-only); return count inserted."""
    if not rows:
        return 0

    cursor = db.cursor()
    count = 0

    for row in rows:
        try:
            cursor.execute(
                """
                INSERT INTO pred_snap
                (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
                 schedule_relationship, revenue, headsign, stop_sequence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("timestamp"),
                    row.get("stop_id"),
                    row.get("route_id"),
                    row.get("trip_id"),
                    row.get("app_eta_min"),
                    row.get("arrival_uncertainty") or row.get("departure_uncertainty"),
                    row.get("stop_schedule_relationship"),
                    1 if row.get("revenue", True) else 0,
                    row.get("headsign"),
                    row.get("stop_sequence"),
                ),
            )
            count += 1
        except Exception as e:
            logger.debug(f"Failed to insert pred_snap record: {e}")
            continue

    db.commit()
    return count


def insert_veh_snap(db: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert veh_snap records (append-only); return count inserted."""
    if not rows:
        return 0

    cursor = db.cursor()
    count = 0

    for row in rows:
        try:
            cursor.execute(
                """
                INSERT INTO veh_snap
                (ts, trip_id, route_id, stop_sequence, current_status,
                 vehicle_timestamp, vehicle_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("timestamp"),
                    row.get("trip_id"),
                    row.get("route_id"),
                    row.get("current_stop_sequence"),
                    row.get("current_status"),
                    row.get("timestamp"),
                    row.get("vehicle_id"),
                ),
            )
            count += 1
        except Exception as e:
            logger.debug(f"Failed to insert veh_snap record: {e}")
            continue

    db.commit()
    return count


def insert_dock_snap(db: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert dock_snap records (append-only); return count inserted."""
    if not rows:
        return 0

    cursor = db.cursor()
    count = 0

    for row in rows:
        try:
            cursor.execute(
                """
                INSERT INTO dock_snap
                (ts, station_id, app_bikes, num_docks_available,
                 is_renting, is_installed, last_reported)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("last_reported"),
                    row.get("station_id"),
                    row.get("app_bikes"),
                    row.get("num_docks_available"),
                    1 if row.get("is_renting", True) else 0,
                    1 if row.get("is_installed", True) else 0,
                    row.get("last_reported"),
                ),
            )
            count += 1
        except Exception as e:
            logger.debug(f"Failed to insert dock_snap record: {e}")
            continue

    db.commit()
    return count


def log_poll(
    db: sqlite3.Connection,
    success: bool,
    counts: dict,
    ages: dict,
) -> None:
    """Record poll_log entry."""
    cursor = db.cursor()
    ts = int(time.time())

    try:
        cursor.execute(
            """
            INSERT INTO poll_log
            (ts, success, n_pred, n_veh, n_dock,
             data_age_trip_updates, data_age_vehicle_positions, data_age_docks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                1 if success else 0,
                counts.get("pred", 0),
                counts.get("veh", 0),
                counts.get("dock", 0),
                ages.get("trip_updates"),
                ages.get("vehicle_positions"),
                ages.get("docks"),
            ),
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log poll: {e}")


def poll_all_feeds(config: dict) -> None:
    """Fetch all feeds, filter by routes, insert into database."""
    db_path = Path("data") / "raw.db"
    db = database.get_connection(db_path)

    try:
        configured_routes = set(config.get("routes", []))
        ts = int(time.time())
        counts = {"pred": 0, "veh": 0, "dock": 0}
        ages = {"trip_updates": None, "vehicle_positions": None, "docks": None}

        # Fetch and parse trip updates
        trip_updates_raw = feeds.fetch_trip_updates()
        if trip_updates_raw:
            trip_updates_records = feeds.parse_trip_updates(trip_updates_raw)

            # Filter by configured routes
            filtered_trips = [
                r for r in trip_updates_records if r.get("route_id") in configured_routes
            ]

            # Insert into database
            inserted = insert_pred_snap(db, filtered_trips)
            counts["pred"] = inserted

            # Compute data age
            if trip_updates_raw.get("header", {}).get("timestamp"):
                ages["trip_updates"] = ts - trip_updates_raw["header"]["timestamp"]

        # Fetch and parse vehicle positions
        vehicle_positions_raw = feeds.fetch_vehicle_positions()
        if vehicle_positions_raw:
            vehicle_positions_records = feeds.parse_vehicle_positions(vehicle_positions_raw)

            # Filter by configured routes
            filtered_vehicles = [
                r for r in vehicle_positions_records if r.get("route_id") in configured_routes
            ]

            # Insert into database
            inserted = insert_veh_snap(db, filtered_vehicles)
            counts["veh"] = inserted

            # Compute data age
            if vehicle_positions_raw.get("header", {}).get("timestamp"):
                ages["vehicle_positions"] = ts - vehicle_positions_raw["header"]["timestamp"]

        # Fetch and parse GBFS (no route filtering for docks)
        gbfs_status_raw, gbfs_info_raw = feeds.fetch_gbfs_status_info()
        if gbfs_status_raw and gbfs_info_raw:
            gbfs_records = feeds.parse_gbfs(gbfs_status_raw, gbfs_info_raw)

            # Insert into database
            inserted = insert_dock_snap(db, gbfs_records)
            counts["dock"] = inserted

            # Compute data age
            if gbfs_status_raw.get("data", {}).get("last_updated"):
                ages["docks"] = ts - gbfs_status_raw["data"]["last_updated"]

        # Log the poll
        success = any(counts.values())
        log_poll(db, success, counts, ages)

        logger.info(
            f"Poll complete: pred={counts['pred']}, veh={counts['veh']}, dock={counts['dock']}"
        )

    except Exception as e:
        logger.error(f"Error during poll_all_feeds: {e}")
        log_poll(db, False, counts, {})
    finally:
        db.close()


def poll_with_retry(config: dict, max_retries: int = 3) -> bool:
    """Poll feeds with exponential backoff retry logic.

    Returns True if successful, False otherwise.
    """
    for attempt in range(max_retries):
        try:
            poll_all_feeds(config)
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                backoff = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"Poll attempt {attempt + 1} failed: {e}. Retrying in {backoff:.1f}s..."
                )
                time.sleep(backoff)
            else:
                logger.error(f"Poll failed after {max_retries} attempts: {e}")
                return False

    return False


def poll_loop(config: dict) -> None:
    """Run poll_all_feeds on schedule forever."""
    poll_seconds = config.get("poll_seconds", 45)

    if poll_seconds < 45:
        logger.warning(f"poll_seconds {poll_seconds} < 45; using 45")
        poll_seconds = 45

    logger.info(f"Starting poll loop every {poll_seconds} seconds")

    while True:
        try:
            poll_with_retry(config)
            time.sleep(poll_seconds)
        except KeyboardInterrupt:
            logger.info("Poll loop interrupted")
            break
        except Exception as e:
            logger.error(f"Unexpected error in poll loop: {e}")
            time.sleep(poll_seconds)


if __name__ == "__main__":
    # Set up logging to print one line per poll
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = load_config()
    initialize_db()
    poll_loop(config)
