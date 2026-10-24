"""Property-based tests for core.bus_trust module.

Feature: unghosted-core
Property 1: Chances in [0, 1]
Property 2: Hidden filtering
Property 3: Location age > 120s never confirmed
Property 4: Uncertainty 300/301 never confirmed
"""
import pytest
from hypothesis import given, strategies as st, assume


def route_id_strategy():
    """Generate realistic MBTA route IDs."""
    return st.sampled_from(["1", "23", "28", "39", "66", "111"])


def uncertainty_strategy():
    """Generate uncertainty values including 300/301 edge cases."""
    return st.one_of(
        st.integers(min_value=0, max_value=299),  # real-time
        st.just(300),                              # schedule-based
        st.just(301),                              # stalled
        st.integers(min_value=302, max_value=400), # invalid
        st.none(),                                  # missing
    )


def location_age_strategy():
    """Generate location age in seconds."""
    return st.one_of(
        st.integers(min_value=0, max_value=120),   # fresh
        st.integers(min_value=121, max_value=600), # stale (>120s)
        st.none(),                                  # missing
    )


def eta_min_strategy():
    """Generate ETA in minutes (0 to 240)."""
    return st.floats(min_value=0.0, max_value=240.0, allow_nan=False, allow_infinity=False)


def model_chance_strategy():
    """Generate model probability in [0, 1]."""
    return st.one_of(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        st.none(),
    )


# ============================================================================
# Property 1: Chances in [0, 1]
# ============================================================================

@given(
    revenue=st.booleans(),
    uncertainty=uncertainty_strategy(),
    schedule_relationship=st.sampled_from(["SCHEDULED", "CANCELED", "SKIPPED"]),
    location_age_sec=location_age_strategy(),
    model_chance=model_chance_strategy(),
    route_id=route_id_strategy(),
)
def test_chances_in_valid_range(
    revenue, uncertainty, schedule_relationship, location_age_sec, model_chance, route_id
):
    """Property 1: All chance_it_arrives in [0, 1] (or None if hidden).
    
    Validates: Requirements 4.1, 4.3
    Feature: unghosted-core, Property 1: Chances in [0, 1]
    """
    from core.bus_trust import compute_status_and_why
    
    pred = {
        "revenue": revenue,
        "schedule_relationship": schedule_relationship,
        "current_status": "IN_TRANSIT_TO",
        "route_id": route_id,
    }
    
    evidence = {
        "uncertainty": uncertainty,
        "vehicle_id": "y1820",
        "location_age_sec": location_age_sec,
    }
    
    status, why, reason_codes, chance = compute_status_and_why(
        pred, evidence, model_chance=model_chance
    )
    
    # Property: chance must be None (hidden) or in [0, 1]
    if chance is not None:
        assert 0.0 <= chance <= 1.0, f"Chance {chance} out of [0, 1]"


# ============================================================================
# Property 2: Hidden Filtering
# ============================================================================

@given(
    revenue=st.booleans(),
    uncertainty=uncertainty_strategy(),
)
def test_hidden_filtering_revenue_false(revenue, uncertainty):
    """Property 2: If revenue=false, prediction is hidden (chance=None).
    
    Validates: Requirements 4.1
    Feature: unghosted-core, Property 2: Hidden filtering
    """
    from core.bus_trust import compute_status_and_why
    
    # Focus on revenue=false case
    if not revenue:
        pred = {"revenue": revenue}
        evidence = {"uncertainty": uncertainty}
        
        status, why, reason_codes, chance = compute_status_and_why(pred, evidence)
        
        # Property: if revenue=false, must be hidden (chance=None)
        assert chance is None, f"revenue=false should be hidden but got chance={chance}"
        assert "hidden" in reason_codes, f"Hidden reason code missing for revenue=false"


