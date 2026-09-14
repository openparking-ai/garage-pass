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

**THE INSTANTS A STAY IS MEASURED BETWEEN ARE RENDERED IN THE GARAGE'S ZONE**,
whatever offset each arrived with. Measured before this: the store handed the
recorded entry back in the database SESSION's zone (the Mac's clock, +03:00)
and the detail showed it beside an exit in the caller's -06:00 -- the instants
and the duration were right, the rendering was not, and a reader comparing
the two clocks would have got the stay wrong by nine hours.

**THE STAY IS MEASURED AT THE GARAGE THE CAR IS LEAVING.** A pass names a set
of garages and the visits handed in span them all -- the allowance counts every
garage's entries (C5) -- but the entry a stay is measured from is the one
recorded at the garage answering. Measured before this (the G3a fix round's
receipt named it, the engine-stay round built it): with no garage on the visit,
an exit at garage B found the entry open at A, measured eleven hours from it
and answered OVER_MAX_STAY quoting A's instant -- wrong-silently, at the
barrier. Now a ``Visit`` carries its garage; an entry open elsewhere is not this
exit's entry, and the stay is UNMEASURED and named.

**EACH RECORDED ENTRY IS READ ON THE CLOCK OF THE GARAGE IT WAS RECORDED AT.**
The allowance counts every garage of the pass (C5); whether an entry fell "in
this window, today" is read in the zone of the garage it was recorded at, and
the pass's garages reach the engine (``garages``) so it can. Measured before
this (the G3a merge gate): the per-window count read every garage's entries
on the ASKING garage's clock, so on a pass over Denver and Tokyo a visit at
Tokyo at 09:00 Monday read at Denver as 18:00 Sunday, counted nothing, and a
one-per-window allowance was spent twice -- with every test green, because no
test put two garages of one pass in two zones. The tests below do, with the
same-zone reading as the control, and the denominator sentence says on whose
clock each entry was read. An entry at a garage whose clock is not here is
REFUSED by name at an entry, never read on the wrong clock (G25 measures the
refusals; the LIFE allowance reads no clock and is unchanged).

Controls: the per-window count planted to count the pass's whole life; the
denominator sentence planted to a fixed string; every entry planted back onto
the asking garage's clock; the open-visit lookup planted to ignore the vehicle
identity, and planted to ignore the garage; the UNMEASURED naming planted away
(the stay then silently treated as satisfied -- wrong-silently, the failure
this exists to catch); the rendering planted back to each instant's own offset.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from fixtures import (
    FAR_ZONE,
    NOON_MONDAY,
    SIX_TO_EIGHT,
    a_pass,
    at,
    far_garage,
    lanes_at,
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


