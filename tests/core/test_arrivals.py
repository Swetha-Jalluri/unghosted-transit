"""Tests for core.arrivals module."""
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from core import arrivals, database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database.initialize_db(db_path)
        yield db_path


def test_compute_eta_error_on_time():
    """Test compute_eta_error when vehicle arrives on time."""
    pred_ts = 1700000000  # Prediction timestamp
    pred_eta_min = 5.0    # Predicted 5 minutes
    actual_ts = 1700000300  # Actual arrival: 300 seconds = 5 minutes later

    error = arrivals.compute_eta_error(pred_ts, pred_eta_min, actual_ts)

    # Error should be 0 (on time)
    assert abs(error) < 0.01


def test_compute_eta_error_late():
    """Test compute_eta_error when vehicle arrives late."""
    pred_ts = 1700000000
    pred_eta_min = 5.0
    actual_ts = 1700000420  # 420 seconds = 7 minutes later (2 minutes late)

    error = arrivals.compute_eta_error(pred_ts, pred_eta_min, actual_ts)

    # Error should be ~2 minutes
    assert abs(error - 2.0) < 0.01


def test_compute_eta_error_early():
    """Test compute_eta_error when vehicle arrives early."""
    pred_ts = 1700000000
    pred_eta_min = 5.0
    actual_ts = 1700000180  # 180 seconds = 3 minutes later (2 minutes early)

    error = arrivals.compute_eta_error(pred_ts, pred_eta_min, actual_ts)

    # Error should be ~-2 minutes
    assert abs(error - (-2.0)) < 0.01


def test_compute_eta_error_fractional_minutes():
    """Test compute_eta_error with fractional minute predictions."""
    pred_ts = 1700000000
    pred_eta_min = 2.5   # 2.5 minutes = 150 seconds
    actual_ts = 1700000210  # 210 seconds later (1 minute late)

    error = arrivals.compute_eta_error(pred_ts, pred_eta_min, actual_ts)

    # Error should be ~1 minute
    assert abs(error - 1.0) < 0.01


def test_record_arrivals_empty_database(temp_db):
    """Test record_arrivals with empty database."""
    db = database.get_connection(temp_db)

    count = arrivals.record_arrivals(db)

    # Should record 0 arrivals (no SERVED labels)
    assert count == 0

    db.close()


def test_record_arrivals_single_served_label(temp_db):
    """Test record_arrivals with a single SERVED label."""
    db = database.get_connection(temp_db)
    cursor = db.cursor()

    ts = int(time.time())
    trip_id = "trip_123"
    stop_id = "stop_1"

    # Insert prediction
    cursor.execute(
        """
        INSERT INTO pred_snap
        (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
         schedule_relationship, revenue, headsign, stop_sequence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts,
            stop_id,
            "23",
            trip_id,
            5.0,  # 5 minute ETA
            10,
            None,
            1,
            "Downtown",
            5,
        ),
    )

    # Insert vehicle record (vehicle reached the stop)
    cursor.execute(
        """
        INSERT INTO veh_snap
        (ts, trip_id, route_id, stop_sequence, current_status, vehicle_timestamp, vehicle_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts + 400,  # Vehicle update after prediction
            trip_id,
            "23",
            5,  # Reached stop sequence 5
            "STOPPED_AT",
            ts + 300,  # Vehicle timestamp: 300 seconds later (on time)
            "v1",
        ),
    )

    # Insert SERVED label
    cursor.execute(
        """
        INSERT INTO labels (trip_id, stop_id, label, ts_labeled)
        VALUES (?, ?, ?, ?)
        """,
        (trip_id, stop_id, "SERVED", int(time.time())),
    )

    db.commit()

    # Record arrivals
    count = arrivals.record_arrivals(db)

    # Should record 1 arrival
    assert count == 1

    # Verify arrival record
    cursor.execute(
        """
        SELECT actual_arrival_ts, predicted_arrival_ts, eta_error_min
        FROM arrivals
        WHERE trip_id = ? AND stop_id = ?
        """,
        (trip_id, stop_id),
    )

    row = cursor.fetchone()
    assert row is not None

    actual_ts, predicted_ts, eta_error = row

    # Actual should be vehicle_timestamp (ts + 300)
    assert actual_ts == ts + 300

    # Predicted should be pred_ts + pred_eta_min in seconds (ts + 300)
    assert predicted_ts == ts + 300

    # Error should be ~0 (on time)
    assert abs(eta_error) < 0.01

    db.close()


