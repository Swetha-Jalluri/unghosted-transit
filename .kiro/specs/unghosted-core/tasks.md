# Implementation Plan: Unghosted Core Pipeline

## Overview

Build the core pipeline in order: feeds → collector → static_load → labeler → arrivals → bus_trust/dock_trust/backup → model → findings → replay/health → service (integration). Each task builds on previous steps. Property-based tests validate correctness properties P1–P9 as specified in the design.

## Tasks

- [x] 1. Set up database schema and test fixtures
  - Create data/raw.db schema (pred_snap, veh_snap, dock_snap, poll_log, labels tables).
  - Create tests/fixtures/ raw feed snapshots (trip_updates.json, vehicle_positions.json, stations.json) with real or realistic data.
  - _Requirements: 2.3, 1.7_

- [ ] 2. Implement feeds.py
  - Implement fetch_trip_updates(), fetch_vehicle_positions(), fetch_gbfs_discovery(), fetch_gbfs_status_info() with HTTPS requests.
  - Implement parse_trip_updates(), parse_vehicle_positions(), parse_gbfs() to flatten records.
  - Implement save_fixture_snapshot() to persist raw JSON to tests/fixtures/.
  - Log and skip records on parse error; never crash.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [ ] 2.1 Write property tests for feeds.py parsing
  - **Property 1: Parse produces flat records** - For any valid feed JSON, parsing must produce a list of dicts with required fields.
  - **Property 2: Malformed records skipped** - For any feed with missing fields, parser must skip and never raise.
  - _Requirements: 1.2, 1.6_

- [ ] 3. Implement collector.py
  - Implement initialize_db() to create schema in data/raw.db.
  - Implement poll_all_feeds() to fetch all feeds, filter by configured routes, insert into pred_snap/veh_snap/dock_snap.
  - Implement insert_pred_snap(), insert_veh_snap(), insert_dock_snap(), log_poll().
  - Implement retry logic with exponential backoff (max 3 retries, jitter); log failures; never crash.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 3.1 Write property tests for collector.py route filtering
  - **Property 1: Only configured routes inserted** - For any snapshot with mixed routes, only those in config.yaml routes must be inserted.
  - _Requirements: 2.2_

- [ ] 4. Implement static_load.py
  - Implement fetch_and_cache_stops() (MBTA V3 API) and fetch_and_cache_stations() (Bluebikes GBFS).
  - Implement get_stops(), get_stations() with in-memory cache and 1-hour TTL.
  - _Requirements: 2.7_

- [ ] 4.1 Write property tests for static_load.py caching
  - **Property 1: Caching returns consistent data** - Multiple calls must return same data within TTL.
  - _Requirements: 2.7_

- [ ] 5. Implement labeler.py
  - Implement assign_label() to return SERVED | VANISHED | CANCELED | OPEN per (trip_id, stop_id).
  - Implement label_predictions() to iterate all predictions in a window and store labels.
  - Implement flicker_filter() to suppress labels until prediction is old or vehicle confirmed.
  - _Requirements: 3.1, 3.2, 3.3, 3.6_

- [ ] 5.1 Write property tests for labeler.py
  - **Property 8: One label per (trip_id, stop_id)** - For any set of snapshots, exactly one label per (trip_id, stop_id).
  - **Property 2: CANCELED propagation** - If trip marked CANCELED, all stops must have label CANCELED.
  - _Requirements: 3.1, 3.2, 3.5_

- [ ] 6. Implement arrivals.py
  - Implement record_arrivals() to compute arrival time and ETA error for all SERVED labels.
  - Implement compute_eta_error() to return actual - predicted in minutes.
  - _Requirements: 3.4_

- [ ] 7. Implement bus_trust.py (pure function)
  - Implement compute_status_and_why() to apply status rules in order: revenue, CANCELED, uncertainty, location_age, motion, vanish_rate.
  - Return (status, why, reason_codes, chance_it_arrives).
  - _Requirements: 4.1, 4.3, 4.4_

- [ ] 7.1 Write property tests for bus_trust.py status rules
  - **Property 2: Hidden filtering** - If revenue=false OR uncertainty > 301, must be hidden.
  - **Property 3: Location age > 120s never confirmed** - If location_age_sec > 120, status != confirmed.
  - **Property 4: Uncertainty 300/301 never confirmed** - If uncertainty in {300, 301}, status != confirmed.
  - **Property 1: Chances in [0, 1]** - All chance_it_arrives in [0, 1].
  - _Requirements: 4.1_

