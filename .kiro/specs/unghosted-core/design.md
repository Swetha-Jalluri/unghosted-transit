# Design: Unghosted Core Pipeline

## Overview

The core pipeline fetches transit feeds (MBTA + Bluebikes), stores snapshots in SQLite, labels historical outcomes, trains a predictive model, and serves trust scores via a fixed contract. Three modes: **live** (current feeds), **demo** (sample.db or mocks), **replay** (historic with hindsight). All decision logic is pure, testable functions with property-based validation.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        service.py (Contract)                    │
│ get_bus_trust | get_dock_trust | get_nearby_docks | get_health  │
└────────┬─────────────────────────────────────────────────────────┘
         │
    ┌────┴────────────────────────────────────────┐
    │                                             │
   live                                      demo/replay
    │                                             │
┌───▼─────────────┐                   ┌───────────▼────────┐
│  feeds.py       │                   │  sample.db or      │
│  collector.py   │                   │  tests/fixtures/   │
│  data/raw.db    │                   │  mocks/            │
└───┬─────────────┘                   └───────────┬────────┘
    │                                             │
    └────────────────┬──────────────────┬────────┘
                     │                  │
         ┌───────────▼────┐    ┌────────▼──────────┐
         │  labeler.py    │    │  replay.py        │
         │  arrivals.py   │    │  get_replay_window│
         │  labels table  │    │  outcomes         │
         └────────┬───────┘    └────────┬──────────┘
                  │                     │
         ┌────────▼─────────────────────┘
         │
    ┌────▼──────────────────────────────┐
    │  bus_trust.py                      │
    │  dock_trust.py                     │
    │  backup.py                         │
    │  Pure decision functions           │
    └────┬───────────────────────────────┘
         │
    ┌────▼──────────────────────────────┐
    │  model.py                          │
    │  Logistic regression + fallback    │
    │  artifacts/model.joblib            │
    └────┬───────────────────────────────┘
         │
    ┌────▼──────────────────────────────┐
    │  findings.py                       │
    │  Calibration + metrics             │
    │  artifacts/findings.json           │
    └────────────────────────────────────┘
```

## Components and Interfaces

### feeds.py: Feed Fetching and Parsing

```python
def fetch_trip_updates() -> list[dict]
  """Fetch TripUpdates_enhanced.json; return flat records."""

def fetch_vehicle_positions() -> list[dict]
  """Fetch VehiclePositions_enhanced.json; return flat records."""

def fetch_gbfs_discovery() -> str
  """Fetch gbfs.json auto-discovery; return actual feed URL."""

def fetch_gbfs_status_info() -> tuple[list[dict], list[dict]]
  """Fetch station_status and station_information; return flat records."""

def save_fixture_snapshot(feed_name: str, data: list[dict]) -> None
  """Save raw feed to tests/fixtures/"""

def parse_trip_updates(raw: dict) -> list[dict]
  """Parse TripUpdates protobuf/JSON into flat records."""

def parse_vehicle_positions(raw: dict) -> list[dict]
  """Parse VehiclePositions protobuf/JSON into flat records."""

def parse_gbfs(status: dict, info: dict) -> list[dict]
  """Parse GBFS status + info into flat records."""
```

**Error Handling:** On parse error, log and skip record. Never crash.

### collector.py: Scheduled Collection and Storage

```python
def initialize_db() -> None
  """Create data/raw.db schema: pred_snap, veh_snap, dock_snap, poll_log."""

def poll_all_feeds(config: dict) -> None
  """Fetch all feeds, filter routes, insert snapshots, log result."""

def poll_loop(config: dict) -> None
  """Run poll_all_feeds every poll_seconds forever (with graceful shutdown)."""

def insert_pred_snap(db: sqlite3.Connection, rows: list[dict]) -> int
  """Insert into pred_snap; return count."""

def insert_veh_snap(db: sqlite3.Connection, rows: list[dict]) -> int
  """Insert into veh_snap; return count."""

