"""Rider view.

What a rider sees: for a chosen stop, which arrivals are trustworthy, a
realistic time range instead of one number, and a backup when things look bad.

Data flows through ``core.service`` only via :func:`app.calls.call`, which turns
Service exceptions into a typed :class:`~app.calls.CallResult` and implements the
single Live-to-Demo fallback. A stop picker is used instead of any location
request; there is no analytics (R7.7).
"""
from __future__ import annotations

import streamlit as st

from app import calls
from app.components import page_header, status_card, status_legend
from app.logic import format_age, is_displayable, status_word
from app.settings import SETTINGS
from app.validation import InvalidInput, validate_number_in
from core import service

# User-facing mode labels, in display order. The word is always shown as text
# (R10.2); default is Demo. The Service understands the lowercase forms.
_MODE_LABELS = ("Live", "Demo", "Replay")


def _mode_to_service(label: str) -> str:
    """Map a display mode label ("Demo") to the Service mode ("demo")."""
    return str(label).strip().lower()


def _age_text(data_age_sec: dict, key: str) -> str:
    """Return a formatted data age for ``key``; absent keys read "unknown"."""
    if not isinstance(data_age_sec, dict) or key not in data_age_sec:
        return "unknown"
    return format_age(data_age_sec[key])


def _stop_options() -> list:
    """Load demo stops; return an empty list if the Service call fails."""
    result = calls.call(service.list_demo_stops, mode="demo")
    if result.ok and result.value:
        return list(result.value)
    return []


def render() -> None:
    page_header("Rider view")

    st.write(
        "Pick a stop to see whether each arrival is trustworthy. We show a "
        "realistic time range, not a single number, and the status word is "
        "always spelled out."
    )

    # ------------------------------------------------------------------
    # Session defaults (keys per design). streamlit_app.main() already sets
    # rider_mode to "Demo"; setdefault here keeps the view self-contained.
    # ------------------------------------------------------------------
    st.session_state.setdefault("rider_mode", "Demo")
    st.session_state.setdefault("walk_min", float(SETTINGS.walk_min["default"]))
    st.session_state.setdefault("selected_dock", None)
    # The replay session keys (replay_ts, replay_playing, last_ok_replay_ts) are
    # owned and seeded by app.replay; rider must not pre-seed them to None or
    # app.replay would skip clamping and read a non-integer timestamp.

    # ------------------------------------------------------------------
    # Stop picker (from list_demo_stops) and mode switch.
    # ------------------------------------------------------------------
    stops = _stop_options()
    if not stops:
        st.error("Stops are unavailable right now. Please try again.")
        return

    stop_labels = {
        f"{stop.name} ({', '.join(stop.routes)})": stop.stop_id for stop in stops
    }

    col_pick, col_mode = st.columns([2, 1])
    with col_pick:
        chosen_label = st.selectbox("Stop", options=list(stop_labels.keys()))
        st.session_state["rider_stop"] = stop_labels[chosen_label]
    with col_mode:
        st.selectbox("Mode", options=list(_MODE_LABELS), key="rider_mode")

    stop_id = st.session_state["rider_stop"]
    mode_label = st.session_state["rider_mode"]
    service_mode = _mode_to_service(mode_label)

    status_legend()
    st.write("")

    # ------------------------------------------------------------------
    # Replay (task 6.2). In Replay mode the controls and clock live in
    # app.replay; it drives one snapshot at a time through the callback below,
    # which fetches bus trust (and docks) with mode="replay", at_ts=<slider>
    # and draws the cards. The callback returns True on success and False when
    # a snapshot could not be loaded, so replay can stop playback and keep the
    # last good data (R4.2, R4.14). In Live/Demo modes at_ts stays None and the
    # snapshot is rendered once, inline (behavior unchanged from 5.2/5.3).
    # ------------------------------------------------------------------
    if service_mode == "replay":
        from app import replay  # noqa: WPS433 (B-owned; created in task 6.1)

        def render_snapshot(at_ts: int) -> bool:
            return _render_snapshot(stop_id, service_mode, at_ts)

        replay.render_replay(render_snapshot)
    else:
        _render_snapshot(stop_id, service_mode, None)


