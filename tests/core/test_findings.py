"""Property-based tests for core.findings module.

Feature: unghosted-core
Property 1: Findings is_placeholder logic
"""
import sqlite3
import tempfile
import time
from pathlib import Path

from hypothesis import given, settings, HealthCheck, strategies as st

from core import database, findings, labeler


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


# ============================================================================
# Property 1: Findings is_placeholder logic
# ============================================================================


@given(
    num_labels=st.integers(min_value=0, max_value=500),
    is_placeholder_mode=st.booleans(),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None, max_examples=10)
def test_findings_is_placeholder_logic(num_labels, is_placeholder_mode):
    """Property 1: is_placeholder=true iff in demo or n_labels < min_labels.

    Validates: Requirements 5.7
    Feature: unghosted-core, Property 1: Findings is_placeholder logic
    """
    db_path, tmpdir = create_temp_db()
    try:
        db = database.get_connection(db_path)
        config = config_dict()
        min_labels = config["thresholds"]["min_labels"]

        cursor = db.cursor()
        ts = int(time.time())

        # Create labels
        for i in range(num_labels):
            trip_id = f"trip_{i}"
            stop_id = f"stop_{i % 5}"

            # Insert prediction
            cursor.execute(
                """
                INSERT INTO pred_snap
                (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
                 schedule_relationship, revenue, headsign, stop_sequence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts + i, stop_id, "23", trip_id, 5.0, 10, None, 1, "Downtown", i % 10),
            )

            # Assign label (mix of types for variety)
            label = ["SERVED", "VANISHED", "CANCELED", "OPEN"][i % 4]
            cursor.execute(
                """
                INSERT INTO labels (trip_id, stop_id, label, ts_labeled)
                VALUES (?, ?, ?, ?)
                """,
                (trip_id, stop_id, label, ts),
            )

        # Insert poll log entry to create a valid window
        cursor.execute(
            """
            INSERT INTO poll_log
            (ts, success, n_pred, n_veh, n_dock, data_age_trip_updates,
             data_age_vehicle_positions, data_age_docks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, 1, num_labels, 0, 0, 0, 0, 0),
        )

        db.commit()

        # Generate findings with the given placeholder mode
        findings_obj = findings.generate_findings(
            db, model=None, is_placeholder=is_placeholder_mode, config=config
        )

        # Property 1: is_placeholder logic
        # is_placeholder should be True if:
        # 1. is_placeholder_mode=True (demo mode), OR
        # 2. n_labels < min_labels
        expected_placeholder = is_placeholder_mode or num_labels < min_labels

        assert (
            findings_obj.is_placeholder == expected_placeholder
        ), f"is_placeholder={findings_obj.is_placeholder}, expected={expected_placeholder}, num_labels={num_labels}, min_labels={min_labels}, is_placeholder_mode={is_placeholder_mode}"

        # Property 2: If not placeholder, should have n_labels >= min_labels
        if not findings_obj.is_placeholder and not is_placeholder_mode:
            assert (
                findings_obj.model.n_labels >= min_labels
            ), f"Not placeholder but n_labels={findings_obj.model.n_labels} < {min_labels}"

        # Property 3: If is_placeholder=false, model should not be "placeholder"
        if not findings_obj.is_placeholder:
            # Can be model or empirical, but not placeholder
            assert findings_obj.model.method in [
                "model",
                "empirical",
            ], f"Placeholder False but method={findings_obj.model.method}"

        db.close()
    finally:
        tmpdir.cleanup()


@given(
    num_labels=st.just(100),  # Less than min_labels (300)
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None, max_examples=10)
def test_findings_placeholder_insufficient_labels(num_labels):
    """Property 1: is_placeholder=true when n_labels < min_labels (insufficient data).

    Validates: Requirements 5.7
    Feature: unghosted-core, Property 1: Findings is_placeholder logic
    """
    db_path, tmpdir = create_temp_db()
    try:
        db = database.get_connection(db_path)
        config = config_dict()
        min_labels = config["thresholds"]["min_labels"]

        cursor = db.cursor()
        ts = int(time.time())

        # Create fewer labels than threshold
        for i in range(num_labels):
            trip_id = f"trip_{i}"
            stop_id = f"stop_{i % 5}"

            cursor.execute(
                """
                INSERT INTO pred_snap
                (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
                 schedule_relationship, revenue, headsign, stop_sequence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts + i, stop_id, "23", trip_id, 5.0, 10, None, 1, "Downtown", i % 10),
            )

            cursor.execute(
                """
                INSERT INTO labels (trip_id, stop_id, label, ts_labeled)
                VALUES (?, ?, ?, ?)
                """,
                (trip_id, stop_id, "SERVED", ts),
            )

        cursor.execute(
            """
            INSERT INTO poll_log
            (ts, success, n_pred, n_veh, n_dock, data_age_trip_updates,
             data_age_vehicle_positions, data_age_docks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, 1, num_labels, 0, 0, 0, 0, 0),
        )

        db.commit()

        # Generate findings without placeholder flag
        findings_obj = findings.generate_findings(
            db, model=None, is_placeholder=False, config=config
        )

        # Property: is_placeholder must be True because n_labels < min_labels
        assert (
            findings_obj.is_placeholder is True
        ), f"is_placeholder should be True for n_labels={num_labels} < {min_labels}"

        # Property: totals.labeled should match num_labels
        assert (
            findings_obj.totals["labeled"] == num_labels
        ), f"totals.labeled={findings_obj.totals['labeled']}, expected {num_labels}"

        db.close()
    finally:
        tmpdir.cleanup()


