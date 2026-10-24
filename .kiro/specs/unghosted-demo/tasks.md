# Implementation Plan: Unghosted Demo

## Overview

Python 3.11, `uv` only, no new dependencies (ask owner A if one is needed). Build the shared foundation first, then the Streamlit views, FastAPI and MCP in parallel groups. Extend existing files in `app/` and `streamlit_app.py`; never edit `core/`, `tests/core/`, `tests/fixtures/`, `data/`, `artifacts/`, `config.yaml`, `pyproject.toml`, `uv.lock` or `.kiro/steering/`. Import only `core.service` and `core.contracts`. Do not work around the documented service gaps (Req 12).

## Tasks

- [ ] 1. Shared foundation (everything else depends on it)
  - [ ] 1.1 Create `app/settings.py`
    - Frozen `Settings` dataclass, `SETTINGS = load_settings()`, `DISCLAIMER`, `ATTRIBUTION` (glossary text), `mbta_api_base_url`, `api_routes`, `mcp_tools`, bounds, `cors_origins`, `replay_play_speed`, `display_tz`, `modes`
    - `demo_stop_coords` inside `# BEGIN DEMO_STOP_COORDS` / `# END DEMO_STOP_COORDS` markers, empty by default
    - `load_settings(config_path=None)`: read-only `config.yaml` override of matching top-level keys; ignore unknown keys and wrong types; no Streamlit import
    - _Requirements: 7.1, 8.9, 9.2, 11.5, 11.6, 11.9_

  - [ ]* 1.2 Write property test for settings override
    - File `tests/app/test_settings.py`; also pin `ATTRIBUTION` equal to the joined `core.service` attribution list
    - **Property 16: config.yaml overrides defaults without being written**
    - **Validates: Requirements 11.6**

  - [ ] 1.3 Create `app/logic.py` (pure, no I/O, clock or mutation)
    - `status_word`, `is_displayable`, `format_chance`, `hindsight_badge`, `format_age`, `parse_age`, `format_ny_time`, `next_replay_ts`, `percent`, `fmt_metric` (None gives "not available", zero stays "0")
    - _Requirements: 1.5, 1.6, 1.7, 1.8, 1.10, 1.11, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 5.2, 5.3, 5.4, 6.2, 10.1_

  - [ ]* 1.4 Write property test for status words
    - File `tests/app/test_logic_status.py`
    - **Property 1: Status is always shown as a word**
    - **Validates: Requirements 1.7, 1.8, 10.2**

  - [ ]* 1.5 Write property test for chance formatting
    - File `tests/app/test_logic_chance.py`
    - **Property 2: Every chance shows its sample size**
    - **Validates: Requirements 1.5, 1.6, 1.10, 10.3**

  - [ ]* 1.6 Write property test for hindsight badge
    - File `tests/app/test_logic_badge.py`
    - **Property 3: Hindsight badge is deterministic and honest**
    - **Validates: Requirements 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 10.1, 10.4**

  - [ ]* 1.7 Write property test for data-age round trip
    - File `tests/app/test_logic_age.py`
    - **Property 4: Data-age round trip**
    - **Validates: Requirements 1.11, 10.5**

  - [ ]* 1.8 Write property test for New York time formatting
    - File `tests/app/test_logic_time.py`
    - **Property 5: New York times carry a zone abbreviation**
    - **Validates: Requirements 4.5**

  - [ ]* 1.9 Write property test for replay advance
    - File `tests/app/test_logic_replay.py`
    - **Property 6: Replay advance is bounded and terminates**
    - **Validates: Requirements 4.3, 4.4**

  - [ ]* 1.10 Write property test for missing values and zero
    - File `tests/app/test_logic_display.py`
    - **Property 7: Missing values read "not available", zero stays zero**
    - **Validates: Requirements 5.2, 5.3, 5.4, 6.2**

  - [ ] 1.11 Create `app/validation.py` (pure)
    - `InvalidInput(field, allowed)`, `validate_id`, `validate_mode`, `validate_int_in`, `validate_number_in`, `validate_lat`, `validate_lon`, `validate_at_ts`; bounds from `SETTINGS`; reject booleans and non-numeric values
    - _Requirements: 2.4, 2.5, 8.3, 9.2, 9.3_

  - [ ]* 1.12 Write property test for validators
    - File `tests/app/test_validation.py`
    - **Property 8: Bounds validators accept exactly the allowed range**
    - **Validates: Requirements 2.4, 2.5, 9.2**

  - [ ] 1.13 Create `app/calls.py`
    - `CallResult` and `call(fn, *args, mode, **kwargs)`: `NotFound` to `not_found` (no fallback), `LiveDataUnavailable` in live mode retries once in demo with `fell_back=True`, other exceptions to generic `error`; no caching; pass `at_ts` only when not `None`; messages never contain exception text
    - _Requirements: 1.13, 2.6, 3.4, 3.5, 3.6, 7.8_

  - [ ]* 1.14 Write property test for exception mapping
    - File `tests/app/test_calls.py`, stub service functions
    - **Property 10: Service exceptions map to typed outcomes**
    - **Validates: Requirements 1.13, 2.6, 3.4, 3.5, 3.6**

  - [ ] 1.15 Move footer to the app shell
    - `app/theme.py`: re-export `DISCLAIMER`/`ATTRIBUTION` from `app.settings` (single source)
    - `streamlit_app.py`: set session default mode to Demo; call `footer()` once after the selected page renders (also in error states)
    - Remove the per-page `footer()` calls from `app/rider.py`, `app/operator.py`, `app/api_mcp.py`, `app/about.py`
    - _Requirements: 3.2, 7.1, 7.8, 11.4_

