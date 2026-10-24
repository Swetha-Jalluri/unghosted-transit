# Requirements Document

## Introduction

Unghosted Demo is the delivery layer for the Unghosted trust layer: a Streamlit app (Rider, Operator, API & MCP, About), a FastAPI service under `/v1`, and a read-only FastMCP server. All three consume only `core.service` and `core.contracts`. The existing Streamlit shell (`streamlit_app.py`, `app/`) is extended, not recreated. URLs, routes, thresholds, intervals, coordinates, and ids come from Settings (`app/settings.py`, B-owned); no change to `config.yaml` is requested from owner A.

## Glossary

- **Settings**: The B-owned module `app/settings.py`, shared by `app/`, `api/` and `mcp_server/`. It holds defaults for demo stop coordinates (keyed by stop id), API base URL and route paths, CORS origins, replay play speed (60 logged seconds per real second), walk-minute default/minimum/maximum, dock limit, API and MCP input bounds (limit, walk_min, lat, lon), and the shared Disclaimer and Attribution strings. A value under the same key in `config.yaml` overrides the Settings default (read-only access; `config.yaml` is never edited).
- **App**: The Streamlit application started from `streamlit_app.py`.
- **Rider_View**: The App page showing bus and dock trust for one stop.
- **Operator_View**: The App page showing findings and system health.
- **API_MCP_Page**: The App page documenting the REST API and MCP server.
- **About_Page**: The App page covering guardrails, evals, observability, attribution, disclaimer, limits, and roadmap.
- **API**: The FastAPI application in `api/main.py`, with routes under `/v1`.
- **MCP_Server**: The FastMCP server in `mcp_server/server.py`.
- **Service**: The `core.service` module and its `core.contracts` models.
- **Mode**: One of `live`, `demo`, `replay`, as defined by the Service.
- **Status_Label**: The word `confirmed`, `estimate`, or `unreliable`, paired with a color.
- **Chance**: A `chance_it_arrives` or `chance_bike_on_arrival` value with its `chance_basis.n`.
- **Disclaimer**: "Unofficial. Not affiliated with or endorsed by MBTA, MassDOT or Bluebikes. For information only."
- **Attribution**: "Data: MBTA GTFS-realtime (MassDOT Developers License Agreement); Bluebikes GBFS (Bluebikes Data License Agreement)."
- **Data_Age**: The `data_age_sec` values from a Service response, shown as human-readable age.
- **Hindsight_Badge**: A replay label derived from `BusPrediction.outcome`. For `vanished` with no computable minutes, the label is "disappeared before arrival".
- **Placeholder_Banner**: A visible notice shown while `Findings.is_placeholder` is true.

## Requirements

### Requirement 1: Rider stop selection and cards

**User Story:** As a rider, I want to pick a stop and see what the app shows next to what Unghosted says, so that I can judge whether a bus will really come.

#### Acceptance Criteria

1. WHEN the Rider_View loads, THE Rider_View SHALL populate the stop picker from `list_demo_stops()`, showing each stop's name and its routes.
2. WHEN a stop is selected or the Mode changes while a stop is selected, THE Rider_View SHALL call `get_bus_trust` for that stop and the selected Mode and display the result within the same page render.
3. THE Rider_View SHALL show a left column titled "What the app shows" containing only the route and the app ETA in minutes for each prediction, in the order returned by `get_bus_trust`.
4. THE Rider_View SHALL show a right column with exactly one Unghosted card per displayed prediction, in the same order as the left column.
5. THE Rider_View SHALL show on each card the Status_Label word, the `why` text, the `realistic_eta_min` range as a low-to-high pair in minutes, the Chance as a percentage together with its n from `chance_basis`, and the backup when present.
6. IF `chance_it_arrives` is absent for a prediction, THEN THE Rider_View SHALL show text on that card indicating the chance is unavailable instead of a percentage.
7. THE Rider_View SHALL render every Status_Label as its word plus a color: green for confirmed, amber for estimate, red for unreliable, so that the word is visible regardless of color.
8. IF a prediction has a status other than confirmed, estimate or unreliable, THEN THE Rider_View SHALL omit that prediction from both columns.
9. WHEN `hidden_count` is greater than 0, THE Rider_View SHALL show `hidden_count` as a number only, without any detail about the hidden predictions.
10. IF `chance_basis.method` is `placeholder`, THEN THE Rider_View SHALL show the word "placeholder" next to the Chance on that card.
11. THE Rider_View SHALL show Data_Age in seconds for trip updates and for vehicle positions for every response it displays, and SHALL show text indicating the age is unknown for any value that is absent.
12. THE Rider_View SHALL not request user location or run analytics.
13. IF `get_bus_trust` raises `LiveDataUnavailable` or `NotFound`, THEN THE Rider_View SHALL show a message indicating live data is unavailable or the stop was not found respectively, SHALL show no cards, and SHALL keep the current stop and Mode selection.
14. IF `get_bus_trust` returns no displayable predictions, THEN THE Rider_View SHALL show a message indicating that no predictions are available for the stop and SHALL still show Data_Age.
15. THE Rider_View SHALL show the response's disclaimer and attribution text unaltered alongside every response it displays.

