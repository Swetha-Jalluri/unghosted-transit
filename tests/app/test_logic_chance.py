"""Property 2: every chance shows its sample size.

``format_chance`` turns a raw chance into rider-facing text. The trust promise
is that a number never appears without the context that lets a rider judge it:
the sample size ``n`` is always present, a ``placeholder`` basis is always
named as such (so an unmeasured number is never mistaken for a measured one),
and a missing chance reads as unavailable with no percentage at all.

Feature: unghosted-demo, Property 2: Every chance shows its sample size
Validates: Requirements 1.5, 1.6, 1.10, 10.3
"""
from __future__ import annotations

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.logic import format_chance

_METHODS = ("model", "empirical", "placeholder")

# Chances span the closed unit interval; n covers the documented 0..1,000,000.
_chances = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
_sample_sizes = st.integers(min_value=0, max_value=1_000_000)
_methods = st.sampled_from(_METHODS)


@hyp_settings(max_examples=200)
@given(chance=_chances, n=_sample_sizes, method=_methods)
def test_property_2_present_chance_shows_sample_size(chance, n, method):
    # Feature: unghosted-demo, Property 2: Every chance shows its sample size
    # Validates: Requirements 1.5, 1.6, 1.10, 10.3
    out = format_chance(chance, n, method)

    # The decimal digits of n always appear (R1.6, R10.3).
    assert str(n) in out

    # A present chance is shown as a percentage (R1.5).
    assert "%" in out

    # The placeholder basis is always named, so an unmeasured number is never
    # dressed up as a measured result (R1.10).
    if method == "placeholder":
        assert "placeholder" in out


@hyp_settings(max_examples=200)
@given(n=_sample_sizes, method=_methods)
def test_property_2_none_chance_is_unavailable_no_percent(n, method):
    # Feature: unghosted-demo, Property 2: Every chance shows its sample size
    # Validates: Requirements 1.5, 1.6, 1.10, 10.3
    out = format_chance(None, n, method)

    # Sample size still present even when the chance is missing (R1.6, R10.3).
    assert str(n) in out

    # A missing chance says it is unavailable and shows no percentage (R1.5).
    assert "unavailable" in out
    assert "%" not in out
