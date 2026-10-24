# Data: Sources, Licenses, and Architecture

## Overview

Unghosted collects real-time transit data from two public sources and processes it through a pipeline that validates, labels, and serves predictions of bus arrivals and bike availability.

## Data Sources

### MBTA Real-Time Feeds

- **Trip Updates:** https://cdn.mbta.com/realtime/TripUpdates_enhanced.json
- **Vehicle Positions:** https://cdn.mbta.com/realtime/VehiclePositions_enhanced.json

Both feeds are polled every 45 seconds and contain Protocol Buffer data (parsed to JSON). The feeds provide:
- **Trip Updates:** Predicted arrival/departure times and schedule changes per stop on a trip.
- **Vehicle Positions:** Current vehicle location, bearing, occupancy, and status (e.g., IN_TRANSIT_TO, STOPPED_AT).

**Accessibility:** Public, no authentication required (optional free API key for V3 stops/routes).

### Bluebikes GBFS

- **Discovery:** Auto-discovery endpoint specified in Bluebikes system data page.
- **Station Status:** Real-time dock availability, bike counts, rental/return availability.
- **Station Information:** Static metadata (station ID, name, latitude, longitude, capacity).

Polled every 45 seconds per GBFS feed TTL.

**Accessibility:** Public, no authentication required.

### MBTA V3 API

- **Endpoint:** https://api-v3.mbta.com
- **Use:** Fetch static stop and route metadata (names, coordinates).

**Accessibility:** Public, optional free API key via .env as `MBTA_API_KEY`.

---

## Licenses and Attribution

**Unghosted is not affiliated with or endorsed by MBTA, MassDOT, or Bluebikes.**

### MassDOT Developers License Agreement

- **Applies to:** MBTA GTFS-realtime feeds and V3 API data.
- **Key terms:**
  - No logos or brand marks; cite sources.
  - Do not overload servers (minimum 45 s poll interval).
  - Use data for research, development, and rider-facing applications.
- **Attribution required:** "Data: MBTA GTFS-realtime (MassDOT Developers License Agreement)"

### Bluebikes Data License Agreement

- **Applies to:** GBFS station status and information.
- **Key terms:**
  - Respect system status (is_installed, is_renting flags).
  - Attribute Bluebikes in all outputs.
- **Attribution required:** "Bluebikes GBFS (Bluebikes Data License Agreement)"

### Derived Data (sample.db)

Data in `data/sample.db` is derived from both MBTA and Bluebikes feeds. It remains subject to both licenses when shared or published.

**Combined Attribution:**
> Data: MBTA GTFS-realtime (MassDOT Developers License Agreement); Bluebikes GBFS (Bluebikes Data License Agreement).

---

## Polling and Collection

### Schedule

- **Interval:** Every 45 seconds (minimum, per GBFS spec and license).
- **Sources:** Fetch all three live feeds concurrently; skip any that timeout.
- **Retry logic:** Exponential backoff with jitter (max 3 retries per cycle); log failures; continue.

### Data Storage

#### `data/raw.db`

Raw snapshots collected by the collector. Contains:

| Table | Purpose | Retention |
|-------|---------|-----------|
| `pred_snap` | Bus prediction snapshots (one row per trip-stop prediction per poll) | All history |
| `veh_snap` | Vehicle position snapshots (one row per vehicle per poll) | All history |
| `dock_snap` | Bike dock status snapshots (one row per station per poll) | All history |
| `poll_log` | Metadata: fetch timestamps, success/failure, row counts, data age | All history |

**Schema notes:**
- Timestamps stored as POSIX seconds (UTC).
- Foreign keys: (trip_id, stop_id) link pred_snap to labels.
- Indexes on (trip_id, stop_id, ts) for efficient labeling queries.

#### `data/sample.db`

Trimmed snapshot of `raw.db` for demo and replay modes. Target size < 25 MB.

Contents:
- `pred_snap`, `veh_snap`, `dock_snap`, `poll_log` (filtered history, same schema as raw.db).
- `labels` (enriched labels: trip_id, stop_id, label, route_id, uncertainty_bucket, first_status, ts_labeled).

**Purpose:** Enables replay mode (hindsight outcomes) and offline demo without raw.db present.

#### Artifacts

Computed outputs saved for demo/replay:

| File | Content | Purpose |
|------|---------|---------|
| `artifacts/findings.json` | Findings object (vanish rates, totals, model calibration) | Demo findings endpoint |
| `artifacts/model.joblib` | Trained logistic regression model | Prediction scoring (not yet implemented) |
| `artifacts/model_info.json` | Model metadata (AUC, Brier, n_labels) | Model provenance |

---

## Data Architecture

```
┌──────────────────────────────────────────┐
│  Live Feeds (every 45 s)                 │
│  - TripUpdates_enhanced.json             │
│  - VehiclePositions_enhanced.json        │
│  - GBFS station_status + info            │
└──────────────────┬───────────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │  feeds.py       │
         │  Parse & flatten│
         └────────┬────────┘
                  │
         ┌────────▼────────┐
         │  collector.py   │
         │  Poll loop      │
         │  Retry + log    │
         └────────┬────────┘
                  │
         ┌────────▼────────────┐
         │  data/raw.db        │
         │ (All history)       │
         └────────┬────────────┘
                  │
    ┌─────────────┼──────────────┐
    │             │              │
    ▼             ▼              ▼
 labeler.py   make_sample.py  findings.py
 (labels)     (trimmed)       (metrics)
    │             │              │
    ▼             ▼              ▼
labels.db   sample.db      findings.json
            model.joblib
            model_info.json
```

---

## Data Privacy and Collection

### Personal Data

Unghosted does **not** collect, store, or process personal data:
- No user identity tracking.
- No location requests (uses stop picker for demo).
- No analytics or event logging.
- No cookies or analytics trackers.

### Public Data Only

All data collected is:
- Publicly available via open feeds.
- Attribution-linked to source (MBTA, Bluebikes).
- Stored in encrypted database at rest (optional, via .env).

### Data Retention

- `raw.db` grows indefinitely (can be archived or rotated).
- `sample.db` is trimmed to < 25 MB and committed to the repository (for demo/replay).
- Mock fixtures in `tests/fixtures/` are real snapshots trimmed for test reproducibility.

---

## Configuration

All URLs, thresholds, and poll intervals are defined in `config.yaml` (or `.env` for secrets). Never hardcoded in code.

**Example (config.yaml):**
```yaml
poll_seconds: 45
routes:
  - 1
  - 23
  - 28
  - 39
  - 66
  - 111
demo_stops:
  - place-haecl
  - place-kencl
  - place-neast
thresholds:
  min_labels: 300
  vanish_margin_s: 120
```

**Secrets (.env, not committed):**
```
MBTA_API_KEY=<optional key for V3 API>
```

---

## Disclaimer

**Unofficial. Not affiliated with or endorsed by MBTA, MassDOT or Bluebikes. For information only.**

Predictions and metrics are for informational purposes only. Do not use Unghosted as your primary source of truth for transit reliability. Consult official MBTA and Bluebikes systems for service alerts, real-time updates, and operational decisions.

---

**Last updated:** October 24, 2026  
**Sources:** MBTA GTFS-realtime, Bluebikes GBFS, MBTA V3 API  
**Repository:** Unghosted core pipeline (owner: Swetha)