### Requirement 2: Nearby docks

**User Story:** As a rider, I want to see nearby Bluebikes docks with a realistic bike count, so that I can pick a dock that will have a bike.

#### Acceptance Criteria

1. WHEN a stop is selected or the walk minutes are changed to a valid value, THE Rider_View SHALL call `get_nearby_docks` using that stop's coordinates from Settings, the selected Mode, the current walk minutes, and the dock limit from Settings, and SHALL replace the displayed dock list with the result.
2. THE Rider_View SHALL show for each returned dock its name, Status_Label word (as text, never color alone), `app_bikes`, `usable_bikes_estimate` range (low to high), Chance with n, `why`, and data age in seconds (or the word "unknown" when `last_reported_age_sec` is absent), and SHALL NOT show any dock whose status is hidden.
3. WHEN a dock is selected, THE Rider_View SHALL call `get_dock_trust` with that dock's station id, the current walk minutes and the selected Mode, and SHALL show each returned backup with its name and Status_Label word, or a message indicating that no backup is available when the backup list is empty.
4. THE Rider_View SHALL initialize the walk minutes from the Settings default and SHALL provide an on-screen input that accepts only values between the Settings minimum and maximum walk minutes.
5. IF the entered walk minutes are non-numeric or outside the Settings minimum and maximum, THEN THE Rider_View SHALL reject the value, show a message indicating the accepted range, keep the last valid walk minutes and the displayed dock list, and make no service call.
6. IF `get_nearby_docks` or `get_dock_trust` raises `LiveDataUnavailable` or `NotFound`, THEN THE Rider_View SHALL show a message indicating that dock data is unavailable (or that the item was not found), show no dock data from the failed call, and make no fallback to another Mode other than the visible Demo fallback defined in Requirement 3.4 for `LiveDataUnavailable`, keeping the selected Mode unchanged for `NotFound`.
7. IF `get_nearby_docks` returns zero docks, THEN THE Rider_View SHALL show a message indicating that no docks were found within the current walk minutes.
8. IF `get_dock_trust` raises `NotFound`, THEN THE Rider_View SHALL leave the bus cards already displayed unchanged and SHALL NOT clear them.

### Requirement 3: Mode switch and live fallback

**User Story:** As a demo presenter, I want to switch between Live, Demo, and Replay, so that the app works with or without live feeds.

#### Acceptance Criteria

1. THE Rider_View SHALL provide a mode switch with exactly three options (Live, Demo, and Replay) and SHALL indicate the currently selected option with a text label.
2. WHEN a new user session begins, THE App SHALL set the active Mode to Demo.
3. WHEN the user selects a different option on the mode switch, THE Rider_View SHALL request data in the selected Mode and SHALL replace all previously displayed responses with the new response before any further user interaction is accepted.
4. IF the Service raises `LiveDataUnavailable`, THEN THE Rider_View SHALL display a note stating that live data is unavailable and that Demo data is shown, SHALL display Demo mode data in place of the failed Live response, and SHALL set the displayed active Mode to Demo.
5. WHEN the user selects Live after a `LiveDataUnavailable` fallback, THE Rider_View SHALL request live data from the Service again rather than reusing the earlier failure.
6. IF the Service raises `NotFound` for a stop, THEN THE Rider_View SHALL display a message that includes the unknown id and states that it was not found, SHALL show no cards for that call, and SHALL keep the mode switch and stop or station selection controls operable.
7. THE Rider_View SHALL display the active Mode as a text word (Live, Demo, or Replay) alongside every bus trust response and every dock trust response it shows, and the word SHALL match the mode of the data actually displayed.