def _render_snapshot(stop_id: str, service_mode: str, at_ts) -> bool:
    """Fetch and render the bus cards and nearby docks for one snapshot.

    Shared by the normal Live/Demo flow (``at_ts`` is ``None``) and the Replay
    callback (``at_ts`` is the slider value). Bus and dock calls carry the
    selected Mode and, in Replay, ``at_ts`` (R4.2); ``get_nearby_docks`` has no
    ``at_ts`` parameter (documented gap R12.1) so it is never passed one.

    Returns True when the bus trust call succeeded (so Replay keeps the
    snapshot) and False when it failed, including a NotFound, so Replay stops
    playback and keeps the last good data (R4.14). Dock errors are handled
    inside the dock block and never flip this result: the bus cards above stay
    on screen regardless (R2.8).
    """
    # ------------------------------------------------------------------
    # Bus trust call through the typed wrapper. In Replay, at_ts is forwarded;
    # in Live/Demo it is None and calls.call drops it entirely.
    # ------------------------------------------------------------------
    result = calls.call(
        service.get_bus_trust,
        stop_id,
        mode=service_mode,
        at_ts=at_ts,
    )

    # The mode actually shown (after any Live -> Demo fallback), as a word.
    st.caption(f"Mode: {result.mode_shown.title()}")
    if result.fell_back:
        st.warning("Live data is unavailable. Showing Demo data.")

    if result.kind == "not_found":
        st.warning(result.message)
        return False
    if not result.ok or result.value is None:
        st.error(result.message or "Something went wrong. Please try again.")
        return False

    response = result.value

    # ------------------------------------------------------------------
    # Keep only displayable predictions, in service order. The same list
    # feeds both columns so the rows line up.
    # ------------------------------------------------------------------
    shown = [p for p in response.predictions if is_displayable(p.status)]

    # Data age for both feeds; absent keys read "unknown".
    trip_age = _age_text(response.data_age_sec, "trip_updates")
    veh_age = _age_text(response.data_age_sec, "vehicle_positions")
    st.caption(
        f"Data age — trip updates: {trip_age} · vehicle positions: {veh_age}"
    )

    # Hidden count as a bare number.
    st.caption(f"Hidden arrivals (non-revenue or invalid): {response.hidden_count}")

    if not shown:
        st.info("No trustworthy arrivals to show for this stop right now.")
    else:
        col_app, col_ug = st.columns(2)
        with col_app:
            st.markdown("**What the app shows**")
            for pred in shown:
                st.write(f"Route {pred.route_id} — {pred.app_eta_min:g} min")
        with col_ug:
            st.markdown("**Unghosted**")
            for pred in shown:
                # Pass the replay timestamp so served/vanished/canceled/open
                # outcomes surface a hindsight badge (R4.6-R4.12). at_ts is None
                # in Live/Demo, where predictions carry no outcome, so no badge
                # is shown there.
                _render_card(pred, at_ts)

    # ------------------------------------------------------------------
    # Nearby docks (task 5.3). Rendered below the bus cards. A dock error
    # never clears the bus cards above; the dock block manages its own
    # messages and session state.
    # ------------------------------------------------------------------
    _render_docks(stop_id, service_mode, at_ts)

    # ------------------------------------------------------------------
    # Disclaimer and attribution straight from the response, unaltered.
    # ------------------------------------------------------------------
    st.caption(response.disclaimer)
    for line in response.attribution:
        st.caption(line)

    return True


