"""Property-based tests for core.feeds module.

Feature: unghosted-core
Property 1: Parse produces flat records
Property 2: Malformed records skipped
"""
import pytest
from hypothesis import given, strategies as st, assume
import json
from core.feeds import (
    parse_trip_updates,
    parse_vehicle_positions,
    parse_gbfs,
)


# ============================================================================
# Generators for realistic MBTA/Bluebikes data
# ============================================================================

def stop_id_strategy():
    """Generate realistic MBTA stop IDs."""
    return st.sampled_from(["place-haecl", "place-kencl", "place-neast", "334", "367", "369"])


def route_id_strategy():
    """Generate realistic MBTA route IDs."""
    return st.sampled_from(["1", "23", "28", "39", "66", "111"])


def trip_id_strategy():
    """Generate trip IDs."""
    return st.integers(min_value=1000000, max_value=99999999).map(str)


def vehicle_id_strategy():
    """Generate vehicle IDs."""
    prefix = st.sampled_from(["y", "x"])
    number = st.integers(min_value=1000, max_value=2000)
    return st.builds(lambda p, n: f"{p}{n}", prefix, number)


def timestamp_strategy():
    """Generate realistic POSIX timestamps."""
    return st.integers(min_value=1790000000, max_value=1800000000)


def uncertainty_strategy():
    """Generate realistic uncertainty values (< 300 real-time, 300 schedule, 301+ invalid)."""
    return st.one_of(
        st.integers(min_value=0, max_value=299),  # real-time
        st.just(300),  # schedule-based
        st.just(301),  # stalled
    )


def eta_time_strategy():
    """Generate realistic ETA timestamps (near now, in the future)."""
    return st.integers(min_value=1792869000, max_value=1792875000)


# ============================================================================
# Property 1: Parse produces flat records
# ============================================================================

@given(
    trip_id=trip_id_strategy(),
    stop_id=stop_id_strategy(),
    route_id=route_id_strategy(),
    eta_time=eta_time_strategy(),
    uncertainty=uncertainty_strategy(),
)
def test_parse_trip_updates_produces_flat_records(trip_id, stop_id, route_id, eta_time, uncertainty):
    """Property 1: For any valid feed JSON, parsing must produce a list of dicts with required fields.
    
    Validates: Requirements 1.2, 1.6
    Feature: unghosted-core, Property 1: Parse produces flat records
    """
    feed_timestamp = 1792869000
    
    # Construct minimal valid trip_updates entity
    raw = {
        "entity": [
            {
                "id": trip_id,
                "trip_update": {
                    "timestamp": feed_timestamp,
                    "trip": {
                        "trip_id": trip_id,
                        "route_id": route_id,
                        "revenue": True,
                    },
                    "stop_time_update": [
                        {
                            "stop_id": stop_id,
                            "stop_sequence": 1,
                            "arrival": {
                                "time": eta_time,
                                "uncertainty": uncertainty,
                            },
                        }
                    ],
                },
            }
        ]
    }
    
    records = parse_trip_updates(raw)
    
    # Property: should produce at least one record
    assert isinstance(records, list)
    assert len(records) >= 1
    
    # Property: all records must be dicts
    assert all(isinstance(r, dict) for r in records)
    
    # Property: all records must have required fields
    required_fields = {"trip_id", "stop_id", "app_eta_min", "route_id"}
    for record in records:
        assert all(field in record for field in required_fields)
        assert record["trip_id"] == trip_id
        assert record["stop_id"] == stop_id
        assert record["route_id"] == route_id
        # app_eta_min should be computed as (eta_time - feed_timestamp) / 60 (in minutes)
        expected_eta_min = round(max(0, eta_time - feed_timestamp) / 60.0, 1)
        assert record["app_eta_min"] == expected_eta_min