### Requirement 4: Replay

**User Story:** As a judge, I want to scrub through logged time and see what actually happened, so that I can see whether Unghosted was right in hindsight.

#### Acceptance Criteria

1. WHEN Replay mode is selected, THE Rider_View SHALL build a time slider from `get_replay_window()` with minimum `start`, maximum `end`, increments of `step_sec` seconds, and an initial value of `start`.
2. WHEN the slider changes, THE Rider_View SHALL call the Service with `mode="replay"` and `at_ts` set to the slider value (POSIX seconds UTC), and SHALL replace the displayed predictions and docks with the returned data.
3. WHEN the play button is pressed, THE Rider_View SHALL advance the slider so that logged time elapses at the speed multiplier read from Settings (logged seconds per real second), moving in increments of `step_sec` and calling the Service at each new slider value.
4. WHEN the slider value reaches `end`, THE Rider_View SHALL stop playback, hold the slider at `end`, and show the play button as ready to be pressed again.
5. THE Rider_View SHALL display every replay time (slider label, replay time, and data timestamps) in America/New_York and SHALL show the time zone abbreviation next to each displayed time.
6. WHEN a prediction card with `outcome` set to one of `served`, `vanished`, `canceled`, or `open` is rendered, THE Rider_View SHALL show a Hindsight_Badge on that card; IF `outcome` is absent or any other value, THEN THE Rider_View SHALL show no Hindsight_Badge on that card.
7. WHEN a prediction card with `outcome` equal to `served` is rendered, THE Rider_View SHALL label the Hindsight_Badge "served".
8. WHEN a prediction card with `outcome` equal to `vanished` is rendered, THE Rider_View SHALL label the Hindsight_Badge "disappeared N min later", where N is `app_eta_min` rounded to the nearest whole number with a minimum of 0, because `app_eta_min` is already relative to the snapshot time.
9. IF N cannot be computed because the replay time or `app_eta_min` is absent or not finite, THEN THE Rider_View SHALL label the Hindsight_Badge "disappeared before arrival" without a number.
10. WHEN a prediction card with `outcome` equal to `canceled` is rendered, THE Rider_View SHALL label the Hindsight_Badge "canceled".
11. WHEN a prediction card with `outcome` equal to `open` is rendered, THE Rider_View SHALL label the Hindsight_Badge "still open".
12. THE Rider_View SHALL show every Hindsight_Badge with its text label, never by color alone, and SHALL NOT use the words "ghost" or "proven" (in any letter case) in any badge.
13. IF `get_replay_window()` fails, or returns `n_snapshots` equal to 0, or returns `end` earlier than `start`, THEN THE Rider_View SHALL disable the slider and play button, and SHALL show a message stating that replay data is unavailable.
14. IF the Service raises an error for a slider value (including NotFound), THEN THE Rider_View SHALL stop any active playback, keep the previously displayed data and slider position of the last successful call, and show a message stating that the snapshot could not be loaded.

### Requirement 5: Operator findings

**User Story:** As a city or MBTA analyst, I want measured vanish rates and model quality, so that I can see where predictions fail.

#### Acceptance Criteria

1. WHEN the Operator_View is opened, THE Operator_View SHALL call `get_findings()` and show three separate tables of vanish rates, one by status, one by uncertainty code, and one by route, with each row showing the group name, the rate as a percentage with one decimal place, and its n as a whole number, in the order returned by `get_findings()`.
2. WHEN the Operator_View shows the calibration data, THE Operator_View SHALL show one table and one chart, each with predicted value, observed value, and n for every bin, and SHALL show "not available" in place of both when the calibration list is empty.
3. WHEN the Operator_View shows model quality, THE Operator_View SHALL show AUC and Brier score with 3 decimal places and `n_labels` as a whole number from `Findings.model`, and SHALL show "not available" for each value that is absent.
4. WHEN the Operator_View shows ETA accuracy, THE Operator_View SHALL show ETA range hit and single ETA hit as percentages with one decimal place, together with n, and SHALL show "not available" when `eta_range_hit` has no values.
5. WHEN the Operator_View shows the least reliable docks, THE Operator_View SHALL list each dock with its name, metric, and n, in the order returned by `get_findings()`, and SHALL show "no data" when the list is empty.
6. WHEN the Operator_View shows sample details, THE Operator_View SHALL show the label "Saturday sample" with `sample_label`, the window start and end in America/New_York time, and the eval train count and test count, and SHALL show "not available" for each value that is absent.
7. WHILE `Findings.is_placeholder` is true, THE Operator_View SHALL show the Placeholder_Banner, above all figures, stating the numbers are not measured results.
8. WHILE `Findings.is_placeholder` is true, THE Operator_View SHALL include the word "placeholder" in the label of every table, chart, and metric.
9. IF `get_findings()` raises an error, THEN THE Operator_View SHALL show an error message indicating findings are unavailable, show no figures, and keep the page usable for navigation to other views.
10. THE Operator_View SHALL show the Disclaimer and Attribution text, together with the `Findings.generated_at` time in America/New_York, whenever findings are displayed.