- [ ] 2. Checkpoint - foundation
  - Run `uv run pytest -q`. Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Demo stop coordinates script
  - [ ] 3.1 Create `scripts/fetch_demo_coords.py`
    - Stop ids from `list_demo_stops()`; base URL from `SETTINGS.mbta_api_base_url`; optional `MBTA_API_KEY` from `.env` via `python-dotenv`, sent as `x-api-key`, never printed or logged
    - `GET {base}/stops/{stop_id}` with `httpx`; read `data.attributes.latitude` / `longitude`
    - Rewrite only the text between the `DEMO_STOP_COORDS` markers in `app/settings.py`; on any request failure or missing numeric coordinate, exit non-zero with a clear error and write nothing
    - Not imported by runtime code; no MBTA call at runtime
    - _Requirements: 11.9, 11.10, 11.11_

  - [ ] 3.2 Write stub-HTTP test for the script
    - File `tests/app/test_fetch_coords.py`: only the marked block changes; failed request or missing coordinates leaves the file byte-identical; API key never appears in output
    - _Requirements: 11.9, 11.10_

- [ ] 4. Checkpoint - fetch real coordinates (user action, network call)
  - Ask the user to run `uv run python scripts/fetch_demo_coords.py` (optional `MBTA_API_KEY` in `.env`) and confirm `app/settings.py` now holds coordinates for each demo stop. Rider docks degrade gracefully while the block is empty, so other tasks do not wait on this.

- [ ] 5. Rider view
  - [ ] 5.1 Extend `app/components.py`
    - `status_card` gains chance text, realistic range, backup and hindsight badge arguments (status word always shown); add small table/metric helpers that put the word "placeholder" in labels when requested
    - _Requirements: 1.5, 1.7, 4.6, 5.8_

  - [ ] 5.2 Extend `app/rider.py`: stop picker, mode switch, bus cards
    - Replace the sample data with `list_demo_stops()` and `get_bus_trust` through `calls.call`; session keys per design, default Demo
    - Mode switch Live/Demo/Replay with text label; two columns ("What the app shows" vs one Unghosted card per displayable prediction); omit non-displayable statuses; bare `hidden_count`; data age for trip updates and vehicle positions ("unknown" when absent); fallback note and displayed mode from `CallResult`; NotFound/error/empty messages; show mode word, disclaimer and attribution from the response
    - No location request, no analytics
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 3.1, 3.3, 3.4, 3.5, 3.6, 3.7, 7.7, 7.8_

  - [ ] 5.3 Extend `app/rider.py`: nearby docks and walk minutes
    - Walk-minutes input bounded by Settings and checked with `validate_number_in` (invalid keeps last valid value and dock list, shows range, no call)
    - `get_nearby_docks` with coordinates from `demo_stop_coords` (empty entry shows "dock data unavailable for this stop", no call), dock limit from Settings; hide `hidden` docks; per-dock fields and "unknown" age; dock select calls `get_dock_trust` and lists backups or "no backup available"; dock NotFound leaves bus cards unchanged
    - Do not work around the service gaps
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 12.1_

  - [ ]* 5.4 Write AppTest examples for the Rider view
    - File `tests/app/test_page_rider.py`: default mode Demo, columns and cards, hidden count, placeholder word, NotFound/fallback via stubs
    - _Requirements: 1.1, 1.4, 1.9, 1.13, 3.2, 3.4_

