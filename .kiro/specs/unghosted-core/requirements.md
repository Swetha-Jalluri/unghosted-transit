# Requirements: Unghosted Core Pipeline

## Introduction

Build the core data pipeline and decision engine that powers Unghosted—a trust layer for transit. The pipeline fetches live feeds (MBTA and Bluebikes), labels historical outcomes, trains a predictive model, and serves bus/dock trust scores. It must support three modes: live (current feeds), demo (sample database + mocks), and replay (historic data with hindsight outcomes). Never change contract names or signatures in `core/contracts.py` or `core/service.py`.

## Glossary

- **BusTrustResponse**: Predictions for a stop including status, chance, and realistic ETA range.
- **DockTrustResponse**: Bike availability prediction for a station with backup options.
- **Findings**: Model calibration, vanish rates, and reliability metrics.
- **Health**: System status snapshot (polls, data age, available modes).
- **ReplayWindow**: Time range for replay mode with snapshot metadata.
- **BusPrediction**: Single prediction (route, trip, ETA, status, why, reason codes, chance, evidence, backup, outcome).
- **DockResult**: Single dock with bikes, chance, status, why, reason codes.
- **Status**: "confirmed" (green), "estimate" (amber), "unreliable" (red).
- **Hidden**: Prediction excluded from response (revenue=false or uncertainty>301).
- **Vanished**: Vehicle disappeared before arrival with no confirmation.
- **Served**: Vehicle reached the stop or prediction stayed within 1 min.
- **Canceled**: GTFS schedule_relationship CANCELED/SKIPPED.
- **Open**: Still in current feed.
- **Chance**: Probability in [0,1] with basis (model, empirical, placeholder) and sample size n.
- **Realistic_eta_min**: [low, high] in minutes; confirmed range must contain app_eta_min.
- **Evidence**: Uncertainty (< 300 = real-time, 300 = schedule-based, 301+ = invalid), vehicle_id, location_age_sec.
- **Poll_log**: Record of each fetch cycle (ts, success, row counts, data age).
- **Pred_snap**: Bus prediction snapshot (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty, status, ...).
- **Veh_snap**: Vehicle position snapshot (ts, trip_id, route_id, stop_sequence, current_status, timestamp).
- **Dock_snap**: Bike availability snapshot (ts, station_id, app_bikes, is_renting, last_reported).

## Requirements

### Requirement 1: Feed Fetching and Parsing

**User Story:** As the core engine, I want to fetch and parse MBTA and Bluebikes feeds, so that I have fresh data to label and model.

#### Acceptance Criteria

1. WHEN `feeds.py` is called to fetch TripUpdates, VehiclePositions, and GBFS, THE Fetcher SHALL fetch each feed over HTTPS with the URLs from config.yaml.
2. WHEN a feed is fetched successfully, THE Fetcher SHALL parse it into flat records (dict-like) matching the feed schema from data.md.
3. WHEN parsing TripUpdates_enhanced.json, THE Fetcher SHALL extract stop_time_updates (stop_id, arrival/departure uncertainty, schedule_relationship, revenue) per trip.
4. WHEN parsing VehiclePositions_enhanced.json, THE Fetcher SHALL extract vehicle position (route_id, trip_id, current_stop_sequence, current_status, timestamp) per entity.
5. WHEN parsing GBFS station_status and station_information, THE Fetcher SHALL extract dock state (station_id, num_bikes_available, num_docks_available, is_renting, is_installed, last_reported).
6. WHEN a record is missing required fields, THE Fetcher SHALL log and skip it; never crash.
7. WHEN feeds are first fetched, THE Fetcher SHALL save one raw JSON snapshot of each feed to tests/fixtures/ (trip_updates.json, vehicle_positions.json, stations.json).
8. WHEN serving demo mode, THE service SHALL parse and use tests/fixtures/ snapshots, never live feeds.

### Requirement 2: Data Collection and Storage

**User Story:** As the core engine, I want to collect feeds on a schedule and store snapshots in SQLite, so that I can label and model historical outcomes.

#### Acceptance Criteria

