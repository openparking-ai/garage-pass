"""G14 -- the fixtures can exercise what they claim.

A fixture is part of the measurement. The shifting zone must shift on the
named days, the fixed zone must not, and the terms matrix must hold a case on
each side of every axis the answer branches on. These assertions live beside
the fixtures; this module runs them as a test, so a fixture that stops holding
its property is a red test and not a quiet loss of coverage.

Control: the shifting zone planted to a zone that does not shift.
"""

from __future__ import annotations

import pytest

from fixtures import (
    assert_fixed_zone_really_does_not_shift,
    assert_shifting_zone_really_shifts,
    assert_the_everything_terms_carry_every_term,
    assert_the_far_zone_is_on_another_day_at_noon_monday,
    assert_the_matrix_holds_both_sides_of_every_axis,
)


@pytest.mark.guarantee("G14")
def test_the_shifting_zone_really_shifts():
    assert_shifting_zone_really_shifts()


@pytest.mark.guarantee("G14")
def test_the_fixed_zone_really_does_not():
    assert_fixed_zone_really_does_not_shift()


@pytest.mark.guarantee("G14")
def test_the_far_zone_is_on_another_day_at_noon_monday_and_does_not_shift():
    assert_the_far_zone_is_on_another_day_at_noon_monday()


@pytest.mark.guarantee("G14")
def test_the_everything_terms_carry_every_term():
    assert_the_everything_terms_carry_every_term()


@pytest.mark.guarantee("G14")
def test_the_matrix_holds_both_sides_of_every_axis():
    assert_the_matrix_holds_both_sides_of_every_axis()