- [ ] 6. Replay
  - [ ] 6.1 Create `app/replay.py`
    - Slider from `get_replay_window()` (min `start`, max `end`, step `step_sec`, initial `start`); fragment with `run_every = step_sec / replay_play_speed` while playing; `next_replay_ts` to advance and stop at `end`; NY times with zone abbreviation; on a failed snapshot stop playback, keep last good data, show "snapshot could not be loaded"; disable slider and play with "replay data is unavailable" for a bad window
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.13, 4.14_

  - [ ] 6.2 Wire replay into `app/rider.py`
    - Replay mode renders `replay.py`; pass `mode="replay", at_ts` to bus and dock calls; show hindsight badges from `outcome` on cards
    - _Requirements: 4.2, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12_

  - [ ]* 6.3 Write AppTest examples for Replay
    - File `tests/app/test_page_replay.py`: slider bounds, badge text, disabled state on bad window, error keeps last data (stubs)
    - _Requirements: 4.1, 4.6, 4.13, 4.14_

- [ ] 7. Operator view and health
  - [ ] 7.1 Extend `app/operator.py`: findings
    - `get_findings` through `calls.call`; placeholder banner above all figures and "placeholder" in every label when `is_placeholder`; three vanish tables, calibration table and altair chart, model metrics, ETA hit rates, least reliable docks, sample block with NY window; generated_at in NY time; error message without hiding the rest
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 7.8, 7.9_

  - [ ] 7.2 Extend `app/operator.py`: health panel
    - `get_health` called once; all fields via `fmt_metric`/`show` ("not available" for absent, "0" for zero); modes as enabled/disabled; independent of findings errors
    - _Requirements: 6.1, 6.2, 6.3, 12.4_

  - [ ]* 7.3 Write AppTest examples for the Operator view
    - File `tests/app/test_page_operator.py`: placeholder banner and labels, empty calibration, missing health keys, findings failure keeps health
    - _Requirements: 5.2, 5.7, 5.9, 6.2, 6.3_

- [ ] 8. About and API & MCP pages
  - [ ] 8.1 Extend `app/about.py`
    - Labeled sections Guardrails, Evals, Observability, Honest limits, Roadmap (names AWS); four statuses with one-sentence meanings and "hidden is never shown"; honest limits list the four documented service gaps; quote no unlabeled numbers; no logos
    - _Requirements: 7.4, 7.5, 7.6, 7.9, 12.2, 12.3, 12.4_

  - [ ] 8.2 Extend `app/api_mcp.py`
    - Build route and tool docs, one request example each, from `SETTINGS.api_routes`, `api_base_url`, `mcp_tools`; example ids and coordinates from `list_demo_stops()` and `demo_stop_coords`; omit an item and name the missing setting if empty; no hardcoded values
    - _Requirements: 7.2, 7.3, 11.5_

  - [ ]* 8.3 Write AppTest examples for static pages
    - File `tests/app/test_page_static.py`: Disclaimer and Attribution word for word on every page, About sections and AWS roadmap item, no "ghost"/"proven" text, empty-setting omission
    - _Requirements: 7.1, 7.3, 7.4, 7.5, 4.12_

- [ ] 9. Checkpoint - app pages
  - Run `uv run pytest -q`. Ensure all tests pass, ask the user if questions arise.

- [ ] 10. FastAPI
  - [ ] 10.1 Create `api/models.py`
    - `Envelope[T]` with `data`, `attribution`, `disclaimer`; error body model (`error`, `message`, optional `params`)
    - _Requirements: 8.8_

  - [ ] 10.2 Create `api/main.py`
    - `create_app()` and `app`; six `/v1` routes with paths from `SETTINGS.api_routes`; `Query` constraints from Settings, `mode` as `Literal`; bus-trust, dock-trust, health, replay-window return contract models; findings and nearby-docks use the envelope
    - Handlers: 422 naming each offending param (no Service call), 404 naming the id, 503, 500 generic; CORS middleware only for non-empty `cors_origins`, no wildcard or credentials
    - Unauthenticated read-only service; note it in About limits
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 10.6_

  - [ ] 10.3 Create `tests/api/conftest.py` and invalid-input test
    - `TestClient` fixture and a spy on `core.service`
    - **Property 9: Invalid input never reaches the Service** (API part, `tests/api/test_api_invalid.py`)
    - **Validates: Requirements 8.3**

  - [ ]* 10.4 Write property test for unknown ids
    - File `tests/api/test_api_notfound.py`
    - **Property 11: Unknown ids are 404 / not_found, never a crash**
    - **Validates: Requirements 8.4, 10.6**

  - [ ]* 10.5 Write property test for failure mapping
    - File `tests/api/test_api_errors.py`
    - **Property 12: Service failures are mapped without leaking detail**
    - **Validates: Requirements 8.5, 8.6**

  - [ ]* 10.6 Write property test for legal text
    - File `tests/api/test_api_legal.py`
    - **Property 13: Successful API and MCP responses carry the legal text**
    - **Validates: Requirements 8.7, 10.7**

  - [ ]* 10.7 Write property test for body shape
    - File `tests/api/test_api_bodies.py`
    - **Property 14: API body matches the Service result**
    - **Validates: Requirements 8.2, 8.8**

  - [ ]* 10.8 Write property test for CORS
    - File `tests/api/test_api_cors.py`
    - **Property 15: CORS only for listed origins**
    - **Validates: Requirements 8.9**

  - [ ]* 10.9 Write one example test per route
    - File `tests/api/test_api_routes.py`, demo mode, offline
    - _Requirements: 8.1, 8.2_

