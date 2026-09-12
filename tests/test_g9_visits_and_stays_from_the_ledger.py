"""G9 -- a visit allowance and a maximum stay are computed from the module's
own recorded visits, and the answer names its denominator.

"Counted 3 recorded entries on pass 'pass-1' in window Mon,Tue,... 06:00-20:00
on 2026-06-01" is a measurement with its instrument and denominator stated.
"3 of 3" alone is a number that two correct measurements of different things
would both produce. The tests below assert the sentence, not just the count.

The store half -- the ledger is the rows the lane wrote -- is in this module
too, marked needs_postgres per test rather than per module, so the pure half
runs everywhere.

A maximum stay with no open recorded entry to measure from is UNMEASURED and
the answer SAYS SO BY NAME (``Answer.unmeasured``) while answering on the terms
that can be evaluated -- never silently treated as satisfied, and never a
refusal, because an exit is never refused an answer (G4).

Controls: the per-window count planted to count the pass's whole life; the
denominator sentence planted to a fixed string; the open-visit lookup planted
to ignore the vehicle identity; the UNMEASURED naming planted away (the stay
then silently treated as satisfied -- wrong-silently, the failure this exists
to catch).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from fixtures import (
    NOON_MONDAY,
    SIX_TO_EIGHT,
    a_pass,
    at,
    registered,
    simple_terms,
    transient_garage,
)
from garage_pass import findings as f
from garage_pass.access import Outcome, access
from garage_pass.passes import Visit
from garage_pass.terms import AllowancePeriod, Direction, VisitAllowance

GARAGE = transient_garage()
MONDAY = date(2026, 6, 1)


def visit(pass_, identity, hour, minute=0, day=MONDAY, exited_hour=None):
    return Visit(
        pass_id=pass_.id, vehicle_identity=identity, entry_lane="L1",
        entered_at=at(day, hour, minute),
        exited_at=at(day, exited_hour) if exited_hour else None,
        exit_lane="L1" if exited_hour else None,
    )


def ask(pass_, visits, direction=Direction.ENTRY, when=NOON_MONDAY, identity="CAR-1"):
    return access(
        garage=GARAGE, passes=[pass_], registrations=[registered(pass_, identity)],
        visits=visits, vehicle_identity=identity, lane="L1", direction=direction, at=when,
    )


@pytest.mark.guarantee("G9")
def test_an_allowance_over_the_life_counts_every_entry_on_the_pass_and_says_so():
    pass_ = a_pass(terms=simple_terms(visit_allowance=VisitAllowance(3, AllowancePeriod.LIFE)))
    ledger = [visit(pass_, "CAR-1", 7, exited_hour=8), visit(pass_, "CAR-2", 9, exited_hour=10)]
    third = ask(pass_, ledger)
    assert third.outcome is Outcome.COVERED
    assert "visit 3 of 3" in third.covering_term
    assert "counted 2 recorded entries on pass 'pass-1' over its life" in third.covering_term
    fourth = ask(pass_, ledger + [visit(pass_, "CAR-3", 11, exited_hour=11)])
    assert fourth.outcome is Outcome.NOT_COVERED and fourth.reason == f.OUT_OF_VISITS
    assert "3 of 3 visit(s) used; counted 3 recorded entries on pass 'pass-1' over its life" in (
        fourth.detail
    )


@pytest.mark.guarantee("G9")
def test_an_allowance_per_window_counts_only_this_windows_entries_and_names_the_window():
    """Entries yesterday, and entries today before the window opened, are not
    in today's window. A life-count would refuse the entry; the per-window
    count admits it and says what it counted."""
    pass_ = a_pass(terms=simple_terms(
        windows=(SIX_TO_EIGHT,), visit_allowance=VisitAllowance(2, AllowancePeriod.WINDOW),
    ))
    friday = date(2026, 5, 29)
    ledger = [
        visit(pass_, "CAR-1", 7, day=friday, exited_hour=8),
        visit(pass_, "CAR-1", 9, day=friday, exited_hour=10),
        visit(pass_, "CAR-1", 5, exited_hour=5),   # Monday, before 06:00: outside the window
        visit(pass_, "CAR-2", 8, exited_hour=9),    # Monday, inside
    ]
    second = ask(pass_, ledger)
    assert second.outcome is Outcome.COVERED, second
    assert "visit 2 of 2" in second.covering_term
    assert (
        "counted 1 recorded entry on pass 'pass-1' in window Mon,Tue,Wed,Thu,Fri 06:00-20:00 "
        "on 2026-06-01"
    ) in second.covering_term
    third = ask(pass_, ledger + [visit(pass_, "CAR-3", 10, exited_hour=11)])
    assert third.reason == f.OUT_OF_VISITS
    assert "counted 2 recorded entries" in third.detail and "on 2026-06-01" in third.detail


@pytest.mark.guarantee("G9")
def test_the_allowance_is_the_passs_not_the_vehicles():
    """A pass may carry many vehicles; the count is over the pass."""
    pass_ = a_pass(terms=simple_terms(visit_allowance=VisitAllowance(2, AllowancePeriod.LIFE)))
    ledger = [visit(pass_, "CAR-2", 7, exited_hour=8), visit(pass_, "CAR-3", 8, exited_hour=9)]
    answer = ask(pass_, ledger, identity="CAR-1")
    assert answer.reason == f.OUT_OF_VISITS, "CAR-1 has never entered, and the pass is used up"


@pytest.mark.guarantee("G9")
def test_a_stay_is_measured_from_the_open_entry_of_this_vehicle_on_this_pass():
    pass_ = a_pass(terms=simple_terms(max_stay=timedelta(hours=2)))
    ledger = [
        visit(pass_, "CAR-1", 7, exited_hour=8),  # this car's earlier, closed visit
        visit(pass_, "CAR-1", 11),                # this car's open visit, 1 hour ago
        visit(pass_, "CAR-2", 11, 30),            # somebody else's open visit, later
    ]
    answer = ask(pass_, ledger, Direction.EXIT)
    assert answer.outcome is Outcome.COVERED, answer
    assert "stayed 1:00:00 of at most 2:00:00" in answer.covering_term
    late = ask(pass_, ledger, Direction.EXIT, when=at(MONDAY, 13, 30))
    assert late.reason == f.OVER_MAX_STAY
    assert "entered 2026-06-01T11:00:00-06:00" in late.detail and "2:30:00 elapsed" in late.detail


@pytest.mark.guarantee("G9")
def test_a_maximum_stay_with_no_recorded_entry_is_unmeasured_and_says_so_by_name():
    """Answered on the terms that CAN be evaluated; the stay named UNMEASURED,
    with why. Not a refusal, not a silent pass."""
    pass_ = a_pass(terms=simple_terms(max_stay=timedelta(hours=2)))
    nothing = ask(pass_, [], Direction.EXIT)
    assert nothing.outcome is Outcome.COVERED and nothing.missing is None
    assert nothing.exit_note == f.EXIT_IS_NEVER_REFUSED
    assert nothing.unmeasured is not None
    assert "max_stay 2:00:00 of pass 'pass-1' could not be measured" in nothing.unmeasured
    assert "no open recorded entry" in nothing.unmeasured
    assert "UNMEASURED" in nothing.covering_term
    closed_only = ask(pass_, [visit(pass_, "CAR-1", 7, exited_hour=8)], Direction.EXIT)
    assert closed_only.outcome is Outcome.COVERED and "no open recorded entry" in (
        closed_only.unmeasured
    )
    entered_later = ask(pass_, [visit(pass_, "CAR-1", 13)], Direction.EXIT)
    assert entered_later.outcome is Outcome.COVERED
    assert "later than this exit" in entered_later.unmeasured
    assert "2026-06-01T13:00:00-06:00" in entered_later.unmeasured
    # the other terms still decide the outcome: an out-of-terms exit with an
    # unmeasurable stay is not-covered AND names the unmeasured stay
    entry_only = a_pass(terms=simple_terms(max_stay=timedelta(hours=2),
                                           allowed_lanes=frozenset({"L9"})))
    out = ask(entry_only, [], Direction.EXIT)
    assert out.outcome is Outcome.NOT_COVERED and out.reason == f.WRONG_LANE
    assert out.unmeasured is None, "the stay was never reached; nothing to name"
    # and a MEASURED stay names nothing
    measured = ask(pass_, [visit(pass_, "CAR-1", 11)], Direction.EXIT)
    assert measured.outcome is Outcome.COVERED and measured.unmeasured is None


@pytest.mark.guarantee("G9")
def test_without_a_maximum_stay_an_exit_needs_no_ledger():
    answer = ask(a_pass(), [], Direction.EXIT)
    assert answer.outcome is Outcome.COVERED


@pytest.mark.guarantee("G9")
def test_the_allowance_is_not_checked_at_exit():
    pass_ = a_pass(terms=simple_terms(visit_allowance=VisitAllowance(1, AllowancePeriod.LIFE)))
    ledger = [visit(pass_, "CAR-1", 7), visit(pass_, "CAR-2", 8, exited_hour=9)]
    assert ask(pass_, ledger).reason == f.OUT_OF_VISITS
    assert ask(pass_, ledger, Direction.EXIT).outcome is Outcome.COVERED


# ---------------------------------------------------------------------------
# the store: the ledger is the rows the lane wrote
# ---------------------------------------------------------------------------

from garage_pass.store.access import access_from_store  # noqa: E402
from garage_pass.store.postgres import tenant  # noqa: E402
from garage_pass.store.records import (  # noqa: E402
    ONE_OPEN_VISIT,
    record_entry,
    record_exit,
    register_vehicle,
)
from store_harness import query, seed, store_test  # noqa: E402


def _store_pass(app, tenant_id, terms):
    pass_ = a_pass(terms=terms)
    seed(app, tenant_id, GARAGE, (pass_,))
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, GARAGE.id, pass_.id, "CAR-1", date(2026, 1, 1))
        register_vehicle(cursor, tenant_id, GARAGE.id, pass_.id, "CAR-2", date(2026, 1, 1))
    app.commit()
    return pass_


def _entry(app, tenant_id, pass_, identity, hour, day=MONDAY):
    with tenant(app, tenant_id) as cursor:
        record_entry(cursor, tenant_id, GARAGE.id, pass_.id, identity, "L1", at(day, hour))
    app.commit()


def _exit(app, tenant_id, pass_, identity, hour, day=MONDAY):
    with tenant(app, tenant_id) as cursor:
        record_exit(cursor, tenant_id, GARAGE.id, pass_.id, identity, "L1", at(day, hour))
    app.commit()


@pytest.mark.guarantee("G9")
@store_test
def test_the_store_counts_the_entries_the_lane_recorded(app, tenant_id):
    pass_ = _store_pass(app, tenant_id, simple_terms(
        visit_allowance=VisitAllowance(2, AllowancePeriod.LIFE)))
    _entry(app, tenant_id, pass_, "CAR-1", 7)
    _exit(app, tenant_id, pass_, "CAR-1", 8)
    second = access_from_store(app, tenant_id, GARAGE.id, "CAR-2", "L1", Direction.ENTRY,
                               NOON_MONDAY)
    assert second.outcome is Outcome.COVERED and "visit 2 of 2" in second.covering_term
    _entry(app, tenant_id, pass_, "CAR-2", 9)
    third = access_from_store(app, tenant_id, GARAGE.id, "CAR-1", "L1", Direction.ENTRY,
                              NOON_MONDAY)
    assert third.reason == f.OUT_OF_VISITS
    assert "counted 2 recorded entries on pass 'pass-1' over its life" in third.detail


@pytest.mark.guarantee("G9")
@store_test
def test_the_store_measures_a_stay_from_the_recorded_entry(app, tenant_id):
    pass_ = _store_pass(app, tenant_id, simple_terms(max_stay=timedelta(hours=2)))
    _entry(app, tenant_id, pass_, "CAR-1", 9)
    answer = access_from_store(app, tenant_id, GARAGE.id, "CAR-1", "L1", Direction.EXIT,
                               NOON_MONDAY)
    assert answer.reason == f.OVER_MAX_STAY and "3:00:00 elapsed" in answer.detail
    nothing = access_from_store(app, tenant_id, GARAGE.id, "CAR-2", "L1", Direction.EXIT,
                                NOON_MONDAY)
    assert nothing.outcome is Outcome.COVERED and nothing.missing is None
    assert nothing.unmeasured and "no open recorded entry" in nothing.unmeasured


@pytest.mark.guarantee("G9")
@store_test
def test_one_open_visit_per_vehicle_per_pass_by_refusal_and_by_index(app, tenant_id):
    import psycopg

    pass_ = _store_pass(app, tenant_id, simple_terms())
    _entry(app, tenant_id, pass_, "CAR-1", 7)
    with pytest.raises(f.Refused) as refused:
        _entry(app, tenant_id, pass_, "CAR-1", 8)
    app.rollback()
    assert refused.value.code == f.REFUSAL_VISIT_ALREADY_OPEN
    (garage_uuid, pass_uuid) = query(
        app, tenant_id, "SELECT garage_id, id FROM passes WHERE external_id = 'pass-1'")[0]
    with pytest.raises(psycopg.errors.UniqueViolation) as violation:
        with tenant(app, tenant_id) as cursor:
            cursor.execute(
                "INSERT INTO visits (tenant_id, garage_id, pass_id, vehicle_identity, entry_lane, "
                "entered_at) VALUES (%s, %s, %s, 'CAR-1', 'L1', now())",
                (tenant_id, garage_uuid, pass_uuid),
            )
    app.rollback()
    assert violation.value.diag.constraint_name == ONE_OPEN_VISIT
    with pytest.raises(f.Refused) as refused:
        _exit(app, tenant_id, pass_, "CAR-2", 9)
    app.rollback()
    assert refused.value.code == f.REFUSAL_NO_OPEN_VISIT
    with pytest.raises(f.Refused) as refused:
        _exit(app, tenant_id, pass_, "CAR-1", 6)
    app.rollback()
    assert refused.value.code == f.REFUSAL_EXIT_BEFORE_ENTRY
    _exit(app, tenant_id, pass_, "CAR-1", 8)
    assert query(app, tenant_id, "SELECT count(*) FROM visits WHERE exited_at IS NULL") == [(0,)]
