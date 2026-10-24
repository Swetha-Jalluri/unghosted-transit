---
inclusion: always
---
# Data facts (verify field paths on saved fixtures before coding)
Feeds (no key, poll every 45 s or slower; never faster):
- https://cdn.mbta.com/realtime/TripUpdates_enhanced.json
- https://cdn.mbta.com/realtime/VehiclePositions_enhanced.json
- Bluebikes GBFS auto-discovery gbfs.json (link on bluebikes.com/system-data; confirm URL, respect ttl)
- MBTA V3 API (stops/routes, optional free key in .env as MBTA_API_KEY): https://api-v3.mbta.com

MBTA bus StopTimeEvent.uncertainty: < 300 valid real-time; 300 schedule-based (no vehicle assigned yet); 301 stalled or significantly delayed; > 301 likely invalid, do not show.
Enhanced trip.revenue = false means non-revenue: never show. Absent means true.
schedule_relationship CANCELED / SKIPPED: trip or stop canceled.
Vehicle positions: current_stop_sequence, current_status (INCOMING_AT, STOPPED_AT, IN_TRANSIT_TO), timestamp = location age source.
GBFS station_status: num_bikes_available (excludes disabled), num_ebikes_available, num_bikes_disabled, num_docks_available, is_renting, is_installed, last_reported.

Labels per (trip_id, stop_id): SERVED (vehicle reached/passed the stop, or prediction stayed until within 1 min), VANISHED (disappeared while > 2 min before its time and no vehicle reached the stop), CANCELED, OPEN (still in feed).
Licenses: MassDOT Developers License Agreement (no logos, cite sources, don't overload servers); Bluebikes Data License Agreement. sample.db is derived data: attribute both.