@given(uncertainty=uncertainty_strategy())
def test_hidden_filtering_high_uncertainty(uncertainty):
    """Property 2: If uncertainty > 301, prediction is hidden (chance=None).
    
    Validates: Requirements 4.1
    Feature: unghosted-core, Property 2: Hidden filtering
    """
    from core.bus_trust import compute_status_and_why
    
    # Only test when uncertainty > 301
    if uncertainty is not None and uncertainty > 301:
        pred = {"revenue": True}
        evidence = {"uncertainty": uncertainty}
        
        status, why, reason_codes, chance = compute_status_and_why(pred, evidence)
        
        # Property: if uncertainty > 301, must be hidden (chance=None)
        assert chance is None, f"uncertainty={uncertainty} > 301 should be hidden"
        assert "hidden" in reason_codes, f"Hidden reason code missing for uncertainty > 301"


@given(
    revenue=st.booleans(),
    uncertainty=uncertainty_strategy(),
)
def test_not_hidden_when_conditions_not_met(revenue, uncertainty):
    """Property 2: Prediction is NOT hidden if revenue=true AND uncertainty <= 301.
    
    Validates: Requirements 4.1
    Feature: unghosted-core, Property 2: Hidden filtering
    """
    from core.bus_trust import compute_status_and_why
    
    # Only test valid conditions
    if revenue and (uncertainty is None or uncertainty <= 301):
        pred = {"revenue": revenue, "schedule_relationship": "SCHEDULED"}
        evidence = {"uncertainty": uncertainty}
        
        status, why, reason_codes, chance = compute_status_and_why(pred, evidence)
        
        # Property: if conditions not met for hiding, chance should NOT be None
        assert chance is not None, f"Should not be hidden when revenue=true, uncertainty={uncertainty}"
        assert "hidden" not in reason_codes or len(reason_codes) > 1


# ============================================================================
# Property 3: Location Age > 120s Never Confirmed
# ============================================================================

@given(
    location_age_sec=location_age_strategy(),
    uncertainty=uncertainty_strategy(),
    schedule_relationship=st.sampled_from(["SCHEDULED", "CANCELED"]),
)
def test_location_age_120s_constraint(location_age_sec, uncertainty, schedule_relationship):
    """Property 3: If location_age_sec > 120, status != 'confirmed'.
    
    Validates: Requirements 4.1
    Feature: unghosted-core, Property 3: Location age > 120s never confirmed
    """
    from core.bus_trust import compute_status_and_why
    
    # Skip if hidden
    if location_age_sec is not None and location_age_sec > 120:
        pred = {
            "revenue": True,
            "schedule_relationship": schedule_relationship,
            "current_status": "IN_TRANSIT_TO",
        }
        evidence = {
            "uncertainty": uncertainty if uncertainty is not None and uncertainty <= 301 else 50,
            "location_age_sec": location_age_sec,
        }
        
        status, why, reason_codes, chance = compute_status_and_why(pred, evidence)
        
        # Property: status must NOT be "confirmed"
        assert status != "confirmed", \
            f"location_age_sec={location_age_sec} > 120 but status={status} is confirmed"


@given(location_age_sec=location_age_strategy())
def test_location_age_fresh_can_be_confirmed(location_age_sec):
    """Property 3: If location_age_sec <= 120, status CAN be 'confirmed'.
    
    Validates: Requirements 4.1
    Feature: unghosted-core, Property 3: Location age constraint
    """
    from core.bus_trust import compute_status_and_why
    
    if location_age_sec is not None and location_age_sec <= 120:
        pred = {
            "revenue": True,
            "schedule_relationship": "SCHEDULED",
            "current_status": "IN_TRANSIT_TO",
        }
        evidence = {
            "uncertainty": 50,
            "location_age_sec": location_age_sec,
        }
        
        status, why, reason_codes, chance = compute_status_and_why(pred, evidence)
        
        # Property: status CAN be confirmed (no constraint prevents it)
        assert status in ["confirmed", "estimate"], \
            f"Fresh location (age={location_age_sec}<=120) got unreliable status"


# ============================================================================
# Property 4: Uncertainty 300/301 Never Confirmed
# ============================================================================