- [ ] 11. MCP server
  - [ ] 11.1 Create `mcp_server/tools.py`
    - Plain functions `list_demo_stops`, `check_bus_trust`, `check_dock_trust`, `nearby_docks`, `todays_findings`; validate with `app/validation.py` before any Service call; return the `{ok, data, data_age_sec, attribution, disclaimer}` / `{ok: False, error{code, field?, message}}` shapes; never raise; read-only
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 10.9_

  - [ ] 11.2 Create `mcp_server/server.py`
    - First inspect the installed FastMCP version (`uv run python -c "import fastmcp; print(fastmcp.__version__)"` and its tool-registration API) and register exactly the five tools with names from `SETTINGS.mcp_tools`; `uv run python -m mcp_server.server` starts it
    - _Requirements: 9.1, 9.8_

  - [ ] 11.3 Create `tests/mcp/conftest.py` and invalid-input test
    - Service spy fixture
    - **Property 9: Invalid input never reaches the Service** (MCP part, `tests/mcp/test_tools_invalid.py`)
    - **Validates: Requirements 9.3**

  - [ ]* 11.4 Write property test for unknown ids
    - File `tests/mcp/test_tools_notfound.py`
    - **Property 11: Unknown ids are 404 / not_found, never a crash**
    - **Validates: Requirements 9.4, 10.9**

  - [ ]* 11.5 Write property test for failure mapping
    - File `tests/mcp/test_tools_errors.py`
    - **Property 12: Service failures are mapped without leaking detail**
    - **Validates: Requirements 9.5, 9.6**

  - [ ]* 11.6 Write property test for legal text and data age
    - File `tests/mcp/test_tools_legal.py`
    - **Property 13: Successful API and MCP responses carry the legal text**
    - **Validates: Requirements 9.7, 10.7**

  - [ ]* 11.7 Write MCP unit tests
    - File `tests/mcp/test_server.py`: exactly five tools, none writes, in-memory `fastmcp.Client` smoke call
    - _Requirements: 9.1, 9.8_

- [ ] 12. Boundaries and run commands
  - [ ] 12.1 Write boundary and no-hardcoding scan test
    - File `tests/app/test_boundaries.py`: AST scan of `streamlit_app.py`, `app/`, `api/`, `mcp_server/` imports only `core.service` / `core.contracts`; no URL, route, stop/station id or coordinate literals outside `app/settings.py`; no logo assets; `.env` not tracked (`git ls-files`)
    - _Requirements: 7.6, 11.1, 11.5, 11.7_

  - [ ] 12.2 Write run-command test
    - File `tests/app/test_run_commands.py`: every run command documented in `README.md` and the About/API_MCP pages starts with `uv run`; no `pip` or `requirements.txt`
    - _Requirements: 11.8_

- [ ] 13. Final checkpoint
  - Run `uv run pytest -q`, then the manual smoke commands below. Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked `*` are optional property/unit tests. The stub-HTTP test (3.2) and the 10.3 / 11.3 fixtures are kept required because they guard the no-write-on-failure rule and are shared by later tests.
- Per-property test files (instead of one `test_logic.py`) let property tests run in parallel without file conflicts.
- `app/replay.py` is a small addition to the design so Replay and Rider work can run in parallel; `rider.py` only wires it in (6.2).
- Manual smoke commands (user runs): `uv run streamlit run streamlit_app.py`, `uv run uvicorn api.main:app --reload` then open `/v1/health`, `uv run python -m mcp_server.server`, `uv run python scripts/fetch_demo_coords.py` (once).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.11", "1.13", "1.15", "3.1", "10.1"] },
    { "id": 2, "tasks": ["1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10", "1.12", "1.14", "3.2", "5.1", "8.1", "8.2", "10.2", "11.1"] },
    { "id": 3, "tasks": ["5.2", "6.1", "7.1", "10.3", "11.2", "11.3"] },
    { "id": 4, "tasks": ["5.3", "7.2", "10.4", "10.5", "10.6", "10.7", "10.8", "10.9", "11.4", "11.5", "11.6", "11.7"] },
    { "id": 5, "tasks": ["5.4", "6.2", "7.3", "8.3"] },
    { "id": 6, "tasks": ["6.3"] },
    { "id": 7, "tasks": ["12.1", "12.2"] }
  ]
}
```
