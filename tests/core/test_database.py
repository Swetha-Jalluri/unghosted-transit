"""Tests for database schema initialization."""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.database import initialize_db, get_connection, clear_db


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


def test_initialize_db_creates_tables(temp_db):
    """Test that initialize_db creates all required tables."""
    initialize_db(temp_db)

    conn = get_connection(temp_db)
    cursor = conn.cursor()

    # Query sqlite_master for table names (excluding sqlite_sequence)
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()

    expected_tables = ["dock_snap", "labels", "poll_log", "pred_snap", "veh_snap"]
    assert set(tables) == set(expected_tables)


def test_pred_snap_schema(temp_db):
    """Test pred_snap table has correct columns."""
    initialize_db(temp_db)

    conn = get_connection(temp_db)
    cursor = conn.cursor()

    # Get column info for pred_snap
    cursor.execute("PRAGMA table_info(pred_snap)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    conn.close()

    expected_columns = {
        "ts": "INTEGER",
        "stop_id": "TEXT",
        "route_id": "TEXT",
        "trip_id": "TEXT",
        "app_eta_min": "REAL",
        "uncertainty": "INTEGER",
        "schedule_relationship": "TEXT",
        "revenue": "INTEGER",
        "headsign": "TEXT",
    }

    for col, col_type in expected_columns.items():
        assert col in columns, f"Missing column {col}"
        assert columns[col] == col_type


def test_veh_snap_schema(temp_db):
    """Test veh_snap table has correct columns."""
    initialize_db(temp_db)

    conn = get_connection(temp_db)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(veh_snap)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    conn.close()

    expected_columns = {
        "ts": "INTEGER",
        "trip_id": "TEXT",
        "route_id": "TEXT",
        "stop_sequence": "INTEGER",
        "current_status": "TEXT",
        "vehicle_timestamp": "INTEGER",
        "vehicle_id": "TEXT",
    }

    for col, col_type in expected_columns.items():
        assert col in columns, f"Missing column {col}"
        assert columns[col] == col_type


def test_dock_snap_schema(temp_db):
    """Test dock_snap table has correct columns."""
    initialize_db(temp_db)

    conn = get_connection(temp_db)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(dock_snap)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    conn.close()

    expected_columns = {
        "ts": "INTEGER",
        "station_id": "TEXT",
        "app_bikes": "INTEGER",
        "num_docks_available": "INTEGER",
        "is_renting": "INTEGER",
        "is_installed": "INTEGER",
        "last_reported": "INTEGER",
    }

    for col, col_type in expected_columns.items():
        assert col in columns, f"Missing column {col}"
        assert columns[col] == col_type


def test_poll_log_schema(temp_db):
    """Test poll_log table has correct columns."""
    initialize_db(temp_db)

    conn = get_connection(temp_db)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(poll_log)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    conn.close()

    expected_columns = {
        "ts": "INTEGER",
        "success": "INTEGER",
        "n_pred": "INTEGER",
        "n_veh": "INTEGER",
        "n_dock": "INTEGER",
        "data_age_trip_updates": "INTEGER",
        "data_age_vehicle_positions": "INTEGER",
        "data_age_docks": "INTEGER",
    }

    for col, col_type in expected_columns.items():
        assert col in columns, f"Missing column {col}"
        assert columns[col] == col_type


def test_labels_schema(temp_db):
    """Test labels table has correct columns."""
    initialize_db(temp_db)

    conn = get_connection(temp_db)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(labels)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    conn.close()

    expected_columns = {
        "trip_id": "TEXT",
        "stop_id": "TEXT",
        "label": "TEXT",
        "ts_labeled": "INTEGER",
    }

    for col, col_type in expected_columns.items():
        assert col in columns, f"Missing column {col}"
        assert columns[col] == col_type


def test_clear_db(temp_db):
    """Test that clear_db removes all data but keeps schema."""
    initialize_db(temp_db)

    conn = get_connection(temp_db)
    cursor = conn.cursor()

    # Insert test data
    cursor.execute(
        "INSERT INTO pred_snap (ts, stop_id, route_id, trip_id, app_eta_min) VALUES (?, ?, ?, ?, ?)",
        (1705347300, "70036", "1", "trip_1", 5.0),
    )
    conn.commit()

    # Verify data exists
    cursor.execute("SELECT COUNT(*) FROM pred_snap")
    assert cursor.fetchone()[0] == 1

    conn.close()

    # Clear database
    clear_db(temp_db)

    # Verify data is gone but table exists
    conn = get_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pred_snap")
    assert cursor.fetchone()[0] == 0

    # Verify tables still exist
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "pred_snap" in tables

    conn.close()


def test_fixtures_exist():
    """Test that required fixture files exist and are valid JSON."""
    fixtures_dir = Path("tests/fixtures")

    # Check trip updates fixture
    trip_updates_file = fixtures_dir / "trip_updates.json"
    assert trip_updates_file.exists(), "trip_updates.json not found"
    with open(trip_updates_file) as f:
        trip_updates = json.load(f)
    assert "entity" in trip_updates
    assert "header" in trip_updates
    assert len(trip_updates["entity"]) > 0

    # Check vehicle positions fixture
    vehicle_positions_file = fixtures_dir / "vehicle_positions.json"
    assert vehicle_positions_file.exists(), "vehicle_positions.json not found"
    with open(vehicle_positions_file) as f:
        vehicle_positions = json.load(f)
    assert "entity" in vehicle_positions
    assert "header" in vehicle_positions
    assert len(vehicle_positions["entity"]) > 0

    # Check station information fixture
    station_info_file = fixtures_dir / "station_information.json"
    assert station_info_file.exists(), "station_information.json not found"
    with open(station_info_file) as f:
        station_info = json.load(f)
    assert "data" in station_info
    assert "stations" in station_info["data"]
    assert len(station_info["data"]["stations"]) > 0

    # Check station status fixture
    station_status_file = fixtures_dir / "station_status.json"
    assert station_status_file.exists(), "station_status.json not found"
    with open(station_status_file) as f:
        station_status = json.load(f)
    assert "data" in station_status
    assert "stations" in station_status["data"]
    assert len(station_status["data"]["stations"]) > 0


def test_trip_updates_structure():
    """Test that trip_updates.json has correct GTFS-rt structure."""
    with open("tests/fixtures/trip_updates.json") as f:
        data = json.load(f)

    # Check header
    assert data["header"]["gtfs_realtime_version"] == "2.0"
    assert data["header"]["incrementality"] == "FULL_DATASET"

    # Check entities
    for entity in data["entity"]:
        assert "id" in entity
        assert "trip_update" in entity
        trip_update = entity["trip_update"]

        # Check trip fields
        assert "trip" in trip_update
        trip = trip_update["trip"]
        assert "trip_id" in trip
        assert "route_id" in trip

        # Check stop_time_updates
        assert "stop_time_update" in trip_update
        assert len(trip_update["stop_time_update"]) > 0

        for stop_update in trip_update["stop_time_update"]:
            assert "stop_id" in stop_update
            assert "stop_sequence" in stop_update


def test_vehicle_positions_structure():
    """Test that vehicle_positions.json has correct GTFS-rt structure."""
    with open("tests/fixtures/vehicle_positions.json") as f:
        data = json.load(f)

    # Check header
    assert data["header"]["gtfs_realtime_version"] == "2.0"

    # Check entities
    for entity in data["entity"]:
        assert "id" in entity
        assert "vehicle" in entity
        vehicle = entity["vehicle"]

        # Check required fields
        assert "trip" in vehicle
        assert "vehicle" in vehicle
        assert "position" in vehicle
        assert "current_stop_sequence" in vehicle
        assert "stop_id" in vehicle
        assert "current_status" in vehicle
        assert "timestamp" in vehicle


def test_stations_structure():
    """Test that station_information.json and station_status.json have correct GBFS structure."""
    # Check station information
    with open("tests/fixtures/station_information.json") as f:
        station_info = json.load(f)

    assert "data" in station_info
    assert "stations" in station_info["data"]
    stations_info = station_info["data"]["stations"]
    assert len(stations_info) > 0

    for station in stations_info:
        assert "station_id" in station
        assert "name" in station
        assert "lat" in station
        assert "lon" in station

    # Check station status
    with open("tests/fixtures/station_status.json") as f:
        station_status = json.load(f)

    assert "data" in station_status
    assert "stations" in station_status["data"]
    stations_status = station_status["data"]["stations"]
    assert len(stations_status) > 0

    for status in stations_status:
        assert "station_id" in status
        assert "num_bikes_available" in status
        assert "num_docks_available" in status
        assert "is_renting" in status
        assert "last_reported" in status