@given(uncertainty=st.sampled_from([300, 301]))
def test_uncertainty_300_301_not_confirmed(uncertainty):
    """Property 4: If uncertainty in {300, 301}, status != 'confirmed'.
    
    Validates: Requirements 4.1
    Feature: unghosted-core, Property 4: Uncertainty 300/301 never confirmed
    """
    from core.bus_trust import compute_status_and_why
    
    pred = {
        "revenue": True,
        "schedule_relationship": "SCHEDULED",
        "current_status": "IN_TRANSIT_TO",
    }
    evidence = {
        "uncertainty": uncertainty,
        "location_age_sec": 30,
    }
    
    status, why, reason_codes, chance = compute_status_and_why(pred, evidence)
    
    # Property: status must NOT be "confirmed"
    assert status != "confirmed", \
        f"uncertainty={uncertainty} but status={status} is confirmed"
    # Property: status should be at most "estimate"
    assert status in ["estimate", "unreliable"], \
        f"uncertainty={uncertainty} produced unexpected status={status}"


@given(
    uncertainty=st.integers(min_value=0, max_value=299),
    location_age_sec=st.integers(min_value=0, max_value=120),
)
def test_low_uncertainty_can_be_confirmed(uncertainty, location_age_sec):
    """Property 4: If uncertainty < 300 and location fresh, status CAN be 'confirmed'.
    
    Validates: Requirements 4.1
    Feature: unghosted-core, Property 4: Uncertainty constraint
    """
    from core.bus_trust import compute_status_and_why
    
    pred = {
        "revenue": True,
        "schedule_relationship": "SCHEDULED",
        "current_status": "IN_TRANSIT_TO",
    }
    evidence = {
        "uncertainty": uncertainty,
        "location_age_sec": location_age_sec,
    }
    
    status, why, reason_codes, chance = compute_status_and_why(pred, evidence)
    
    # Property: status CAN be confirmed
    assert status in ["confirmed", "estimate"], \
        f"Low uncertainty ({uncertainty}), fresh location ({location_age_sec}s) got unreliable"


# ============================================================================
# Integration: Combining constraints
# ============================================================================

@given(
    revenue=st.booleans(),
    schedule_relationship=st.sampled_from(["SCHEDULED", "CANCELED", "SKIPPED"]),
    uncertainty=uncertainty_strategy(),
    location_age_sec=location_age_strategy(),
    model_chance=model_chance_strategy(),
)
def test_combined_constraints(
    revenue, schedule_relationship, uncertainty, location_age_sec, model_chance
):
    """Integration test: All constraints must hold together.
    
    Feature: unghosted-core, Property: Combined constraints
    Validates: Requirements 4.1
    """
    from core.bus_trust import compute_status_and_why
    
    pred = {
        "revenue": revenue,
        "schedule_relationship": schedule_relationship,
        "current_status": "IN_TRANSIT_TO",
    }
    evidence = {
        "uncertainty": uncertainty,
        "location_age_sec": location_age_sec,
    }
    
    status, why, reason_codes, chance = compute_status_and_why(
        pred, evidence, model_chance=model_chance
    )
    
    # P1: Chance must be None or in [0, 1]
    if chance is not None:
        assert 0.0 <= chance <= 1.0, f"Chance {chance} out of range"
    
    # P2: If revenue=false or uncertainty > 301, must be hidden (chance=None)
    if not revenue or (uncertainty is not None and uncertainty > 301):
        assert chance is None, f"Should be hidden but chance={chance}"
        # Skip other assertions for hidden predictions
        return
    
    # P3: If location_age_sec > 120, status != confirmed
    if location_age_sec is not None and location_age_sec > 120:
        assert status != "confirmed", f"Stale location but status={status}"
    
    # P4: If uncertainty in {300, 301}, status != confirmed
    if uncertainty in [300, 301]:
        assert status != "confirmed", f"High uncertainty but status={status}"


# ============================================================================
# Edge cases and specific scenarios
# ============================================================================