1. WHEN the Collector runs, THE Collector SHALL fetch all feeds every poll_seconds from config.yaml (minimum 45 s).
2. WHEN fetching, THE Collector SHALL keep only routes listed in config.yaml routes.
3. WHEN a fetch succeeds, THE Collector SHALL insert rows into data/raw.db tables: pred_snap (ts, stop_id, route_id, trip_id, app_eta_min, uncertainty, ...), veh_snap (ts, trip_id, route_id, stop_sequence, current_status, timestamp, ...), dock_snap (ts, station_id, app_bikes, is_renting, ...).
4. WHEN a fetch fails, THE Collector SHALL retry with exponential backoff (max 3 retries, jitter); log failure and continue.
5. WHEN a fetch cycle completes, THE Collector SHALL record poll_log (ts, success, n_pred, n_veh, n_dock, data_age_sec).
6. WHEN running in demo mode, THE Collector SHALL use sample.db (read-only); skip live fetching.
7. THE static_load.py module SHALL fetch and cache MBTA V3 stops and Bluebikes stations (station_id, name, lat, lon) on startup; refresh if stale.

### Requirement 3: Label Generation and Arrival Observations

**User Story:** As the core engine, I want to label historical predictions with outcomes (SERVED, VANISHED, CANCELED, OPEN), so that I can train a predictive model.

#### Acceptance Criteria

1. WHEN labeling predictions, THE Labeler SHALL assign one label per (trip_id, stop_id): SERVED if vehicle reached/passed stop or prediction stayed until within 1 min; VANISHED if disappeared > 2 min before; CANCELED if schedule_relationship changed; OPEN if still in feed.
2. WHEN a trip is marked CANCELED in any snapshot, THE Labeler SHALL propagate CANCELED to all affected stops.
3. WHEN a vehicle vanishes, THE Labeler SHALL record the disappearance without backtracking.
4. THE arrivals.py module SHALL record observed arrival times and ETA errors (actual - predicted in minutes).
5. WHEN computing metrics, THE Labeler SHALL ensure no duplicate labels per (trip_id, stop_id).
6. WHEN labeling, THE Labeler SHALL use flicker logic (no label until prediction is old enough or vehicle confirmed).

### Requirement 4: Bus and Dock Trust Scoring

**User Story:** As the core engine, I want to compute trust scores (status, chance, why, reason codes, realistic ETA range), so that the service layer can respond to queries.

#### Acceptance Criteria

1. WHEN scoring a bus prediction, THE bus_trust module SHALL determine status and reason codes using rules:
   - Hide (hidden_count++) if revenue=false OR uncertainty > 301.
   - Set status=unreliable if schedule_relationship CANCELED.
   - Set status to at most estimate if uncertainty 300 or 301.
   - Set status to never confirmed if location_age_sec > 120.
   - Downgrade status if vehicle not moving.
   - Set status unreliable and add backup if vanish_rate > threshold.
2. WHEN scoring a dock, THE dock_trust module SHALL set chance=0 if NOT is_renting; else compute chance via Poisson on observed departure rate.
3. WHEN computing chance_it_arrives, THE bus_trust module SHALL use the trained model (method=model), empirical label rate (method=empirical), or placeholder (method=placeholder) with sample size n > 0.
4. WHEN computing realistic_eta_min, THE bus_trust module SHALL compute [low, high] range; if status=confirmed, range MUST contain app_eta_min.
5. WHEN computing usable_bikes_estimate, THE dock_trust module SHALL compute [low, high] estimate from app_bikes and historical drain.
6. THE backup.py module SHALL select bus or bike backup options; never select unreliable or hidden backups.
7. ALL reason codes SHALL be in a predefined set (e.g., "revenue_false", "high_uncertainty", "location_stale", "vehicle_not_moving", "high_vanish_rate", "schedule_canceled").

### Requirement 5: Predictive Modeling

**User Story:** As the core engine, I want to train a model to predict arrival certainty, so that I can emit chances with statistical backing.

#### Acceptance Criteria

1. WHEN training, THE model.py module SHALL use logistic regression on labeled data with time-based holdout (train on all but last hour, test on last hour).
2. WHEN training, THE model SHALL compute AUC (area under ROC curve) and Brier score on test set.
3. WHEN training, THE model SHALL generate calibration bins (e.g., [0-0.1], [0.1-0.2], ..., [0.9-1.0]) with predicted vs observed rate and count n per bin.
4. WHEN there are fewer than min_labels (from config), THE model SHALL fall back to empirical (label rate per route or uncertainty) with method=empirical.
5. WHEN there are fewer than min_vanished predictions, vanish metrics SHALL be marked with low confidence.
6. THE findings.py module SHALL populate all Findings fields: generated_at, sample_label (e.g., "SERVED"), window, totals, vanish_by_status/uncertainty/route, eta_range_hit, least_reliable_docks, model, calibration, eval, is_placeholder.
7. WHEN in demo or insufficient data, THE Findings SHALL set is_placeholder=true; else false.

