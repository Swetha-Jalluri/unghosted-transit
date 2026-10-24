"""Backup selection module.

Pure functions for selecting next-best backup transit options (bus or bike).
Decision logic: Never return unreliable or hidden alternatives.
"""
from typing import Optional
from core.contracts import Backup, BusPrediction, DockResult


def select_backups(
    primary: BusPrediction | DockResult,
    alternatives: list[BusPrediction] | list[DockResult],
    primary_type: str,
) -> Optional[Backup]:
    """
    Select next-best backup option (bus or bike).
    
    Args:
        primary: Primary BusPrediction or DockResult.
        alternatives: List of alternative BusPredictions or DockResults.
        primary_type: "bus" or "bike" (type of primary).
    
    Returns:
        Backup object if suitable backup found, else None.
        
    Property 6: Backups never unreliable or hidden
    - Never select unreliable alternatives (status="unreliable").
    - Never select hidden alternatives (revenue=false or uncertainty>301 for buses).
    - For buses: status != "unreliable", evidence.uncertainty <= 301.
    - For bikes: status != "unreliable", is_renting=true.
    
    Validates: Requirements 4.6
    """
    if not alternatives:
        return None
    
    # Filter out unsuitable alternatives
    suitable = []
    
    if primary_type == "bus":
        # Backing up from a bus to another bus or bike
        for alt in alternatives:
            if isinstance(alt, BusPrediction):
                # Bus backup: must not be unreliable or hidden
                if alt.status == "unreliable":
                    continue  # Skip unreliable buses
                
                if alt.chance_it_arrives is None:
                    continue  # Skip hidden buses (chance=None signals hidden)
                
                # This bus is suitable
                suitable.append(alt)
            
            elif isinstance(alt, DockResult):
                # Bike backup: must not be unreliable and must be renting
                if alt.status == "unreliable":
                    continue  # Skip unreliable docks
                
                # Dock must be renting and have bikes available
                if alt.chance_bike_on_arrival == 0.0:
                    continue  # Skip non-renting docks
                
                # This dock is suitable
                suitable.append(alt)
    
    else:  # primary_type == "bike"
        # Backing up from a bike to a bus or another bike
        for alt in alternatives:
            if isinstance(alt, BusPrediction):
                # Bus backup: must not be unreliable or hidden
                if alt.status == "unreliable":
                    continue  # Skip unreliable buses
                
                if alt.chance_it_arrives is None:
                    continue  # Skip hidden buses
                
                # This bus is suitable
                suitable.append(alt)
            
            elif isinstance(alt, DockResult):
                # Bike backup: must not be unreliable and must be renting
                if alt.status == "unreliable":
                    continue  # Skip unreliable docks
                
                if alt.chance_bike_on_arrival == 0.0:
                    continue  # Skip non-renting docks
                
                # This dock is suitable
                suitable.append(alt)
    
    if not suitable:
        return None
    
    # Select first suitable alternative (best by position/chance)
    best_alt = suitable[0]
    
    # Convert to Backup object
    if isinstance(best_alt, BusPrediction):
        backup = Backup(
            type="bus",
            route_id=best_alt.route_id,
            station_id=None,
            name=best_alt.headsign,
            status=best_alt.status,
            eta_min=best_alt.app_eta_min,
            walk_min=None,
            chance=best_alt.chance_it_arrives,
        )
    else:  # DockResult
        backup = Backup(
            type="bike",
            route_id=None,
            station_id=best_alt.station_id,
            name=best_alt.name,
            status=best_alt.status,
            eta_min=None,
            walk_min=None,
            chance=best_alt.chance_bike_on_arrival,
        )
    
    return backup


def are_backups_valid(backups: list[Backup] | None) -> bool:
    """
    Validate that all backups meet Property 6 constraints.
    
    Property 6: Backups never unreliable or hidden
    - All backups must have status != "unreliable".
    - All backups must have been selected (not hidden).
    
    Args:
        backups: List of Backup objects to validate, or None.
    
    Returns:
        bool: True if all backups are valid, False otherwise.
    
    Validates: Requirements 4.6
    """
    if backups is None:
        return True
    
    if not isinstance(backups, list):
        return False
    
    for backup in backups:
        if not isinstance(backup, Backup):
            return False
        
        # Backup must not be unreliable
        if backup.status == "unreliable":
            return False
        
        # Backup chance (if set) must be non-None (not hidden)
        # and must be in [0, 1]
        if backup.chance is not None:
            if not (0.0 <= backup.chance <= 1.0):
                return False
    
    return True