def insert_dock_snap(db: sqlite3.Connection, rows: list[dict]) -> int
  """Insert into dock_snap; return count."""

def log_poll(db: sqlite3.Connection, success: bool, counts: dict, ages: dict) -> None
  """Record poll_log entry."""
```

**Retry Logic:** Exponential backoff with jitter, max 3 retries per cycle. On persistent failure, skip and log; continue.

### static_load.py: Stops and Stations Cache

```python
def fetch_and_cache_stops(config: dict) -> dict[str, dict]
  """Fetch MBTA V3 stops; return {stop_id: {name, lat, lon, routes}}."""

def fetch_and_cache_stations(config: dict) -> dict[str, dict]
  """Fetch Bluebikes stations; return {station_id: {name, lat, lon}}."""

def get_stops() -> dict[str, dict]
  """Get cached stops (refresh if stale)."""

def get_stations() -> dict[str, dict]
  """Get cached stations (refresh if stale)."""
```

**Caching:** In-memory cache with timestamp; refresh if > 1 hour old or on startup.

### labeler.py: Label Assignment

```python
def label_predictions(db: sqlite3.Connection, window: tuple[int, int]) -> None
  """For all predictions in window, assign label per (trip_id, stop_id)."""

def assign_label(pred: dict, veh_history: list[dict], pred_history: list[dict]) -> str
  """Return label: SERVED | VANISHED | CANCELED | OPEN."""

def flicker_filter(history: list[dict], ts: int) -> bool
  """Flicker logic: suppress label until prediction is old enough or vehicle confirmed."""
```

**Logic:**
- **SERVED**: Vehicle reached/passed stop, or prediction stayed until within 1 min.
- **VANISHED**: Disappeared > 2 min before arrival; no vehicle reached.
- **CANCELED**: schedule_relationship changed to CANCELED/SKIPPED.
- **OPEN**: Still in feed.

### arrivals.py: Arrival Metrics

```python
def record_arrivals(db: sqlite3.Connection) -> None
  """For all SERVED labels, compute arrival time and ETA error."""

def compute_eta_error(pred: dict, actual: int) -> float
  """Return actual - predicted in minutes."""
```

### bus_trust.py: Bus Trust Scoring (Pure Function)

```python
def compute_status_and_why(
  pred: dict,
  evidence: dict,
  vanish_rates: dict,
  model_chance: float | None,
) -> tuple[str, str, list[str], float | None]
  """Return (status, why, reason_codes, chance_it_arrives)."""
```

**Rules (applied in order):**
1. If revenue=false OR uncertainty > 301 → hidden (skip from response).
2. If schedule_relationship CANCELED → status=unreliable.
3. If uncertainty 300 or 301 → status = at most estimate.
4. If location_age_sec > 120 → status != confirmed.
5. If vehicle not moving → downgrade status.
6. If vanish_rate > threshold → status=unreliable, add backup.

**Chance:** From trained model (method=model, n=model.n_labels), or empirical label rate (method=empirical), or placeholder (method=placeholder, n=0).

**Realistic ETA:** Compute [low, high] from model quantiles or empirical distribution. If confirmed, must contain app_eta_min.

**Reason Codes:** "revenue_false", "high_uncertainty", "location_stale", "vehicle_not_moving", "high_vanish_rate", "schedule_canceled".

### dock_trust.py: Dock Trust Scoring (Pure Function)

```python
def compute_dock_status_and_chance(
  dock: dict,
  drain_rate: float | None,
  model_chance: float | None,
) -> tuple[str, str, list[str], float]
  """Return (status, why, reason_codes, chance_bike_on_arrival)."""
```

**Chance Logic:**
- If NOT is_renting → chance = 0.
- Else → Poisson parameter from observed departure rate over `drain_window_min`.

**Status:** confirmed/estimate/unreliable based on dock age, data quality, historical availability.

### backup.py: Backup Selection (Pure Function)

```python
def select_backups(
  primary: BusPrediction | DockResult,
  alternatives: list[BusPrediction | DockResult],
  primary_type: str,
) -> Backup | None
  """Return next-best backup (bus or bike)."""