def _render_docks(stop_id: str, service_mode: str, at_ts=None) -> None:
    """Render the nearby-docks block for the selected stop.

    Walk minutes are bounded by Settings and re-checked with
    ``validate_number_in``; an invalid value keeps the last valid walk minutes
    and the last dock list and makes no Service call (R2.4, R2.5). Docks are
    fetched with coordinates from ``SETTINGS.demo_stop_coords`` (an absent entry
    shows "dock data unavailable for this stop" and makes no call, R2.1).

    ``get_nearby_docks`` has no ``at_ts`` parameter (documented gap R12.1,
    R12.2): we never pass one and never work around the gap, so the dock list
    shown in Replay does not change with the slider. ``get_dock_trust`` does
    take ``at_ts``, so ``at_ts`` is threaded through to the backups call only
    (R4.2).
    """
    st.subheader("Nearby docks")

    # ------------------------------------------------------------------
    # Walk-minutes input, bounded by Settings. The widget itself is bounded,
    # and we re-validate with validate_number_in so a rejected value keeps the
    # last valid walk minutes and the last dock list, and makes no call.
    # ------------------------------------------------------------------
    bounds = SETTINGS.walk_min
    wmin = float(bounds["min"])
    wmax = float(bounds["max"])
    last_valid = float(st.session_state.get("walk_min", bounds["default"]))

    entered = st.number_input(
        "Walk minutes",
        min_value=wmin,
        max_value=wmax,
        value=last_valid,
        step=1.0,
        help=f"Accepted range: {wmin:g} to {wmax:g} minutes.",
    )

    try:
        walk_min = validate_number_in(entered, wmin, wmax, field="walk_min")
    except InvalidInput as exc:
        # Keep the last valid value and the last dock list; make no call.
        st.warning(f"Walk minutes must be a {exc.allowed}. Keeping {last_valid:g}.")
        walk_min = last_valid
        self_rerender = True
    else:
        st.session_state["walk_min"] = walk_min
        self_rerender = False

    # ------------------------------------------------------------------
    # Coordinates come from Settings only; no coordinate is ever guessed. An
    # empty entry means we cannot look up docks for this stop (R2.1, R11.10).
    # ------------------------------------------------------------------
    coords = SETTINGS.demo_stop_coords.get(stop_id)
    if not coords or "lat" not in coords or "lon" not in coords:
        st.info("dock data unavailable for this stop")
        return

    if self_rerender:
        # Invalid walk minutes: do not call the Service. Re-render the last
        # dock list we successfully fetched, if any, so it stays on screen.
        _render_dock_list(st.session_state.get("last_docks"), service_mode, at_ts)
        return

    # ------------------------------------------------------------------
    # get_nearby_docks has no at_ts parameter (R12.1): never pass one.
    # ------------------------------------------------------------------
    result = calls.call(
        service.get_nearby_docks,
        float(coords["lat"]),
        float(coords["lon"]),
        walk_min=walk_min,
        limit=SETTINGS.dock_limit,
        mode=service_mode,
    )

    if result.fell_back:
        st.warning("Live data is unavailable. Showing Demo data.")
    if result.kind == "not_found":
        st.warning(result.message)
        return
    if not result.ok or result.value is None:
        st.error(result.message or "Dock data is unavailable right now.")
        return

    # Hide any dock whose status is not displayable (e.g. "hidden"); R2.2.
    docks = [d for d in result.value if is_displayable(d.status)]
    st.session_state["last_docks"] = docks
    _render_dock_list(docks, service_mode, at_ts)


