"""G2 -- a contradiction is refused when the pass is created, naming the field.

Never at the gate at seven in the morning. ``Terms`` validates itself in
``__post_init__``, so a contradictory value cannot be handed to the access call
at all; each case below asserts the CODE and the FIELD, because a refusal that
names the wrong field sends the owner to the wrong box.

Control: the validator planted away (``check_terms`` returns at once) -- every
contradiction here is then accepted, and the assertion that a Terms value
cannot exist contradictory goes red.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from fixtures import BOTH, SIX_TO_EIGHT, WEEKDAYS, simple_terms
from garage_pass import findings as f
from garage_pass.access import Outcome, access
from garage_pass.passes import Visit
from garage_pass.terms import AllowancePeriod, Direction, Terms, VisitAllowance, Window

CASES = [
    (
        "valid_to before valid_from",
        dict(valid_from=date(2026, 6, 1), valid_to=date(2026, 5, 31)),
        f.REFUSAL_VALID_TO_BEFORE_VALID_FROM, "valid_to",
    ),
    (
        "a window naming no day",
        dict(windows=(Window(days=frozenset(), start_minute=0, end_minute=60),)),
        f.REFUSAL_WINDOW_HAS_NO_DAYS, "windows[0].days",
    ),
    (
        "a window naming day 8",
        dict(windows=(Window(days=frozenset({8}), start_minute=0, end_minute=60),)),
        f.REFUSAL_WINDOW_DAY_UNKNOWN, "windows[0].days",
    ),
    (
        "a window ending at minute 1441",
        dict(windows=(Window(days=WEEKDAYS, start_minute=0, end_minute=1441),)),
        f.REFUSAL_WINDOW_MINUTE_OUT_OF_RANGE, "windows[0].end_minute",
    ),
    (
        "an empty window",
        dict(windows=(Window(days=WEEKDAYS, start_minute=600, end_minute=600),)),
        f.REFUSAL_WINDOW_ENDS_BEFORE_IT_STARTS, "windows[0].end_minute",
    ),
    (
        "a weekend window on a Monday-to-Wednesday pass",
        dict(
            valid_from=date(2026, 6, 1), valid_to=date(2026, 6, 3),  # Mon..Wed
            windows=(SIX_TO_EIGHT, Window(days=frozenset({6, 7}), start_minute=0, end_minute=1440)),
        ),
        f.REFUSAL_WINDOW_NEVER_OCCURS, "windows[1].days",
    ),
    (
        "a zero maximum stay",
        dict(max_stay=timedelta(0)),
        f.REFUSAL_MAX_STAY_NOT_POSITIVE, "max_stay",
    ),
    (
        "a visit allowance of zero",
        dict(visit_allowance=VisitAllowance(count=0, per=AllowancePeriod.LIFE)),
        f.REFUSAL_VISIT_ALLOWANCE_NOT_POSITIVE, "visit_allowance.count",
    ),
    (
        "a per-window allowance with no windows",
        dict(visit_allowance=VisitAllowance(count=2, per=AllowancePeriod.WINDOW)),
        f.REFUSAL_ALLOWANCE_PER_WINDOW_WITHOUT_WINDOWS, "visit_allowance.per",
    ),
    (
        "no direction",
        dict(directions=frozenset()),
        f.REFUSAL_NO_DIRECTIONS, "directions",
    ),
    (
        "lanes stated but empty",
        dict(allowed_lanes=frozenset()),
        f.REFUSAL_LANES_STATED_BUT_EMPTY, "allowed_lanes",
    ),
    (
        "a blank lane name",
        dict(allowed_lanes=frozenset({"L1", " "})),
        f.REFUSAL_LANE_NAME_BLANK, "allowed_lanes",
    ),
]


@pytest.mark.guarantee("G2")
@pytest.mark.parametrize("what,overrides,code,field", CASES, ids=[c[0] for c in CASES])
def test_a_contradiction_is_refused_naming_the_field(what, overrides, code, field):
    with pytest.raises(f.Refused) as refused:
        simple_terms(**overrides)
    assert refused.value.code == code, what
    assert refused.value.field == field, what


@pytest.mark.guarantee("G2")
def test_the_cases_cover_every_terms_refusal_the_registry_publishes():
    """The control on the list above: derived from the registry, so a refusal
    added to ``check_terms`` without a case here is noticed."""
    import inspect

    from garage_pass import terms as module

    raised_in_validator = {
        name for name in dir(f)
        if name.startswith("REFUSAL_") and name in inspect.getsource(module)
    }
    covered = {code for _w, _o, code, _f in CASES}
    assert raised_in_validator == covered, (
        f"validator raises {sorted(raised_in_validator - covered)} with no case; "
        f"cases name {sorted(covered - raised_in_validator)} the validator never raises"
    )


@pytest.mark.guarantee("G2")
def test_the_same_terms_without_the_contradiction_are_accepted():
    """The negative control: the validator says yes to something, so a red
    above is about the contradiction and not about the validator refusing all."""
    terms = Terms(
        valid_from=date(2026, 1, 1), valid_to=date(2026, 12, 31),
        windows=(SIX_TO_EIGHT,), max_stay=timedelta(hours=10),
        visit_allowance=VisitAllowance(count=3, per=AllowancePeriod.WINDOW),
        directions=BOTH, allowed_lanes=frozenset({"L1"}),
    )
    assert terms.max_stay == timedelta(hours=10)
    assert simple_terms(directions=frozenset({Direction.EXIT})).directions == {Direction.EXIT}


@pytest.mark.guarantee("G2")
def test_a_window_that_occurs_on_one_day_of_a_short_range_is_accepted():
    """Six days or fewer is walked day by day; the boundary case where the
    range is exactly the window's one day must not be refused."""
    monday = date(2026, 6, 1)
    terms = simple_terms(
        valid_from=monday, valid_to=monday,
        windows=(Window(days=frozenset({1}), start_minute=0, end_minute=1440),),
    )
    assert terms.windows[0].days == {1}