def test_canceled_trip_unreliable():
    """Test that CANCELED trips are unreliable with 0 chance."""
    from core.bus_trust import compute_status_and_why
    
    pred = {"revenue": True, "schedule_relationship": "CANCELED"}
    evidence = {}
    
    status, why, reason_codes, chance = compute_status_and_why(pred, evidence)
    
    assert status == "unreliable", f"CANCELED trip should be unreliable, got {status}"
    assert chance == 0.0, f"CANCELED trip should have 0 chance, got {chance}"
    assert "TRIP_CANCELED" in reason_codes


def test_scheduled_trip_with_good_evidence():
    """Test that SCHEDULED trip with good evidence can be confirmed."""
    from core.bus_trust import compute_status_and_why
    
    pred = {
        "revenue": True,
        "schedule_relationship": "SCHEDULED",
        "current_status": "IN_TRANSIT_TO",
    }
    evidence = {
        "uncertainty": 50,
        "location_age_sec": 30,
        "vehicle_id": "y1820",
    }
    
    status, why, reason_codes, chance = compute_status_and_why(pred, evidence)
    
    assert status == "confirmed", f"Good evidence should confirm, got {status}"
    assert chance is not None, f"Should have chance, got {chance}"
    assert 0.0 <= chance <= 1.0, f"Chance out of range: {chance}"


def test_missing_evidence_defaults():
    """Test that missing evidence fields don't crash."""
    from core.bus_trust import compute_status_and_why
    
    pred = {}
    evidence = {}
    
    status, why, reason_codes, chance = compute_status_and_why(pred, evidence)
    
    # Should not crash and return valid outputs
    assert status in ["confirmed", "estimate", "unreliable"], f"Invalid status: {status}"
    assert isinstance(reason_codes, list), f"reason_codes not a list"
    if chance is not None:
        assert 0.0 <= chance <= 1.0, f"Invalid chance: {chance}"


def test_model_chance_affects_probability():
    """Test that model_chance parameter affects returned chance."""
    from core.bus_trust import compute_status_and_why
    
    pred = {"revenue": True, "schedule_relationship": "SCHEDULED"}
    evidence = {"uncertainty": 50, "location_age_sec": 30}
    
    # With high model chance
    status1, _, _, chance1 = compute_status_and_why(pred, evidence, model_chance=0.9)
    
    # With low model chance
    status2, _, _, chance2 = compute_status_and_why(pred, evidence, model_chance=0.2)
    
    # Both should be valid
    assert chance1 is not None and 0.0 <= chance1 <= 1.0
    assert chance2 is not None and 0.0 <= chance2 <= 1.0
    
    # Higher model chance should result in higher prediction chance
    assert chance1 >= chance2, f"Model chance should affect result: {chance1} vs {chance2}"


# ============================================================================
# Realistic ETA range tests
# ============================================================================

def test_realistic_eta_range_confirmed_contains_app_eta():
    """Property 7: For confirmed status, realistic_eta_min must contain app_eta_min."""
    from core.bus_trust import compute_realistic_eta_range
    
    app_eta_min = 5.0
    status = "confirmed"
    evidence = {}
    
    low, high = compute_realistic_eta_range(app_eta_min, status, evidence)
    
    # Property: range must contain app_eta_min
    assert low <= app_eta_min <= high, \
        f"Confirmed range [{low}, {high}] doesn't contain app_eta_min={app_eta_min}"
    
    # Property: confirmed range is tight
    assert high - low <= 1.0 + app_eta_min * 0.2, \
        f"Confirmed range too wide: [{low}, {high}]"


def test_realistic_eta_range_estimate_wider():
    """Test that estimate status produces wider range than confirmed."""
    from core.bus_trust import compute_realistic_eta_range
    
    app_eta_min = 5.0
    
    low_c, high_c = compute_realistic_eta_range(app_eta_min, "confirmed", {})
    low_e, high_e = compute_realistic_eta_range(app_eta_min, "estimate", {})
    low_u, high_u = compute_realistic_eta_range(app_eta_min, "unreliable", {})
    
    width_c = high_c - low_c
    width_e = high_e - low_e
    width_u = high_u - low_u
    
    # Property: ranges get progressively wider
    assert width_e >= width_c, f"Estimate range narrower than confirmed"
    assert width_u >= width_e, f"Unreliable range narrower than estimate"


