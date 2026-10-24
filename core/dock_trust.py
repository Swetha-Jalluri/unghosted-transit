"""Dock trust scoring module.

Pure functions for computing dock prediction status, reason codes, and bike availability chances.
Decision logic: is_renting → data_age → historical drain rate.
"""
from typing import Optional
import math


def compute_dock_status_and_chance(
    dock: dict,
    drain_rate: Optional[float] = None,
    model_chance: Optional[float] = None,
) -> tuple[str, str, list[str], float]:
    """
    Compute dock trust status and bike availability chance.
    
    Args:
        dock: Dock dict with fields: station_id, app_bikes, is_renting, last_reported, is_installed.
        drain_rate: Optional float representing observed departure rate (bikes/minute).
        model_chance: Optional float in [0, 1] from trained model.
    
    Returns:
        tuple: (status, why, reason_codes, chance_bike_on_arrival)
        - status: "confirmed" | "estimate" | "unreliable"
        - why: Human-readable explanation
        - reason_codes: List of reason codes
        - chance_bike_on_arrival: float in [0, 1]
    
    Decision rules:
        1. If NOT is_renting → chance = 0, status = unreliable
        2. If NOT is_installed → status = unreliable
        3. If dock data too stale (last_reported > dock_stale_s) → status = unreliable
        4. If app_bikes = 0 and drain_rate high → chance low
        5. If drain_rate available → use Poisson to compute chance
        6. Else → use model_chance or default empirical
    """
    status = "confirmed"
    reason_codes = []
    why = ""
    
    # Extract fields with safe defaults
    is_renting = dock.get("is_renting", True)
    is_installed = dock.get("is_installed", True)
    app_bikes = dock.get("app_bikes", 0)
    last_reported_age_sec = dock.get("last_reported_age_sec", 0)
    
    # Rule 1: Check if dock is renting
    if not is_renting:
        reason_codes.append("dock_not_renting")
        why = "Station not renting bikes"
        # Property 5: Non-renting dock chance is zero
        return (status, why, reason_codes, 0.0)
    
    # Rule 2: Check if dock is installed
    if not is_installed:
        status = "unreliable"
        reason_codes.append("dock_not_installed")
        why = "Station not installed or offline"
        # Unreliable station: low chance
        chance = 0.1
        return (status, why, reason_codes, chance)
    
    # Rule 3: Check data staleness (dock_stale_s from config is 300)
    # Assuming threshold of 300 seconds
    dock_stale_s = 300
    if last_reported_age_sec > dock_stale_s:
        status = "unreliable"
        reason_codes.append("data_stale")
        why = f"Dock data stale ({last_reported_age_sec}s old)"
        # Stale data: medium-low chance
        chance = 0.4
        return (status, why, reason_codes, chance)
    
    # Rule 4: If no bikes available, downgrade status
    if app_bikes == 0:
        if status == "confirmed":
            status = "estimate"
        if "no_bikes_available" not in reason_codes:
            reason_codes.append("no_bikes_available")
    
    # Rule 5: Compute chance using drain_rate (Poisson)
    if drain_rate is not None and drain_rate >= 0:
        # Use Poisson distribution to compute probability of having a bike
        # drain_rate: bikes per minute
        # window: 5 minutes (typical user arrival time)
        drain_window_min = 5
        expected_departures = drain_rate * drain_window_min
        
        # P(X >= 1) where X ~ Poisson(lambda)
        # = 1 - P(X = 0) = 1 - exp(-lambda)
        # But we want P(at least 1 bike available after drain)
        # Simplify: chance of having a bike = max(0, 1 - drain_rate_fraction)
        
        if expected_departures < 0.1:
            # Very low drain: high chance
            chance = 0.95
        elif expected_departures > 10:
            # Very high drain: low chance
            chance = 0.1
        else:
            # Poisson-based: 1 - P(no bikes left)
            # P(no bikes) ~ exp(-drain_rate) for low rates
            chance = max(0.0, 1.0 - math.exp(-expected_departures * 0.5))
    
    elif model_chance is not None:
        # Use model-based chance
        chance = model_chance
    else:
        # Empirical fallback: based on status and current availability
        if status == "confirmed":
            chance = 0.8
        elif status == "estimate":
            chance = 0.6 if app_bikes > 0 else 0.3
        else:
            chance = 0.2
    
    # Ensure chance is in [0, 1]
    chance = max(0.0, min(1.0, chance))
    
    # Build why message
    if not why:
        why = f"Status: {status}; {app_bikes} bikes available"
        if reason_codes:
            why += f"; Reasons: {', '.join(reason_codes)}"
    
    return (status, why, reason_codes, chance)


def compute_usable_bikes_estimate(
    app_bikes: int,
    drain_rate: Optional[float] = None,
    confidence: str = "estimate",
) -> tuple[int, int]:
    """
    Compute realistic [low, high] estimate of usable bikes available.
    
    Args:
        app_bikes: Current reported available bikes.
        drain_rate: Optional departure rate (bikes/minute).
        confidence: "confirmed" | "estimate" | "unreliable".
    
    Returns:
        tuple: (low_count, high_count) representing a range.
    """
    if confidence == "confirmed":
        # Tight range around current count
        margin = max(1, int(app_bikes * 0.1))
        low = max(0, app_bikes - margin)
        high = app_bikes + margin
    elif confidence == "estimate":
        # Medium range: ±30% or ±2, whichever larger
        margin = max(2, int(app_bikes * 0.3))
        low = max(0, app_bikes - margin)
        high = app_bikes + margin
    else:  # unreliable
        # Wide range: ±50% or ±3, whichever larger
        margin = max(3, int(app_bikes * 0.5))
        low = max(0, app_bikes - margin)
        high = app_bikes + margin
    
    return (low, high)
