"""Static data loading and caching for MBTA stops and Bluebikes stations."""
import logging
import os
import time
from typing import Optional
import requests
import yaml

logger = logging.getLogger(__name__)

# Global cache with TTL
_cache = {
    "stops": None,
    "stops_ts": None,
    "stations": None,
    "stations_ts": None,
}

# TTL in seconds (1 hour = 3600 seconds)
TTL_SECONDS = 3600


def _load_config() -> dict:
    """Load config.yaml."""
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
        return config or {}
    except Exception as e:
        logger.warning(f"Failed to load config.yaml: {e}")
        return {}


def fetch_and_cache_stops(config: Optional[dict] = None) -> dict[str, dict]:
    """Fetch MBTA V3 stops and cache them.
    
    Args:
        config: Optional config dict. If None, loads from config.yaml.
    
    Returns:
        Dict mapping stop_id to {name, lat, lon, routes}.
    """
    if config is None:
        config = _load_config()
    
    try:
        # Build MBTA V3 stops URL
        mbta_v3_url = config.get("feeds", {}).get("mbta_v3", "https://api-v3.mbta.com")
        api_key = os.getenv("MBTA_API_KEY", "")
        
        # Fetch all stops with minimal fields
        stops_url = f"{mbta_v3_url}/stops"
        headers = {}
        if api_key:
            headers["x-api-key"] = api_key
        
        params = {
            "fields[stop]": "id,name,latitude,longitude,route_ids",
            "include": "routes",
            "limit": 1000,
        }
        
        response = requests.get(stops_url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Build stops dict
        stops = {}
        for stop in data.get("data", []):
            stop_id = stop.get("id")
            if stop_id:
                # Extract route IDs from relationships or from route_ids field
                route_ids = stop.get("relationships", {}).get("routes", {}).get("data", [])
                routes = [r.get("id") for r in route_ids if r.get("id")]
                
                stops[stop_id] = {
                    "name": stop.get("attributes", {}).get("name", ""),
                    "lat": stop.get("attributes", {}).get("latitude"),
                    "lon": stop.get("attributes", {}).get("longitude"),
                    "routes": routes,
                }
        
        logger.info(f"Fetched {len(stops)} stops from MBTA V3 API")
        return stops
    except Exception as e:
        logger.warning(f"Failed to fetch stops from MBTA V3 API: {e}")
        return {}


def fetch_and_cache_stations(config: Optional[dict] = None) -> dict[str, dict]:
    """Fetch Bluebikes stations and cache them.
    
    Args:
        config: Optional config dict. If None, loads from config.yaml.
    
    Returns:
        Dict mapping station_id to {name, lat, lon}.
    """
    if config is None:
        config = _load_config()
    
    try:
        # Fetch GBFS discovery
        gbfs_discovery_url = config.get("feeds", {}).get("gbfs_discovery", 
                                                          "https://gbfs.bluebikes.com/gbfs/gbfs.json")
        discovery_response = requests.get(gbfs_discovery_url, timeout=10)
        discovery_response.raise_for_status()
        discovery_data = discovery_response.json()
        
        # Find station_information URL
        station_info_url = None
        if "data" in discovery_data and "en" in discovery_data["data"]:
            feeds = discovery_data["data"]["en"].get("feeds", [])
            for feed in feeds:
                if feed.get("name") == "station_information":
                    station_info_url = feed.get("url")
                    break
        
        if not station_info_url:
            logger.warning("Could not find station_information feed in GBFS discovery")
            return {}
        
        # Fetch station information
        info_response = requests.get(station_info_url, timeout=10)
        info_response.raise_for_status()
        info_data = info_response.json()
        
        # Build stations dict
        stations = {}
        for station in info_data.get("data", {}).get("stations", []):
            station_id = station.get("station_id")
            if station_id:
                stations[station_id] = {
                    "name": station.get("name", ""),
                    "lat": station.get("lat"),
                    "lon": station.get("lon"),
                }
        
        logger.info(f"Fetched {len(stations)} stations from Bluebikes GBFS")
        return stations
    except Exception as e:
        logger.warning(f"Failed to fetch stations from Bluebikes GBFS: {e}")
        return {}


def get_stops() -> dict[str, dict]:
    """Get cached stops; refresh if stale (> 1 hour) or on startup.
    
    Returns:
        Dict mapping stop_id to {name, lat, lon, routes}.
    """
    current_time = time.time()
    
    # Check if cache is valid
    if _cache["stops"] is not None and _cache["stops_ts"] is not None:
        age = current_time - _cache["stops_ts"]
        if age < TTL_SECONDS:
            logger.debug(f"Returning cached stops (age {age:.0f}s)")
            return _cache["stops"]
    
    # Refresh cache
    logger.info("Refreshing stops cache")
    config = _load_config()
    try:
        stops = fetch_and_cache_stops(config)
    except Exception as e:
        logger.warning(f"Failed to refresh stops cache: {e}")
        stops = {}
    
    _cache["stops"] = stops
    _cache["stops_ts"] = current_time
    
    return stops


def get_stations() -> dict[str, dict]:
    """Get cached stations; refresh if stale (> 1 hour) or on startup.
    
    Returns:
        Dict mapping station_id to {name, lat, lon}.
    """
    current_time = time.time()
    
    # Check if cache is valid
    if _cache["stations"] is not None and _cache["stations_ts"] is not None:
        age = current_time - _cache["stations_ts"]
        if age < TTL_SECONDS:
            logger.debug(f"Returning cached stations (age {age:.0f}s)")
            return _cache["stations"]
    
    # Refresh cache
    logger.info("Refreshing stations cache")
    config = _load_config()
    try:
        stations = fetch_and_cache_stations(config)
    except Exception as e:
        logger.warning(f"Failed to refresh stations cache: {e}")
        stations = {}
    
    _cache["stations"] = stations
    _cache["stations_ts"] = current_time
    
    return stations


def clear_cache() -> None:
    """Clear all caches (useful for testing)."""
    _cache["stops"] = None
    _cache["stops_ts"] = None
    _cache["stations"] = None
    _cache["stations_ts"] = None
    logger.debug("Cache cleared")
