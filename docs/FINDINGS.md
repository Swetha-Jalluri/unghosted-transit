# Findings: Unghosted Saturday Sample (October 24, 2026)

## Overview

This document reports findings from a sample of MBTA bus predictions collected on Saturday, October 24, 2026. The data shows how often predictions came true (served), disappeared before arrival, or were canceled across different prediction statuses, uncertainty levels, and routes.

**Key Headline:**
Predictions with uncertainty of 300 or higher (schedule-based, no vehicle assigned) vanished at **12.9%**, compared to **8.0%** for predictions with vehicle data (uncertainty < 300). Route 66 had the highest vanish rate at **13.1%** across all routes measured.

## Data Summary

| Metric | Value |
|--------|-------|
| Total Labeled Predictions | 3,453 |
| Predictions Served | 3,052 (88.4%) |
| Predictions Disappeared | 281 (8.1%) |
| Predictions Canceled | 0 (0%) |
| Collection Window | Saturday, Oct 24 (approx. 95 minutes) |
| Prediction Age at Labeling | > 5 minutes old |

## Disappearance Rate by Status at First Sighting

Predictions fade over time. This table shows disappearance rate by the status assigned when we first saw the prediction.

| First Sighting Status | Vanished | Total | Rate | Sample Size |
|-----------------------|----------|-------|------|------------|
| Estimate | 248 | 2,965 | 8.4% | 2,965 |
| Confirmed | 33 | 368 | 9.0% | 368 |

**Interpretation:** Predictions marked "confirmed" (vehicle tracked) were only slightly less likely to disappear than "estimate" status. Both groups show similar reliability.

## Disappearance Rate by Vehicle Data and Uncertainty

This breakdown combines whether a vehicle was detected with the prediction's uncertainty level at first sighting.

| Vehicle Data | Uncertainty | Vanished | Total | Rate | Sample Size |
|---|---|---|---|---|---|
| Vehicle present | Mixed | 248 | 3,061 | 8.0% | 3,061 |
| No vehicle assigned | Uncertainty 300 | 35 | 272 | 12.9% | 272 |

**Interpretation:** Predictions without a vehicle yet assigned (uncertainty 300, schedule-based) vanished at **12.9%**, significantly higher than the **8.0%** rate for predictions without the uncertainty-300 flag. This suggests that schedule-based predictions are less reliable than those with real-time vehicle tracking.

## Disappearance Rate by Route

Each bus route shows different reliability. This table ranks routes by disappearance rate (highest first).

| Route | Vanished | Total | Rate | Sample Size |
|-------|----------|-------|------|------------|
| 66 | 87 | 664 | 13.1% | 664 |
| 28 | 53 | 679 | 7.8% | 679 |
| 1 | 44 | 553 | 8.0% | 553 |
| 23 | 37 | 545 | 6.8% | 545 |
| 39 | 27 | 408 | 6.6% | 408 |
| 111 | 33 | 484 | 6.8% | 484 |

**Interpretation:** Route 66 stands out with a **13.1%** disappearance rate—almost double the average across other routes. Routes 23 and 39 show the lowest rates at ~6.7%.

---

## Terminology

- **Served:** Vehicle reached the stop or prediction stayed until within 1 minute of arrival. The bus showed up.
- **Disappeared before arrival:** Vehicle was tracked but then vanished while > 2 minutes away from its predicted arrival time, and no vehicle reached the stop.
- **Canceled:** Trip or stop canceled in GTFS schedule.
- **Uncertainty (MBTA):** Indicates prediction freshness. < 300 = real-time vehicle data; 300 = schedule-based (no vehicle assigned yet); 301+ = stalled or invalid.
- **First Sighting:** The moment we first saw this prediction in the live feed.

## Limitations

1. **One day of data:** This sample covers only Saturday. Weekday and Sunday patterns may differ.
2. **"Disappeared" is not proof of a ghost:** A vehicle may have exited service, gotten stuck in traffic beyond our data window, or served an earlier stop. Our label reflects what we observed in the feeds, not ultimate ground truth.
3. **Next steps for deeper confidence:**
   - Train a predictive model to forecast disappearance risk (model method, not empirical).
   - Run live-mode validation: compare predictions to actual rider arrivals.
   - Implement replay mode: test predictions with hindsight outcomes across historic days.
   - Add dock trust: measure bike availability predictions against real dock states.

---

**Generated:** Saturday, October 24, 2026  
**Data sources:** MBTA GTFS-realtime (MassDOT Developers License Agreement); Bluebikes GBFS (Bluebikes Data License Agreement)  
**Disclaimer:** Unofficial. Not affiliated with or endorsed by MBTA, MassDOT or Bluebikes. For information only.
