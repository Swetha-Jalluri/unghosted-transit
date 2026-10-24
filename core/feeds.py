"""Feed fetching and parsing for MBTA and Bluebikes data."""
import logging
import json
from pathlib import Path
from typing import Optional
import requests
import httpx

logger = logging.getLogger(__name__)


def fetch_trip_updates() -> Optional[dict]:
    """Fetch TripUpdates_enhanced.json from MBTA; return parsed JSON or None."""
    try:
        url = "https://cdn.mbta.com/realtime/TripUpdates_enhanced.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch trip_updates: {e}")
        return None


def fetch_vehicle_positions() -> Optional[dict]:
    """Fetch VehiclePositions_enhanced.json from MBTA; return parsed JSON or None."""
    try:
        url = "https://cdn.mbta.com/realtime/VehiclePositions_enhanced.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch vehicle_positions: {e}")
        return None


def fetch_gbfs_discovery() -> Optional[str]:
    """Fetch gbfs.json from Bluebikes; return feed URL or None."""
    try:
        url = "https://gbfs.bluebikes.com/gbfs/gbfs.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        # Find station_status and station_information feeds
        if "data" in data and "en" in data["data"]:
            feeds = data["data"]["en"].get("feeds", [])
            for feed in feeds:
                if feed.get("name") == "station_status":
                    return feed.get("url")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch gbfs_discovery: {e}")
        return None


def fetch_gbfs_status_info() -> tuple[Optional[dict], Optional[dict]]:
    """Fetch station_status and station_information; return (status_data, info_data) or (None, None)."""
    try:
        # Fetch discovery to get station_status URL
        discovery_url = "https://gbfs.bluebikes.com/gbfs/gbfs.json"
        discovery_response = requests.get(discovery_url, timeout=10)
        discovery_response.raise_for_status()
        discovery_data = discovery_response.json()
        
        status_url = None
        info_url = None
        
        if "data" in discovery_data and "en" in discovery_data["data"]:
            feeds = discovery_data["data"]["en"].get("feeds", [])
            for feed in feeds:
                if feed.get("name") == "station_status":
                    status_url = feed.get("url")
                elif feed.get("name") == "station_information":
                    info_url = feed.get("url")
        
        status_data = None
        info_data = None
        
        if status_url:
            status_response = requests.get(status_url, timeout=10)
            status_response.raise_for_status()
            status_data = status_response.json()
        
        if info_url:
            info_response = requests.get(info_url, timeout=10)
            info_response.raise_for_status()
            info_data = info_response.json()
        
        return (status_data, info_data)
    except Exception as e:
        logger.warning(f"Failed to fetch gbfs_status_info: {e}")
        return (None, None)


def parse_trip_updates(raw: dict) -> list[dict]:
    """Parse TripUpdates JSON into flat records; skip on parse error.
    
    Fields per record: trip_id, route_id, direction_id, trip_schedule_relationship,
    revenue, vehicle_id, stop_id, stop_sequence, stop_schedule_relationship,
    arrival_time, arrival_uncertainty, departure_time, departure_uncertainty,
    app_eta_min (computed as minutes from feed timestamp to arrival/departure).
    """
    records = []
    try:
        if not isinstance(raw, dict) or "entity" not in raw:
            logger.warning("Trip updates missing 'entity' key")
            return records
        
        for entity in raw.get("entity", []):
            try:
                trip_update = entity.get("trip_update", {})
                feed_timestamp = trip_update.get("timestamp")
                trip_info = trip_update.get("trip", {})
                vehicle_info = trip_update.get("vehicle", {})
                
                # Trip-level fields
                trip_id = trip_info.get("trip_id")
                route_id = trip_info.get("route_id")
                direction_id = trip_info.get("direction_id")
                trip_schedule_relationship = trip_info.get("schedule_relationship", "SCHEDULED")
                revenue = trip_info.get("revenue", True)
                vehicle_id = vehicle_info.get("id")
                
                # Extract stop time updates
                for stop_update in trip_update.get("stop_time_update", []):
                    try:
                        stop_id = stop_update.get("stop_id")
                        stop_sequence = stop_update.get("stop_sequence")
                        stop_schedule_relationship = stop_update.get("schedule_relationship", "SCHEDULED")
                        
                        # Get arrival times and uncertainty
                        arrival = stop_update.get("arrival", {})
                        departure = stop_update.get("departure", {})
                        
                        arrival_time = arrival.get("time")
                        arrival_uncertainty = arrival.get("uncertainty")
                        departure_time = departure.get("time")
                        departure_uncertainty = departure.get("uncertainty")
                        
                        # Compute app_eta_min: minutes from feed timestamp to arrival/departure
                        eta_time = arrival_time or departure_time
                        app_eta_min = None
                        
                        if eta_time and feed_timestamp:
                            delta_seconds = max(0, eta_time - feed_timestamp)
                            app_eta_min = round(delta_seconds / 60.0, 1)
                        
                        if all([trip_id, stop_id, route_id]) and app_eta_min is not None:
                            record = {
                                "trip_id": trip_id,
                                "route_id": route_id,
                                "direction_id": direction_id,
                                "trip_schedule_relationship": trip_schedule_relationship,
                                "revenue": revenue,
                                "vehicle_id": vehicle_id,
                                "stop_id": stop_id,
                                "stop_sequence": stop_sequence,
                                "stop_schedule_relationship": stop_schedule_relationship,
                                "arrival_time": arrival_time,
                                "arrival_uncertainty": arrival_uncertainty,
                                "departure_time": departure_time,
                                "departure_uncertainty": departure_uncertainty,
                                "app_eta_min": app_eta_min,
                                "timestamp": feed_timestamp,
                            }
                            records.append(record)
                    except Exception as e:
                        logger.debug(f"Skipped stop_time_update: {e}")
                        continue
            except Exception as e:
                logger.debug(f"Skipped entity in trip_updates: {e}")
                continue
    except Exception as e:
        logger.warning(f"Error parsing trip_updates: {e}")
    
    return records