def _render_dock_list(docks, service_mode: str, at_ts=None) -> None:
    """Render a list of dock results and the dock-trust backups panel."""
    if docks is None:
        return
    if not docks:
        st.info("no docks found within walk minutes")
        return

    dock_by_id = {d.station_id: d for d in docks}
    labels = {f"{d.name} ({d.station_id})": d.station_id for d in docks}

    for dock in docks:
        _render_dock_row(dock)

    # ------------------------------------------------------------------
    # Dock select -> get_dock_trust for backups. A dock NotFound shows a dock
    # message only and leaves the bus cards above unchanged (R2.8).
    # ------------------------------------------------------------------
    option_labels = list(labels.keys())
    # Clear a stale selection (e.g. the None default, or a dock no longer in
    # the current list) so the selectbox initializes to a valid option.
    if st.session_state.get("selected_dock") not in option_labels:
        st.session_state["selected_dock"] = option_labels[0]
    chosen_label = st.selectbox(
        "See backups for a dock",
        options=option_labels,
        key="selected_dock",
    )
    station_id = labels[chosen_label]

    walk_min = float(st.session_state.get("walk_min", SETTINGS.walk_min["default"]))
    # get_dock_trust accepts at_ts, so in Replay the backups follow the slider
    # (R4.2). In Live/Demo at_ts is None and calls.call drops it.
    trust = calls.call(
        service.get_dock_trust,
        station_id,
        walk_min=walk_min,
        mode=service_mode,
        at_ts=at_ts,
    )

    if trust.fell_back:
        st.warning("Live data is unavailable. Showing Demo data.")
    if trust.kind == "not_found":
        st.warning(trust.message)
        return
    if not trust.ok or trust.value is None:
        st.error(trust.message or "Dock data is unavailable right now.")
        return

    backups = trust.value.backups
    st.markdown(f"**Backups for {dock_by_id[station_id].name}**")
    if not backups:
        st.write("no backup available")
        return
    for backup in backups:
        word = status_word(backup.status) or backup.status or ""
        st.write(f"{backup.name} — {word}")


def _render_dock_row(dock) -> None:
    """Render one dock's fields: name, status word, counts, chance, why, age.

    The status word is always shown as text (never color alone). The data age
    is shown in seconds, or the word "unknown" when ``last_reported_age_sec`` is
    absent (R2.2). ``DockResult`` carries no chance sample size, so the chance
    is shown as a bare percentage with no fabricated ``n``.
    """
    word = status_word(dock.status) or dock.status or ""
    low, high = dock.usable_bikes_estimate
    chance_pct = f"{round(dock.chance_bike_on_arrival * 100)}%"

    if dock.last_reported_age_sec is None:
        age_text = "unknown"
    else:
        age_text = f"{int(dock.last_reported_age_sec)} s"

    st.markdown(f"**{dock.name}** — {word}")
    st.write(
        f"App bikes: {dock.app_bikes} · "
        f"Usable: {low}-{high} · "
        f"Chance a bike is there: {chance_pct}"
    )
    st.caption(f"{dock.why}")
    st.caption(f"Data age: {age_text}")


def _render_card(pred, replay_ts) -> None:
    """Render one Unghosted status card for a displayable prediction."""
    word = status_word(pred.status) or ""
    title = f"Route {pred.route_id}"
    if pred.headsign:
        title = f"{title} → {pred.headsign}"

    headline = f"Realistically {pred.realistic_eta_min[0]:g}-{pred.realistic_eta_min[1]:g} min"

    backup_text = None
    if pred.backup is not None:
        backup = pred.backup
        parts = [backup.name or "Backup"]
        if backup.status:
            bw = status_word(backup.status) or backup.status
            parts.append(bw)
        if backup.walk_min is not None:
            parts.append(f"{backup.walk_min:g} min walk")
        backup_text = " · ".join(parts)

    status_card(
        title=title,
        status=pred.status,
        headline=headline,
        why=pred.why,
        chance=pred.chance_it_arrives,
        chance_n=pred.chance_basis.n,
        chance_method=pred.chance_basis.method,
        realistic_eta_min=list(pred.realistic_eta_min),
        meta_lines=[f"App says: {pred.app_eta_min:g} min"],
        backup_text=backup_text,
        outcome=pred.outcome,
        replay_ts=replay_ts,
        app_eta_min=pred.app_eta_min,
    )
