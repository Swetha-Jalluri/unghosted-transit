"""Property tests for status-word presentation in ``app.logic``.

# Feature: unghosted-demo, Property 1: Status is always shown as a word
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic import STATUSES, is_displayable, status_word

# Case variants of the three displayable statuses (e.g. "Confirmed", "ESTIMATE").
_valid_status_cased = st.sampled_from(STATUSES).flatmap(
    lambda s: st.sampled_from([s, s.upper(), s.capitalize(), s.title(), s.swapcase()])
)


# Feature: unghosted-demo, Property 1: Status is always shown as a word
@settings(max_examples=200)
@given(status=_valid_status_cased)
def test_displayable_status_renders_a_word(status: str) -> None:
    """A displayable status yields a non-empty word containing it (any case).

    Validates: Requirements 1.7, 1.8, 10.2
    """
    word = status_word(status)
    assert word is not None
    assert word.strip() != ""
    # The canonical status text appears in the word, case-insensitively.
    assert status.strip().lower() in word.lower()
    # is_displayable agrees with status_word.
    assert is_displayable(status) is True


# Feature: unghosted-demo, Property 1: Status is always shown as a word
@settings(max_examples=200)
@given(status=st.text())
def test_non_status_strings_are_omitted(status: str) -> None:
    """Any string that is not one of the three statuses is not displayable.

    Validates: Requirements 1.7, 1.8, 10.2
    """
    if status.strip().lower() in STATUSES:
        # A randomly generated valid status must still render a word.
        assert status_word(status) is not None
        assert is_displayable(status) is True
    else:
        # Everything else (including "hidden" and unknown text) is omitted.
        assert status_word(status) is None
        assert is_displayable(status) is False