### Requirement 6: System health

**User Story:** As an operator, I want a health panel, so that I can see whether data collection is working.

#### Acceptance Criteria

1. WHEN the Operator_View is opened or refreshed, THE Operator_View SHALL call `get_health()` once and show: last poll time in the America/New_York time zone; polls in the last hour as a whole number; poll success rate as a percentage; row counts for predictions, vehicle positions and docks as whole numbers; Data_Age in seconds for trip updates, vehicle positions and docks; each of the demo, live and replay modes labeled with the word "enabled" or "disabled"; and `model_method`.
2. IF a health value is absent (null or missing), including any single Data_Age entry, THEN THE Operator_View SHALL show "not available" for that value only, SHALL show all other health values unchanged, and SHALL show a value of zero as "0" rather than "not available".
3. IF `get_health()` raises an error, THEN THE Operator_View SHALL show an error message indicating that health data could not be retrieved, SHALL show no health values, and SHALL keep the other Operator_View content usable.

### Requirement 7: Shared page content

**User Story:** As a user, I want every page to carry the legal notices, so that I know the data source and its limits.

#### Acceptance Criteria

1. THE App SHALL show the Disclaimer and the Attribution as visible text, word for word as defined in the Glossary, on every page (Rider, Operator, API_MCP_Page, About_Page) in every mode (live, demo, replay).
2. THE API_MCP_Page SHALL document each API route and each MCP tool, with one request example per route and per tool, and SHALL read the base URL and every route path from Settings.
3. IF the Settings base URL or a Settings route path is empty, THEN THE API_MCP_Page SHALL omit the affected route and its request example and SHALL show a message naming the missing setting, without substituting a hardcoded value.
4. THE About_Page SHALL describe guardrails, evals, observability, honest limits, and a roadmap, each under its own labeled section containing at least one sentence, and the roadmap section SHALL name AWS in at least one item.
5. THE About_Page SHALL list the four statuses `confirmed`, `estimate`, `unreliable`, and `hidden`, each with its word and a one-sentence meaning, and SHALL state that `hidden` is never shown to users.
6. THE App SHALL not display MBTA or Bluebikes logos or brand marks on any page.
7. THE App SHALL display no number that is not read from a Service response or from Settings.
8. IF a Service call raises LiveDataUnavailable or NotFound, THEN THE App SHALL still show the Disclaimer and Attribution on that page and SHALL replace the affected numbers with a message indicating the data is unavailable, without showing stale or placeholder numbers.
9. IF a Service response has `is_placeholder` set to true, THEN THE About_Page SHALL label every number derived from that response as placeholder and not as a measured result.

### Requirement 8: REST API

**User Story:** As a transit app developer, I want a REST API, so that I can add trust information to my app.

#### Acceptance Criteria