@given(
    station_id=st.sampled_from(["station_hub_001", "station_hub_002", "station_hub_003"]),
    app_bikes=st.integers(min_value=0, max_value=50),
    num_docks=st.integers(min_value=5, max_value=100),
)
def test_parse_gbfs_produces_flat_records(station_id, app_bikes, num_docks):
    """Property 1: For any valid GBFS data, parsing must produce flat records with required fields.
    
    Validates: Requirements 1.2, 1.6
    Feature: unghosted-core, Property 1: Parse produces flat records
    """
    # Construct minimal valid GBFS status + info
    status = {
        "data": {
            "stations": [
                {
                    "station_id": station_id,
                    "num_bikes_available": app_bikes,
                    "num_docks_available": num_docks,
                    "is_renting": True,
                    "last_reported": 1792869000,
                }
            ]
        }
    }
    
    info = {
        "data": {
            "stations": [
                {
                    "station_id": station_id,
                    "name": f"Station {station_id}",
                    "lat": 42.365,
                    "lon": -71.110,
                    "is_installed": True,
                }
            ]
        }
    }
    
    records = parse_gbfs(status, info)
    
    # Property: should produce at least one record
    assert isinstance(records, list)
    assert len(records) >= 1
    
    # Property: all records must be dicts
    assert all(isinstance(r, dict) for r in records)
    
    # Property: all records must have required fields
    required_fields = {"station_id", "app_bikes"}
    for record in records:
        assert all(field in record for field in required_fields)
        assert record["station_id"] == station_id
        assert record["app_bikes"] == app_bikes


@given(
    trip_id=trip_id_strategy(),
    route_id=route_id_strategy(),
    current_status=st.sampled_from(["INCOMING_AT", "STOPPED_AT", "IN_TRANSIT_TO"]),
    stop_sequence=st.integers(min_value=1, max_value=50),
)
def test_parse_vehicle_positions_produces_flat_records(trip_id, route_id, current_status, stop_sequence):
    """Property 1: For any valid vehicle position data, parsing must produce flat records.
    
    Validates: Requirements 1.2, 1.6
    Feature: unghosted-core, Property 1: Parse produces flat records
    """
    # Construct minimal valid vehicle_positions entity
    raw = {
        "entity": [
            {
                "id": "y1820",
                "vehicle": {
                    "trip": {
                        "trip_id": trip_id,
                        "route_id": route_id,
                        "schedule_relationship": "SCHEDULED",
                        "revenue": True,
                    },
                    "current_status": current_status,
                    "current_stop_sequence": stop_sequence,
                    "timestamp": 1792869000,
                    "stop_id": "334",
                    "position": {
                        "latitude": 42.365,
                        "longitude": -71.110,
                    },
                    "vehicle": {
                        "id": "y1820",
                        "label": "1820",
                    },
                },
            }
        ]
    }
    
    records = parse_vehicle_positions(raw)
    
    # Property: should produce at least one record
    assert isinstance(records, list)
    assert len(records) >= 1
    
    # Property: all records must be dicts
    assert all(isinstance(r, dict) for r in records)
    
    # Property: all records must have required fields
    required_fields = {"trip_id", "route_id", "current_status", "timestamp"}
    for record in records:
        assert all(field in record for field in required_fields)


# ============================================================================
# Property 2: Malformed records skipped
# ============================================================================

@given(
    missing_field=st.sampled_from(["trip_id", "stop_id", "app_eta_min", "route_id"])
)
def test_parse_trip_updates_skips_malformed(missing_field):
    """Property 2: For any feed with missing required fields, parser must skip and never raise.
    
    Validates: Requirements 1.2, 1.6
    Feature: unghosted-core, Property 2: Malformed records skipped
    """
    # Construct entity with missing field
    raw = {
        "entity": [
            {
                "id": "78981598",
                "trip_update": {
                    "timestamp": 1792869000,
                    "trip": {
                        "trip_id": "trip_123" if missing_field != "trip_id" else None,
                        "route_id": "1" if missing_field != "route_id" else None,
                    },
                    "stop_time_update": [
                        {
                            "stop_id": "334" if missing_field != "stop_id" else None,
                            "stop_sequence": 1,
                            "arrival": {
                                "time": 1792870000 if missing_field != "app_eta_min" else None,
                                "uncertainty": 50,
                            },
                        }
                    ],
                },
            }
        ]
    }
    
    # Property: parser should never raise
    try:
        records = parse_trip_updates(raw)
        # Property: malformed records should be skipped (no output for that entity)
        assert isinstance(records, list)
        # If the field was missing, record should be skipped
        if None in [raw["entity"][0]["trip_update"]["trip"].get(f) 
                    for f in ["trip_id", "route_id"]] or \
           raw["entity"][0]["trip_update"]["stop_time_update"][0].get("stop_id") is None or \
           raw["entity"][0]["trip_update"]["stop_time_update"][0]["arrival"].get("time") is None:
            assert len(records) == 0
    except Exception as e:
        pytest.fail(f"Parser should never raise: {e}")