def visit(pass_, identity, hour, minute=0, day=MONDAY, exited_hour=None,
          garage_id=GARAGE.id):
    return Visit(
        pass_id=pass_.id, garage_id=garage_id, vehicle_identity=identity, entry_lane="L1",
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
def test_a_per_window_count_reads_each_entry_on_the_clock_of_the_garage_it_was_recorded_at():
    """THE MIXED-ZONE PASS: Denver and Tokyo, one visit per window, Mon-Fri
    06:00-20:00. ONE INSTANT, 2026-06-01T09:00+09:00 -- Monday 09:00 in Tokyo,
    Sunday 18:00 in Denver -- recorded at Tokyo counts against Monday's window
    (it is Monday 09:00 where the car drove in), and recorded at Denver does
    not (it is Sunday there). The gate's own case, flipped: the entry at Denver
    at 09:00 Monday is OUT_OF_VISITS with Tokyo's visit counted, and the
    denominator says the entry was read in the local day of the garage it was
    recorded at, naming that garage. The control is the same instant recorded
    at Denver itself: counted 0, covered -- the reading a single clock gives,
    right only because the entry's garage IS the asking garage."""
    denver, tokyo = GARAGE, far_garage()
    pass_ = a_pass(garage_ids={denver.id, tokyo.id}, terms=simple_terms(
        windows=(SIX_TO_EIGHT,), visit_allowance=VisitAllowance(1, AllowancePeriod.WINDOW)))
    monday_9_tokyo = at(MONDAY, 9, timezone=FAR_ZONE)
    read_at_denver = monday_9_tokyo.astimezone(at(MONDAY, 0).tzinfo).isoformat()
    assert read_at_denver == "2026-05-31T18:00:00-06:00"

    def entry_at_denver(visits):
        return access(garage=denver, garages=[tokyo], passes=[pass_],
                      registrations=[registered(pass_)], visits=visits, vehicle_identity="CAR-1",
                      lane="L1", direction=Direction.ENTRY, at=at(MONDAY, 9))

    at_tokyo = Visit(pass_id=pass_.id, garage_id=tokyo.id, vehicle_identity="CAR-1",
                     entry_lane="L1", entered_at=monday_9_tokyo,
                     exited_at=monday_9_tokyo + timedelta(hours=1), exit_lane="L1")
    spent = entry_at_denver([at_tokyo])
    assert spent.outcome is Outcome.NOT_COVERED and spent.reason == f.OUT_OF_VISITS, spent
    assert (
        "1 of 1 visit(s) used; counted 1 recorded entry on pass 'pass-1' in window "
        "Mon,Tue,Wed,Thu,Fri 06:00-20:00 on 2026-06-01, each read in the local day of the "
        "garage it was recorded at (garage-far: 1)"
    ) in spent.detail, spent.detail
    # the control: the SAME instant recorded at Denver is Sunday evening there
    at_denver = Visit(pass_id=pass_.id, garage_id=denver.id, vehicle_identity="CAR-1",
                      entry_lane="L1", entered_at=monday_9_tokyo,
                      exited_at=monday_9_tokyo + timedelta(hours=1), exit_lane="L1")
    free = entry_at_denver([at_denver])
    assert free.outcome is Outcome.COVERED, free
    assert "visit 1 of 1; counted 0 recorded entries" in free.covering_term
    assert "recorded at (none)" in free.covering_term
    # and the count is still ONE COUNT OVER THE SET (C5): a two-visit allowance,
    # one entry at each garage in Monday's window on its own clock, is spent
    two = a_pass(garage_ids={denver.id, tokyo.id}, terms=simple_terms(
        windows=(SIX_TO_EIGHT,), visit_allowance=VisitAllowance(2, AllowancePeriod.WINDOW)))
    both = [
        Visit(pass_id=two.id, garage_id=tokyo.id, vehicle_identity="CAR-1", entry_lane="L1",
              entered_at=monday_9_tokyo, exited_at=monday_9_tokyo + timedelta(hours=1),
              exit_lane="L1"),
        visit(two, "CAR-1", 7, exited_hour=8),   # Monday 07:00 at Denver
    ]
    spent_both = access(garage=denver, garages=[tokyo], passes=[two],
                        registrations=[registered(two)], visits=both, vehicle_identity="CAR-1",
                        lane="L1", direction=Direction.ENTRY, at=at(MONDAY, 9))
    assert spent_both.reason == f.OUT_OF_VISITS, spent_both
    assert "counted 2 recorded entries" in spent_both.detail
    assert "(garage-downtown: 1, garage-far: 1)" in spent_both.detail, spent_both.detail
    # the same-zone reading is EXACTLY as before: two Denver garages, the
    # sentence and the count unchanged but for naming the garage
    twin = transient_garage()
    twin = type(twin)(id="garage-twin", timezone=twin.timezone, transient_available=True)
    same_zone = a_pass(garage_ids={denver.id, twin.id}, terms=simple_terms(
        windows=(SIX_TO_EIGHT,), visit_allowance=VisitAllowance(2, AllowancePeriod.WINDOW)))
    ledger = [visit(same_zone, "CAR-1", 7, exited_hour=8, garage_id=twin.id)]
    second = access(garage=denver, garages=[twin], passes=[same_zone],
                    registrations=[registered(same_zone)], visits=ledger, vehicle_identity="CAR-1",
                    lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY)
    assert second.outcome is Outcome.COVERED and "visit 2 of 2" in second.covering_term
    assert "counted 1 recorded entry on pass 'pass-1' in window" in second.covering_term
    assert "(garage-twin: 1)" in second.covering_term


@pytest.mark.guarantee("G9")
def test_the_life_allowance_reads_no_clock_and_counts_every_garages_entries_unchanged():
    """The LIFE branch has no clock and gains none: on the mixed-zone pass the
    same entries count wherever they were recorded, and with NO garages handed
    in at all -- nothing to read them on, and nothing needs to."""
    denver, tokyo = GARAGE, far_garage()
    pass_ = a_pass(garage_ids={denver.id, tokyo.id}, terms=simple_terms(
        visit_allowance=VisitAllowance(2, AllowancePeriod.LIFE)))
    ledger = [
        Visit(pass_id=pass_.id, garage_id=tokyo.id, vehicle_identity="CAR-1", entry_lane="L1",
              entered_at=at(MONDAY, 9, timezone=FAR_ZONE)),
        visit(pass_, "CAR-2", 7, exited_hour=8),
    ]
    for handed_in in ([], [tokyo]):
        answer = access(garage=denver, garages=handed_in, passes=[pass_],
                        registrations=[registered(pass_)], visits=ledger, vehicle_identity="CAR-1",
                        lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY)
        assert answer.reason == f.OUT_OF_VISITS, (handed_in, answer)
        assert "counted 2 recorded entries on pass 'pass-1' over its life" in answer.detail


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
def test_a_stay_is_measured_from_the_entry_recorded_at_the_garage_the_car_is_leaving():
    """A pass names a set of garages and the ledger handed in spans them all
    (the allowance counts every garage's entries). The STAY does not: it is
    measured from the entry recorded at the garage answering, and an entry
    still open at another garage of the set is not this exit's entry -- the
    stay is then UNMEASURED and named, A's instant nowhere in the answer.
    Measured before this: the exit at B was OVER_MAX_STAY from A's entry."""
    pass_ = a_pass(garage_ids={GARAGE.id, "garage-other"},
                   terms=simple_terms(max_stay=timedelta(hours=1)))
    elsewhere = [visit(pass_, "CAR-1", 1, garage_id="garage-other")]  # eleven hours ago, elsewhere
    here = ask(pass_, elsewhere, Direction.EXIT)
    assert here.outcome is Outcome.COVERED and here.reason is None, here
    assert here.unmeasured is not None and "at this garage" in here.unmeasured
    assert "01:00" not in here.unmeasured and "01:00" not in (here.detail or "")
    # the control: the same entry recorded HERE is this garage's, and it is over
    same = ask(pass_, [visit(pass_, "CAR-1", 1)], Direction.EXIT)
    assert same.reason == f.OVER_MAX_STAY and "11:00:00 elapsed" in same.detail
    assert "entered 2026-06-01T01:00:00-06:00" in same.detail


@pytest.mark.guarantee("G9")
def test_the_stays_instants_are_rendered_in_the_garages_zone_whatever_offset_they_arrived_in():
    """The recorded entry arrives as +03:00 (the same instant as 11:00 -06:00)
    and the exit as UTC; the detail shows both as the garage's wall clock."""
    from datetime import UTC, datetime, timedelta, timezone

    pass_ = a_pass(terms=simple_terms(max_stay=timedelta(hours=2)))
    plus_three = timezone(timedelta(hours=3))
    entered = at(MONDAY, 11).astimezone(plus_three)  # 20:00+03:00
    assert entered.isoformat().endswith("+03:00")
    exit_utc = at(MONDAY, 13, 30).astimezone(UTC)  # 19:30Z
    ledger = [Visit(pass_id=pass_.id, garage_id=GARAGE.id, vehicle_identity="CAR-1",
                    entry_lane="L1", entered_at=entered)]
    late = ask(pass_, ledger, Direction.EXIT, when=exit_utc)
    assert late.reason == f.OVER_MAX_STAY and "2:30:00 elapsed" in late.detail
    assert "entered 2026-06-01T11:00:00-06:00, exiting 2026-06-01T13:30:00-06:00" in late.detail
    assert "(America/Denver)" in late.detail
    assert "+03:00" not in late.detail and "+00:00" not in late.detail, late.detail
    # the unmeasured naming renders the same way
    later = ask(pass_, ledger, Direction.EXIT,
                when=datetime(2026, 6, 1, 16, 0, tzinfo=UTC))  # 10:00 -06:00
    assert later.unmeasured is not None and "later than this exit" in later.unmeasured
    assert "2026-06-01T11:00:00-06:00" in later.unmeasured and "+03:00" not in later.unmeasured


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
                                           allowed_lanes=lanes_at("garage-downtown", "L9")))
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
    assert "entered 2026-06-01T09:00:00-06:00, exiting 2026-06-01T12:00:00-06:00" in answer.detail
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
        app, tenant_id, "SELECT pg.garage_id, p.id FROM passes p JOIN pass_garages pg "
        "ON pg.pass_id = p.id WHERE p.external_id = 'pass-1'")[0]
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