1. THE API SHALL expose `GET /v1/health`, `/v1/bus-trust`, `/v1/dock-trust`, `/v1/nearby-docks`, `/v1/findings`, and `/v1/replay-window`.
2. WHEN a request passes parameter validation, THE API SHALL call the matching Service function with the validated parameters and return the Service result as a JSON body with the same fields as the corresponding contract model.
3. IF a required query parameter is missing (`stop_id` for bus-trust, `station_id` for dock-trust, `lat` and `lon` for nearby-docks), or any supplied parameter violates its bound (`mode` not one of live, demo, replay; `limit` or `walk_min` outside the bounds set in Settings; `lat` outside -90 to 90; `lon` outside -180 to 180; `at_ts` not an integer of POSIX seconds), THEN THE API SHALL return 422 with a JSON error body that names each offending parameter, and SHALL NOT call the Service.
4. IF the Service raises `NotFound`, THEN THE API SHALL return 404 with a JSON error body that states the requested id was not found.
5. IF the Service raises `LiveDataUnavailable`, THEN THE API SHALL return 503 with a JSON error body that states live data is unavailable.
6. IF the Service raises any exception other than `NotFound` or `LiveDataUnavailable`, THEN THE API SHALL return 500 with a JSON error body that states an internal error occurred and contains no stack trace, file path, or exception text.
7. WHEN a bus-trust or dock-trust request succeeds, THE API SHALL return the contract model unchanged, including its `attribution` list and `disclaimer` text.
8. WHEN a findings or nearby-docks request succeeds, THE API SHALL return the JSON envelope `{"data": ..., "attribution": [...], "disclaimer": "..."}` without changing any contract model, where `data` holds the `Findings` model (findings) or the list of `DockResult` (nearby-docks), `attribution` is a non-empty list containing the Attribution text, and `disclaimer` is the Disclaimer text, both taken from the Settings shared strings.
9. WHERE Settings lists CORS origins, THE API SHALL return CORS allow headers only for requests whose `Origin` matches a listed origin, and SHALL return no CORS allow headers for any other origin or when the list is empty or absent.

### Requirement 9: MCP server

**User Story:** As an AI assistant, I want read-only tools, so that I can answer rider questions with honest uncertainty.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose exactly these five tools: `list_demo_stops`, `check_bus_trust`, `check_dock_trust`, `nearby_docks`, and `todays_findings`, each of which only reads data.
2. WHEN a tool is called, THE MCP_Server SHALL validate all inputs before calling the Service, using these rules: id fields (`stop_id`, `station_id`) are non-empty strings of 1 to 64 characters after trimming whitespace; `mode` is one of `live`, `demo`, `replay`; `limit` is an integer within the Settings minimum and maximum; `walk_min` is a number within the Settings minimum and maximum; `lat` is a number from -90 to 90; `lon` is a number from -180 to 180; `at_ts`, when supplied, is a non-negative integer in POSIX seconds UTC. These bounds SHALL be read from Settings, not hardcoded.
3. IF an input fails validation, THEN THE MCP_Server SHALL NOT call the Service and SHALL return an error result that names the invalid field and states the allowed range or values.
4. IF the Service raises `NotFound`, THEN THE MCP_Server SHALL return an error result stating that the requested id was not found and naming that id.
5. IF the Service raises `LiveDataUnavailable`, THEN THE MCP_Server SHALL return an error result stating that live data is unavailable and suggesting `demo` mode as an alternative.
6. IF the Service raises any exception other than `NotFound` or `LiveDataUnavailable`, THEN THE MCP_Server SHALL return a generic error result that contains no stack trace or internal detail, and SHALL continue to accept subsequent tool calls without restarting.
7. WHEN a tool call succeeds, THE MCP_Server SHALL include in the answer the data age in seconds for each data source reported by the Service, the attribution text, and the disclaimer text, using the same Attribution and Disclaimer strings as the API, taken from the single shared source in Settings.
8. THE MCP_Server SHALL NOT expose any tool that creates, updates, or deletes stored data or configuration.

### Requirement 10: Decision-logic correctness

**User Story:** As a maintainer, I want pure, tested presentation logic, so that the trust rules cannot silently break.

#### Acceptance Criteria

