"""Property tests for missing-value and zero display in ``app.logic``.

# Feature: unghosted-demo, Property 7: Missing values read "not available", zero stays zero
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic import fmt_metric, percent


# Feature: unghosted-demo, Property 7: Missing values read "not available", zero stays zero
def test_missing_reads_not_available_zero_stays_zero() -> None:
    """None gives "not available"; zero reads "0", never "not available".

    Validates: Requirements 5.2, 5.3, 5.4, 6.2
    """
    # Missing values (None) read "not available" for both helpers.
    assert fmt_metric(None) == "not available"
    assert percent(None) == "not available"

    # Zero stays zero: it contains the digit "0" and is not the missing text.
    assert "0" in fmt_metric(0)
    assert fmt_metric(0) != "not available"

    assert "0" in percent(0.0)
    assert percent(0.0) != "not available"


# Feature: unghosted-demo, Property 7: Missing values read "not available", zero stays zero
@settings(max_examples=200)
@given(x=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_percent_default_has_one_decimal_place(x: float) -> None:
    """percent(x) with default places=1 ends with "%" and has one decimal.

    Validates: Requirements 5.2, 5.4
    """
    text = percent(x)
    assert text != "not available"
    assert text.endswith("%")

    number_text = text[:-1]  # strip the trailing "%"
    assert "." in number_text, f"expected a decimal point in {text!r}"
    decimals = number_text.split(".", 1)[1]
    assert len(decimals) == 1, f"expected exactly one decimal place in {text!r}"


# Feature: unghosted-demo, Property 7: Missing values read "not available", zero stays zero
@settings(max_examples=200)
@given(
    x=st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)
    .filter(lambda v: v != 0 and v != int(v))
)
def test_fmt_metric_float_uses_three_decimals(x: float) -> None:
    """fmt_metric(float) with default places=3 renders three decimals.

    Only non-zero, non-integer floats are covered: integers render without a
    decimal point and zero stays "0" (checked separately above).

    Validates: Requirements 5.3, 6.2
    """
    text = fmt_metric(x)
    assert text != "not available"
    assert "." in text, f"expected a decimal point in {text!r}"
    decimals = text.split(".", 1)[1]
    assert len(decimals) == 3, f"expected exactly three decimals in {text!r}"
