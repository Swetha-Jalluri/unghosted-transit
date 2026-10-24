"""Unit and property tests for the operator view's pure data-shaping helpers.

These cover the findings half of the Operator_View (R5.1-R5.10). They exercise
only the pure helpers (no Streamlit render), so they run fast and offline. The
real ``findings.json`` fixture is loaded through ``core.service.get_findings``
to keep the shapes honest (no hand-built mock numbers).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app import operator
from core.contracts import (
    CalibrationBin,
    EvalInfo,
    Findings,
    ModelInfo,
    RateRow,
)
from core.service import get_findings


@pytest.fixture
def findings() -> Findings:
    """The real demo findings fixture (is_placeholder=True)."""
    return get_findings()


# ---------------------------------------------------------------------------
# fetch_findings (R5.9)
# ---------------------------------------------------------------------------
class TestFetchFindings:
    def test_success_returns_ok_result_with_value(self, findings):
        result = operator.fetch_findings()
        assert result.ok is True
        assert result.kind == "ok"
        assert isinstance(result.value, Findings)
        assert result.message == ""

    def test_error_returns_error_result_without_exception_text(self):
        with patch.object(
            operator.service, "get_findings", side_effect=RuntimeError("boom secret")
        ):
            result = operator.fetch_findings()
        assert result.ok is False
        assert result.kind == "error"
        assert result.value is None
        # No exception text leaks into the user-facing message (R5.9).
        assert "boom secret" not in result.message
        assert result.message == operator.FINDINGS_ERROR


# ---------------------------------------------------------------------------
# generated_at_ny (R5.10)
# ---------------------------------------------------------------------------
class TestGeneratedAtNy:
    def test_iso_with_z_renders_ny_time_with_abbreviation(self):
        # 2025-01-15 14:30 UTC -> 09:30 EST (winter).
        assert operator.generated_at_ny("2025-01-15T14:30:00Z") == (
            "2025-01-15 09:30 EST"
        )

    def test_summer_time_uses_edt(self):
        assert operator.generated_at_ny("2025-07-15T14:30:00Z") == (
            "2025-07-15 10:30 EDT"
        )

    @pytest.mark.parametrize("bad", [None, "", "   ", "not-a-date"])
    def test_missing_or_unparseable_reads_unknown(self, bad):
        assert operator.generated_at_ny(bad) == "unknown"


# ---------------------------------------------------------------------------
# vanish_rows (R5.1)
# ---------------------------------------------------------------------------
class TestVanishRows:
    def test_preserves_service_order_and_formats(self):
        rows = [
            RateRow(group="confirmed", rate=0.08, n=892),
            RateRow(group="unreliable", rate=0.68, n=184),
        ]
        shaped = operator.vanish_rows(rows)
        assert shaped == [
            {"group": "confirmed", "rate": "8.0%", "n": "892"},
            {"group": "unreliable", "rate": "68.0%", "n": "184"},
        ]

    def test_empty_list_yields_no_rows(self):
        assert operator.vanish_rows([]) == []

    def test_fixture_three_tables_nonempty(self, findings):
        assert operator.vanish_rows(findings.vanish_by_status)
        assert operator.vanish_rows(findings.vanish_by_uncertainty)
        assert operator.vanish_rows(findings.vanish_by_route)

    @given(
        rate=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        n=st.integers(min_value=0, max_value=100_000),
    )
    def test_rate_is_one_decimal_percent_and_n_whole(self, rate, n):
        """Validates: Requirements 5.1"""
        (row,) = operator.vanish_rows([RateRow(group="g", rate=rate, n=n)])
        assert row["rate"].endswith("%")
        # exactly one decimal place before the percent sign
        number = row["rate"][:-1]
        assert "." in number and len(number.split(".")[1]) == 1
        assert row["n"] == str(n)  # whole number, no decimals


# ---------------------------------------------------------------------------
# calibration (R5.2)
# ---------------------------------------------------------------------------
class TestCalibration:
    def test_rows_formatted(self, findings):
        rows = operator.calibration_rows(findings.calibration)
        assert len(rows) == len(findings.calibration)
        for row in rows:
            assert row["predicted"].endswith("%")
            assert row["observed"].endswith("%")
            assert row["n"].isdigit()

    def test_empty_rows_and_frame(self):
        assert operator.calibration_rows([]) == []
        assert operator.calibration_chart_frame([]) is None

    def test_frame_has_fraction_columns_and_n(self, findings):
        frame = operator.calibration_chart_frame(findings.calibration)
        assert frame is not None
        assert list(frame.columns) == ["bin", "predicted", "observed", "n"]
        assert frame["predicted"].between(0, 1).all()
        assert frame["observed"].between(0, 1).all()
        assert frame["n"].tolist() == [b.n for b in findings.calibration]


# ---------------------------------------------------------------------------
# model_metrics (R5.3)
# ---------------------------------------------------------------------------
class TestModelMetrics:
    def test_three_decimals_and_whole_n(self, findings):
        m = operator.model_metrics(findings.model)
        assert m.auc == "0.782"
        assert m.brier == "0.156"
        assert m.n_labels == "1547"

    def test_absent_values_read_not_available(self):
        m = operator.model_metrics(
            ModelInfo(method="none", auc=None, brier=None, n_labels=None)
        )
        assert m.auc == "not available"
        assert m.brier == "not available"
        assert m.n_labels == "not available"

    def test_zero_auc_is_shown_as_number(self):
        m = operator.model_metrics(ModelInfo(method="m", auc=0.0, brier=0.0))
        assert m.auc == "0"
        assert m.brier == "0"


# ---------------------------------------------------------------------------
# eta_accuracy (R5.4)
# ---------------------------------------------------------------------------
class TestEtaAccuracy:
    def test_counts_become_percentages_with_n(self, findings):
        eta = operator.eta_accuracy(findings.eta_range_hit)
        assert eta.available is True
        # 1089 / 1123 = 96.97...% -> "97.0%"
        assert eta.range_hit == "97.0%"
        # 34 / 1123 = 3.02...% -> "3.0%"
        assert eta.single_eta_hit == "3.0%"
        assert eta.n == "1123"

    @pytest.mark.parametrize("empty", [{}, {"range_hit": 0, "single_eta_hit": 0, "n": 0}])
    def test_no_values_reads_not_available(self, empty):
        eta = operator.eta_accuracy(empty)
        assert eta.available is False
        assert eta.range_hit == "not available"
        assert eta.single_eta_hit == "not available"
        assert eta.n == "not available"


# ---------------------------------------------------------------------------
# dock_rows (R5.5)
# ---------------------------------------------------------------------------
class TestDockRows:
    def test_name_metric_n_in_order(self, findings):
        rows = operator.dock_rows(findings.least_reliable_docks)
        assert rows == [
            {"name": "Bluebikes Mission", "metric": "out_of_bikes_rate", "n": "87"},
            {"name": "Bluebikes Back Bay", "metric": "out_of_docks_rate", "n": "62"},
        ]

    def test_empty_yields_no_rows(self):
        assert operator.dock_rows([]) == []


# ---------------------------------------------------------------------------
# sample_block (R5.6)
# ---------------------------------------------------------------------------
class TestSampleBlock:
    def test_label_window_ny_and_counts(self, findings):
        block = operator.sample_block(findings)
        assert block.sample_label == "demo_sample_2025_01_15"
        assert block.window_start.endswith(("EST", "EDT"))
        assert block.window_end.endswith(("EST", "EDT"))
        assert block.n_train == "1123"
        assert block.n_test == "424"

    def test_absent_window_and_label_read_not_available(self):
        f = Findings(
            generated_at="2025-01-15T14:30:00Z",
            sample_label="",
            window={},
            totals={},
            vanish_by_status=[],
            vanish_by_uncertainty=[],
            vanish_by_route=[],
            eta_range_hit={},
            least_reliable_docks=[],
            model=ModelInfo(method="none"),
            calibration=[],
            eval=EvalInfo(n_train=0, n_test=0),
            is_placeholder=True,
        )
        block = operator.sample_block(f)
        assert block.sample_label == "not available"
        assert block.window_start == "unknown"
        assert block.window_end == "unknown"
        # Zero counts stay "0" rather than "not available".
        assert block.n_train == "0"
        assert block.n_test == "0"