### Requirement 6: Replay and Hindsight Outcomes

**User Story:** As the core engine, I want to replay service queries at historic timestamps with hindsight outcomes, so that users can explore what actually happened.

#### Acceptance Criteria

1. WHEN get_replay_window() is called, THE replay.py module SHALL return ReplayWindow with start, end (POSIX seconds), step_sec (from config), n_snapshots.
2. WHEN rebuilding a prediction at a past timestamp, THE replay module SHALL query snapshots up to at_ts, apply labeling logic, and populate outcome field (SERVED, VANISHED, CANCELED, OPEN).
3. WHEN generating outcomes in replay mode, THE replay module SHALL ensure outcome is only set if the label was finalized before at_ts (never show an outcome before it happened).
4. THE health.py module SHALL populate Health from poll_log: last_poll_ts, polls_last_hour, poll_success_rate, rows {pred, veh, dock}, data_age_sec, modes (demo=always true, live=if live fetching, replay=always true), model_method.

### Requirement 7: Service Layer Integration

**User Story:** As the service layer, I want to query the core pipeline in three modes, so that I can serve live, demo, and replay queries.

#### Acceptance Criteria

1. WHEN service.py is called in live mode, THE service SHALL fetch current feeds via feeds.py and use live database data; raise LiveDataUnavailable if fetch fails.
2. WHEN service.py is called in demo mode, THE service SHALL use sample.db if it exists; else use mocks from tests/fixtures/mock/.
3. WHEN service.py is called in replay mode at at_ts, THE service SHALL rebuild predictions from sample.db snapshots with outcomes populated.
4. WHEN get_bus_trust(stop_id, mode, limit, at_ts) is called, THE service SHALL populate BusTrustResponse with stop_id, stop_name, generated_at, mode, data_age_sec, predictions (up to limit), hidden_count, attribution, disclaimer.
5. WHEN get_dock_trust(station_id, walk_min, mode, at_ts) is called, THE service SHALL populate DockTrustResponse with dock (DockResult for station_id), backups (other docks), and metadata.
6. WHEN get_nearby_docks(lat, lon, walk_min, limit, mode) is called, THE service SHALL return list[DockResult] sorted by distance, capped at limit.
7. WHEN an unknown stop_id or station_id is queried, THE service SHALL raise NotFound.

### Requirement 8: Sample Database and Artifacts

**User Story:** As the core engine, I want to package data and models for demo and replay, so that users can explore without live feeds.

#### Acceptance Criteria

1. WHEN make_sample.py is run, THE script SHALL trim raw.db into data/sample.db (< 25 MB) preserving snapshots needed for replay and model training.
2. WHEN sample.db is created, it SHALL include pred_snap, veh_snap, dock_snap, poll_log, and a labels table (trip_id, stop_id, label, ts_labeled).
3. WHEN findings are computed, THE findings.py module SHALL serialize to artifacts/findings.json (all Findings fields).
4. WHEN a model is trained, THE model.py module SHALL serialize to artifacts/model.joblib and artifacts/model_info.json (method, AUC, Brier, n_labels).

## Testing Strategy

Property-based tests (Hypothesis) will validate correctness properties across generated inputs:

- P1: All chances in [0, 1].
- P2: If revenue=false OR uncertainty > 301, prediction is hidden.
- P3: If location_age_sec > 120, status never confirmed.
- P4: If uncertainty 300 or 301, status never confirmed.
- P5: If dock is_renting=false, chance_bike_on_arrival = 0.
- P6: Backups never have status=unreliable or hidden.
- P7: Realistic_eta_min[0] <= realistic_eta_min[1]; if confirmed, range contains app_eta_min.
- P8: Exactly one label per (trip_id, stop_id).
- P9: In replay, outcome is only set if outcome was finalized before at_ts.

Unit tests will verify specific examples, edge cases, and integration points.
