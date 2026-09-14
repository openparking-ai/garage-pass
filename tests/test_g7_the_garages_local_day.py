"""G7 -- terms evaluate in the garage's local day, proven where UTC disagrees.

**A DST TEST THAT STAYS GREEN UNDER A NAIVE UTC IMPLEMENTATION IS MEASURING
NOTHING.** So every instant below is chosen so that the local reading and the
UTC reading fall on DIFFERENT sides of the term:

* 05:30 local on the spring-forward day (offset -06:00 after 02:00) is 11:30Z:
  local says before the 06:00 window opens; UTC says well inside it.
* 05:30 local on the fall-back day (offset -07:00 after 02:00) is 12:30Z: same.
* 19:30 local on the spring-forward day is 01:30Z NEXT DAY: local says inside
  the window and on Sunday; UTC says outside it and on Monday.
* Sunday 23:30 local is Monday 05:30Z: a weekday pass says Sunday, no;
  a UTC reading says Monday.
* A stay from 00:30 to 03:30 local across the fall-back hour is FOUR hours of
  elapsed time; wall-clock subtraction says three (PEP 495).

Controls: ``minute_of_day`` planted to read the UTC clock; ``iso_weekday_of``
planted to read the UTC day; ``elapsed`` planted to subtract wall clocks.
The Phoenix garage is the negative control on each: with no shift, local and
UTC never disagree about the length of a day, so a red there is arithmetic.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from fixtures import (
    FALL_BACK_2026,
    FIXED_ZONE,
    SHIFTING_ZONE,
    SIX_TO_EIGHT,
    SPRING_FORWARD_2026,
    a_pass,
    at,
    registered,
    simple_terms,
    transient_garage,
)
from garage_pass import findings as f
from garage_pass.access import Outcome, access
from garage_pass.localday import elapsed, zone
from garage_pass.passes import Visit
from garage_pass.terms import Direction, Window

EVERY_DAY_SIX_TO_EIGHT = Window(days=frozenset(range(1, 8)), start_minute=360, end_minute=1200)


def entry(garage, terms, when, identity="CAR-1"):
    pass_ = a_pass(garage_ids={garage.id}, terms=terms)
    return access(
        garage=garage, passes=[pass_], registrations=[registered(pass_)], visits=[],
        vehicle_identity=identity, lane="L1", direction=Direction.ENTRY, at=when,
    )


@pytest.mark.guarantee("G7")
@pytest.mark.parametrize("day", [SPRING_FORWARD_2026, FALL_BACK_2026], ids=["spring", "fall"])
def test_the_window_opens_at_six_on_the_garages_clock_on_a_transition_day(day):
    garage = transient_garage(SHIFTING_ZONE)
    terms = simple_terms(windows=(EVERY_DAY_SIX_TO_EIGHT,))
    before = entry(garage, terms, at(day, 5, 30))
    assert before.outcome is Outcome.NOT_COVERED and before.reason == f.OUTSIDE_WINDOW, (
        f"05:30 local on {day} is {at(day, 5, 30).astimezone(zone('UTC'))} -- a UTC "
        "reading puts it inside the window"
    )
    after = entry(garage, terms, at(day, 6, 30))
    assert after.outcome is Outcome.COVERED


@pytest.mark.guarantee("G7")
def test_the_window_closes_at_twenty_on_the_garages_clock_across_the_utc_midnight():
    garage = transient_garage(SHIFTING_ZONE)
    terms = simple_terms(windows=(EVERY_DAY_SIX_TO_EIGHT,))
    when = at(SPRING_FORWARD_2026, 19, 30)  # 01:30Z the next day
    assert when.astimezone(zone("UTC")).date() == SPRING_FORWARD_2026 + timedelta(days=1)
    assert entry(garage, terms, when).outcome is Outcome.COVERED
    assert entry(garage, terms, at(SPRING_FORWARD_2026, 20, 30)).reason == f.OUTSIDE_WINDOW


@pytest.mark.guarantee("G7")
def test_the_weekday_is_the_garages_weekday():
    """Sunday 23:30 in Denver is Monday 05:30Z. A Monday-to-Friday window says
    no; a UTC weekday would say yes -- and the 06:00 edge would ALSO say no in
    UTC, so this instant is chosen inside the window's minutes both ways
    (23:30 local is outside 06:00-20:00). So the window here is all day."""
    garage = transient_garage(SHIFTING_ZONE)
    weekdays_all_day = Window(days=frozenset({1, 2, 3, 4, 5}), start_minute=0, end_minute=1440)
    terms = simple_terms(windows=(weekdays_all_day,))
    sunday_night = at(date(2026, 6, 7), 23, 30)  # Sunday
    assert sunday_night.astimezone(zone("UTC")).isoweekday() == 1, "the UTC reading is Monday"
    answer = entry(garage, terms, sunday_night)
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.OUTSIDE_WINDOW
    assert entry(garage, terms, at(date(2026, 6, 8), 0, 30)).outcome is Outcome.COVERED


@pytest.mark.guarantee("G7")
def test_a_stay_across_the_fall_back_hour_is_measured_in_elapsed_time():
    """00:30 to 03:30 local on the fall-back day is four hours, not three."""
    tz = zone(SHIFTING_ZONE)
    start = at(FALL_BACK_2026, 0, 30)
    end = at(FALL_BACK_2026, 3, 30)
    assert (end - start) == timedelta(hours=3), "PEP 495: same-zone subtraction is wall clock"
    assert elapsed(start, end) == timedelta(hours=4)

    garage = transient_garage(SHIFTING_ZONE)
    pass_ = a_pass(garage_ids={garage.id},
                   terms=simple_terms(max_stay=timedelta(hours=3, minutes=30)))
    answer = access(
        garage=garage, passes=[pass_], registrations=[registered(pass_)],
        visits=[Visit(pass_id=pass_.id, garage_id=garage.id, vehicle_identity="CAR-1",
                      entry_lane="L1", entered_at=start)],
        vehicle_identity="CAR-1", lane="L1", direction=Direction.EXIT, at=end,
    )
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.OVER_MAX_STAY
    assert "4:00:00" in answer.detail
    assert tz.utcoffset(start) != tz.utcoffset(end), "the fixture really crosses the change"


@pytest.mark.guarantee("G7")
def test_a_stay_across_the_spring_forward_hour_is_an_hour_shorter_than_its_clocks():
    start = at(SPRING_FORWARD_2026, 1, 30)
    end = at(SPRING_FORWARD_2026, 3, 30)
    assert (end - start) == timedelta(hours=2)
    assert elapsed(start, end) == timedelta(hours=1)


@pytest.mark.guarantee("G7")
@pytest.mark.parametrize("day", [SPRING_FORWARD_2026, FALL_BACK_2026], ids=["spring", "fall"])
def test_the_negative_control_a_fixed_zone_never_disagrees_with_itself(day):
    """Phoenix: the same assertions hold, and a stay is as long as its clocks
    say. A red here is the arithmetic, not the zone."""
    garage = transient_garage(FIXED_ZONE)
    terms = simple_terms(windows=(EVERY_DAY_SIX_TO_EIGHT,))
    before = entry(garage, terms, at(day, 5, 30, FIXED_ZONE))
    assert before.reason == f.OUTSIDE_WINDOW
    assert entry(garage, terms, at(day, 6, 30, FIXED_ZONE)).outcome is Outcome.COVERED
    start, end = at(day, 0, 30, FIXED_ZONE), at(day, 3, 30, FIXED_ZONE)
    assert elapsed(start, end) == (end - start) == timedelta(hours=3)


@pytest.mark.guarantee("G7")
def test_the_valid_range_is_read_in_the_garages_day():
    """23:30 local on valid_to is inside the range; 00:30 local the next day
    is not -- and the UTC date of the first is already the next day."""
    garage = transient_garage(SHIFTING_ZONE)
    last = date(2026, 6, 30)
    terms = simple_terms(valid_from=date(2026, 6, 1), valid_to=last)
    late = at(last, 23, 30)
    assert late.astimezone(zone("UTC")).date() == last + timedelta(days=1)
    assert entry(garage, terms, late).outcome is Outcome.COVERED
    after = entry(garage, terms, at(last + timedelta(days=1), 0, 30))
    assert after.outcome is Outcome.NOT_COVERED and after.reason == f.EXPIRED


@pytest.mark.guarantee("G7")
def test_a_naive_instant_is_refused_not_read_as_server_time():
    from datetime import datetime

    garage = transient_garage()
    pass_ = a_pass(terms=simple_terms(windows=(SIX_TO_EIGHT,)))
    with pytest.raises(ValueError, match="timezone"):
        access(
            garage=garage, passes=[pass_], registrations=[registered(pass_)], visits=[],
            vehicle_identity="CAR-1", lane="L1", direction=Direction.ENTRY,
            at=datetime(2026, 6, 1, 12, 0),
        )