def test_record_arrivals_late_arrival(temp_db):
    """Test record_arrivals with a late arrival."""
    db = database.get_connection(temp_db)
    cursor = db.cursor()

    ts = int(time.time())
    trip_id = "trip_456"
    stop_id = "stop_2"

    # Insert prediction
    cursor.execute(
        """
        INSERT INTO pred_snap
        (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
         schedule_relationship, revenue, headsign, stop_sequence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts,
            stop_id,
            "1",
            trip_id,
            5.0,  # Predicted 5 minutes
            10,
            None,
            1,
            "Dudley",
            10,
        ),
    )

    # Insert vehicle record (vehicle arrived late)
    cursor.execute(
        """
        INSERT INTO veh_snap
        (ts, trip_id, route_id, stop_sequence, current_status, vehicle_timestamp, vehicle_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts + 700,
            trip_id,
            "1",
            10,  # Reached stop
            "STOPPED_AT",
            ts + 600,  # Actual: 600 seconds later (10 minutes, 5 minutes late)
            "v2",
        ),
    )

    # Insert SERVED label
    cursor.execute(
        """
        INSERT INTO labels (trip_id, stop_id, label, ts_labeled)
        VALUES (?, ?, ?, ?)
        """,
        (trip_id, stop_id, "SERVED", int(time.time())),
    )

    db.commit()

    # Record arrivals
    count = arrivals.record_arrivals(db)

    assert count == 1

    # Verify arrival record
    cursor.execute(
        """
        SELECT eta_error_min
        FROM arrivals
        WHERE trip_id = ? AND stop_id = ?
        """,
        (trip_id, stop_id),
    )

    row = cursor.fetchone()
    eta_error = row[0]

    # Error should be ~5 minutes (late)
    assert abs(eta_error - 5.0) < 0.1

    db.close()


def test_record_arrivals_multiple_served_labels(temp_db):
    """Test record_arrivals with multiple SERVED labels."""
    db = database.get_connection(temp_db)
    cursor = db.cursor()

    ts = int(time.time())

    # Insert multiple predictions and vehicles
    for i in range(3):
        trip_id = f"trip_{i}"
        stop_id = f"stop_{i}"

        # Prediction
        cursor.execute(
            """
            INSERT INTO pred_snap
            (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
             schedule_relationship, revenue, headsign, stop_sequence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts + i * 100,
                stop_id,
                "23",
                trip_id,
                5.0,
                10,
                None,
                1,
                "Downtown",
                i + 1,
            ),
        )

        # Vehicle
        cursor.execute(
            """
            INSERT INTO veh_snap
            (ts, trip_id, route_id, stop_sequence, current_status, vehicle_timestamp, vehicle_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts + i * 100 + 400,
                trip_id,
                "23",
                i + 1,
                "STOPPED_AT",
                ts + i * 100 + 300,
                f"v{i}",
            ),
        )

        # SERVED label
        cursor.execute(
            """
            INSERT INTO labels (trip_id, stop_id, label, ts_labeled)
            VALUES (?, ?, ?, ?)
            """,
            (trip_id, stop_id, "SERVED", int(time.time())),
        )

    db.commit()

    # Record arrivals
    count = arrivals.record_arrivals(db)

    # Should record 3 arrivals
    assert count == 3

    # Verify all arrivals recorded
    cursor.execute("SELECT COUNT(*) FROM arrivals")
    assert cursor.fetchone()[0] == 3

    db.close()