- [ ] 8. Implement dock_trust.py (pure function)
  - Implement compute_dock_status_and_chance() to compute status and chance_bike_on_arrival.
  - Chance = 0 if NOT is_renting; else Poisson(drain_rate).
  - _Requirements: 4.2_

- [ ] 8.1 Write property tests for dock_trust.py
  - **Property 5: Non-renting dock chance zero** - If is_renting=false, chance_bike_on_arrival = 0.
  - **Property 1: Dock chances in [0, 1]** - All chance_bike_on_arrival in [0, 1].
  - _Requirements: 4.2_

- [ ] 9. Implement backup.py (pure function)
  - Implement select_backups() to select next-best backup (bus or bike).
  - Never return unreliable or hidden alternatives.
  - _Requirements: 4.6_

- [ ] 9.1 Write property tests for backup.py
  - **Property 6: Backups never unreliable or hidden** - All backups must have status != unreliable and revenue=true, uncertainty <= 301.
  - _Requirements: 4.6_

- [ ] 10. Implement model.py
  - Implement train_model() with logistic regression on labels, time-based holdout (last hour test set).
  - Implement compute_metrics() to return AUC, Brier, calibration bins with n per bin.
  - Implement empirical_fallback() if n_labels < min_labels.
  - Implement save_model() to artifacts/model.joblib and artifacts/model_info.json.
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 10.1 Write property tests for model.py metrics
  - **Property 1: Model chances in [0, 1]** - Predicted probabilities and empirical rates in [0, 1].
  - _Requirements: 5.2_

- [ ] 11. Implement findings.py
  - Implement generate_findings() to compute all Findings fields: totals, vanish_by_status/uncertainty/route, eta_range_hit, least_reliable_docks, model, calibration, eval.
  - Set is_placeholder=true if demo or n_labels < min_labels; else false.
  - _Requirements: 5.5, 5.6, 5.7_

- [ ] 11.1 Write property tests for findings.py
  - **Property 1: Findings is_placeholder logic** - is_placeholder=true iff in demo or n_labels < min_labels.
  - _Requirements: 5.7_

- [ ] 12. Implement replay.py and health.py
  - Implement get_replay_window() to return ReplayWindow from poll_log.
  - Implement rebuild_predictions_at(stop_id, at_ts) to query snapshots up to at_ts and apply labeling with outcome.
  - Implement finalize_outcome() to set outcome only if label_ts <= at_ts.
  - Implement get_health_snapshot() to compute Health from poll_log.
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 12.1 Write property tests for replay.py outcomes
  - **Property 9: Replay outcome timeliness** - outcome is only set if finalized before or at at_ts.
  - _Requirements: 6.3_

- [ ] 13. Integrate service.py with live, demo, and replay modes
  - Refactor get_bus_trust() to detect mode and call appropriate backend (live via feeds/collector, demo via sample.db/mocks, replay via replay.py).
  - Refactor get_dock_trust(), get_nearby_docks() similarly.
  - Implement Findings (demo placeholder by default; real if sample.db exists with trained model).
  - Implement Health to query poll_log.
  - Ensure all responses include attribution and disclaimer.
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [ ] 14. Implement make_sample.py
  - Implement script to trim data/raw.db into data/sample.db (< 25 MB).
  - Preserve pred_snap, veh_snap, dock_snap, poll_log, labels needed for replay and model training.
  - _Requirements: 8.1, 8.2_

- [ ] 15. Checkpoint - Ensure all tests pass
  - Run `uv run pytest -q tests/core/` and verify all unit tests and property tests pass.
  - Verify sample.db is < 25 MB if created.
  - Verify artifacts/ contains findings.json, model.joblib, model_info.json if trained.
  - Verify all contract functions (get_bus_trust, get_dock_trust, etc.) work in demo mode.

## Notes

- Tasks marked with `*` are optional property-based tests; focus on core implementation first.
- Each property test task references a specific design property (P1–P9).
- Never modify contract.py or service.py function signatures.
- Use `uv run pytest -q` for all test runs.
- All decision logic (bus_trust, dock_trust, backup, model, replay) must be pure functions (no side effects).
- Demo mode always works; live mode raises LiveDataUnavailable if feeds fail.
- Replay mode never shows hindsight (outcome) before it happens (Property 9).
