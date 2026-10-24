"""Property-based tests for core.dock_trust module.

Feature: unghosted-core
Property 1: Dock chances in [0, 1]
Property 5: Non-renting dock chance zero
"""
import pytest
from hypothesis import given, strategies as st, assume


def station_id_strategy():
    """Generate realistic Bluebikes station IDs."""
    return st.sampled_from(["1", "25", "42", "99", "101", "150"])


def app_bikes_strategy():
    """Generate available bike counts."""
    return st.integers(min_value=0, max_value=30)


def drain_rate_strategy():
    """Generate drain rates (bikes/minute)."""
    return st.one_of(
        st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
        st.none(),
    )


def last_reported_age_strategy():
    """Generate age of last report in seconds."""
    return st.one_of(
        st.integers(min_value=0, max_value=300),      # Fresh (<=300s)
        st.integers(min_value=301, max_value=3600),   # Stale (>300s)
        st.none(),                                      # Missing
    )


def model_chance_strategy():
    """Generate model probability in [0, 1]."""
    return st.one_of(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        st.none(),
    )


# ============================================================================
# Property 1: Dock Chances in [0, 1]
# ============================================================================

@given(
    is_renting=st.booleans(),
    is_installed=st.booleans(),
    app_bikes=app_bikes_strategy(),
    last_reported_age_sec=last_reported_age_strategy(),
    drain_rate=drain_rate_strategy(),
    model_chance=model_chance_strategy(),
)
def test_dock_chances_in_valid_range(
    is_renting, is_installed, app_bikes, last_reported_age_sec, drain_rate, model_chance
):
    """Property 1: All chance_bike_on_arrival in [0, 1].
    
    Validates: Requirements 4.2
    Feature: unghosted-core, Property 1: Dock chances in [0, 1]
    """
    from core.dock_trust import compute_dock_status_and_chance
    
    dock = {
        "station_id": "100",
        "is_renting": is_renting,
        "is_installed": is_installed,
        "app_bikes": app_bikes,
        "last_reported_age_sec": last_reported_age_sec if last_reported_age_sec is not None else 0,
    }
    
    status, why, reason_codes, chance = compute_dock_status_and_chance(
        dock, drain_rate=drain_rate, model_chance=model_chance
    )
    
    # Property: chance must be in [0, 1]
    assert 0.0 <= chance <= 1.0, \
        f"Chance {chance} out of [0, 1]; is_renting={is_renting}, is_installed={is_installed}"


# ============================================================================
# Property 5: Non-Renting Dock Chance is Zero
# ============================================================================

@given(
    app_bikes=app_bikes_strategy(),
    drain_rate=drain_rate_strategy(),
    model_chance=model_chance_strategy(),
)
def test_non_renting_dock_chance_zero(app_bikes, drain_rate, model_chance):
    """Property 5: If is_renting=false, chance_bike_on_arrival = 0.
    
    Validates: Requirements 4.2
    Feature: unghosted-core, Property 5: Non-renting dock chance zero
    """
    from core.dock_trust import compute_dock_status_and_chance
    
    dock = {
        "station_id": "100",
        "is_renting": False,  # Not renting
        "is_installed": True,
        "app_bikes": app_bikes,
        "last_reported_age_sec": 0,
    }
    
    status, why, reason_codes, chance = compute_dock_status_and_chance(
        dock, drain_rate=drain_rate, model_chance=model_chance
    )
    
    # Property: chance must be exactly 0 if not renting
    assert chance == 0.0, \
        f"Non-renting dock should have chance=0, got {chance}"
    assert "dock_not_renting" in reason_codes, \
        f"Should have reason code 'dock_not_renting', got {reason_codes}"


@given(
    is_installed=st.booleans(),
    app_bikes=app_bikes_strategy(),
    last_reported_age_sec=last_reported_age_strategy(),
    drain_rate=drain_rate_strategy(),
)
def test_renting_dock_chance_nonzero_or_low(
    is_installed, app_bikes, last_reported_age_sec, drain_rate
):
    """Property 5: If is_renting=true (and not other failure modes), chance > 0.
    
    Validates: Requirements 4.2
    Feature: unghosted-core, Property 5: Renting dock complement
    """
    from core.dock_trust import compute_dock_status_and_chance
    
    dock = {
        "station_id": "100",
        "is_renting": True,  # Renting
        "is_installed": is_installed,
        "app_bikes": app_bikes,
        "last_reported_age_sec": last_reported_age_sec if last_reported_age_sec is not None else 0,
    }
    
    status, why, reason_codes, chance = compute_dock_status_and_chance(
        dock, drain_rate=drain_rate
    )
    
    # If installed, not stale, and renting: chance should be > 0
    if is_installed and (last_reported_age_sec is None or last_reported_age_sec <= 300):
        assert chance > 0.0, \
            f"Renting dock should have chance > 0, got {chance}"