@given(
    missing_field=st.sampled_from(["trip_id", "route_id", "current_status", "timestamp"])
)
def test_parse_vehicle_positions_skips_malformed(missing_field):
    """Property 2: For any vehicle position with missing fields, parser must skip and never raise.
    
    Validates: Requirements 1.2, 1.6
    Feature: unghosted-core, Property 2: Malformed records skipped
    """
    # Construct entity with missing field
    raw = {
        "entity": [
            {
                "id": "y1820",
                "vehicle": {
                    "trip": {
                        "trip_id": "78981620" if missing_field != "trip_id" else None,
                        "route_id": "23" if missing_field != "route_id" else None,
                    },
                    "current_status": "STOPPED_AT" if missing_field != "current_status" else None,
                    "current_stop_sequence": 16,
                    "timestamp": 1792869000 if missing_field != "timestamp" else None,
                    "stop_id": "471",
                    "position": {"latitude": 42.307398, "longitude": -71.08259},
                    "vehicle": {"id": "y1820", "label": "1820"},
                },
            }
        ]
    }
    
    # Property: parser should never raise
    try:
        records = parse_vehicle_positions(raw)
        # Property: malformed records should be skipped
        assert isinstance(records, list)
        # If any required field is None, record should be skipped
        required_values = [
            raw["entity"][0]["vehicle"]["trip"].get("trip_id"),
            raw["entity"][0]["vehicle"]["trip"].get("route_id"),
            raw["entity"][0]["vehicle"].get("current_status"),
            raw["entity"][0]["vehicle"].get("timestamp"),
        ]
        if None in required_values:
            assert len(records) == 0
    except Exception as e:
        pytest.fail(f"Parser should never raise: {e}")


@given(
    missing_field=st.sampled_from(["station_id"])
)
def test_parse_gbfs_skips_malformed(missing_field):
    """Property 2: For any GBFS data with missing fields, parser must skip and never raise.
    
    Validates: Requirements 1.2, 1.6
    Feature: unghosted-core, Property 2: Malformed records skipped
    """
    # Construct data with missing field
    status = {
        "data": {
            "stations": [
                {
                    "station_id": None if missing_field == "station_id" else "station_hub_001",
                    "num_bikes_available": 10,
                    "num_docks_available": 20,
                    "is_renting": True,
                    "last_reported": 1792869000,
                }
            ]
        }
    }
    
    info = {
        "data": {
            "stations": [
                {
                    "station_id": "station_hub_001",
                    "name": "Station 1",
                    "lat": 42.365,
                    "lon": -71.110,
                    "is_installed": True,
                }
            ]
        }
    }
    
    # Property: parser should never raise
    try:
        records = parse_gbfs(status, info)
        # Property: malformed records should be skipped
        assert isinstance(records, list)
        if missing_field == "station_id":
            assert len(records) == 0
    except Exception as e:
        pytest.fail(f"Parser should never raise: {e}")


@given(st.just({}))
def test_parse_trip_updates_handles_empty_input(raw):
    """Property 2: Parser should handle empty input gracefully.
    
    Validates: Requirements 1.2, 1.6
    Feature: unghosted-core, Property 2: Malformed records skipped
    """
    # Property: parser should never raise on empty dict
    try:
        records = parse_trip_updates(raw)
        assert isinstance(records, list)
        assert len(records) == 0
    except Exception as e:
        pytest.fail(f"Parser should never raise on empty input: {e}")


@given(st.just({}))
def test_parse_vehicle_positions_handles_empty_input(raw):
    """Property 2: Parser should handle empty input gracefully.
    
    Validates: Requirements 1.2, 1.6
    Feature: unghosted-core, Property 2: Malformed records skipped
    """
    # Property: parser should never raise on empty dict
    try:
        records = parse_vehicle_positions(raw)
        assert isinstance(records, list)
        assert len(records) == 0
    except Exception as e:
        pytest.fail(f"Parser should never raise on empty input: {e}")


