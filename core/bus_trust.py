"""Bus trust scoring module.

Pure functions for computing bus prediction status, reason codes, and arrival chances.
Decision logic: revenue → CANCELED → uncertainty → location_age → motion → vanish_rate.
"""
from typing import Optional


def compute_status_and_why(
    pred: dict,
    evidence: dict,
    vanish_rates: Optional[dict] = None,
    model_chance: Optional[float] = None,
) -> tuple[str, str, list[str], Optional[float]]:
    """
    Compute bus prediction status and metadata.
    
    Args:
        pred: Prediction dict with fields: app_eta_min, route_id, trip_id, etc.
        evidence: Evidence dict with fields: uncertainty, vehicle_id, location_age_sec.
        vanish_rates: Optional dict {route_id: vanish_rate} for vanish rate checks.
        model_chance: Optional float in [0, 1] from trained model.
    
    Returns:
        tuple: (status, why, reason_codes, chance_it_arrives)
        - status: "confirmed" | "estimate" | "unreliable"
        - why: Human-readable explanation
        - reason_codes: List of reason codes
        - chance_it_arrives: float in [0, 1] or None if hidden
    
    Implements decision rules in order:
        1. If revenue=false OR uncertainty > 301 → hidden (return None for chance)
        2. If schedule_relationship CANCELED → status=unreliable
        3. If uncertainty 300 or 301 → status = at most estimate
        4. If location_age_sec > 120 → status != confirmed
        5. If vehicle not moving → downgrade status
        6. If vanish_rate > threshold → status=unreliable, add backup note
    """
    if vanish_rates is None:
        vanish_rates = {}
    
    status = "confirmed"
    reason_codes = []
    why = f"Status: {status}"  # Initialize why to avoid UnboundLocalError
    
    # Extract fields with safe defaults
    revenue = pred.get("revenue", True)
    schedule_relationship = pred.get("schedule_relationship", "SCHEDULED")
    uncertainty = evidence.get("uncertainty")
    location_age_sec = evidence.get("location_age_sec")
    vehicle_id = evidence.get("vehicle_id")
    current_status = pred.get("current_status")
    route_id = pred.get("route_id")
    
    # Rule 1: Check revenue and uncertainty for hidden prediction
    if revenue is False or (uncertainty is not None and uncertainty > 301):
        reason_codes.append("hidden")
        why = "Hidden prediction (non-revenue or invalid data)"
        return (status, why, reason_codes, None)  # None signals hidden
    
    # Rule 2: Check if trip is CANCELED
    if schedule_relationship in ["CANCELED", "SKIPPED"]:
        status = "unreliable"
        reason_codes.append("schedule_canceled")
        why = "Trip canceled or skipped in schedule"
        chance = 0.0  # Canceled trips never arrive
        return (status, why, reason_codes, chance)
    
    # Rule 3: Check uncertainty (300/301 limits confirmed status)
    if uncertainty is not None and uncertainty >= 300:
        status = "estimate"
        reason_codes.append("high_uncertainty")
        why = "Schedule-based or stalled (high uncertainty)"
    
    # Rule 4: Check location age (>120s never confirmed)
    if location_age_sec is not None and location_age_sec > 120:
        status = "unreliable" if status == "unreliable" else "estimate"
        reason_codes.append("location_stale")
        why = "Vehicle location data stale (>120s old)"
    
    # Rule 5: Check vehicle motion
    if current_status is not None and current_status == "STOPPED_AT":
        # Vehicle stopped; downgrade if currently confirmed
        if status == "confirmed":
            status = "estimate"
        if "vehicle_stopped" not in reason_codes:
            reason_codes.append("vehicle_stopped")
    
    # Rule 6: Check vanish rate
    if route_id and route_id in vanish_rates:
        vanish_rate = vanish_rates[route_id]
        if vanish_rate > 0.25:  # Threshold from config (unreliable_vanish_rate)
            status = "unreliable"
            reason_codes.append("high_vanish_rate")
            why = f"High vanish rate ({vanish_rate:.1%}) on this route"
    
    # Final why message - include reasons if not already set
    if reason_codes and ":" not in why:
        why = f"{why}; Reasons: {', '.join(reason_codes)}"
    
    # Compute chance_it_arrives based on status and model
    if status == "unreliable":
        chance = 0.1  # Low chance for unreliable
    elif status == "estimate":
        chance = model_chance if model_chance is not None else 0.5
    else:  # confirmed
        chance = model_chance if model_chance is not None else 0.9
    
    # Ensure chance is in [0, 1]
    chance = max(0.0, min(1.0, chance))
    
    return (status, why, reason_codes, chance)


def compute_realistic_eta_range(
    app_eta_min: float,
    status: str,
    evidence: dict,
    uncertainty: Optional[int] = None,
) -> tuple[float, float]:
    """
    Compute realistic [low, high] ETA range in minutes.
    
    For confirmed status, range must contain app_eta_min.
    Otherwise, range is a wider estimate.
    
    Args:
        app_eta_min: Application predicted ETA in minutes.
        status: "confirmed" | "estimate" | "unreliable".
        evidence: Evidence dict (can include location_age_sec, etc.).
        uncertainty: Uncertainty value (affects range width).
    
    Returns:
        tuple: (low_minutes, high_minutes)
    """
    if status == "confirmed":
        # Tight range around app_eta_min
        margin = max(1.0, app_eta_min * 0.1)  # 10% or 1 min, whichever larger
        low = max(0.0, app_eta_min - margin)
        high = app_eta_min + margin
    elif status == "estimate":
        # Medium range: ±2 min around app_eta_min
        low = max(0.0, app_eta_min - 2.0)
        high = app_eta_min + 2.0
    else:  # unreliable
        # Wide range: ±5 min around app_eta_min
        low = max(0.0, app_eta_min - 5.0)
        high = app_eta_min + 5.0
    
    return (round(low, 1), round(high, 1))