```

**Rule:** Never return unreliable or hidden alternatives.

### model.py: Predictive Model

```python
def train_model(
  db: sqlite3.Connection,
  config: dict,
) -> tuple[LogisticRegression, dict]
  """Train on all labels except last hour; return model and metadata."""

def compute_metrics(model, y_test, y_pred_proba) -> dict[str, float]
  """Return {auc, brier, calibration_bins}."""

def empirical_fallback(db: sqlite3.Connection) -> dict
  """Return label rates by route/uncertainty if min_labels not met."""

def save_model(model: LogisticRegression, metadata: dict) -> None
  """Save to artifacts/model.joblib and artifacts/model_info.json."""
```

**Time-Based Holdout:** Train on (now - holdout_window) to (now - 1 hour); test on last hour.

**Metrics:**
- AUC: Area under ROC curve.
- Brier: Mean squared error of probability predictions.
- Calibration: Bins [0-0.1], [0.1-0.2], ..., [0.9-1.0] with predicted vs observed rate and n.

**Fallback:** If n_labels < min_labels, use empirical (label rate) with method=empirical.

### findings.py: Aggregate Findings

```python
def generate_findings(
  db: sqlite3.Connection,
  model: LogisticRegression | None,
  is_placeholder: bool,
) -> Findings
  """Compute all Findings fields from labels and poll_log."""
```

**Fields:**
- `generated_at`: ISO timestamp.
- `sample_label`: E.g., "SERVED".
- `window`: {start, end} POSIX seconds.
- `totals`: {labeled, served, vanished, canceled}.
- `vanish_by_status/uncertainty/route`: List of RateRow.
- `eta_range_hit`: {range_hit, single_eta_hit, n}.
- `least_reliable_docks`: List of {station_id, name, metric, n}.
- `model`: {method, auc, brier, n_labels}.
- `calibration`: List of {bin, predicted, observed, n}.
- `eval`: {holdout_window, n_train, n_test}.
- `is_placeholder`: true if demo or insufficient data; else false.

### replay.py: Historic Reconstruction

```python
def get_replay_window(db: sqlite3.Connection) -> ReplayWindow
  """Return start, end, step_sec, n_snapshots from poll_log."""

def rebuild_predictions_at(
  db: sqlite3.Connection,
  stop_id: str,
  at_ts: int,
) -> list[BusPrediction]
  """Query snapshots up to at_ts; apply labeling; return predictions with outcome."""

def finalize_outcome(pred: dict, label: str, label_ts: int, at_ts: int) -> str | None
  """Return outcome only if label_ts <= at_ts."""
```

**Critical Rule:** Never set outcome if it was finalized after at_ts. This prevents hindsight bias in replay.

### health.py: System Health

```python
def get_health_snapshot(db: sqlite3.Connection) -> Health
  """Compute Health from poll_log and row counts."""

def compute_poll_success_rate(db: sqlite3.Connection, window: int) -> float
  """Fraction of successful polls in window."""

def compute_data_age(db: sqlite3.Connection) -> dict[str, int]
  """Age of most recent snapshot per feed."""