def parse_vehicle_positions(raw: dict) -> list[dict]:
    """Parse VehiclePositions JSON into flat records; skip on parse error.
    
    Fields per record: vehicle_id, trip_id, route_id, lat, lon, 
    current_stop_sequence, stop_id, current_status, timestamp, occupancy_status.
    """
    records = []
    try:
        if not isinstance(raw, dict) or "entity" not in raw:
            logger.warning("Vehicle positions missing 'entity' key")
            return records
        
        for entity in raw.get("entity", []):
            try:
                vehicle = entity.get("vehicle", {})
                trip_info = vehicle.get("trip", {})
                position = vehicle.get("position", {})
                vehicle_info = vehicle.get("vehicle", {})
                
                trip_id = trip_info.get("trip_id")
                route_id = trip_info.get("route_id")
                current_status = vehicle.get("current_status")
                current_stop_sequence = vehicle.get("current_stop_sequence")
                timestamp = vehicle.get("timestamp")
                stop_id = vehicle.get("stop_id")
                vehicle_id = vehicle_info.get("id")
                lat = position.get("latitude")
                lon = position.get("longitude")
                occupancy_status = vehicle.get("occupancy_status")
                
                if all([trip_id, route_id, current_status, timestamp]):
                    record = {
                        "vehicle_id": vehicle_id,
                        "trip_id": trip_id,
                        "route_id": route_id,
                        "lat": lat,
                        "lon": lon,
                        "current_stop_sequence": current_stop_sequence,
                        "stop_id": stop_id,
                        "current_status": current_status,
                        "timestamp": timestamp,
                        "occupancy_status": occupancy_status,
                    }
                    records.append(record)
            except Exception as e:
                logger.debug(f"Skipped entity in vehicle_positions: {e}")
                continue
    except Exception as e:
        logger.warning(f"Error parsing vehicle_positions: {e}")
    
    return records


def parse_gbfs(status: dict, info: dict) -> list[dict]:
    """Parse GBFS status + info into flat records; skip on parse error."""
    records = []
    try:
        # Build station map from info
        station_map = {}
        if info and "data" in info and "stations" in info["data"]:
            for station in info["data"]["stations"]:
                station_id = station.get("station_id")
                if station_id:
                    station_map[station_id] = {
                        "name": station.get("name"),
                        "lat": station.get("lat"),
                        "lon": station.get("lon"),
                        "is_installed": station.get("is_installed", True),
                    }
        
        # Parse status
        if status and "data" in status and "stations" in status["data"]:
            for station in status["data"]["stations"]:
                try:
                    station_id = station.get("station_id")
                    if not station_id or station_id not in station_map:
                        logger.debug(f"Skipped station {station_id}: not in info")
                        continue
                    
                    app_bikes = station.get("num_bikes_available", 0)
                    num_docks = station.get("num_docks_available", 0)
                    is_renting = station.get("is_renting", True)
                    last_reported = station.get("last_reported")
                    
                    station_info = station_map[station_id]
                    record = {
                        "station_id": station_id,
                        "name": station_info.get("name"),
                        "lat": station_info.get("lat"),
                        "lon": station_info.get("lon"),
                        "app_bikes": app_bikes,
                        "num_docks_available": num_docks,
                        "is_renting": is_renting,
                        "is_installed": station_info.get("is_installed", True),
                        "last_reported": last_reported,
                    }
                    records.append(record)
                except Exception as e:
                    logger.debug(f"Skipped station in GBFS: {e}")
                    continue
    except Exception as e:
        logger.warning(f"Error parsing GBFS: {e}")
    
    return records


def save_fixture_snapshot(feed_name: str, data: dict) -> None:
    """Save raw feed JSON to tests/fixtures/."""
    try:
        fixtures_dir = Path("tests/fixtures")
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        
        # Map feed names to file names
        file_map = {
            "trip_updates": "trip_updates.json",
            "vehicle_positions": "vehicle_positions.json",
            "gbfs_status": "gbfs_status.json",
            "gbfs_info": "gbfs_info.json",
        }
        
        filename = file_map.get(feed_name, f"{feed_name}.json")
        filepath = fixtures_dir / filename
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved fixture: {filepath}")
    except Exception as e:
        logger.warning(f"Failed to save fixture {feed_name}: {e}")