1. THE App SHALL implement Status_Label rendering, hindsight badge text, chance formatting, and data-age formatting as pure deterministic functions that perform no network access, file access, clock reads or random number generation, and do not modify their inputs.
2. FOR ALL statuses in {confirmed, estimate, unreliable}, THE Status_Label renderer SHALL output text containing the status word in lowercase or capitalized form, independent of any color or icon.
3. FOR ALL Chance values between 0.0 and 1.0 inclusive and integer n from 0 to 1,000,000, THE chance formatter SHALL output text containing the decimal digits of n.
4. FOR ALL outcomes in {served, vanished, canceled, open} and finite minute values from 0 to 1,440, THE Hindsight_Badge function SHALL return the same output on repeated calls with the same inputs (determinism).
5. FOR ALL `data_age_sec` values from 0 to 604,800, THE data-age formatter SHALL output text that parses back to a value within one display unit (the unit shown in the output: seconds, minutes, hours or days) of the input (round trip).
6. IF an API request names a stop or station id that does not exist, THEN THE API SHALL return 404 with a response body indicating the id was not found, and THE API SHALL NOT return a stack trace or raise an unhandled exception.
7. FOR ALL successful API and MCP responses, THE delivery layer SHALL include the Attribution text and the Disclaimer text exactly as defined in the Glossary.
8. THE test suite SHALL cover the API with `TestClient` in `tests/api/` and the MCP_Server in `tests/mcp/`, SHALL use Hypothesis for properties 2 to 7 with at least 100 generated examples per property, SHALL run offline in demo mode, and SHALL pass under `uv run pytest -q`.
9. IF an MCP_Server tool receives a stop or station id that does not exist, THEN THE MCP_Server SHALL return an error result indicating the id was not found, and THE MCP_Server SHALL NOT raise an unhandled exception or terminate the server process.

### Requirement 11: Boundaries and tooling

**User Story:** As a team member, I want clear boundaries, so that the two branches do not conflict.

#### Acceptance Criteria

1. THE delivery layer SHALL import from `core/` only the modules `core.service` and `core.contracts`, such that a static scan of every Python file under `streamlit_app.py`, `app/`, `api/`, and `mcp_server/` finds zero imports of any other `core` module.
2. THE delivery layer SHALL leave `core/`, `tests/core/`, `tests/fixtures/`, `data/`, `artifacts/`, `config.yaml`, `pyproject.toml`, `uv.lock`, and `.kiro/steering/` unchanged on the delivery branch relative to `main`.
3. IF a dependency is needed that is not already declared in `pyproject.toml`, THEN THE delivery layer SHALL request it from owner A, SHALL NOT add or modify any dependency declaration, and SHALL leave the dependent feature out of the delivery branch until owner A has merged the dependency into `main`. Settings (`app/settings.py`) is B-owned, and THE delivery layer SHALL request no change to `config.yaml` from owner A.
4. THE delivery layer SHALL extend the existing `streamlit_app.py` and the existing files under `app/` rather than recreate them.
5. THE delivery layer SHALL read all URLs, routes, thresholds, intervals, ids, and coordinates only through Settings, such that a scan of delivery-layer source files other than `app/settings.py` finds zero hardcoded literals of those kinds.
6. WHERE `config.yaml` contains a value under the same key as a Settings default, THE Settings module SHALL use the `config.yaml` value in place of the default, reading `config.yaml` without ever writing to it.
7. THE delivery layer SHALL keep all secrets only in `.env`, such that `.env` is absent from the tracked file list.
8. THE delivery layer SHALL run the App, the API, the MCP_Server, and the tests through `uv run`, such that each documented run command begins with `uv run` and none invokes `pip` or a `requirements.txt` file.
9. THE delivery layer SHALL obtain the demo stop coordinates in Settings once, from the MBTA V3 API endpoint `https://api-v3.mbta.com/stops/{stop_id}` for each stop id returned by `list_demo_stops()`, and SHALL write them into `app/settings.py` with a one-time script, such that no coordinate is guessed.
10. THE one-time coordinates script SHALL read the MBTA V3 API base URL from Settings and an optional `MBTA_API_KEY` from `.env`.
11. THE delivery layer SHALL make no call to the MBTA V3 API at runtime in the App, the API, or the MCP_Server.

### Requirement 12: Documented service limitations

**User Story:** As a judge, I want the known Service gaps stated openly, so that I can tell what the demo does not do.

#### Acceptance Criteria

1. THE delivery layer SHALL NOT work around a known Service gap listed in this requirement.
2. THE About_Page honest-limits section SHALL state that `get_nearby_docks` has no `at_ts` parameter, so the docks shown in Replay mode do not change with the slider.
3. THE About_Page honest-limits section SHALL state that `get_dock_trust` ignores `walk_min` and `mode`.
4. THE About_Page honest-limits section SHALL state that Demo mode never raises `LiveDataUnavailable`, so the Live fallback in Requirement 3 is verified with stubs, and that `Health.data_age_sec` may omit keys, which the Operator_View shows as "not available" (Requirement 6).