```

### service.py: Contract Implementation (Fixed)

```python
def list_demo_stops() -> list[DemoStop]
def get_bus_trust(stop_id, mode="demo", limit=5, at_ts=None) -> BusTrustResponse
def get_dock_trust(station_id, walk_min=5, mode="demo", at_ts=None) -> DockTrustResponse
def get_nearby_docks(lat, lon, walk_min=5, limit=3, mode="demo", at_ts=None) -> list[DockResult]
def get_findings() -> Findings
def get_health() -> Health
def get_replay_window() -> ReplayWindow
```

**Modes:**
- **live**: Fetch current feeds via feeds.py; raise LiveDataUnavailable on failure.
- **demo**: Use sample.db if exists; else mocks from tests/fixtures/mock/.
- **replay**: Rebuild from sample.db with outcomes.

## Data Models

### Database Schema (SQLite)

**pred_snap:**
```
ts, stop_id, route_id, trip_id, app_eta_min, uncertainty, 
schedule_relationship, revenue, headsign
```

**veh_snap:**
```
ts, trip_id, route_id, stop_sequence, current_status, 
vehicle_timestamp, vehicle_id
```

**dock_snap:**
```
ts, station_id, app_bikes, num_docks_available, is_renting, 
is_installed, last_reported
```

**poll_log:**
```
ts, success, n_pred, n_veh, n_dock, data_age_trip_updates, 
data_age_vehicle_positions, data_age_docks
```

**labels** (created by labeler.py):
```
trip_id, stop_id, label, ts_labeled
```

### Response Models (from contracts.py - do not change)

All Pydantic models in contracts.py are fixed and must not be modified.

## Correctness Properties

A property is a characteristic that should hold true across all valid executions—a formal specification for machine verification via property-based testing.

### Property 1: Chances in [0, 1]

*For any* BusPrediction or DockResult, the chance field (chance_it_arrives or chance_bike_on_arrival) must be in [0, 1].

**Validates: Requirements 4.3**

### Property 2: Hidden Filtering

*For any* BusPrediction with revenue=false OR uncertainty > 301, the prediction must be hidden (not in BusTrustResponse.predictions; hidden_count incremented).

**Validates: Requirements 4.1, Requirement 7.4**

### Property 3: Location Age > 120s Never Confirmed

*For any* BusPrediction with location_age_sec > 120, the status must never be "confirmed".

**Validates: Requirements 4.1**

### Property 4: Uncertainty 300/301 Never Confirmed

*For any* BusPrediction with uncertainty in {300, 301}, the status must never be "confirmed".

**Validates: Requirements 4.1**

### Property 5: Non-Renting Dock Chance is Zero

*For any* DockResult with is_renting=false, the chance_bike_on_arrival must be 0.

**Validates: Requirements 4.2**

### Property 6: Backups Never Unreliable or Hidden

*For any* BusPrediction or DockResult with a Backup, the backup must have status != "unreliable" and must not be hidden (revenue=true and uncertainty <= 301).

**Validates: Requirements 4.6**

### Property 7: ETA Range Validity

*For any* BusPrediction, realistic_eta_min[0] <= realistic_eta_min[1]. If status="confirmed", realistic_eta_min must contain app_eta_min.

**Validates: Requirements 4.4**

### Property 8: One Label per (trip_id, stop_id)

*For any* trip_id and stop_id, the labels table must contain exactly one row.

**Validates: Requirements 3.1, 3.5**

### Property 9: Replay Outcome Timeliness

*For any* replay query at at_ts, if a BusPrediction has outcome set, the outcome must have been finalized before or at at_ts (never from the future).

**Validates: Requirements 6.2, 6.3**

## Error Handling

- **Parse Errors**: Log and skip record. Never crash.
- **Network Failures**: Retry with backoff; log failure; continue.
- **Database Errors**: Log and propagate (caller decides).
- **Invalid Stop/Station**: Raise NotFound.
- **Live Mode Fetch Failure**: Raise LiveDataUnavailable.
- **Missing Fixtures (Demo)**: Raise FileNotFoundError; fallback to mocks.

## Testing Strategy

**Unit Tests:**
- Specific examples (valid snapshots, expected outcomes).
- Integration (collector → labeler → bus_trust).
- Edge cases (empty feeds, stale data, network errors).

**Property-Based Tests (Hypothesis):**
- P1–P9: Generate random predictions, docks, labels; verify properties hold.
- Generators constrain to realistic input space (e.g., uncertainty in range, chance in [0,1]).
- Minimum 100 iterations per property.
- Tag format: `Feature: unghosted-core, Property {N}: {title}`

**Dual Approach:**
- Unit tests catch concrete bugs and integration issues.
- Property tests verify universal correctness across input space.
- Together: comprehensive coverage.