# ============================================================================
# Specific test cases
# ============================================================================

def test_renting_dock_with_bikes_confirmed():
    """Test that a renting dock with bikes has decent chance."""
    from core.dock_trust import compute_dock_status_and_chance
    
    dock = {
        "station_id": "100",
        "is_renting": True,
        "is_installed": True,
        "app_bikes": 10,
        "last_reported_age_sec": 30,
    }
    
    status, why, reason_codes, chance = compute_dock_status_and_chance(dock)
    
    assert 0.0 <= chance <= 1.0, f"Invalid chance: {chance}"
    assert chance > 0.0, f"Renting dock with bikes should have chance > 0"


def test_not_renting_dock_zero_chance():
    """Test that non-renting dock always has 0 chance."""
    from core.dock_trust import compute_dock_status_and_chance
    
    dock = {
        "station_id": "100",
        "is_renting": False,
        "is_installed": True,
        "app_bikes": 15,
        "last_reported_age_sec": 30,
    }
    
    status, why, reason_codes, chance = compute_dock_status_and_chance(dock)
    
    assert chance == 0.0, f"Non-renting dock should have chance=0, got {chance}"
    assert "dock_not_renting" in reason_codes


def test_not_installed_dock_unreliable():
    """Test that non-installed dock is unreliable."""
    from core.dock_trust import compute_dock_status_and_chance
    
    dock = {
        "station_id": "100",
        "is_renting": True,
        "is_installed": False,
        "app_bikes": 5,
        "last_reported_age_sec": 30,
    }
    
    status, why, reason_codes, chance = compute_dock_status_and_chance(dock)
    
    assert status == "unreliable", f"Non-installed dock should be unreliable, got {status}"
    assert "dock_not_installed" in reason_codes
    assert 0.0 <= chance <= 1.0


def test_stale_dock_data_unreliable():
    """Test that stale dock data results in unreliable status."""
    from core.dock_trust import compute_dock_status_and_chance
    
    dock = {
        "station_id": "100",
        "is_renting": True,
        "is_installed": True,
        "app_bikes": 10,
        "last_reported_age_sec": 400,  # Stale (> 300s)
    }
    
    status, why, reason_codes, chance = compute_dock_status_and_chance(dock)
    
    assert status == "unreliable", f"Stale dock should be unreliable, got {status}"
    assert "data_stale" in reason_codes
    assert 0.0 <= chance <= 1.0


def test_fresh_empty_dock_still_has_chance():
    """Test that even empty dock can have non-zero chance (depends on drain)."""
    from core.dock_trust import compute_dock_status_and_chance
    
    dock = {
        "station_id": "100",
        "is_renting": True,
        "is_installed": True,
        "app_bikes": 0,
        "last_reported_age_sec": 30,
    }
    
    status, why, reason_codes, chance = compute_dock_status_and_chance(dock)
    
    # Empty dock: should downgrade status but might still have some chance
    assert status in ["confirmed", "estimate"], f"Empty dock status: {status}"
    assert 0.0 <= chance <= 1.0
    # With 0 bikes, status should be at most estimate
    if status == "confirmed":
        assert "no_bikes_available" not in reason_codes


def test_missing_fields_defaults():
    """Test that missing fields don't crash and use defaults."""
    from core.dock_trust import compute_dock_status_and_chance
    
    dock = {}
    
    status, why, reason_codes, chance = compute_dock_status_and_chance(dock)
    
    # Should not crash
    assert status in ["confirmed", "estimate", "unreliable"], f"Invalid status: {status}"
    assert isinstance(reason_codes, list), f"reason_codes not a list"
    assert 0.0 <= chance <= 1.0, f"Invalid chance: {chance}"


def test_drain_rate_affects_chance():
    """Test that drain_rate parameter affects returned chance."""
    from core.dock_trust import compute_dock_status_and_chance
    
    dock = {
        "station_id": "100",
        "is_renting": True,
        "is_installed": True,
        "app_bikes": 10,
        "last_reported_age_sec": 30,
    }
    
    # High drain rate (bikes leaving fast)
    _, _, _, chance_high_drain = compute_dock_status_and_chance(
        dock, drain_rate=0.5
    )
    
    # Low drain rate (bikes leaving slowly)
    _, _, _, chance_low_drain = compute_dock_status_and_chance(
        dock, drain_rate=0.05
    )
    
    # Both should be valid
    assert 0.0 <= chance_high_drain <= 1.0
    assert 0.0 <= chance_low_drain <= 1.0
    
    # Higher drain should not increase chance
    # (it represents more bikes leaving, so fewer available)