@given(st.just({"data": {"stations": []}}))
def test_parse_gbfs_handles_empty_input(raw):
    """Property 2: Parser should handle empty GBFS gracefully.
    
    Validates: Requirements 1.2, 1.6
    Feature: unghosted-core, Property 2: Malformed records skipped
    """
    # Property: parser should never raise on empty stations
    try:
        records = parse_gbfs(raw, {"data": {"stations": []}})
        assert isinstance(records, list)
        assert len(records) == 0
    except Exception as e:
        pytest.fail(f"Parser should never raise on empty stations: {e}")


# ============================================================================
# Additional invariant tests
# ============================================================================

def test_parse_trip_updates_with_multiple_stops():
    """Test that parser handles multiple stops per trip correctly."""
    raw = {
        "entity": [
            {
                "id": "trip_123",
                "trip_update": {
                    "timestamp": 1792869000,
                    "trip": {
                        "trip_id": "trip_123",
                        "route_id": "1",
                        "revenue": True,
                    },
                    "stop_time_update": [
                        {
                            "stop_id": "334",
                            "stop_sequence": 1,
                            "arrival": {"time": 1792870000, "uncertainty": 50},
                        },
                        {
                            "stop_id": "367",
                            "stop_sequence": 2,
                            "arrival": {"time": 1792870060, "uncertainty": 50},
                        },
                    ],
                },
            }
        ]
    }
    
    records = parse_trip_updates(raw)
    # Property: should produce one record per stop_time_update
    assert len(records) == 2
    assert records[0]["stop_id"] == "334"
    assert records[1]["stop_id"] == "367"
    # Property: all records share same trip_id and route_id
    assert all(r["trip_id"] == "trip_123" for r in records)
    assert all(r["route_id"] == "1" for r in records)


def test_app_eta_min_in_valid_range():
    """Property: app_eta_min is None or in range [0, 240] minutes.
    
    Feature: unghosted-core, Property: app_eta_min range validation
    Validates: Requirements 1.2, 1.3
    """
    raw = {
        "entity": [
            {
                "id": "trip_123",
                "trip_update": {
                    "timestamp": 1792869000,
                    "trip": {
                        "trip_id": "trip_123",
                        "route_id": "1",
                    },
                    "stop_time_update": [
                        # Stop arriving in 0 minutes (now)
                        {
                            "stop_id": "334",
                            "stop_sequence": 1,
                            "arrival": {"time": 1792869000},
                        },
                        # Stop arriving in 2 minutes
                        {
                            "stop_id": "367",
                            "stop_sequence": 2,
                            "arrival": {"time": 1792869120},
                        },
                        # Stop arriving in 240 minutes (max valid)
                        {
                            "stop_id": "369",
                            "stop_sequence": 3,
                            "arrival": {"time": 1792883400},
                        },
                    ],
                },
            }
        ]
    }
    
    records = parse_trip_updates(raw)
    
    # Property: all app_eta_min values must be None or in [0, 240]
    for record in records:
        eta = record["app_eta_min"]
        assert eta is None or (0 <= eta <= 240), \
            f"app_eta_min {eta} out of valid range [0, 240]"
    
    # Verify specific values from test
    assert records[0]["app_eta_min"] == 0.0
    assert records[1]["app_eta_min"] == 2.0
    assert records[2]["app_eta_min"] == 240.0


def test_parse_vehicle_positions_with_multiple_vehicles():
    """Test that parser handles multiple vehicles correctly."""
    raw = {
        "entity": [
            {
                "id": "y1820",
                "vehicle": {
                    "trip": {"trip_id": "trip_1", "route_id": "23"},
                    "current_status": "STOPPED_AT",
                    "current_stop_sequence": 1,
                    "timestamp": 1792869000,
                    "stop_id": "334",
                    "position": {"latitude": 42.365, "longitude": -71.110},
                    "vehicle": {"id": "y1820", "label": "1820"},
                },
            },
            {
                "id": "y1821",
                "vehicle": {
                    "trip": {"trip_id": "trip_2", "route_id": "23"},
                    "current_status": "IN_TRANSIT_TO",
                    "current_stop_sequence": 2,
                    "timestamp": 1792869000,
                    "stop_id": "367",
                    "position": {"latitude": 42.366, "longitude": -71.111},
                    "vehicle": {"id": "y1821", "label": "1821"},
                },
            },
        ]
    }
    
    records = parse_vehicle_positions(raw)
    # Property: should produce one record per vehicle
    assert len(records) == 2
    assert records[0]["vehicle_id"] == "y1820"
    assert records[1]["vehicle_id"] == "y1821"