def test_record_arrivals_skips_non_served_labels(temp_db):
    """Test that record_arrivals skips non-SERVED labels."""
    db = database.get_connection(temp_db)
    cursor = db.cursor()

    ts = int(time.time())

    # Insert SERVED label with vehicle record
    trip_id = "trip_SERVED"
    stop_id = "stop_SERVED"

    cursor.execute(
        """
        INSERT INTO pred_snap
        (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
         schedule_relationship, revenue, headsign, stop_sequence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, stop_id, "23", trip_id, 5.0, 10, None, 1, "Downtown", 5),
    )

    cursor.execute(
        """
        INSERT INTO veh_snap
        (ts, trip_id, route_id, stop_sequence, current_status, vehicle_timestamp, vehicle_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ts + 400, trip_id, "23", 5, "STOPPED_AT", ts + 300, "v1"),
    )

    cursor.execute(
        """
        INSERT INTO labels (trip_id, stop_id, label, ts_labeled)
        VALUES (?, ?, ?, ?)
        """,
        (trip_id, stop_id, "SERVED", int(time.time())),
    )

    # Insert non-SERVED labels (no vehicle records needed)
    for label_type in ["VANISHED", "CANCELED", "OPEN"]:
        trip_id = f"trip_{label_type}"
        stop_id = f"stop_{label_type}"

        cursor.execute(
            """
            INSERT INTO pred_snap
            (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
             schedule_relationship, revenue, headsign, stop_sequence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, stop_id, "23", trip_id, 5.0, 10, None, 1, "Downtown", 5),
        )

        cursor.execute(
            """
            INSERT INTO labels (trip_id, stop_id, label, ts_labeled)
            VALUES (?, ?, ?, ?)
            """,
            (trip_id, stop_id, label_type, int(time.time())),
        )

    db.commit()

    # Record arrivals
    count = arrivals.record_arrivals(db)

    # Should only record 1 arrival (SERVED only)
    assert count == 1

    db.close()


def test_record_arrivals_idempotent(temp_db):
    """Test that record_arrivals is idempotent."""
    db = database.get_connection(temp_db)
    cursor = db.cursor()

    ts = int(time.time())
    trip_id = "trip_123"
    stop_id = "stop_1"

    # Setup prediction, vehicle, and label
    cursor.execute(
        """
        INSERT INTO pred_snap
        (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
         schedule_relationship, revenue, headsign, stop_sequence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, stop_id, "23", trip_id, 5.0, 10, None, 1, "Downtown", 5),
    )

    cursor.execute(
        """
        INSERT INTO veh_snap
        (ts, trip_id, route_id, stop_sequence, current_status, vehicle_timestamp, vehicle_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ts + 400, trip_id, "23", 5, "STOPPED_AT", ts + 300, "v1"),
    )

    cursor.execute(
        """
        INSERT INTO labels (trip_id, stop_id, label, ts_labeled)
        VALUES (?, ?, ?, ?)
        """,
        (trip_id, stop_id, "SERVED", int(time.time())),
    )

    db.commit()

    # First call to record_arrivals
    count1 = arrivals.record_arrivals(db)
    assert count1 == 1

    # Second call to record_arrivals (should not record again)
    count2 = arrivals.record_arrivals(db)
    assert count2 == 0

    # Verify only one arrival record exists
    cursor.execute("SELECT COUNT(*) FROM arrivals WHERE trip_id = ? AND stop_id = ?", (trip_id, stop_id))
    assert cursor.fetchone()[0] == 1

    db.close()


def test_record_arrivals_uses_vehicle_timestamp_when_available(temp_db):
    """Test that record_arrivals prefers vehicle_timestamp over veh_snap ts."""
    db = database.get_connection(temp_db)
    cursor = db.cursor()

    ts = int(time.time())
    trip_id = "trip_789"
    stop_id = "stop_3"

    # Insert prediction
    cursor.execute(
        """
        INSERT INTO pred_snap
        (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
         schedule_relationship, revenue, headsign, stop_sequence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, stop_id, "23", trip_id, 5.0, 10, None, 1, "Downtown", 5),
    )

    # Insert vehicle with vehicle_timestamp different from ts
    cursor.execute(
        """
        INSERT INTO veh_snap
        (ts, trip_id, route_id, stop_sequence, current_status, vehicle_timestamp, vehicle_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts + 500,  # veh_snap ts
            trip_id,
            "23",
            5,
            "STOPPED_AT",
            ts + 250,  # vehicle_timestamp (different from ts)
            "v1",
        ),
    )

    # Insert SERVED label
    cursor.execute(
        """
        INSERT INTO labels (trip_id, stop_id, label, ts_labeled)
        VALUES (?, ?, ?, ?)
        """,
        (trip_id, stop_id, "SERVED", int(time.time())),
    )

    db.commit()

    # Record arrivals
    arrivals.record_arrivals(db)

    # Verify actual_arrival_ts uses vehicle_timestamp, not veh_snap ts
    cursor.execute(
        """
        SELECT actual_arrival_ts
        FROM arrivals
        WHERE trip_id = ? AND stop_id = ?
        """,
        (trip_id, stop_id),
    )

    row = cursor.fetchone()
    actual_ts = row[0]

    # Should use vehicle_timestamp (ts + 250)
    assert actual_ts == ts + 250

    db.close()