@given(
    num_labels=st.just(400),  # Greater than min_labels (300)
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None, max_examples=10)
def test_findings_not_placeholder_sufficient_labels(num_labels):
    """Property 1: is_placeholder=false when n_labels >= min_labels and not in demo.

    Validates: Requirements 5.7
    Feature: unghosted-core, Property 1: Findings is_placeholder logic
    """
    db_path, tmpdir = create_temp_db()
    try:
        db = database.get_connection(db_path)
        config = config_dict()
        min_labels = config["thresholds"]["min_labels"]

        cursor = db.cursor()
        ts = int(time.time())

        # Create sufficient labels
        for i in range(num_labels):
            trip_id = f"trip_{i}"
            stop_id = f"stop_{i % 10}"

            cursor.execute(
                """
                INSERT INTO pred_snap
                (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
                 schedule_relationship, revenue, headsign, stop_sequence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts + i, stop_id, "23", trip_id, 5.0, 10, None, 1, "Downtown", i % 10),
            )

            cursor.execute(
                """
                INSERT INTO labels (trip_id, stop_id, label, ts_labeled)
                VALUES (?, ?, ?, ?)
                """,
                (trip_id, stop_id, "SERVED", ts),
            )

        cursor.execute(
            """
            INSERT INTO poll_log
            (ts, success, n_pred, n_veh, n_dock, data_age_trip_updates,
             data_age_vehicle_positions, data_age_docks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, 1, num_labels, 0, 0, 0, 0, 0),
        )

        db.commit()

        # Generate findings without placeholder flag
        findings_obj = findings.generate_findings(
            db, model=None, is_placeholder=False, config=config
        )

        # Property: is_placeholder must be False because n_labels >= min_labels and not in demo
        assert (
            findings_obj.is_placeholder is False
        ), f"is_placeholder should be False for n_labels={num_labels} >= {min_labels}"

        # Property: model.method should not be "placeholder"
        assert (
            findings_obj.model.method != "placeholder"
        ), f"model.method should not be placeholder when sufficient labels"

        db.close()
    finally:
        tmpdir.cleanup()


@given(
    num_labels=st.integers(min_value=1, max_value=50),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None, max_examples=10)
def test_findings_placeholder_demo_mode(num_labels):
    """Property 1: is_placeholder=true when in demo mode, regardless of label count.

    Validates: Requirements 5.7
    Feature: unghosted-core, Property 1: Findings is_placeholder logic
    """
    db_path, tmpdir = create_temp_db()
    try:
        db = database.get_connection(db_path)
        config = config_dict()

        cursor = db.cursor()
        ts = int(time.time())

        # Create any number of labels
        for i in range(num_labels):
            trip_id = f"trip_{i}"
            stop_id = f"stop_{i % 5}"

            cursor.execute(
                """
                INSERT INTO pred_snap
                (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty,
                 schedule_relationship, revenue, headsign, stop_sequence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts + i, stop_id, "23", trip_id, 5.0, 10, None, 1, "Downtown", i % 10),
            )

            cursor.execute(
                """
                INSERT INTO labels (trip_id, stop_id, label, ts_labeled)
                VALUES (?, ?, ?, ?)
                """,
                (trip_id, stop_id, "SERVED", ts),
            )

        cursor.execute(
            """
            INSERT INTO poll_log
            (ts, success, n_pred, n_veh, n_dock, data_age_trip_updates,
             data_age_vehicle_positions, data_age_docks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, 1, num_labels, 0, 0, 0, 0, 0),
        )

        db.commit()

        # Generate findings with is_placeholder=True (demo mode)
        findings_obj = findings.generate_findings(
            db, model=None, is_placeholder=True, config=config
        )

        # Property: is_placeholder must always be True in demo mode
        assert (
            findings_obj.is_placeholder is True
        ), f"is_placeholder should be True in demo mode regardless of num_labels={num_labels}"

        db.close()
    finally:
        tmpdir.cleanup()
