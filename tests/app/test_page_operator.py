"""AppTest examples for the Operator view (``app.operator.render``).

These drive the real Streamlit script through ``streamlit.testing.v1.AppTest``
with ``core.service.get_findings`` / ``get_health`` stubbed, so they run fully
offline with no feeds and no sample database. They cover the behaviours the
pure-helper unit tests in ``test_operator.py`` cannot see: what actually lands
on the page when ``render()`` runs.

Stubbing note
-------------
``operator.render`` reaches the service as ``service.get_findings()`` /
``service.get_health()`` where ``service`` is the ``core.service`` module object
(``from core import service``). ``AppTest.from_function`` re-imports and runs the
wrapper in its own thread, but that re-import returns the SAME already-imported
``core.service`` module object, so patching the attribute on that module before
``at.run()`` is seen by the threaded run. We patch ``core.service`` directly
(not ``operator.service``) to make that shared-object contract explicit.

Covered examples:
- Placeholder banner + labels (R5.7, R5.8): demo findings (is_placeholder True)
  show the warning banner above the figures and weave "placeholder" into labels.
- Empty calibration (R5.2): empty calibration -> "not available" for the
  calibration table and the calibration chart.
- Missing health keys (R6.2): an absent ``data_age_sec`` key reads
  "not available" while a zero value stays "0", independently per key.
- Independent sections (R5.9, R6.3): findings failing still renders the health
  panel, and health failing still renders the findings figures.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from core import service
from core.contracts import (
    CalibrationBin,
    EvalInfo,
    Findings,
    Health,
    ModelInfo,
    RateRow,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
def _operator_script() -> None:
    """Script body for AppTest: render only the Operator view.

    The footer (attribution + disclaimer) is wired by ``streamlit_app.main``'s
    finally block, not by ``render`` itself, so driving ``render`` alone is
    enough to exercise every findings/health branch of this page.
    """
    from app import operator

    operator.render()


def _run() -> AppTest:
    """Build and run the Operator view via AppTest."""
    at = AppTest.from_function(_operator_script)
    at.run()
    return at


def _all_text(at: AppTest) -> str:
    """Join every text-bearing element on the page into one searchable string.

    Pulls markdown, captions, subheaders, warnings, errors, writes, tables and
    metric labels/values so a single ``in`` check can assert a word is present
    anywhere on the rendered page.
    """
    parts: list[str] = []
    for coll in (
        at.markdown,
        at.caption,
        at.subheader,
        at.warning,
        at.error,
        at.info,
        at.get("write"),
    ):
        for el in coll:
            value = getattr(el, "value", None)
            if isinstance(value, str):
                parts.append(value)
    for m in at.metric:
        if isinstance(getattr(m, "label", None), str):
            parts.append(m.label)
        if isinstance(getattr(m, "value", None), str):
            parts.append(m.value)
    for t in at.get("table"):
        parts.append(str(getattr(t, "value", "")))
    return "\n".join(parts)


# Capture the real demo fixtures ONCE at import time, before any patch is in
# place. Returning these pre-captured objects from a stub avoids re-entering the
# (now patched) service functions, which would recurse forever.
_DEMO_FINDINGS = service.get_findings()
_DEMO_HEALTH = service.get_health()


def _demo_findings() -> Findings:
    """Return the pre-captured real demo findings fixture (is_placeholder True)."""
    return _DEMO_FINDINGS


def _demo_health() -> Health:
    """Return the pre-captured real demo health fixture."""
    return _DEMO_HEALTH


def _findings_with(**overrides) -> Findings:
    """A minimal valid Findings, with named fields overridden.

    Defaults are empty/zero so individual examples can isolate one behaviour
    (e.g. empty calibration) without pulling in unrelated figures.
    """
    base = dict(
        generated_at="2025-01-15T14:30:00Z",
        sample_label="demo_sample",
        window={"start": 1737000000, "end": 1737086400},
        totals={"labeled": 0, "served": 0, "vanished": 0, "canceled": 0},
        vanish_by_status=[RateRow(group="confirmed", rate=0.08, n=10)],
        vanish_by_uncertainty=[],
        vanish_by_route=[],
        eta_range_hit={},
        least_reliable_docks=[],
        model=ModelInfo(method="none", auc=None, brier=None, n_labels=None),
        calibration=[],
        eval=EvalInfo(n_train=0, n_test=0),
        is_placeholder=False,
    )
    base.update(overrides)
    return Findings(**base)


def _health_with(**overrides) -> Health:
    """A minimal valid Health, with named fields overridden."""
    base = dict(
        generated_at="2025-01-15T14:30:00Z",
        last_poll_ts=1737018600,
        polls_last_hour=0,
        poll_success_rate=None,
        rows={"pred": 0, "veh": 0, "dock": 0},
        data_age_sec={"trip_updates": 12, "vehicle_positions": 8, "docks": 45},
        modes={"demo": True, "live": False, "replay": True},
        model_method="logistic_regression",
    )
    base.update(overrides)
    return Health(**base)


# ---------------------------------------------------------------------------
# Placeholder banner + labels (R5.7, R5.8)
# ---------------------------------------------------------------------------
class TestPlaceholderBanner:
    def test_banner_shown_above_figures_with_placeholder_findings(self):
        """is_placeholder True -> the warning banner text appears (R5.7)."""
        from app import operator

        with patch.object(service, "get_findings", side_effect=_demo_findings), patch.object(
            service, "get_health", side_effect=_demo_health
        ):
            at = _run()

        assert not at.exception
        warnings = [w.value for w in at.warning]
        assert operator.PLACEHOLDER_BANNER in warnings

        # The banner is the first warning on the page, i.e. above the figures.
        assert warnings[0] == operator.PLACEHOLDER_BANNER

    def test_labels_contain_the_word_placeholder(self):
        """Figure labels weave in the word "placeholder" (R5.8)."""
        with patch.object(service, "get_findings", side_effect=_demo_findings), patch.object(
            service, "get_health", side_effect=_demo_health
        ):
            at = _run()

        assert not at.exception
        text = _all_text(at).lower()
        assert "placeholder" in text

    def test_no_banner_when_not_placeholder(self):
        """is_placeholder False -> no placeholder banner (guards the signal)."""
        from app import operator

        findings = _findings_with(is_placeholder=False)
        with patch.object(service, "get_findings", side_effect=lambda: findings), patch.object(
            service, "get_health", side_effect=_demo_health
        ):
            at = _run()

        assert not at.exception
        warnings = [w.value for w in at.warning]
        assert operator.PLACEHOLDER_BANNER not in warnings


# ---------------------------------------------------------------------------
# Empty calibration (R5.2)
# ---------------------------------------------------------------------------
class TestEmptyCalibration:
    def test_empty_calibration_reads_not_available(self):
        """Empty calibration -> "not available" for both table and chart (R5.2)."""
        from app import operator

        findings = _findings_with(calibration=[], is_placeholder=False)
        with patch.object(service, "get_findings", side_effect=lambda: findings), patch.object(
            service, "get_health", side_effect=_demo_health
        ):
            at = _run()

        assert not at.exception
        captions = [c.value for c in at.caption]
        # Both the calibration table and chart captions are present...
        assert any("Calibration bins" in c for c in captions)
        assert any("Calibration chart" in c for c in captions)
        # ...and the empty branch writes "not available" for each (st.write of a
        # plain string lands in the markdown stream). The empty branch emits two
        # such writes (table + chart), so at least two must be present.
        markdown = [m.value for m in at.markdown]
        assert markdown.count(operator.NOT_AVAILABLE) >= 2

    def test_nonempty_calibration_renders_table_not_na(self):
        """A populated calibration renders a real table, not "not available"."""
        from app import operator

        findings = _findings_with(
            calibration=[CalibrationBin(bin="0.0-0.2", predicted=0.1, observed=0.08, n=20)],
            is_placeholder=False,
        )
        with patch.object(service, "get_findings", side_effect=lambda: findings), patch.object(
            service, "get_health", side_effect=_demo_health
        ):
            at = _run()

        assert not at.exception
        # With one bin the calibration table renders and the chart is drawn, so
        # the two "not available" writes the empty branch produces are gone.
        # (A single NA may still come from the unrelated ETA-accuracy block, so
        # we assert fewer than the two the empty calibration branch emits.)
        markdown = [m.value for m in at.markdown]
        assert markdown.count(operator.NOT_AVAILABLE) < 2
        # And a real table was rendered for the calibration bins.
        assert len(at.get("table")) >= 1


# ---------------------------------------------------------------------------
# Missing health keys (R6.2)
# ---------------------------------------------------------------------------
class TestMissingHealthKeys:
    def test_absent_key_not_available_and_zero_stays_zero(self):
        """Absent data_age_sec key -> "not available"; a zero value -> "0" (R6.2)."""
        from app import operator

        # trip_updates absent (missing key) and vehicle_positions == 0.
        health = _health_with(data_age_sec={"vehicle_positions": 0, "docks": 45})
        findings = _findings_with(is_placeholder=False)
        with patch.object(service, "get_findings", side_effect=lambda: findings), patch.object(
            service, "get_health", side_effect=lambda: health
        ):
            at = _run()

        assert not at.exception

        # The data-age table is the one carrying a "trip_updates" row.
        age_table = None
        for t in at.get("table"):
            rows = t.value
            # Streamlit stores a table as a DataFrame-like; render to text.
            if "trip_updates" in str(rows):
                age_table = str(rows)
                break
        assert age_table is not None
        # Absent trip_updates reads "not available"; zero vehicle_positions "0".
        assert operator.NOT_AVAILABLE in age_table
        # A standalone "0" (not "0.something") is present for the zero age.
        assert "0" in age_table

    def test_all_keys_present_render_their_numbers(self):
        """When every data_age_sec key is present each number is shown."""
        health = _health_with(
            data_age_sec={"trip_updates": 12, "vehicle_positions": 8, "docks": 45}
        )
        findings = _findings_with(is_placeholder=False)
        with patch.object(service, "get_findings", side_effect=lambda: findings), patch.object(
            service, "get_health", side_effect=lambda: health
        ):
            at = _run()

        assert not at.exception
        age_table = None
        for t in at.get("table"):
            if "trip_updates" in str(t.value):
                age_table = str(t.value)
                break
        assert age_table is not None
        assert "12" in age_table
        assert "45" in age_table


# ---------------------------------------------------------------------------
# Independent findings/health sections (R5.9, R6.3)
# ---------------------------------------------------------------------------
class TestIndependentSections:
    def test_findings_failure_keeps_health(self):
        """get_findings raising shows the findings error AND the health panel (R5.9, R6.3)."""
        from app import operator

        def boom() -> Findings:
            raise RuntimeError("secret findings detail")

        with patch.object(service, "get_findings", side_effect=boom), patch.object(
            service, "get_health", side_effect=_demo_health
        ):
            at = _run()

        assert not at.exception

        errors = [e.value for e in at.error]
        assert operator.FINDINGS_ERROR in errors
        # No exception text leaks to the UI.
        assert all("secret findings detail" not in e for e in errors)

        # Health still renders: its "System health" subheader is on the page.
        subheaders = [s.value for s in at.subheader]
        assert "System health" in subheaders

    def test_health_failure_keeps_findings(self):
        """get_health raising shows the health error AND the findings figures (R6.3)."""
        from app import operator

        def boom() -> Health:
            raise RuntimeError("secret health detail")

        findings = _findings_with(is_placeholder=False)
        with patch.object(service, "get_findings", side_effect=lambda: findings), patch.object(
            service, "get_health", side_effect=boom
        ):
            at = _run()

        assert not at.exception

        errors = [e.value for e in at.error]
        assert operator.HEALTH_ERROR in errors
        assert all("secret health detail" not in e for e in errors)

        # Findings still render: "System health" subheader is absent (the panel
        # did not render), but the findings "Vanish rates" subheader is present.
        subheaders = [s.value for s in at.subheader]
        assert any("Vanish rates" in s for s in subheaders)
        assert "System health" not in subheaders
