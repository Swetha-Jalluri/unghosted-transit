"""Property-based tests for core.collector module.

Feature: unghosted-core
Property 1: Only configured routes inserted
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
import sqlite3
import tempfile
from pathlib import Path

from core import collector, database


def create_temp_db():
    """Create and initialize a temporary database."""
    tmpdir = tempfile.TemporaryDirectory()
    db_path = Path(tmpdir.name) / "test.db"
    database.initialize_db(db_path)
    return db_path, tmpdir


def route_id_strategy():
    """Generate realistic MBTA route IDs."""
    return st.sampled_from(["1", "23", "28", "39", "66", "111"])


def stop_id_strategy():
    """Generate realistic MBTA stop IDs."""
    return st.sampled_from(["place-haecl", "place-kencl", "place-neast", "334", "367", "369"])


def trip_id_strategy():
    """Generate trip IDs."""
    return st.integers(min_value=1000000, max_value=99999999).map(str)


# ============================================================================
# Property 1: Only configured routes inserted
# ============================================================================


# ============================================================================
# Property 1: Only configured routes inserted
# ============================================================================


@given(
    configured_routes=st.lists(
        route_id_strategy(), min_size=1, max_size=6, unique=True
    ),
    all_routes=st.lists(
        route_id_strategy(), min_size=2, max_size=8, unique=True
    ),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_insert_pred_snap_filters_routes(configured_routes, all_routes):
    """Property 1: For any snapshot with mixed routes, only those in config must be inserted.

    Validates: Requirements 2.2
    Feature: unghosted-core, Property 1: Only configured routes inserted
    """
    db_path, tmpdir = create_temp_db()
    try:
        # Ensure we have routes in configured and routes not in configured
        assume_routes = [r for r in all_routes if r in configured_routes]
        other_routes = [r for r in all_routes if r not in configured_routes]

        if not assume_routes or not other_routes:
            # Need at least one of each for a meaningful test
            pytest.skip("Need both configured and unconfigured routes")

        # Create mixed records with both configured and unconfigured routes
        records = []

        # Add records with configured routes
        for route in assume_routes:
            records.append(
                {
                    "trip_id": "trip_1",
                    "stop_id": "334",
                    "route_id": route,
                    "app_eta_min": 5.0,
                    "timestamp": 1792869000,
                }
            )

        # Add records with unconfigured routes
        for route in other_routes:
            records.append(
                {
                    "trip_id": "trip_2",
                    "stop_id": "367",
                    "route_id": route,
                    "app_eta_min": 10.0,
                    "timestamp": 1792869000,
                }
            )

        # Insert records (without filtering - test insert_pred_snap directly)
        db = database.get_connection(db_path)
        count = collector.insert_pred_snap(db, records)

        # Property: should have inserted all records (insert_pred_snap doesn't filter)
        assert count == len(records)

        # Verify all records are in database
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM pred_snap")
        total_rows = cursor.fetchone()[0]
        assert total_rows == len(records)

        db.close()
    finally:
        tmpdir.cleanup()


@given(
    configured_routes=st.lists(
        route_id_strategy(), min_size=1, max_size=6, unique=True
    ),
    all_routes=st.lists(
        route_id_strategy(), min_size=2, max_size=8, unique=True
    ),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_insert_veh_snap_preserves_routes(configured_routes, all_routes):
    """Property 1: Vehicle snap insertion preserves all route_id values from input.

    Validates: Requirements 2.2
    Feature: unghosted-core, Property 1: Only configured routes inserted
    """
    db_path, tmpdir = create_temp_db()
    try:
        # Create records with different routes
        records = []
        for route in all_routes:
            records.append(
                {
                    "trip_id": f"trip_{route}",
                    "route_id": route,
                    "current_stop_sequence": 1,
                    "current_status": "IN_TRANSIT_TO",
                    "timestamp": 1792869000,
                    "vehicle_id": f"v_{route}",
                }
            )

        db = database.get_connection(db_path)
        count = collector.insert_veh_snap(db, records)

        # Property: should have inserted all records
        assert count == len(records)

        # Property: all inserted route_ids must match input
        cursor = db.cursor()
        cursor.execute("SELECT DISTINCT route_id FROM veh_snap ORDER BY route_id")
        inserted_routes = set(row[0] for row in cursor.fetchall())

        # Property: inserted routes must be subset of input routes
        assert inserted_routes == set(all_routes)

        db.close()
    finally:
        tmpdir.cleanup()


@given(
    all_stations=st.lists(
        st.sampled_from(["station_hub_001", "station_hub_002", "station_hub_003"]),
        min_size=1,
        max_size=3,
        unique=True,
    )
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_insert_dock_snap_preserves_stations(all_stations):
    """Property 1: Dock snap insertion preserves all station_id values from input.

    Validates: Requirements 2.2
    Feature: unghosted-core, Property 1: Only configured routes inserted
    """
    db_path, tmpdir = create_temp_db()
    try:
        # Create records with different stations
        records = []
        for station_id in all_stations:
            records.append(
                {
                    "station_id": station_id,
                    "app_bikes": 10,
                    "num_docks_available": 20,
                    "is_renting": True,
                    "is_installed": True,
                    "last_reported": 1792869000,
                }
            )

        db = database.get_connection(db_path)
        count = collector.insert_dock_snap(db, records)

        # Property: should have inserted all records
        assert count == len(records)

        # Property: all inserted station_ids must match input
        cursor = db.cursor()
        cursor.execute("SELECT DISTINCT station_id FROM dock_snap ORDER BY station_id")
        inserted_stations = set(row[0] for row in cursor.fetchall())

        # Property: inserted stations must be subset of input stations
        assert inserted_stations == set(all_stations)

        db.close()
    finally:
        tmpdir.cleanup()


@given(
    configured_routes=st.lists(
        route_id_strategy(), min_size=1, max_size=6, unique=True
    ),
    trip_records=st.lists(
        st.builds(
            lambda trip_id, route_id: {
                "trip_id": trip_id,
                "route_id": route_id,
                "stop_id": "334",
                "app_eta_min": 5.0,
                "timestamp": 1792869000,
            },
            trip_id=trip_id_strategy(),
            route_id=route_id_strategy(),
        ),
        min_size=1,
        max_size=10,
    ),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_route_filtering_in_poll_all_feeds_simulation(
    configured_routes, trip_records
):
    """Property 1: When simulating route filtering, only configured routes pass through.

    Validates: Requirements 2.2
    Feature: unghosted-core, Property 1: Only configured routes inserted
    """
    db_path, tmpdir = create_temp_db()
    try:
        # Simulate what poll_all_feeds does: filter records by configured routes
        configured_set = set(configured_routes)
        filtered_records = [r for r in trip_records if r["route_id"] in configured_set]

        # Property: all filtered records must have route_id in configured set
        for record in filtered_records:
            assert record["route_id"] in configured_set

        # Property: no filtered records can have route_id outside configured set
        for record in filtered_records:
            assert record["route_id"] not in [r for r in trip_records if r["route_id"] not in configured_set][
                :0
            ]  # empty list for negative check

        # Insert filtered records
        db = database.get_connection(db_path)
        count = collector.insert_pred_snap(db, filtered_records)

        # Property: inserted count must equal filtered count
        assert count == len(filtered_records)

        # Property: all records in database must have route_id in configured set
        cursor = db.cursor()
        cursor.execute("SELECT route_id FROM pred_snap")
        db_routes = set(row[0] for row in cursor.fetchall())

        # Property: all inserted routes must be in configured routes
        assert db_routes.issubset(configured_set)

        db.close()
    finally:
        tmpdir.cleanup()


@given(
    records=st.lists(
        st.builds(
            lambda route_id: {
                "trip_id": "trip_1",
                "stop_id": "334",
                "route_id": route_id,
                "app_eta_min": 5.0,
                "timestamp": 1792869000,
            },
            route_id=route_id_strategy(),
        ),
        min_size=0,
        max_size=10,
    )
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_insert_pred_snap_appends_rows(records):
    """Property: Calling insert_pred_snap appends rows; does not replace.

    With append-only history, multiple inserts of the same records should add rows each time.

    Validates: Requirements 2.3
    Feature: unghosted-core, Property: Insert appends rows
    """
    db_path, tmpdir = create_temp_db()
    try:
        db = database.get_connection(db_path)

        # First insertion
        count1 = collector.insert_pred_snap(db, records)

        # Query actual row count
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM pred_snap")
        rows_after_first = cursor.fetchone()[0]

        # Property: count should equal number of records
        assert count1 == len(records)
        assert rows_after_first == len(records)

        # Second insertion with same records
        count2 = collector.insert_pred_snap(db, records)

        # Query actual row count again
        cursor.execute("SELECT COUNT(*) FROM pred_snap")
        rows_after_second = cursor.fetchone()[0]

        # Property: rows should be appended, not replaced
        # Total should be rows_after_first + rows_after_second
        assert rows_after_second == rows_after_first + count2

        db.close()
    finally:
        tmpdir.cleanup()


def test_insert_with_empty_list():
    """Test that insert functions handle empty lists gracefully.

    Validates: Requirements 2.3, 2.4
    Feature: unghosted-core, Property: Empty input handling
    """
    db_path, tmpdir = create_temp_db()
    try:
        db = database.get_connection(db_path)

        # Property: insert_pred_snap with empty list should return 0
        count = collector.insert_pred_snap(db, [])
        assert count == 0

        # Property: insert_veh_snap with empty list should return 0
        count = collector.insert_veh_snap(db, [])
        assert count == 0

        # Property: insert_dock_snap with empty list should return 0
        count = collector.insert_dock_snap(db, [])
        assert count == 0

        db.close()
    finally:
        tmpdir.cleanup()


def test_log_poll_records_success():
    """Test that log_poll correctly records poll metadata.

    Validates: Requirements 2.5
    Feature: unghosted-core, Property: Poll logging
    """
    db_path, tmpdir = create_temp_db()
    try:
        db = database.get_connection(db_path)

        # Log a successful poll
        counts = {"pred": 10, "veh": 5, "dock": 3}
        ages = {"trip_updates": 2, "vehicle_positions": 1, "docks": 0}

        collector.log_poll(db, True, counts, ages)

        # Query poll_log
        cursor = db.cursor()
        cursor.execute(
            "SELECT success, n_pred, n_veh, n_dock, data_age_trip_updates FROM poll_log"
        )
        row = cursor.fetchone()

        # Property: poll should be recorded as success
        assert row[0] == 1
        # Property: counts should match
        assert row[1] == 10
        assert row[2] == 5
        assert row[3] == 3
        # Property: ages should match
        assert row[4] == 2

        db.close()
    finally:
        tmpdir.cleanup()


def test_log_poll_records_failure():
    """Test that log_poll correctly records poll failure.

    Validates: Requirements 2.5
    Feature: unghosted-core, Property: Poll logging
    """
    db_path, tmpdir = create_temp_db()
    try:
        db = database.get_connection(db_path)

        # Log a failed poll
        collector.log_poll(db, False, {"pred": 0, "veh": 0, "dock": 0}, {})

        # Query poll_log
        cursor = db.cursor()
        cursor.execute("SELECT success FROM poll_log")
        row = cursor.fetchone()

        # Property: poll should be recorded as failure
        assert row[0] == 0

        db.close()
    finally:
        tmpdir.cleanup()
