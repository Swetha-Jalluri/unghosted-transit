"""Database initialization and schema management."""
import sqlite3
from pathlib import Path


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Get a database connection."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db(db_path: str | Path) -> None:
    """Initialize database schema for raw feeds."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # pred_snap: bus predictions/trip updates (append-only, one row per poll per prediction)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pred_snap (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            stop_id TEXT NOT NULL,
            route_id TEXT NOT NULL,
            trip_id TEXT NOT NULL,
            app_eta_min REAL NOT NULL,
            uncertainty INTEGER,
            schedule_relationship TEXT,
            revenue INTEGER,
            headsign TEXT,
            stop_sequence INTEGER
        )
    """)

    # veh_snap: vehicle positions (append-only, one row per poll per vehicle)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS veh_snap (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            trip_id TEXT NOT NULL,
            route_id TEXT NOT NULL,
            stop_sequence INTEGER,
            current_status TEXT,
            vehicle_timestamp INTEGER,
            vehicle_id TEXT
        )
    """)

    # dock_snap: bike dock status (append-only, one row per poll per dock)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dock_snap (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            station_id TEXT NOT NULL,
            app_bikes INTEGER,
            num_docks_available INTEGER,
            is_renting INTEGER,
            is_installed INTEGER,
            last_reported INTEGER
        )
    """)

    # poll_log: collection cycle metadata
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS poll_log (
            ts INTEGER PRIMARY KEY,
            success INTEGER,
            n_pred INTEGER,
            n_veh INTEGER,
            n_dock INTEGER,
            data_age_trip_updates INTEGER,
            data_age_vehicle_positions INTEGER,
            data_age_docks INTEGER
        )
    """)

    # labels: ground truth outcomes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            trip_id TEXT NOT NULL,
            stop_id TEXT NOT NULL,
            label TEXT NOT NULL,
            ts_labeled INTEGER,
            PRIMARY KEY (trip_id, stop_id)
        )
    """)

    # arrivals: observed arrival times and ETA errors for SERVED labels
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS arrivals (
            trip_id TEXT NOT NULL,
            stop_id TEXT NOT NULL,
            actual_arrival_ts INTEGER,
            predicted_arrival_ts INTEGER,
            eta_error_min REAL,
            ts_recorded INTEGER,
            PRIMARY KEY (trip_id, stop_id),
            FOREIGN KEY (trip_id, stop_id) REFERENCES labels(trip_id, stop_id)
        )
    """)

    conn.commit()
    conn.close()


def clear_db(db_path: str | Path) -> None:
    """Clear all tables from database."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    for table in ["pred_snap", "veh_snap", "dock_snap", "poll_log", "labels", "arrivals"]:
        cursor.execute(f"DELETE FROM {table}")

    conn.commit()
    conn.close()
