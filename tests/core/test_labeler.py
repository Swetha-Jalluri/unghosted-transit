"""Property-based tests for core.labeler module.

Feature: unghosted-core
Property 8: One label per (trip_id, stop_id)
Property 2: CANCELED propagation
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
import sqlite3
import tempfile
import time
from pathlib import Path

from core import labeler, database


def create_temp_db():
    """Create and initialize a temporary database."""
    tmpdir = tempfile.TemporaryDirectory()
    db_path = Path(tmpdir.name) / "test.db"
    database.initialize_db(db_path)
    return db_path, tmpdir


def config_dict():
    """Return test configuration."""
    return {
        "thresholds": {
            "stale_location_s": 120,
            "vanish_margin_s": 120,
            "dock_stale_s": 300,
            "unreliable_vanish_rate": 0.25,
            "min_labels": 300,
            "min_vanished": 20,
            "drain_window_min": 20,
            "walk_m_per_min": 80,
        }
    }


def trip_id_strategy():
    """Generate trip IDs."""
    return st.integers(min_value=1000000, max_value=99999999).map(str)


def stop_id_strategy():
    """Generate realistic MBTA stop IDs."""
    return st.sampled_from(["place-haecl", "place-kencl", "place-neast", "334", "367", "369"])


def route_id_strategy():
    """Generate realistic MBTA route IDs."""
    return st.sampled_from(["1", "23", "28", "39", "66", "111"])


# ============================================================================
# Property 8: One label per (trip_id, stop_id)
# ============================================================================


@given(
    snapshots=st.lists(
        st.builds(
            lambda trip_id, stop_id, route_id, ts, seq: {
                "trip_id": trip_id,
                "stop_id": stop_id,
                "route_id": route_id,
                "ts": ts,
                "app_eta_min": 5.0,
                "uncertainty": 10,
                "schedule_relationship": None,
                "revenue": 1,
                "headsign": "Downtown",
                "stop_sequence": seq,
            },
            trip_id=trip_id_strategy(),
            stop_id=stop_id_strategy(),
            route_id=route_id_strategy(),
            ts=st.integers(min_value=1700000000, max_value=1700001000),
            seq=st.integers(min_value=1, max_value=50),
        ),
        min_size=1,
        max_size=20,
    )
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_one_label_per_trip_stop_pair(snapshots):
    """Property 8: For any set of snapshots, exactly one label per (trip_id, stop_id).

    Validates: Requirements 3.1, 3.5
    Feature: unghosted-core, Property 8: One label per (trip_id, stop_id)
    """
    db_path, tmpdir = create_temp_db()
    try:
        db = database.get_connection(db_path)
        config = config_dict()

        # Insert snapshots into pred_snap
        cursor = db.cursor()
        for snap in snapshots:
            cursor.execute(
                """
                INSERT INTO pred_snap
                (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
                 schedule_relationship, revenue, headsign, stop_sequence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap["ts"],
                    snap["stop_id"],
                    snap["route_id"],
                    snap["trip_id"],
                    snap["app_eta_min"],
                    snap["uncertainty"],
                    snap["schedule_relationship"],
                    snap["revenue"],
                    snap["headsign"],
                    snap["stop_sequence"],
                ),
            )
        db.commit()

        # Label predictions in a window
        start_ts = min(s["ts"] for s in snapshots)
        end_ts = max(s["ts"] for s in snapshots) + 600

        labeler.label_predictions(db, (start_ts, end_ts), config)

        # Property: Get all labeled (trip_id, stop_id) pairs
        cursor.execute(
            """
            SELECT trip_id, stop_id, COUNT(*) as count
            FROM labels
            GROUP BY trip_id, stop_id
            """
        )

        label_counts = cursor.fetchall()

        # Property: For each (trip_id, stop_id) pair, there must be exactly one label
        for trip_id, stop_id, count in label_counts:
            assert count == 1, f"Multiple labels for ({trip_id}, {stop_id}): count={count}"

        # Property: Number of unique (trip_id, stop_id) pairs should not exceed input snapshots
        unique_pairs_input = set(
            (s["trip_id"], s["stop_id"]) for s in snapshots
        )
        cursor.execute(
            """
            SELECT COUNT(*) FROM (SELECT DISTINCT trip_id, stop_id FROM labels)
            """
        )
        labeled_pairs_count = cursor.fetchone()[0]

        assert labeled_pairs_count <= len(unique_pairs_input)

        db.close()
    finally:
        tmpdir.cleanup()