@given(
    app_eta_min=eta_min_strategy(),
    status=st.sampled_from(["confirmed", "estimate", "unreliable"]),
)
def test_realistic_eta_range_validity(app_eta_min, status):
    """Property 7: Realistic ETA range must have low <= high and both non-negative."""
    from core.bus_trust import compute_realistic_eta_range
    
    low, high = compute_realistic_eta_range(app_eta_min, status, {})
    
    # Property: low <= high
    assert low <= high, f"Invalid range: low={low} > high={high}"
    
    # Property: both must be non-negative
    assert low >= 0.0, f"Negative low: {low}"
    assert high >= 0.0, f"Negative high: {high}"


# ============================================================================
# Property 10: Confirmed implies vehicle_id and fresh location
# ============================================================================

@given(
    vehicle_id=st.one_of(st.just(None), st.text(min_size=1)),
    location_age_sec=location_age_strategy(),
    uncertainty=uncertainty_strategy(),
    schedule_relationship=st.sampled_from(["SCHEDULED", "CANCELED"]),
)
def test_confirmed_requires_vehicle_and_fresh_location(
    vehicle_id, location_age_sec, uncertainty, schedule_relationship
):
    """Property 10: If status is 'confirmed', then vehicle_id is not None AND location_age_sec <= 120.
    
    Validates: Requirements 4.1
    Feature: unghosted-core, Property 10: Confirmed implies vehicle and fresh location
    """
    from core.bus_trust import compute_status_and_why
    
    # Skip hidden predictions
    if schedule_relationship == "CANCELED" or (uncertainty is not None and uncertainty > 301):
        return
    
    pred = {
        "revenue": True,
        "schedule_relationship": schedule_relationship,
        "current_status": "IN_TRANSIT_TO",
    }
    evidence = {
        "uncertainty": uncertainty if uncertainty is not None and uncertainty < 300 else 50,
        "location_age_sec": location_age_sec,
        "vehicle_id": vehicle_id,
    }
    
    status, why, reason_codes, chance = compute_status_and_why(pred, evidence)
    
    # Property: If status is confirmed, then vehicle_id must not be None
    if status == "confirmed":
        assert vehicle_id is not None, \
            f"status=confirmed but vehicle_id is None"
        assert "NO_VEHICLE_ASSIGNED" not in reason_codes, \
            f"status=confirmed but NO_VEHICLE_ASSIGNED in reason_codes"
    
    # Property: If status is confirmed, then location_age_sec must be <= 120
    if status == "confirmed":
        assert location_age_sec is not None and location_age_sec <= 120, \
            f"status=confirmed but location_age_sec={location_age_sec} (should be <= 120)"
        assert "STALE_LOCATION" not in reason_codes, \
            f"status=confirmed but STALE_LOCATION in reason_codes"
    
    # Property: If vehicle_id is None, status must NOT be confirmed
    if vehicle_id is None and schedule_relationship != "CANCELED":
        assert status != "confirmed", \
            f"vehicle_id=None but status=confirmed (should be at most estimate)"
        if uncertainty is None or uncertainty < 300:
            assert "NO_VEHICLE_ASSIGNED" in reason_codes, \
                f"vehicle_id=None but NO_VEHICLE_ASSIGNED not in reason_codes"
    
    # Property: If location_age_sec > 120, status must NOT be confirmed
    if location_age_sec is not None and location_age_sec > 120:
        assert status != "confirmed", \
            f"location_age_sec={location_age_sec} > 120 but status=confirmed"
        assert "STALE_LOCATION" in reason_codes, \
            f"location_age_sec > 120 but STALE_LOCATION not in reason_codes"