@pytest.mark.guarantee("G2")
def test_a_maximum_longer_than_a_window_is_slack_not_a_contradiction_created_and_binding():
    """Windows bind the two instants, never the stay between them, so a
    maximum longer than any window is reachable: created here, then measured
    binding at the exit -- 14:59 covered, 15:01 over the maximum. The first
    cut refused this pass at creation; the L3 settled it by execution.

    Control: the removed refusal re-planted into the validator."""
    from fixtures import a_pass, at, registered, transient_garage

    two_short_windows = (
        Window(days=WEEKDAYS, start_minute=6 * 60, end_minute=10 * 60),
        Window(days=WEEKDAYS, start_minute=14 * 60, end_minute=18 * 60),
    )
    try:
        terms = simple_terms(windows=two_short_windows, max_stay=timedelta(hours=6))
    except f.Refused as refused:
        pytest.fail(f"a slack maximum was refused at creation: {refused}")
    assert terms.max_stay == timedelta(hours=6) and all(
        terms.max_stay > w.length for w in terms.windows
    ), "the premise: the maximum is longer than every window"
    garage = transient_garage()
    pass_ = a_pass(garage_id=garage.id, terms=terms)
    monday = date(2026, 6, 1)
    ledger = [Visit(pass_id=pass_.id, vehicle_identity="CAR-1", entry_lane="L1",
                    entered_at=at(monday, 9))]

    def exit_at(hour, minute):
        return access(
            garage=garage, passes=[pass_], registrations=[registered(pass_)], visits=ledger,
            vehicle_identity="CAR-1", lane="L1", direction=Direction.EXIT,
            at=at(monday, hour, minute),
        )

    inside = exit_at(14, 59)
    assert inside.outcome is Outcome.COVERED, inside
    assert "stayed 5:59:00 of at most 6:00:00" in inside.covering_term
    over = exit_at(15, 1)
    assert over.outcome is Outcome.NOT_COVERED and over.reason == f.OVER_MAX_STAY, over
    assert "6:01:00 elapsed, more than 6:00:00" in over.detail
