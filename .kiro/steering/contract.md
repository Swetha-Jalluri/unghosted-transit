---
inclusion: always
---
# The contract (core/contracts.py + core/service.py). Fixed for the day.
mode: "live" (current feeds; failure raises LiveDataUnavailable) | "demo" (data/sample.db + artifacts/, else mocks in tests/fixtures/mock/) | "replay" (state at at_ts from sample.db or the mock timeline, with outcome filled). Unknown ids raise NotFound.

## service.py
- list_demo_stops() -> list[DemoStop]
- get_bus_trust(stop_id: str, mode: str = "demo", limit: int = 5, at_ts: int | None = None) -> BusTrustResponse
- get_dock_trust(station_id: str, walk_min: float = 5, mode: str = "demo", at_ts: int | None = None) -> DockTrustResponse
- get_nearby_docks(lat: float, lon: float, walk_min: float = 5, limit: int = 3, mode: str = "demo", at_ts: int | None = None) -> list[DockResult]
- get_findings() -> Findings
- get_health() -> Health
- get_replay_window() -> ReplayWindow

## contracts.py (pydantic; ? = optional/nullable)
- DemoStop: stop_id, name, routes: list[str]
- Backup: type ("bus"|"bike"), route_id?, station_id?, name?, status?, eta_min?, walk_min?, chance?
- ChanceBasis: method ("model"|"empirical"|"placeholder"), n: int
- Evidence: uncertainty?, vehicle_id?, location_age_sec?
- BusPrediction: route_id, trip_id, headsign?, app_eta_min: float, status ("confirmed"|"estimate"|"unreliable"), why: str, reason_codes: list[str], chance_it_arrives?: float, chance_basis: ChanceBasis, realistic_eta_min: [float, float], evidence: Evidence, backup?: Backup, outcome? ("served"|"vanished"|"canceled"|"open"; replay only)
- BusTrustResponse: stop_id, stop_name, generated_at (ISO str), mode, data_age_sec {trip_updates?, vehicle_positions?}, predictions: list[BusPrediction], hidden_count: int, attribution: list[str], disclaimer: str
- DockResult: station_id, name, lat, lon, app_bikes: int, usable_bikes_estimate: [int, int], chance_bike_on_arrival: float, status, why, reason_codes, last_reported_age_sec?, drain_per_min?
- DockTrustResponse: generated_at, mode, walk_min, dock: DockResult, backups: list[DockResult], attribution, disclaimer
- RateRow: group: str, rate: float, n: int
- Findings: generated_at, sample_label, window {start, end}, totals {labeled, served, vanished, canceled}, vanish_by_status: list[RateRow], vanish_by_uncertainty: list[RateRow], vanish_by_route: list[RateRow], eta_range_hit {range_hit, single_eta_hit, n}, least_reliable_docks: list[{station_id, name, metric, n}], model {method, auc?, brier?, n_labels}, calibration: list[{bin, predicted, observed, n}], eval {holdout_window?, n_train, n_test}, is_placeholder: bool
- Health: generated_at, last_poll_ts?, polls_last_hour: int, poll_success_rate?, rows {pred, veh, dock}, data_age_sec {trip_updates?, vehicle_positions?, docks?}, modes {demo: bool, live: bool, replay: bool}, model_method
- ReplayWindow: start, end (POSIX seconds), step_sec, n_snapshots
- Exceptions: LiveDataUnavailable, NotFound