@pytest.mark.guarantee("G9")
@store_test
def test_the_store_renders_the_recorded_entry_in_the_garages_zone_not_the_sessions(
    app, tenant_id
):
    """The database session's zone is set to one the garage is not in (+03:00,
    the clock the gate found this on) and the detail still shows the recorded
    entry as the garage's wall clock. Fails under the session zone with the
    rendering planted back."""
    pass_ = _store_pass(app, tenant_id, simple_terms(max_stay=timedelta(hours=2)))
    _entry(app, tenant_id, pass_, "CAR-1", 9)
    with app.cursor() as cursor:
        cursor.execute("SET TIME ZONE 'Europe/Istanbul'")
    app.commit()  # session-level, past the per-test rollback
    try:
        with app.cursor() as cursor:
            cursor.execute("SELECT entered_at FROM visits LIMIT 0")  # the session zone applies
            cursor.execute("SHOW TIME ZONE")
            assert cursor.fetchone() == ("Europe/Istanbul",), "the premise: a foreign session zone"
        app.rollback()
        answer = access_from_store(app, tenant_id, GARAGE.id, "CAR-1", "L1", Direction.EXIT,
                                   NOON_MONDAY)
        assert answer.reason == f.OVER_MAX_STAY and "3:00:00 elapsed" in answer.detail
        assert "entered 2026-06-01T09:00:00-06:00, exiting 2026-06-01T12:00:00-06:00" in (
            answer.detail
        ), answer.detail
        assert "+03:00" not in answer.detail
    finally:
        with app.cursor() as cursor:
            cursor.execute("SET TIME ZONE DEFAULT")
        app.commit()
