"""Operator view.

For bikeshare operations and MBTA/city analysts: aggregate reliability
findings, the least reliable docks, model calibration, and a system-health
panel at a glance.

Findings come from ``core.service.get_findings`` (no mode parameter), fetched
through a small guarded wrapper so no exception text ever reaches the UI. When
``Findings.is_placeholder`` is true a banner sits above every figure and the
word "placeholder" is woven into every table, chart and metric label so
unmeasured numbers are never read as measured results (R5.7, R5.8).

System health comes from ``core.service.get_health`` (also no mode parameter),
fetched through its own guarded wrapper. Findings and health render in two
independent guarded sections, so one failing never hides the other
(R6.3). Every health value flows through :func:`show` so an absent value reads
"not available" while a value of zero stays "0", and any single missing
``data_age_sec`` key reads "not available" without touching the others
(R6.1, R6.2, R12.4).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
import streamlit as st

try:  # altair is a project dependency; guard only so import errors degrade gracefully.
    import altair as alt
except Exception:  # pragma: no cover - altair is pinned, this is defensive only.
    alt = None  # type: ignore[assignment]

from app import calls
from app import logic
from app.components import page_header, placeholder_label, small_table
from core import service
from core.contracts import Findings, Health

# Text shown where a value is absent or a section has no data.
NOT_AVAILABLE = "not available"
NO_DATA = "no data"

# The placeholder banner sentence (R5.7): states the numbers are not measured.
PLACEHOLDER_BANNER = (
    "Preview numbers below are not measured results. They are placeholder "
    "figures shown for layout only until real findings are logged."
)

# Message shown when get_findings raises (R5.9): findings unavailable, no figures.
FINDINGS_ERROR = (
    "Findings are unavailable right now. Other views remain available from the "
    "sidebar."
)

# Message shown when get_health raises (R6.3): no health values, page stays usable.
HEALTH_ERROR = "Health data could not be retrieved."


# ---------------------------------------------------------------------------
# Pure data-shaping helpers (no Streamlit, no I/O). These are property/unit
# tested so the trust presentation cannot silently drift.
# ---------------------------------------------------------------------------
def fetch_findings() -> calls.CallResult[Findings]:
    """Fetch findings without leaking exception text to the UI.

    ``core.service.get_findings`` takes no ``mode`` parameter, so it cannot go
    through ``calls.call`` (which always passes ``mode=``). This mirrors the
    same contract: success -> ``ok`` result; any failure -> ``error`` result
    with a generic, user-safe message and no value (R5.9).
    """
    try:
        value = service.get_findings()
    except Exception:
        return calls.CallResult(
            ok=False,
            value=None,
            kind="error",
            mode_shown="demo",
            fell_back=False,
            message=FINDINGS_ERROR,
            missing_id=None,
        )
    return calls.CallResult(
        ok=True,
        value=value,
        kind="ok",
        mode_shown="demo",
        fell_back=False,
        message="",
        missing_id=None,
    )


def fetch_health() -> calls.CallResult[Health]:
    """Fetch system health without leaking exception text to the UI.

    Like :func:`fetch_findings`, ``core.service.get_health`` takes no ``mode``
    parameter so it cannot go through ``calls.call``. Success -> ``ok`` result;
    any failure -> ``error`` result with a generic, user-safe message and no
    value (R6.3).
    """
    try:
        value = service.get_health()
    except Exception:
        return calls.CallResult(
            ok=False,
            value=None,
            kind="error",
            mode_shown="demo",
            fell_back=False,
            message=HEALTH_ERROR,
            missing_id=None,
        )
    return calls.CallResult(
        ok=True,
        value=value,
        kind="ok",
        mode_shown="demo",
        fell_back=False,
        message="",
        missing_id=None,
    )


def show(value: Any, fmt: Any = logic.fmt_metric) -> str:
    """Format a single health value, mapping absent to "not available".

    ``fmt`` is the formatter to apply (defaults to :func:`app.logic.fmt_metric`,
    which already reads ``None`` as "not available" and keeps a value of zero as
    "0"). When ``value`` is ``None`` the formatter is bypassed so the result is
    always "not available"; this covers a missing ``data_age_sec`` key without
    disturbing the other entries (R6.2, R12.4).
    """
    if value is None:
        return NOT_AVAILABLE
    return fmt(value)


def generated_at_ny(generated_at: Optional[str]) -> str:
    """Format an ISO ``generated_at`` string in America/New_York time.

    ``Findings.generated_at`` is an ISO timestamp string, while
    ``logic.format_ny_time`` works on POSIX seconds. This parses the ISO string
    to POSIX seconds and defers all zone formatting to ``logic.format_ny_time``
    so the display rule stays in one place (R5.10). Unparseable or missing
    input reads "unknown" (same sentinel ``format_ny_time`` uses).
    """
    if not isinstance(generated_at, str) or not generated_at.strip():
        return logic.format_ny_time(None)
    text = generated_at.strip()
    # Accept a trailing "Z" (UTC) which datetime.fromisoformat predates.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return logic.format_ny_time(None)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return logic.format_ny_time(int(moment.timestamp()))


def vanish_rows(rate_rows: list[Any]) -> list[dict[str, str]]:
    """Shape a list of ``RateRow`` into display rows, in service order.

    Each row shows the group name, the rate as a percentage with one decimal
    place (via :func:`app.logic.percent`) and ``n`` as a whole number (R5.1).
    Order is preserved exactly as returned by the service.
    """
    rows: list[dict[str, str]] = []
    for row in rate_rows:
        rows.append(
            {
                "group": str(row.group),
                "rate": logic.percent(row.rate, 1),
                "n": logic.fmt_metric(int(row.n)),
            }
        )
    return rows


def calibration_rows(bins: list[Any]) -> list[dict[str, str]]:
    """Shape calibration bins into table rows (predicted, observed, n).

    Predicted and observed are shown as percentages with one decimal; ``n`` is
    a whole number. An empty list yields no rows so the caller can show
    "not available" for both the table and the chart (R5.2).
    """
    rows: list[dict[str, str]] = []
    for b in bins:
        rows.append(
            {
                "bin": str(b.bin),
                "predicted": logic.percent(b.predicted, 1),
                "observed": logic.percent(b.observed, 1),
                "n": logic.fmt_metric(int(b.n)),
            }
        )
    return rows


def calibration_chart_frame(bins: list[Any]) -> Optional[pd.DataFrame]:
    """Build a tidy DataFrame for the calibration chart, or ``None`` when empty.

    Columns: ``bin``, ``predicted`` and ``observed`` as 0..1 fractions (so the
    axis reads as a probability), and ``n`` for the tooltip. Returns ``None``
    for an empty list so the caller renders "not available" (R5.2).
    """
    if not bins:
        return None
    return pd.DataFrame(
        [
            {
                "bin": str(b.bin),
                "predicted": float(b.predicted),
                "observed": float(b.observed),
                "n": int(b.n),
            }
            for b in bins
        ]
    )


@dataclass(frozen=True)
class ModelMetrics:
    """Formatted model-quality values, each already display-ready."""

    method: str
    auc: str
    brier: str
    n_labels: str


def model_metrics(model: Any) -> ModelMetrics:
    """Format AUC and Brier at 3 decimals and ``n_labels`` as a whole number.

    Each value that is absent (``None``) reads "not available"; a present value
    of zero is still shown as a number (R5.3). ``fmt_metric`` defaults to 3
    decimal places for floats.
    """
    return ModelMetrics(
        method=str(model.method) if model.method is not None else NOT_AVAILABLE,
        auc=logic.fmt_metric(model.auc, 3),
        brier=logic.fmt_metric(model.brier, 3),
        n_labels=logic.fmt_metric(model.n_labels),
    )


@dataclass(frozen=True)
class EtaAccuracy:
    """Formatted ETA accuracy values, or a sentinel when unavailable."""

    available: bool
    range_hit: str
    single_eta_hit: str
    n: str


def eta_accuracy(eta_range_hit: dict[str, int]) -> EtaAccuracy:
    """Format ETA range/single hit as percentages (one decimal) with n.

    ``eta_range_hit`` carries counts (``range_hit``, ``single_eta_hit``, ``n``),
    so each rate is that count divided by ``n``. When the mapping has no values
    (empty or missing ``n``) the result is marked unavailable so the caller
    shows "not available" (R5.4).
    """
    n = eta_range_hit.get("n") if eta_range_hit else None
    if not n:  # empty dict or n == 0 / None -> no rate can be computed.
        return EtaAccuracy(
            available=False,
            range_hit=NOT_AVAILABLE,
            single_eta_hit=NOT_AVAILABLE,
            n=NOT_AVAILABLE,
        )
    range_hit = eta_range_hit.get("range_hit", 0)
    single_eta_hit = eta_range_hit.get("single_eta_hit", 0)
    return EtaAccuracy(
        available=True,
        range_hit=logic.percent(range_hit / n, 1),
        single_eta_hit=logic.percent(single_eta_hit / n, 1),
        n=logic.fmt_metric(int(n)),
    )


def dock_rows(docks: list[dict]) -> list[dict[str, str]]:
    """Shape least-reliable docks into rows (name, metric, n), in service order.

    An empty list yields no rows so the caller shows "no data" (R5.5).
    """
    rows: list[dict[str, str]] = []
    for d in docks:
        rows.append(
            {
                "name": str(d.get("name", NOT_AVAILABLE)),
                "metric": str(d.get("metric", NOT_AVAILABLE)),
                "n": logic.fmt_metric(d.get("n")),
            }
        )
    return rows


@dataclass(frozen=True)
class SampleBlock:
    """Formatted sample-details block for the operator view."""

    sample_label: str
    window_start: str
    window_end: str
    n_train: str
    n_test: str


def sample_block(findings: Findings) -> SampleBlock:
    """Format the sample block: label, NY window and train/test counts.

    Window start/end are rendered in America/New_York via
    ``logic.format_ny_time``; absent values read "not available" (R5.6).
    """
    window = findings.window or {}
    sample_label = findings.sample_label or NOT_AVAILABLE
    return SampleBlock(
        sample_label=sample_label,
        window_start=logic.format_ny_time(window.get("start")),
        window_end=logic.format_ny_time(window.get("end")),
        n_train=logic.fmt_metric(findings.eval.n_train),
        n_test=logic.fmt_metric(findings.eval.n_test),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _render_findings(findings: Findings) -> None:
    """Render every findings figure for a successful ``get_findings`` call."""
    placeholder = bool(findings.is_placeholder)

    # Placeholder banner ABOVE all figures (R5.7).
    if placeholder:
        st.warning(PLACEHOLDER_BANNER, icon="⚠️")

    # Generated-at time in NY, always shown with findings (R5.10).
    st.caption(f"Generated: {generated_at_ny(findings.generated_at)}")

    # Vanish tables (R5.1): status, uncertainty, route, in service order.
    st.subheader(placeholder_label("Vanish rates", placeholder))
    small_table(
        "By status",
        vanish_rows(findings.vanish_by_status),
        is_placeholder=placeholder,
        empty_text=NO_DATA,
    )
    small_table(
        "By uncertainty code",
        vanish_rows(findings.vanish_by_uncertainty),
        is_placeholder=placeholder,
        empty_text=NO_DATA,
    )
    small_table(
        "By route",
        vanish_rows(findings.vanish_by_route),
        is_placeholder=placeholder,
        empty_text=NO_DATA,
    )

    # Calibration table + chart (R5.2): "not available" for both when empty.
    st.subheader(placeholder_label("Model calibration", placeholder))
    cal_rows = calibration_rows(findings.calibration)
    if cal_rows:
        small_table(
            "Calibration bins",
            cal_rows,
            is_placeholder=placeholder,
        )
        _render_calibration_chart(findings.calibration, placeholder)
    else:
        st.caption(placeholder_label("Calibration bins", placeholder))
        st.write(NOT_AVAILABLE)
        st.caption(placeholder_label("Calibration chart", placeholder))
        st.write(NOT_AVAILABLE)

    # Model metrics (R5.3): AUC/Brier at 3 decimals, n_labels whole number.
    metrics = model_metrics(findings.model)
    st.subheader(placeholder_label("Model quality", placeholder))
    m1, m2, m3 = st.columns(3)
    m1.metric(placeholder_label("AUC", placeholder), metrics.auc)
    m2.metric(placeholder_label("Brier score", placeholder), metrics.brier)
    m3.metric(placeholder_label("Labeled n", placeholder), metrics.n_labels)
    st.caption(placeholder_label(f"Method: {metrics.method}", placeholder))

    # ETA accuracy (R5.4): range/single hit as percentages with n, else N/A.
    eta = eta_accuracy(findings.eta_range_hit)
    st.subheader(placeholder_label("ETA accuracy", placeholder))
    if eta.available:
        e1, e2, e3 = st.columns(3)
        e1.metric(placeholder_label("Range hit", placeholder), eta.range_hit)
        e2.metric(
            placeholder_label("Single ETA hit", placeholder), eta.single_eta_hit
        )
        e3.metric(placeholder_label("n", placeholder), eta.n)
    else:
        st.caption(placeholder_label("ETA accuracy", placeholder))
        st.write(NOT_AVAILABLE)

    # Least reliable docks (R5.5): name, metric, n in service order, else no data.
    st.subheader(placeholder_label("Least reliable docks", placeholder))
    small_table(
        "Docks",
        dock_rows(findings.least_reliable_docks),
        is_placeholder=placeholder,
        empty_text=NO_DATA,
    )

    # Sample block (R5.6): "Saturday sample" label, NY window, train/test counts.
    sample = sample_block(findings)
    st.subheader(placeholder_label("Saturday sample", placeholder))
    small_table(
        "Sample details",
        [
            {"field": "sample_label", "value": sample.sample_label},
            {"field": "window start (NY)", "value": sample.window_start},
            {"field": "window end (NY)", "value": sample.window_end},
            {"field": "train n", "value": sample.n_train},
            {"field": "test n", "value": sample.n_test},
        ],
        is_placeholder=placeholder,
    )


def _render_calibration_chart(bins: list[Any], placeholder: bool) -> None:
    """Render the predicted-vs-observed calibration chart with n in the tooltip."""
    frame = calibration_chart_frame(bins)
    st.caption(placeholder_label("Calibration chart", placeholder))
    if frame is None or alt is None:
        st.write(NOT_AVAILABLE)
        return
    chart = (
        alt.Chart(frame)
        .mark_circle(size=90)
        .encode(
            x=alt.X("predicted:Q", title="Predicted", scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("observed:Q", title="Observed", scale=alt.Scale(domain=[0, 1])),
            tooltip=[
                alt.Tooltip("bin:N", title="Bin"),
                alt.Tooltip("predicted:Q", title="Predicted", format=".1%"),
                alt.Tooltip("observed:Q", title="Observed", format=".1%"),
                alt.Tooltip("n:Q", title="n", format="d"),
            ],
        )
    )
    st.altair_chart(chart, use_container_width=True)


# Label for each of the three modes reported by the Service.
_MODE_LABELS = (("demo", "Demo"), ("live", "Live"), ("replay", "Replay"))


def mode_flag(enabled: Optional[bool]) -> str:
    """Return "enabled" / "disabled" for a mode flag, "not available" if absent.

    A missing mode flag (``None``) reads "not available"; otherwise the boolean
    is shown as the word "enabled" or "disabled" so a mode is never conveyed by
    anything other than its word (R6.1, R6.2).
    """
    if enabled is None:
        return NOT_AVAILABLE
    return "enabled" if enabled else "disabled"


def _render_health(health: Health) -> None:
    """Render the system-health panel for a successful ``get_health`` call.

    Every value flows through :func:`show` so absent reads "not available" and
    zero stays "0". Data-age entries are looked up per key so one missing source
    does not affect the others (R6.1, R6.2, R12.4).
    """
    st.subheader("System health")

    # Poll activity: last poll time in NY, polls last hour, success rate.
    rows = health.rows or {}
    age = health.data_age_sec or {}
    modes = health.modes or {}

    c1, c2, c3 = st.columns(3)
    c1.metric("Last poll (NY)", show(health.last_poll_ts, logic.format_ny_time))
    c2.metric("Polls last hour", show(health.polls_last_hour))
    c3.metric("Poll success rate", show(health.poll_success_rate, logic.percent))

    # Row counts for predictions, vehicle positions and docks as whole numbers.
    r1, r2, r3 = st.columns(3)
    r1.metric("Prediction rows", show(rows.get("pred")))
    r2.metric("Vehicle rows", show(rows.get("veh")))
    r3.metric("Dock rows", show(rows.get("dock")))

    # Data age in seconds; any single missing key reads "not available" alone.
    st.caption("Data age (seconds)")
    small_table(
        "Data age",
        [
            {"source": "trip_updates", "age_sec": show(age.get("trip_updates"))},
            {
                "source": "vehicle_positions",
                "age_sec": show(age.get("vehicle_positions")),
            },
            {"source": "docks", "age_sec": show(age.get("docks"))},
        ],
    )

    # Modes labeled with the word "enabled" / "disabled".
    st.caption("Modes")
    small_table(
        "Modes",
        [
            {"mode": label, "state": mode_flag(modes.get(key))}
            for key, label in _MODE_LABELS
        ],
    )

    # Model method name.
    st.caption(f"Model method: {show(health.model_method, str)}")


def render() -> None:
    page_header("Operator view")

    st.write(
        "Measured vanish rates, model quality and the least reliable docks at a "
        "glance. Every figure carries its sample size; we never claim certainty."
    )

    # Findings and health are two INDEPENDENT guarded sections: either can fail
    # on its own without hiding the other (R5.9, R6.3).
    findings_result = fetch_findings()
    if not findings_result.ok or findings_result.value is None:
        # Findings error: show the message, no figures, keep the page usable (R5.9).
        st.error(findings_result.message or FINDINGS_ERROR)
    else:
        _render_findings(findings_result.value)

    st.divider()

    health_result = fetch_health()
    if not health_result.ok or health_result.value is None:
        # Health error: show the message, no health values, keep the rest usable (R6.3).
        st.error(health_result.message or HEALTH_ERROR)
    else:
        _render_health(health_result.value)

    # Attribution + disclaimer are rendered once by streamlit_app.main()'s
    # finally block on every page, including these error branches, so the
    # required legal notices appear whenever this view is shown (R5.10, R7.1).
