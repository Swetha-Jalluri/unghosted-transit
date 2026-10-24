"""Property-based tests for core.static_load module.

Feature: unghosted-core
Property 1: Caching returns consistent data
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
import time
from unittest.mock import patch, MagicMock
from core.static_load import (
    get_stops,
    get_stations,
    fetch_and_cache_stops,
    fetch_and_cache_stations,
    clear_cache,
    TTL_SECONDS,
)


# ============================================================================
# Property 1: Caching returns consistent data
# ============================================================================

def test_get_stops_caching_returns_consistent_data():
    """Property 1: Multiple calls within TTL must return same data.
    
    Validates: Requirements 2.7
    Feature: unghosted-core, Property 1: Caching returns consistent data
    """
    # Clear cache before test
    clear_cache()
    
    # Mock the fetch function to return consistent data
    mock_stops = {
        "place-haecl": {"name": "Harvard", "lat": 42.3655, "lon": -71.1096, "routes": ["1", "23"]},
        "place-kencl": {"name": "Kendall", "lat": 42.3626, "lon": -71.0882, "routes": ["28", "39"]},
    }
    
    with patch("core.static_load.fetch_and_cache_stops", return_value=mock_stops):
        # First call - should fetch
        result1 = get_stops()
        assert result1 == mock_stops
        
        # Second call within TTL - should return cached data (not call fetch again)
        result2 = get_stops()
        assert result2 == mock_stops
        
        # Property: both results are identical
        assert result1 is result2, "Cached results should be the same object"
        
        # Property: results have same content
        assert result1 == result2, "Cached results should have identical content"


def test_get_stations_caching_returns_consistent_data():
    """Property 1: Multiple calls within TTL must return same station data.
    
    Validates: Requirements 2.7
    Feature: unghosted-core, Property 1: Caching returns consistent data
    """
    # Clear cache before test
    clear_cache()
    
    # Mock the fetch function to return consistent data
    mock_stations = {
        "station_hub_001": {"name": "Harvard Station", "lat": 42.3657, "lon": -71.1096},
        "station_hub_002": {"name": "MIT Station", "lat": 42.3601, "lon": -71.0914},
    }
    
    with patch("core.static_load.fetch_and_cache_stations", return_value=mock_stations):
        # First call - should fetch
        result1 = get_stations()
        assert result1 == mock_stations
        
        # Second call within TTL - should return cached data
        result2 = get_stations()
        assert result2 == mock_stations
        
        # Property: both results are identical
        assert result1 is result2, "Cached results should be the same object"
        
        # Property: results have same content
        assert result1 == result2, "Cached results should have identical content"


def test_cache_expiry_and_refresh():
    """Test that cache expires after TTL and is refreshed.
    
    Property: Once TTL expires, next call should refresh the cache.
    
    Validates: Requirements 2.7
    Feature: unghosted-core, Property 1: Caching returns consistent data
    """
    clear_cache()
    
    # Initial mock data
    initial_stops = {
        "place-haecl": {"name": "Harvard", "lat": 42.3655, "lon": -71.1096, "routes": ["1"]},
    }
    
    # Updated mock data
    updated_stops = {
        "place-haecl": {"name": "Harvard Station", "lat": 42.3655, "lon": -71.1096, "routes": ["1", "2"]},
        "place-kencl": {"name": "Kendall", "lat": 42.3626, "lon": -71.0882, "routes": ["28"]},
    }
    
    fetch_count = 0
    
    def mock_fetch(config=None):
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count == 1:
            return initial_stops
        else:
            return updated_stops
    
    with patch("core.static_load.fetch_and_cache_stops", side_effect=mock_fetch):
        # First call
        result1 = get_stops()
        assert result1 == initial_stops
        assert fetch_count == 1
        
        # Second call within TTL - should use cache
        result2 = get_stops()
        assert result2 == initial_stops
        assert fetch_count == 1  # No additional fetch
        
        # Simulate TTL expiry by manually clearing the timestamp
        import core.static_load
        current_time = time.time()
        core.static_load._cache["stops_ts"] = current_time - (TTL_SECONDS + 1)
        
        # Third call after TTL expiry - should refresh
        result3 = get_stops()
        assert result3 == updated_stops
        assert fetch_count == 2  # Fetch was called again


def test_stations_cache_expiry_and_refresh():
    """Test that stations cache expires after TTL and is refreshed.
    
    Property: Once TTL expires, next call should refresh the cache.
    
    Validates: Requirements 2.7
    Feature: unghosted-core, Property 1: Caching returns consistent data
    """
    clear_cache()
    
    # Initial mock data
    initial_stations = {
        "station_hub_001": {"name": "Station 1", "lat": 42.365, "lon": -71.110},
    }
    
    # Updated mock data
    updated_stations = {
        "station_hub_001": {"name": "Station 1 Updated", "lat": 42.365, "lon": -71.110},
        "station_hub_002": {"name": "Station 2", "lat": 42.366, "lon": -71.111},
    }
    
    fetch_count = 0
    
    def mock_fetch(config=None):
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count == 1:
            return initial_stations
        else:
            return updated_stations
    
    with patch("core.static_load.fetch_and_cache_stations", side_effect=mock_fetch):
        # First call
        result1 = get_stations()
        assert result1 == initial_stations
        assert fetch_count == 1
        
        # Second call within TTL - should use cache
        result2 = get_stations()
        assert result2 == initial_stations
        assert fetch_count == 1  # No additional fetch
        
        # Simulate TTL expiry
        import core.static_load
        current_time = time.time()
        core.static_load._cache["stations_ts"] = current_time - (TTL_SECONDS + 1)
        
        # Third call after TTL expiry - should refresh
        result3 = get_stations()
        assert result3 == updated_stations
        assert fetch_count == 2


@given(st.just(1))
def test_stops_cache_respects_ttl_window(dummy):
    """Property 1: Cache should be valid for TTL seconds and invalid after.
    
    Validates: Requirements 2.7
    Feature: unghosted-core, Property 1: Caching returns consistent data
    """
    clear_cache()
    
    mock_stops = {
        "place-haecl": {"name": "Harvard", "lat": 42.3655, "lon": -71.1096, "routes": ["1"]},
    }
    
    with patch("core.static_load.fetch_and_cache_stops", return_value=mock_stops) as mock_fetch:
        # First call - cache empty, should fetch
        result1 = get_stops()
        assert mock_fetch.call_count == 1
        
        # Call immediately after - should use cache (within TTL)
        result2 = get_stops()
        assert mock_fetch.call_count == 1  # No additional call
        
        # Verify same data returned
        assert result1 == result2


@given(st.just(1))
def test_stations_cache_respects_ttl_window(dummy):
    """Property 1: Cache should be valid for TTL seconds and invalid after.
    
    Validates: Requirements 2.7
    Feature: unghosted-core, Property 1: Caching returns consistent data
    """
    clear_cache()
    
    mock_stations = {
        "station_hub_001": {"name": "Station 1", "lat": 42.365, "lon": -71.110},
    }
    
    with patch("core.static_load.fetch_and_cache_stations", return_value=mock_stations) as mock_fetch:
        # First call - cache empty, should fetch
        result1 = get_stations()
        assert mock_fetch.call_count == 1
        
        # Call immediately after - should use cache (within TTL)
        result2 = get_stations()
        assert mock_fetch.call_count == 1  # No additional call
        
        # Verify same data returned
        assert result1 == result2


def test_clear_cache_forces_refresh():
    """Test that clearing cache forces a refresh on next call.
    
    Property: After cache clear, next get_stops/get_stations should fetch fresh data.
    
    Validates: Requirements 2.7
    Feature: unghosted-core, Property 1: Caching returns consistent data
    """
    clear_cache()
    
    mock_stops = {
        "place-haecl": {"name": "Harvard", "lat": 42.3655, "lon": -71.1096, "routes": ["1"]},
    }
    
    fetch_count = 0
    
    def mock_fetch(config=None):
        nonlocal fetch_count
        fetch_count += 1
        return mock_stops
    
    with patch("core.static_load.fetch_and_cache_stops", side_effect=mock_fetch):
        # First call
        result1 = get_stops()
        assert fetch_count == 1
        
        # Second call within TTL
        result2 = get_stops()
        assert fetch_count == 1  # No additional fetch
        
        # Clear cache
        clear_cache()
        
        # Third call after clear - should fetch again
        result3 = get_stops()
        assert fetch_count == 2


def test_empty_cache_on_fetch_failure():
    """Test that empty dict is returned if fetch fails.
    
    Property: Fetch failures should return empty dict, not crash.
    
    Validates: Requirements 2.7
    Feature: unghosted-core, Property 1: Caching returns consistent data
    """
    clear_cache()
    
    # Mock fetch to raise exception
    with patch("core.static_load.fetch_and_cache_stops", side_effect=Exception("Network error")):
        result = get_stops()
        # Should return empty dict on failure
        assert result == {}
        assert isinstance(result, dict)
    
    # Verify cache is updated with empty dict
    with patch("core.static_load.fetch_and_cache_stops", side_effect=Exception("Still failing")):
        result2 = get_stops()
        assert result2 == {}


def test_fetch_and_cache_stops_returns_dict_structure():
    """Test that fetch_and_cache_stops returns correctly structured data.
    
    Property: Each stop in result must have name, lat, lon, and routes fields.
    
    Validates: Requirements 2.7
    Feature: unghosted-core, Property 1: Caching returns consistent data
    """
    clear_cache()
    
    mock_response = {
        "data": [
            {
                "id": "place-haecl",
                "attributes": {
                    "name": "Harvard Square",
                    "latitude": 42.3655,
                    "longitude": -71.1096,
                },
                "relationships": {
                    "routes": {
                        "data": [
                            {"id": "1"},
                            {"id": "23"},
                        ]
                    }
                },
            },
        ]
    }
    
    with patch("requests.get") as mock_get:
        mock_response_obj = MagicMock()
        mock_response_obj.json.return_value = mock_response
        mock_get.return_value = mock_response_obj
        
        result = fetch_and_cache_stops({"feeds": {"mbta_v3": "https://api-v3.mbta.com"}})
        
        # Property: result is dict
        assert isinstance(result, dict)
        
        # Property: each value has required fields
        for stop_id, stop_data in result.items():
            assert "name" in stop_data
            assert "lat" in stop_data
            assert "lon" in stop_data
            assert "routes" in stop_data
            assert isinstance(stop_data["routes"], list)


def test_fetch_and_cache_stations_returns_dict_structure():
    """Test that fetch_and_cache_stations returns correctly structured data.
    
    Property: Each station in result must have name, lat, and lon fields.
    
    Validates: Requirements 2.7
    Feature: unghosted-core, Property 1: Caching returns consistent data
    """
    clear_cache()
    
    mock_discovery = {
        "data": {
            "en": {
                "feeds": [
                    {
                        "name": "station_information",
                        "url": "https://gbfs.bluebikes.com/data/station_information.json",
                    }
                ]
            }
        }
    }
    
    mock_info = {
        "data": {
            "stations": [
                {
                    "station_id": "station_hub_001",
                    "name": "Harvard Station",
                    "lat": 42.3657,
                    "lon": -71.1096,
                },
            ]
        }
    }
    
    with patch("requests.get") as mock_get:
        # First call returns discovery, second returns station info
        mock_responses = [
            MagicMock(json=lambda: mock_discovery),
            MagicMock(json=lambda: mock_info),
        ]
        mock_get.side_effect = mock_responses
        
        result = fetch_and_cache_stations({"feeds": {"gbfs_discovery": "https://gbfs.bluebikes.com/gbfs/gbfs.json"}})
        
        # Property: result is dict
        assert isinstance(result, dict)
        
        # Property: each value has required fields
        for station_id, station_data in result.items():
            assert "name" in station_data
            assert "lat" in station_data
            assert "lon" in station_data