@given(
    trip_snapshots=st.just("trip_123"),
    stop_snapshots=st.lists(
        st.sampled_from(["stop_1", "stop_2", "stop_3"]),
        min_size=1,
        max_size=5,
        unique=True,
    ),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_exactly_one_label_per_trip_stop_fixed(trip_snapshots, stop_snapshots):
    """Property 8: For a fixed trip, exactly one label per stop.

    Validates: Requirements 3.1, 3.5
    Feature: unghosted-core, Property 8: One label per (trip_id, stop_id)
    """
    db_path, tmpdir = create_temp_db()
    try:
        db = database.get_connection(db_path)
        config = config_dict()

        # Create snapshots for trip at multiple stops
        cursor = db.cursor()
        ts = int(time.time())

        for i, stop_id in enumerate(stop_snapshots):
            # First prediction
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
                    trip_snapshots,
                    5.0,
                    10,
                    None,
                    1,
                    "Downtown",
                    i + 1,
                ),
            )

            # Second prediction (should update to at most one label per (trip, stop))
            cursor.execute(
                """
                INSERT INTO pred_snap
                (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
                 schedule_relationship, revenue, headsign, stop_sequence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts + i * 100 + 50,
                    stop_id,
                    "23",
                    trip_snapshots,
                    4.0,
                    10,
                    None,
                    1,
                    "Downtown",
                    i + 1,
                ),
            )

        db.commit()

        # Label predictions
        labeler.label_predictions(db, (ts, ts + 10000), config)

        # Query labels for this trip
        cursor.execute(
            """
            SELECT stop_id, COUNT(*) as count
            FROM labels
            WHERE trip_id = ?
            GROUP BY stop_id
            """,
            (trip_snapshots,),
        )

        label_counts = cursor.fetchall()

        # Property: Each stop should have exactly one label
        for stop_id, count in label_counts:
            assert count == 1, f"Stop {stop_id} has {count} labels (expected 1)"

        # Property: Should have labeled all stops
        assert len(label_counts) == len(stop_snapshots)

        db.close()
    finally:
        tmpdir.cleanup()


# ============================================================================
# Property 2: CANCELED propagation
# ============================================================================


@given(
    trip_id=trip_id_strategy(),
    num_stops=st.integers(min_value=2, max_value=10),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_canceled_propagation_all_stops(trip_id, num_stops):
    """Property 2: If trip marked CANCELED, all stops must have label CANCELED.

    Validates: Requirements 3.1, 3.2
    Feature: unghosted-core, Property 2: CANCELED propagation
    """
    db_path, tmpdir = create_temp_db()
    try:
        db = database.get_connection(db_path)
        config = config_dict()

        cursor = db.cursor()
        ts = int(time.time())

        # Create predictions for multiple stops
        for i in range(num_stops):
            stop_id = f"stop_{i}"

            # Prediction with CANCELED schedule_relationship
            # This gets labeled as CANCELED by assign_label
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
                    "CANCELED",
                    1,
                    "Downtown",
                    i + 1,
                ),
            )

        db.commit()

        # Label predictions - they should all be CANCELED due to schedule_relationship
        labeler.label_predictions(db, (ts, ts + 10000), config)

        # Propagate canceled (shouldn't need to, but calling to be thorough)
        labeler.propagate_canceled(db, config)

        # Query all labels for this trip
        cursor.execute(
            """
            SELECT stop_id, label
            FROM labels
            WHERE trip_id = ?
            ORDER BY stop_id
            """,
            (trip_id,),
        )

        labels = cursor.fetchall()

        # Property: All labels for this trip must be CANCELED
        for stop_id, label in labels:
            assert label == "CANCELED", (
                f"Stop {stop_id} has label {label} (expected CANCELED)"
            )

        # Property: All stops should have been labeled
        assert len(labels) == num_stops, f"Expected {num_stops} labels, got {len(labels)}"

        db.close()
    finally:
        tmpdir.cleanup()


@given(
    num_stops=st.integers(min_value=1, max_value=5),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_canceled_propagation_across_trip_stops(num_stops):
    """Property 2: CANCELED label on any stop propagates to all stops of the trip.

    Validates: Requirements 3.2
    Feature: unghosted-core, Property 2: CANCELED propagation
    """
    db_path, tmpdir = create_temp_db()
    try:
        db = database.get_connection(db_path)
        config = config_dict()

        cursor = db.cursor()
        ts = int(time.time())
        trip_id = "trip_123"

        # Create snapshots: first with OPEN label, then mark one stop as CANCELED
        for i in range(num_stops):
            stop_id = f"stop_{i}"

            # Normal prediction
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
                    5.0,
                    10,
                    None,
                    1,
                    "Downtown",
                    i + 1,
                ),
            )

        db.commit()

        # Label predictions (should get mixed labels)
        labeler.label_predictions(db, (ts, ts + 600), config)

        # Manually create a CANCELED label for one stop to trigger propagation
        cursor.execute(
            """
            INSERT OR REPLACE INTO labels (trip_id, stop_id, label, ts_labeled)
            VALUES (?, ?, ?, ?)
            """,
            (trip_id, "stop_0", "CANCELED", ts),
        )
        db.commit()

        # Propagate canceled
        labeler.propagate_canceled(db, config)

        # Query all labels for this trip
        cursor.execute(
            """
            SELECT stop_id, label
            FROM labels
            WHERE trip_id = ?
            ORDER BY stop_id
            """,
            (trip_id,),
        )

        labels = cursor.fetchall()

        # Property: All labels for this trip must be CANCELED
        for stop_id, label in labels:
            assert label == "CANCELED", (
                f"Stop {stop_id} has label {label} after propagation (expected CANCELED)"
            )

        db.close()
    finally:
        tmpdir.cleanup()


# ============================================================================
# Helper property tests for assign_label logic
# ============================================================================


def test_assign_label_canceled_schedule():
    """Test that CANCELED schedule_relationship returns CANCELED label."""
    config = config_dict()
    pred = {
        "ts": 1700000000,
        "stop_id": "stop_1",
        "route_id": "23",
        "trip_id": "trip_1",
        "app_eta_min": 5.0,
        "uncertainty": 10,
        "schedule_relationship": "CANCELED",
        "revenue": True,
        "headsign": "Downtown",
        "stop_sequence": 5,
    }

    label = labeler.assign_label(pred, [], [], config)
    assert label == "CANCELED"


def test_assign_label_open_with_future_predictions():
    """Test that presence of future predictions returns OPEN label."""
    config = config_dict()
    pred = {
        "ts": 1700000000,
        "stop_id": "stop_1",
        "route_id": "23",
        "trip_id": "trip_1",
        "app_eta_min": 5.0,
        "uncertainty": 10,
        "schedule_relationship": None,
        "revenue": True,
        "headsign": "Downtown",
        "stop_sequence": 5,
    }

    # Future prediction exists
    pred_history = [
        {
            "ts": 1700000100,
            "stop_id": "stop_1",
            "route_id": "23",
            "trip_id": "trip_1",
            "app_eta_min": 4.0,
            "uncertainty": 10,
            "schedule_relationship": None,
            "revenue": True,
            "headsign": "Downtown",
            "stop_sequence": 5,
        }
    ]

    label = labeler.assign_label(pred, [], pred_history, config)
    assert label == "OPEN"


def test_assign_label_served_vehicle_reached():
    """Test that vehicle reaching stop returns SERVED label."""
    config = config_dict()
    pred = {
        "ts": 1700000000,
        "stop_id": "stop_1",
        "route_id": "23",
        "trip_id": "trip_1",
        "app_eta_min": 5.0,
        "uncertainty": 10,
        "schedule_relationship": None,
        "revenue": True,
        "headsign": "Downtown",
        "stop_sequence": 5,
    }

    # Vehicle reached stop 5
    veh_history = [
        {
            "ts": 1700000300,
            "trip_id": "trip_1",
            "route_id": "23",
            "stop_sequence": 5,
            "current_status": "STOPPED_AT",
            "vehicle_timestamp": 1700000300,
            "vehicle_id": "v1",
        }
    ]

    label = labeler.assign_label(pred, veh_history, [], config)
    assert label == "SERVED"


def test_assign_label_vanished():
    """Test that vehicle disappearance returns VANISHED label."""
    config = config_dict()
    pred = {
        "ts": 1700000000,
        "stop_id": "stop_1",
        "route_id": "23",
        "trip_id": "trip_1",
        "app_eta_min": 5.0,
        "uncertainty": 10,
        "schedule_relationship": None,
        "revenue": True,
        "headsign": "Downtown",
        "stop_sequence": 5,
    }

    # Vehicle seen before prediction arrival but disappeared
    # Prediction ETA: 1700000000 + 300 = 1700000300
    # Vehicle last seen at 1700000000 (before arrival)
    # Time since vehicle seen: 1700000300 - 1700000000 = 300 seconds > 120s threshold
    veh_history = [
        {
            "ts": 1700000000,
            "trip_id": "trip_1",
            "route_id": "23",
            "stop_sequence": 3,  # Not yet at stop 5
            "current_status": "IN_TRANSIT_TO",
            "vehicle_timestamp": 1700000000,
            "vehicle_id": "v1",
        }
    ]

    label = labeler.assign_label(pred, veh_history, [], config)
    assert label == "VANISHED"


def test_flicker_filter_suppresses_young_predictions():
    """Test that flicker filter suppresses labels for young predictions."""
    config = config_dict()
    ts = int(time.time())

    # Recent prediction (just 1 second old)
    pred_history = [
        {
            "ts": ts - 1,
            "stop_id": "stop_1",
            "route_id": "23",
            "trip_id": "trip_1",
            "app_eta_min": 5.0,
            "uncertainty": 10,
            "schedule_relationship": None,
            "revenue": True,
            "headsign": "Downtown",
            "stop_sequence": 5,
        }
    ]

    # Should suppress (flicker filter returns True)
    suppressed = labeler.flicker_filter(pred_history, ts, config)
    assert suppressed is True


def test_flicker_filter_allows_old_predictions():
    """Test that flicker filter allows labels for old predictions."""
    config = config_dict()
    ts = int(time.time())

    # Old prediction (200 seconds old, past its ETA)
    pred_history = [
        {
            "ts": ts - 500,
            "stop_id": "stop_1",
            "route_id": "23",
            "trip_id": "trip_1",
            "app_eta_min": 5.0,
            "uncertainty": 10,
            "schedule_relationship": None,
            "revenue": True,
            "headsign": "Downtown",
            "stop_sequence": 5,
        }
    ]

    # Should NOT suppress (flicker filter returns False)
    suppressed = labeler.flicker_filter(pred_history, ts, config)
    assert suppressed is False