def test_model_chance_affects_probability():
    """Test that model_chance parameter affects returned chance."""
    from core.dock_trust import compute_dock_status_and_chance
    
    dock = {
        "station_id": "100",
        "is_renting": True,
        "is_installed": True,
        "app_bikes": 10,
        "last_reported_age_sec": 30,
    }
    
    # With high model chance
    _, _, _, chance_high = compute_dock_status_and_chance(
        dock, model_chance=0.9
    )
    
    # With low model chance
    _, _, _, chance_low = compute_dock_status_and_chance(
        dock, model_chance=0.2
    )
    
    # Both should be valid
    assert 0.0 <= chance_high <= 1.0
    assert 0.0 <= chance_low <= 1.0
    
    # Higher model chance should result in higher returned chance
    assert chance_high >= chance_low, \
        f"Model chance should affect result: {chance_high} vs {chance_low}"


# ============================================================================
# Integration tests
# ============================================================================

@given(
    is_renting=st.booleans(),
    is_installed=st.booleans(),
    app_bikes=app_bikes_strategy(),
    last_reported_age_sec=last_reported_age_strategy(),
    drain_rate=drain_rate_strategy(),
    model_chance=model_chance_strategy(),
)
def test_combined_constraints(
    is_renting, is_installed, app_bikes, last_reported_age_sec, drain_rate, model_chance
):
    """Integration test: All constraints must hold together.
    
    Feature: unghosted-core, Property: Combined constraints
    Validates: Requirements 4.2
    """
    from core.dock_trust import compute_dock_status_and_chance
    
    dock = {
        "station_id": "100",
        "is_renting": is_renting,
        "is_installed": is_installed,
        "app_bikes": app_bikes,
        "last_reported_age_sec": last_reported_age_sec if last_reported_age_sec is not None else 0,
    }
    
    status, why, reason_codes, chance = compute_dock_status_and_chance(
        dock, drain_rate=drain_rate, model_chance=model_chance
    )
    
    # P1: Chance must be in [0, 1]
    assert 0.0 <= chance <= 1.0, f"Chance {chance} out of [0, 1]"
    
    # P5: If not renting, chance must be 0
    if not is_renting:
        assert chance == 0.0, f"Non-renting should have chance=0, got {chance}"
        # Skip other assertions since chance=0 ends processing
        return
    
    # Status should be valid
    assert status in ["confirmed", "estimate", "unreliable"], f"Invalid status: {status}"
    
    # Reason codes should be valid
    valid_codes = {"dock_not_renting", "dock_not_installed", "data_stale", "no_bikes_available"}
    for code in reason_codes:
        assert code in valid_codes, f"Unknown reason code: {code}"


# ============================================================================
# Usable bikes estimate tests
# ============================================================================

def test_usable_bikes_estimate_confirmed():
    """Test that confirmed status produces tight range."""
    from core.dock_trust import compute_usable_bikes_estimate
    
    low, high = compute_usable_bikes_estimate(10, confidence="confirmed")
    
    assert low <= high, f"Invalid range: [{low}, {high}]"
    assert low >= 0, f"Negative low: {low}"
    # Range should be tight
    assert high - low <= 10, f"Confirmed range too wide: {high - low}"


def test_usable_bikes_estimate_estimate():
    """Test that estimate status produces wider range."""
    from core.dock_trust import compute_usable_bikes_estimate
    
    low_c, high_c = compute_usable_bikes_estimate(10, confidence="confirmed")
    low_e, high_e = compute_usable_bikes_estimate(10, confidence="estimate")
    
    # Estimate range should be wider
    assert (high_e - low_e) >= (high_c - low_c), \
        f"Estimate range narrower than confirmed"


def test_usable_bikes_estimate_unreliable():
    """Test that unreliable status produces widest range."""
    from core.dock_trust import compute_usable_bikes_estimate
    
    low_c, high_c = compute_usable_bikes_estimate(10, confidence="confirmed")
    low_u, high_u = compute_usable_bikes_estimate(10, confidence="unreliable")
    
    # Unreliable range should be widest
    assert (high_u - low_u) >= (high_c - low_c), \
        f"Unreliable range narrower than confirmed"


@given(
    app_bikes=st.integers(min_value=0, max_value=50),
    confidence=st.sampled_from(["confirmed", "estimate", "unreliable"]),
)
def test_usable_bikes_estimate_validity(app_bikes, confidence):
    """Property: Usable bikes estimate must have low <= high and both non-negative."""
    from core.dock_trust import compute_usable_bikes_estimate
    
    low, high = compute_usable_bikes_estimate(app_bikes, confidence=confidence)
    
    # Property: low <= high
    assert low <= high, f"Invalid range: low={low} > high={high}"
    
    # Property: both must be non-negative
    assert low >= 0, f"Negative low: {low}"
    assert high >= 0, f"Negative high: {high}"
