"""G25 -- A PASS ANSWERS ONLY AT THE GARAGES IT NAMES, and G1's multi-garage
path: one enrolment, one registration row per garage of the pass, all or none.

His decision, 2026-09-14: one account, many garages under it, and a monthly
may be good at more than one of that account's garages. The pass carries a
non-empty SET of garages; registrations stay keyed per garage and the
one-car-one-pass EXCLUDE keeps its exact meaning; lanes are stated per garage;
the terms are one set evaluated at whichever garage the car is at; the
external id is unique per tenant.

**EVERY SITE THAT READS THE SET HAS A CONTROL.** The two comprehensions in
``access.py``, the store's create and load, the two credential comparisons --
a planted removal of the membership test at any one of them reddens a test
here, and the fan-out's two halves are each measured WITH THE OTHER REMOVED:
the EXCLUDE with the module's named refusal monkeypatched away, the named
refusal with the fan-out's atomicity monkeypatched away. A control run with
both in place would prove nothing about either.

**THE VISIT LEDGER IS PER GARAGE, AND A MEMBERSHIP ROW ERASES NOTHING** (the
G3a L3's F2 and F1, the fix round). Measured on the round's first head: the
open-visit lookup was keyed on the pass alone, so an entry at garage B was
refused for a visit open at A and an exit at B closed A's visit with B's lane
on it; and the keys from ``visits`` and ``vehicle_registrations`` into
``pass_garages`` were CASCADE, so deleting one membership row took that
garage's ledger with it. Now the lookup and the index are keyed on the garage,
the two keys are RESTRICT (the lanes key stays CASCADE: a lane is configuration
of the pass at that garage), and the allowance -- C5 -- still counts the set.
Controls: the garage predicate planted out of the lookup; the index planted
back to per pass (the entry at B then meets it as a bare constraint); each key
planted back to CASCADE, with the visits key measured on a garage that holds
ONLY a visit so the registrations key cannot stand in for it. AND THE ENGINE'S
OWN SELECTION (the engine-stay round): a ``Visit`` carries its garage, the store
hands the engine each row's garage, and the stay at an exit is measured from
the entry recorded at that garage -- never from one open at another garage of
the set, which leaves the stay UNMEASURED and named; the garage planted out of
the engine's selection reddens G9 and the tests here.

**AND EACH RECORDED ENTRY IS READ ON THE CLOCK OF THE GARAGE IT WAS RECORDED
AT** (the G3a merge gate's fourth finding, the gate-fix round). The allowance
is one count over the set (C5, unchanged -- planted per garage, red); whether
an entry is "in this window, today" is read in ITS garage's zone, so the
pass's garages reach the engine (``access(garages=...)``): the store hands in
every garage of every pass it selected, the command line hands in
``--garages``. THE FIXTURES NOW HOLD A MIXED-ZONE PASS -- Denver beside Tokyo,
and Denver beside Phoenix on the fall-back day -- because every multi-garage
test before this put its garages in one zone, and that absence is why four
review layers walked past a one-per-window allowance spent twice. An entry at
a garage whose clock is not here is refused by name at an entry: not handed
in, handed in unreadable, handed in twice -- never read on this garage's clock,
never dropped, never raised; an exit never reaches it (no exit counts an
allowance). And a REVOCATION ends each garage's registrations on THAT
garage's day of the instant (the gate's same-class finding): the day a car is
free again at a garage is that garage's, not the day at whichever garage the
operator typed the command from.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pytest

from fixtures import (
    FALL_BACK_2026,
    FAR_ZONE,
    FIXED_ZONE,
    HOLDER,
    NOON_MONDAY,
    SHIFTING_ZONE,
    a_pass,
    at,
    far_garage,
    fixed_garage,
    lanes_at,
    registered,
    simple_terms,
)
from garage_pass import findings as f
from garage_pass.access import Outcome, access
from garage_pass.garage import Garage
from garage_pass.passes import Pass, State
from garage_pass.terms import Direction, GarageLanes, Terms

A = Garage(id="garage-a", timezone=SHIFTING_ZONE, transient_available=True, enrols_at="entry")
B = Garage(id="garage-b", timezone=SHIFTING_ZONE, transient_available=True, enrols_at="entry")
C = Garage(id="garage-c", timezone=SHIFTING_ZONE, transient_available=True, enrols_at="entry")
ELSEWHERE = Garage(id="garage-elsewhere", timezone=SHIFTING_ZONE, transient_available=True,
                   enrols_at="entry")
THREE = (A, B, C)
#: The mixed-zone pass's other garages: Tokyo (another calendar day for most
#: of Denver's working day), and Phoenix (Denver's winter clock all year, for
#: the fall-back edge). G14 proves each has the property it is here for.
FAR = far_garage()
FIXED = fixed_garage()


def spanning(*garages: Garage, id: str = "pass-span", **overrides) -> Pass:
    return a_pass(id=id, garage_ids={g.id for g in garages}, **overrides)


# ---------------------------------------------------------------------------
# The engine: the set is stated, and the answer reads it.
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G25")
@pytest.mark.parametrize("value, code", [
    (frozenset(), f.REFUSAL_PASS_NAMES_NO_GARAGE),
    ([], f.REFUSAL_PASS_NAMES_NO_GARAGE),
    (frozenset({"", "g1"}), f.REFUSAL_FIELD_BLANK),
    (frozenset({" ", "g1"}), f.REFUSAL_FIELD_BLANK),
    ("garage-a", f.REFUSAL_PASS_NAMES_NO_GARAGE),  # a string is not a set of its characters
    (None, f.REFUSAL_PASS_NAMES_NO_GARAGE),
], ids=["empty frozenset", "empty list", "blank member", "space member", "string", "none"])
def test_a_pass_names_at_least_one_garage_and_no_blank_one_refused_naming_the_field(value, code):
    with pytest.raises(f.Refused) as refused:
        Pass(id="p", garage_ids=value, label="x", holder=HOLDER, terms=simple_terms())
    assert refused.value.code == code and refused.value.field == "pass.garage_ids", refused.value


@pytest.mark.guarantee("G25")
def test_a_single_garage_pass_constructs_and_answers_exactly_as_before():
    """The control for the round: nothing about a one-garage pass moved."""
    pass_ = a_pass(garage_ids={A.id})
    assert pass_.garage_ids == frozenset({A.id})
    answer = access(garage=A, passes=[pass_], registrations=[registered(pass_)], visits=[],
                    vehicle_identity="CAR-1", lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY)
    assert answer.outcome is Outcome.COVERED and answer.pass_id == pass_.id


@pytest.mark.guarantee("G25")
@pytest.mark.parametrize("direction", list(Direction), ids=lambda d: d.value)
def test_a_pass_covers_at_every_garage_it_names_and_at_no_other(direction):
    """{A, B}: covered at A and at B; at C the pass is not this garage's
    business -- NO_PASS, the same answer an unknown identity gets -- at both
    ends. The registration is one row in the pure API: a car on a pass."""
    pass_ = spanning(A, B)
    for garage in (A, B):
        answer = access(garage=garage, passes=[pass_], registrations=[registered(pass_)],
                        visits=[], vehicle_identity="CAR-1", lane="L1", direction=direction,
                        at=NOON_MONDAY)
        assert answer.outcome is Outcome.COVERED and answer.pass_id == pass_.id, (garage, answer)
    answer = access(garage=C, passes=[pass_], registrations=[registered(pass_)], visits=[],
                    vehicle_identity="CAR-1", lane="L1", direction=direction, at=NOON_MONDAY)
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.NO_PASS, answer
    assert answer.pass_id is None, "a pass that does not name this garage is not named either"
    assert "garage-c" in answer.detail


@pytest.mark.guarantee("G25")
def test_the_terms_are_one_set_evaluated_at_whichever_garage_the_car_is_at():
    """C5, his rule stated back: a 2-visit allowance is 2 ON THE PASS. One
    recorded entry at A and one at B use it up at C."""
    from fixtures import TWO_HOURS_BEFORE
    from garage_pass.passes import Visit
    from garage_pass.terms import AllowancePeriod, VisitAllowance

    pass_ = spanning(A, B, C, terms=simple_terms(
        visit_allowance=VisitAllowance(count=2, per=AllowancePeriod.LIFE)))
    visits = [Visit(pass_id=pass_.id, garage_id=A.id, vehicle_identity="CAR-1", entry_lane="L1",
                    entered_at=TWO_HOURS_BEFORE),
              Visit(pass_id=pass_.id, garage_id=B.id, vehicle_identity="CAR-1", entry_lane="L1",
                    entered_at=at(date(2026, 5, 31), 9))]
    answer = access(garage=C, passes=[pass_], registrations=[registered(pass_)], visits=visits,
                    vehicle_identity="CAR-1", lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY)
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.OUT_OF_VISITS, answer
    assert "2 of 2 visit(s) used" in answer.detail


@pytest.mark.guarantee("G25")
def test_a_stay_is_measured_at_the_garage_the_car_is_leaving_never_from_another_garages_entry():
    """THE STAY IS PER GARAGE; THE ALLOWANCE IS PER PASS. Measured on the fix
    round's head: with no garage on the visit, an exit at B found the entry
    open at A, measured eleven hours from it and answered OVER_MAX_STAY quoting
    A's instant -- wrong-silently, at the barrier, chargeable. Now: an entry
    open at A is not B's entry. The exit at B is answered on every other term,
    the stay UNMEASURED and NAMED, A's instant nowhere in it (G1's F4 ruling);
    and the control -- the same entry at B itself -- is OVER_MAX_STAY exactly
    as before, quoting that entry in the garage's wall clock."""
    from datetime import timedelta

    from fixtures import TWO_HOURS_BEFORE
    from garage_pass.passes import Visit

    pass_ = spanning(A, B, terms=simple_terms(max_stay=timedelta(hours=1)))
    entered_at_a = at(date(2026, 6, 1), 1)   # eleven hours before noon
    open_at_a = [Visit(pass_id=pass_.id, garage_id=A.id, vehicle_identity="CAR-1",
                       entry_lane="L1", entered_at=entered_at_a)]
    at_b = access(garage=B, passes=[pass_], registrations=[registered(pass_)], visits=open_at_a,
                  vehicle_identity="CAR-1", lane="L1", direction=Direction.EXIT, at=NOON_MONDAY)
    assert at_b.outcome is Outcome.COVERED, at_b
    assert at_b.unmeasured and "max_stay" in at_b.unmeasured and "at this garage" in at_b.unmeasured
    assert "01:00" not in at_b.unmeasured and "01:00" not in (at_b.detail or ""), (
        "A's entry instant was quoted at B")
    assert at_b.exit_note
    # the control: the same entry recorded AT B is B's, and the rule is unchanged
    open_at_b = [Visit(pass_id=pass_.id, garage_id=B.id, vehicle_identity="CAR-1",
                       entry_lane="L1", entered_at=entered_at_a)]
    same = access(garage=B, passes=[pass_], registrations=[registered(pass_)], visits=open_at_b,
                  vehicle_identity="CAR-1", lane="L1", direction=Direction.EXIT, at=NOON_MONDAY)
    assert same.outcome is Outcome.NOT_COVERED and same.reason == f.OVER_MAX_STAY, same
    assert "11:00:00 elapsed" in same.detail and "01:00:00-06:00" in same.detail
    assert same.exit_note
    # and the ALLOWANCE still counts A's entry beside B's (C5): a 2-visit
    # allowance, one entry at each, is spent at B -- the stay fix reaches nothing here
    from garage_pass.terms import AllowancePeriod, VisitAllowance

    counted = spanning(A, B, terms=simple_terms(
        visit_allowance=VisitAllowance(count=2, per=AllowancePeriod.LIFE)))
    both = [Visit(pass_id=counted.id, garage_id=A.id, vehicle_identity="CAR-1", entry_lane="L1",
                  entered_at=TWO_HOURS_BEFORE),
            Visit(pass_id=counted.id, garage_id=B.id, vehicle_identity="CAR-1", entry_lane="L1",
                  entered_at=at(date(2026, 5, 31), 9))]
    spent = access(garage=B, passes=[counted], registrations=[registered(counted)], visits=both,
                   vehicle_identity="CAR-1", lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY)
    assert spent.reason == f.OUT_OF_VISITS and "counted 2 recorded entries" in spent.detail


@pytest.mark.guarantee("G25")
@pytest.mark.parametrize("direction", list(Direction), ids=lambda d: d.value)
def test_a_two_garage_pass_handed_in_twice_is_duplicated_data_answered_the_same_way(direction):
    """H3's control: the duplicate-copy rule, re-measured on a pass that holds
    TWO garages -- the entry refuses naming the id, the exit evaluates every
    copy and is covered if any covers -- and then with the copies DISAGREEING
    on their garage sets, a shape that could not exist before this round:
    duplicated data, answered the same way, never resolved by order."""
    agreeing = [spanning(A, B), spanning(A, B)]
    disagreeing = [spanning(A, B), spanning(A)]
    for copies in (agreeing, disagreeing):
        answers = []
        for ordered in (copies, list(reversed(copies))):
            answers.append(access(
                garage=A, passes=ordered, registrations=[registered(copies[0])], visits=[],
                vehicle_identity="CAR-1", lane="L1", direction=direction, at=NOON_MONDAY))
        first, second = answers
        assert first == second, "the answer depended on the order the copies arrived in"
        if direction is Direction.ENTRY:
            assert first.outcome is Outcome.REFUSED_TO_ANSWER
            assert first.missing == f.DUPLICATED_PASS_ID and "'pass-span'" in first.detail
        else:
            assert first.outcome is Outcome.COVERED and "handed in 2 times" in first.detail


@pytest.mark.guarantee("G25")
def test_a_pass_handed_in_twice_that_names_another_garage_is_not_this_garages_business():
    """The duplicated comprehension reads membership too: two copies of a pass
    that names only B, handed in at A, are neither duplicated here nor
    selected here -- NO_PASS, not a refusal about an id A never reads."""
    copies = [spanning(B), spanning(B)]
    answer = access(garage=A, passes=copies, registrations=[registered(copies[0])], visits=[],
                    vehicle_identity="CAR-1", lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY)
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.NO_PASS, answer


# ---------------------------------------------------------------------------
# Each recorded entry is read on the clock of the garage it was recorded at.
# ---------------------------------------------------------------------------

from datetime import timedelta  # noqa: E402

from garage_pass.passes import Visit  # noqa: E402
from garage_pass.terms import AllowancePeriod, VisitAllowance, Window  # noqa: E402

EVERY_DAY = frozenset(range(1, 8))


def per_window(count: int, window: Window, *garages: Garage, id: str = "pass-span") -> Pass:
    return spanning(*garages, id=id, terms=simple_terms(
        windows=(window,), visit_allowance=VisitAllowance(count, AllowancePeriod.WINDOW)))


def entry_at(garage: Garage, pass_: Pass, visits, when, handed_in=(), identity="CAR-1"):
    return access(garage=garage, garages=list(handed_in), passes=[pass_],
                  registrations=[registered(pass_, identity)], visits=visits,
                  vehicle_identity=identity, lane="L1", direction=Direction.ENTRY, at=when)


def recorded(pass_: Pass, garage: Garage, entered_at, identity="CAR-1", open_=False) -> Visit:
    return Visit(pass_id=pass_.id, garage_id=garage.id, vehicle_identity=identity,
                 entry_lane="L1", entered_at=entered_at,
                 exited_at=None if open_ else entered_at + timedelta(minutes=30),
                 exit_lane=None if open_ else "L1")


@pytest.mark.guarantee("G25")
def test_a_per_window_allowance_reads_each_entry_in_the_local_day_of_its_own_garage():
    """The gate's case, on the fixture's mixed-zone pass, read BOTH ways. A
    visit at Tokyo at 09:00 Monday Tokyo time is in Monday's window there; at
    Denver that instant is 18:00 Sunday. Asked at Denver on Monday morning:
    counted, spent. The mirror: a visit at Denver at 18:00 SUNDAY Denver time
    -- 09:00 Monday in Tokyo -- asked about at Tokyo on Monday afternoon: NOT
    counted, covered, because at the door it drove through it was Sunday
    evening, outside Mon-Fri 08:00-18:00. Same rule, each direction; and the
    sentence names the clock each entry was read on."""
    window = Window(days=frozenset({1, 2, 3, 4, 5}), start_minute=8 * 60, end_minute=18 * 60)
    pass_ = per_window(1, window, A, FAR)
    monday = date(2026, 6, 1)
    tokyo_visit = recorded(pass_, FAR, at(monday, 9, timezone=FAR_ZONE))
    at_denver = entry_at(A, pass_, [tokyo_visit], at(monday, 9), handed_in=[FAR])
    assert at_denver.reason == f.OUT_OF_VISITS, at_denver
    assert "1 of 1 visit(s) used" in at_denver.detail
    assert "each read in the local day of the garage it was recorded at (garage-far: 1)" in (
        at_denver.detail)
    # the mirror: a Sunday-evening Denver visit is Monday morning in Tokyo, and
    # is NOT in Monday's window because it was Sunday where it was recorded
    sunday_evening = at(date(2026, 5, 31), 18)
    assert sunday_evening == at(monday, 9, timezone=FAR_ZONE), "one instant, two days"
    denver_visit = recorded(pass_, A, sunday_evening)
    at_tokyo = entry_at(FAR, pass_, [denver_visit], at(monday, 17, timezone=FAR_ZONE),
                        handed_in=[A])
    assert at_tokyo.outcome is Outcome.COVERED, at_tokyo
    assert "visit 1 of 1; counted 0 recorded entries" in at_tokyo.covering_term
    assert "recorded at (none)" in at_tokyo.covering_term
    # the same-zone control: A and B share a clock, and the reading is the
    # single-clock reading exactly -- a Monday-morning B visit counts at A
    twin = per_window(1, window, A, B)
    b_visit = recorded(twin, B, at(monday, 9))
    at_a = entry_at(A, twin, [b_visit], at(monday, 10), handed_in=[B])
    assert at_a.reason == f.OUT_OF_VISITS and "(garage-b: 1)" in at_a.detail, at_a


@pytest.mark.guarantee("G25")
def test_the_allowance_is_still_one_count_over_the_set_on_a_mixed_zone_pass():
    """C5, THE CONTROL ON THE FIX'S REACH: a 20-visit-per-window allowance
    on Denver + Tokyo, 12 entries at Denver and 8 at Tokyo each inside
    Monday's window on its own clock, is 20 of 20 at both garages and the
    21st is refused at either. A per-garage count would read 12 of 20 at
    Denver and 8 at Tokyo; the plant that makes it one reddens this."""
    window = Window(days=EVERY_DAY, start_minute=0, end_minute=24 * 60)
    pass_ = per_window(20, window, A, FAR)
    monday = date(2026, 6, 1)
    ledger = [recorded(pass_, A, at(monday, 1, 5 * i), identity=f"CAR-{i}") for i in range(12)]
    ledger += [recorded(pass_, FAR, at(monday, 9, 5 * i, timezone=FAR_ZONE),
                        identity=f"CAR-{i}") for i in range(8)]
    for garage, when in ((A, at(monday, 12)), (FAR, at(monday, 12, timezone=FAR_ZONE))):
        answer = entry_at(garage, pass_, ledger, when, handed_in=[A, FAR])
        assert answer.reason == f.OUT_OF_VISITS, (garage.id, answer)
        assert "20 of 20 visit(s) used; counted 20 recorded entries" in answer.detail
        assert "(garage-a: 12, garage-far: 8)" in answer.detail, answer.detail
    nineteen = ledger[:19]
    assert entry_at(A, pass_, nineteen, at(monday, 12), handed_in=[A, FAR]).outcome is (
        Outcome.COVERED)


@pytest.mark.guarantee("G25")
def test_the_dst_edge_two_denver_entries_that_read_as_one_wall_clock_are_two_on_denvers_day():
    """THE DST EDGE, at one garage and not the other. On 2026-11-01 Denver's
    day is 25 hours long: 01:30 happens twice (MDT, then MST). Phoenix does
    not shift. Two entries recorded at Denver, one in each 01:30 -- 07:30 and
    08:30 UTC -- both fall in a 01:00-03:00 window ON DENVER'S CLOCK. Read on
    Phoenix's clock they are 00:30 and 01:30: only one in the window. So an
    entry at Phoenix at 02:30 on a 2-per-window allowance is OUT_OF_VISITS --
    both Denver entries counted, on Denver's day -- where the asking clock
    would have admitted it as visit 2 of 2. The control: the same two instants
    recorded at Phoenix itself ARE 00:30 and 01:30 there, one counted, covered."""
    window = Window(days=EVERY_DAY, start_minute=1 * 60, end_minute=3 * 60)
    pass_ = per_window(2, window, A, FIXED)
    first_0130 = at(FALL_BACK_2026, 1, 30, fold=0)   # 01:30 MDT = 07:30 UTC
    second_0130 = at(FALL_BACK_2026, 1, 30, fold=1)  # 01:30 MST = 08:30 UTC
    assert (second_0130 - first_0130).total_seconds() == 0, "same wall clock, by PEP 495"
    from garage_pass.localday import elapsed
    assert elapsed(first_0130, second_0130) == timedelta(hours=1), "one hour apart in fact"
    at_denver = [recorded(pass_, A, first_0130, identity="CAR-2"),
                 recorded(pass_, A, second_0130, identity="CAR-3")]
    asked_at = at(FALL_BACK_2026, 2, 30, timezone=FIXED_ZONE)  # 09:30 UTC, after both
    spent = entry_at(FIXED, pass_, at_denver, asked_at, handed_in=[A])
    assert spent.reason == f.OUT_OF_VISITS, spent
    assert "2 of 2 visit(s) used; counted 2 recorded entries" in spent.detail
    assert "on 2026-11-01, each read in the local day of the garage it was recorded at " in (
        spent.detail) and "(garage-a: 2)" in spent.detail
    # the control: the same two instants recorded at Phoenix are 00:30 and 01:30 there
    at_phoenix = [recorded(pass_, FIXED, first_0130, identity="CAR-2"),
                  recorded(pass_, FIXED, second_0130, identity="CAR-3")]
    admitted = entry_at(FIXED, pass_, at_phoenix, asked_at, handed_in=[A])
    assert admitted.outcome is Outcome.COVERED, admitted
    assert "visit 2 of 2; counted 1 recorded entry" in admitted.covering_term
    assert "(garage-fixed: 1)" in admitted.covering_term
    # and asked at Denver in its own doubled hour, both count there too
    at_home = entry_at(A, pass_, at_denver, at(FALL_BACK_2026, 2, 45, fold=1), handed_in=[FIXED])
    assert at_home.reason == f.OUT_OF_VISITS, at_home


@pytest.mark.guarantee("G25")
def test_an_entry_at_a_garage_whose_clock_is_not_here_is_refused_by_name_never_read_on_this_one():
    """The three ways the clock can be missing, each refused at an ENTRY
    naming the garage, and each bearing on the answer ONLY when an entry
    recorded there must be read: not handed in; handed in unreadable (the
    asking garage's own path, one garage over); handed in twice under one id
    (never resolved by order -- the two orders give one answer). Where no
    entry was recorded there, a missing or doubled garage bears on nothing.
    An exit reaches none of them: no exit counts an allowance."""
    from garage_pass.findings import Unreadable
    from garage_pass.garage import garage_from_stored

    window = Window(days=frozenset({1, 2, 3, 4, 5}), start_minute=8 * 60, end_minute=18 * 60)
    pass_ = per_window(1, window, A, FAR)
    monday = date(2026, 6, 1)
    tokyo_visit = recorded(pass_, FAR, at(monday, 9, timezone=FAR_ZONE))
    when = at(monday, 9)
    # 1. not handed in
    answer = entry_at(A, pass_, [tokyo_visit], when)
    assert answer.outcome is Outcome.REFUSED_TO_ANSWER, answer
    assert answer.missing == f.MISSING_GARAGE_HANDED_IN and answer.pass_id == pass_.id
    assert "garage 'garage-far' was not handed in (handed in: none; asking: 'garage-a')" in (
        answer.detail)
    assert "at 2026-06-01T00:00:00Z (UTC; unrendered on that garage's wall clock, which is " \
        "not here) must be read on that garage's clock" in answer.detail, answer.detail
    assert "+09:00" not in answer.detail, "the entry it could not read, named -- as UTC, said so"
    # 2. handed in unreadable: the same refusal the asking garage gets, naming the far one
    stale = garage_from_stored(FAR.id, "Mars/Olympus", True, "entry")
    assert isinstance(stale.unreadable, Unreadable)
    answer = entry_at(A, pass_, [tokyo_visit], when, handed_in=[stale])
    assert answer.outcome is Outcome.REFUSED_TO_ANSWER and answer.missing == f.MISSING_TIMEZONE
    assert "garage 'garage-far': REFUSAL_TIMEZONE_UNKNOWN [garage.timezone]" in answer.detail
    # 3. handed in twice, whether or not the copies agree, in either order
    twice = [FAR, Garage(id=FAR.id, timezone=SHIFTING_ZONE, transient_available=True)]
    answers = {entry_at(A, pass_, [tokyo_visit], when, handed_in=order)
               for order in (twice, list(reversed(twice)), [FAR, FAR])}
    assert len(answers) == 1, "the answer depended on the order the copies arrived in"
    (answer,) = answers
    assert answer.outcome is Outcome.REFUSED_TO_ANSWER and answer.missing == f.DUPLICATED_GARAGE_ID
    assert "garage 'garage-far' was handed in 2 times" in answer.detail
    # bears on nothing without an entry recorded there: the same three, no Tokyo visit
    denver_visit = recorded(pass_, A, at(monday, 8, 30))
    for handed_in in ([], [stale], twice):
        answer = entry_at(A, pass_, [denver_visit], when, handed_in=handed_in)
        assert answer.reason == f.OUT_OF_VISITS, (handed_in, answer)
    # the asking garage is the `garage` parameter whatever `garages` carries under its id
    answer = entry_at(A, pass_, [denver_visit], when, handed_in=[Garage(
        id=A.id, timezone=FAR_ZONE, transient_available=True)])
    assert answer.reason == f.OUT_OF_VISITS and "(garage-a: 1)" in answer.detail, answer
    # an exit never reaches any of it
    for handed_in in ([], [stale], twice):
        exit_ = access(garage=A, garages=handed_in, passes=[pass_],
                       registrations=[registered(pass_)], visits=[tokyo_visit],
                       vehicle_identity="CAR-1", lane="L1", direction=Direction.EXIT, at=when)
        assert exit_.outcome is Outcome.COVERED and exit_.exit_note, (handed_in, exit_)


@pytest.mark.guarantee("G25")
def test_the_instant_a_clock_not_here_refusal_names_is_the_same_bytes_in_any_arriving_offset():
    """The refusal quotes the entry it could not read. It holds NO clock for
    that garage -- that is why it refuses -- so it cannot render the entry
    on that garage's wall clock, and it must not render it on whatever
    clock the value happened to arrive with: through the store that is the
    DATABASE SESSION's zone, and under a Denver session the Tokyo entry
    read ``2026-05-31T18:00:00-06:00`` -- the asking clock's day, inside a
    sentence whose point is that the entry is not read on the asking
    clock. So: one instant, handed in with three different tzinfos (the
    in-memory shape of three session zones), each of the three refusals
    -- not handed in, handed in unreadable, handed in twice -- is the SAME
    BYTES, the instant as UTC and said to be unrendered on that garage's
    clock. A single reading cannot see this class at all; the comparison
    is the test."""
    from garage_pass.findings import Unreadable
    from garage_pass.garage import garage_from_stored

    window = Window(days=frozenset({1, 2, 3, 4, 5}), start_minute=8 * 60, end_minute=18 * 60)
    pass_ = per_window(1, window, A, FAR)
    monday = date(2026, 6, 1)
    tokyo_9 = at(monday, 9, timezone=FAR_ZONE)
    stale = garage_from_stored(FAR.id, "Mars/Olympus", True, "entry")
    assert isinstance(stale.unreadable, Unreadable)
    paths = {
        f.MISSING_GARAGE_HANDED_IN: [],
        f.MISSING_TIMEZONE: [stale],
        f.DUPLICATED_GARAGE_ID: [FAR, FAR],
    }
    for missing, handed_in in paths.items():
        answers = {}
        for zone_name in (FAR_ZONE, "UTC", SHIFTING_ZONE):
            arrived = tokyo_9.astimezone(ZoneInfo(zone_name))
            assert arrived == tokyo_9, "the premise: one instant"
            visit = recorded(pass_, FAR, arrived)
            answer = entry_at(A, pass_, [visit], at(monday, 9), handed_in=handed_in)
            assert answer.outcome is Outcome.REFUSED_TO_ANSWER and answer.missing == missing
            answers[zone_name] = (answer.missing, answer.pass_id, answer.detail)
        assert len(set(answers.values())) == 1, (missing, answers)
        (detail,) = {detail for _, _, detail in answers.values()}
        assert "at 2026-06-01T00:00:00Z (UTC; unrendered on that garage's wall clock, which " \
            "is not here) must be read on that garage's clock" in detail, detail
        for offset in ("+09:00", "+00:00", "-06:00", "2026-05-31"):
            assert offset not in detail, (offset, detail)
        assert "garage 'garage-far'" in detail


# ---------------------------------------------------------------------------
# Lanes are stated PER GARAGE.
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G25")
def test_lanes_stated_at_one_garage_of_two_is_refused_at_creation_naming_the_garage():
    with pytest.raises(f.Refused) as refused:
        spanning(A, B, terms=simple_terms(allowed_lanes=lanes_at(A.id, "L1")))
    assert refused.value.code == f.REFUSAL_LANES_NOT_STATED_FOR_GARAGE
    assert refused.value.field == "allowed_lanes" and "'garage-b'" in refused.value.detail


@pytest.mark.guarantee("G25")
def test_lanes_stated_at_a_garage_the_pass_does_not_name_is_refused_naming_the_garage():
    with pytest.raises(f.Refused) as refused:
        spanning(A, terms=simple_terms(allowed_lanes=lanes_at(A.id, "L1") + lanes_at(B.id, "L1")))
    assert refused.value.code == f.REFUSAL_LANES_AT_A_GARAGE_THE_PASS_DOES_NOT_NAME
    assert "'garage-b'" in refused.value.detail


@pytest.mark.guarantee("G25")
@pytest.mark.guarantee("G2")
@pytest.mark.parametrize("lanes, code, field", [
    ((), f.REFUSAL_LANES_STATED_BUT_EMPTY, "allowed_lanes"),
    ((GarageLanes("garage-a", frozenset()),), f.REFUSAL_LANES_STATED_BUT_EMPTY,
     "allowed_lanes[0].lanes"),
    ((GarageLanes("garage-a", frozenset({"L1", " "})),), f.REFUSAL_LANE_NAME_BLANK,
     "allowed_lanes[0].lanes"),
    ((GarageLanes(" ", frozenset({"L1"})),), f.REFUSAL_FIELD_BLANK, "allowed_lanes[0].garage_id"),
    ((GarageLanes("garage-a", frozenset({"L1"})), GarageLanes("garage-a", frozenset({"L2"}))),
     f.REFUSAL_LANES_GARAGE_REPEATED, "allowed_lanes[1].garage_id"),
], ids=["empty", "empty at a garage", "blank lane", "blank garage", "garage twice"])
def test_a_contradiction_in_the_per_garage_lane_set_is_refused_at_creation(lanes, code, field):
    with pytest.raises(f.Refused) as refused:
        Terms(directions=frozenset(Direction), allowed_lanes=lanes)
    assert (refused.value.code, refused.value.field) == (code, field), refused.value


@pytest.mark.guarantee("G25")
@pytest.mark.parametrize("direction", list(Direction), ids=lambda d: d.value)
def test_the_lane_check_at_each_garage_reads_its_own_set(direction):
    """A lane valid at A, presented at B, is outside the pass's terms AT B --
    WRONG_LANE naming B's set, not A's -- while the same lane at A covers."""
    pass_ = spanning(A, B, terms=simple_terms(
        allowed_lanes=lanes_at(A.id, "L1", "L2") + lanes_at(B.id, "L3")))
    at_a = access(garage=A, passes=[pass_], registrations=[registered(pass_)], visits=[],
                  vehicle_identity="CAR-1", lane="L1", direction=direction, at=NOON_MONDAY)
    assert at_a.outcome is Outcome.COVERED, at_a
    at_b = access(garage=B, passes=[pass_], registrations=[registered(pass_)], visits=[],
                  vehicle_identity="CAR-1", lane="L1", direction=direction, at=NOON_MONDAY)
    assert at_b.outcome is Outcome.NOT_COVERED and at_b.reason == f.WRONG_LANE, at_b
    assert "['L3']" in at_b.detail and "'garage-b'" in at_b.detail and "L2" not in at_b.detail
    assert pass_.terms.lanes_at(B.id) == frozenset({"L3"})
    assert pass_.terms.lanes_at(C.id) == frozenset(), "stated, and none here: no lane at all"
    assert simple_terms().lanes_at(C.id) is None, "not stated: every lane, everywhere"


@pytest.mark.guarantee("G25")
def test_a_pass_document_carries_its_garages_and_its_lanes_per_garage():
    """The document door: ``garage_ids`` is a list, ``allowed_lanes`` a list of
    {garage_id, lanes} objects, both derived from the dataclasses; a string
    where the list belongs is refused naming the field, never read as a set of
    its characters (W3)."""
    from fixtures import pass_document
    from garage_pass.documents import load_pass

    document = pass_document(
        garage_ids=["garage-a", "garage-b"],
        terms={**pass_document()["terms"],
               "allowed_lanes": [{"garage_id": "garage-a", "lanes": ["L1"]},
                                 {"garage_id": "garage-b", "lanes": ["L2", "L3"]}]},
    )
    loaded = load_pass(document)
    assert loaded.garage_ids == frozenset({"garage-a", "garage-b"})
    assert loaded.terms.lanes_at("garage-b") == frozenset({"L2", "L3"})
    with pytest.raises(f.Refused) as refused:
        load_pass(pass_document(garage_ids="garage-a"))
    assert refused.value.code == f.REFUSAL_FIELD_WRONG_TYPE
    assert refused.value.field == "pass.garage_ids"
    with pytest.raises(f.Refused) as refused:
        load_pass(pass_document(garage_ids=["garage-a"], terms={
            **pass_document()["terms"], "allowed_lanes": ["L1"]}))
    assert refused.value.field == "pass.terms.allowed_lanes[0]", refused.value


# ---------------------------------------------------------------------------
# The store: create, load, enrol, redeem -- the set through every door.
# ---------------------------------------------------------------------------

from enrolment_harness import issue, issue_link, redeem, redeem_link  # noqa: E402
from garage_pass.store.access import access_from_store  # noqa: E402
from garage_pass.store.postgres import tenant  # noqa: E402
from garage_pass.store.records import (  # noqa: E402
    ONE_PASS_PER_GARAGE,
    create_pass,
    end_registration,
    load_pass,
    register_vehicle,
    store_garage,
)
from store_harness import CREATED_AT, query, store_test  # noqa: E402


def seed_garages(app, tenant_id, *garages: Garage) -> dict[str, object]:
    uuids = {}
    with tenant(app, tenant_id) as cursor:
        for garage in garages:
            uuids[garage.id] = store_garage(cursor, tenant_id, garage)
    app.commit()
    return uuids


def create(app, tenant_id, garage: Garage, pass_: Pass) -> None:
    with tenant(app, tenant_id) as cursor:
        create_pass(cursor, tenant_id, garage.id, pass_, by="owner", at=CREATED_AT)
    app.commit()


def registration_rows(app, tenant_id) -> list[tuple]:
    """(pass, garage, identity, effective, end) -- every row, by garage."""
    return query(
        app, tenant_id,
        "SELECT p.external_id, g.external_id, r.vehicle_identity, r.effective_day, r.end_day "
        "FROM vehicle_registrations r JOIN passes p ON p.id = r.pass_id "
        "JOIN garages g ON g.id = r.garage_id ORDER BY 1, 2, 4",
    )


def pass_garage_rows(app, tenant_id) -> list[tuple]:
    return query(
        app, tenant_id,
        "SELECT p.external_id, g.external_id FROM pass_garages pg "
        "JOIN passes p ON p.id = pg.pass_id JOIN garages g ON g.id = pg.garage_id ORDER BY 1, 2",
    )


@pytest.mark.guarantee("G25")
@store_test
def test_a_pass_stored_at_a_naming_a_and_b_loads_at_both_and_not_at_c(app, tenant_id):
    """H4's control. Same terms, same set, at either garage; at C, refused by
    name -- the refusal every caller already has -- naming the set."""
    uuids = seed_garages(app, tenant_id, A, B, C)
    pass_ = spanning(A, B, terms=simple_terms(
        allowed_lanes=lanes_at(A.id, "L1") + lanes_at(B.id, "L2", "L3")))
    create(app, tenant_id, A, pass_)
    assert pass_garage_rows(app, tenant_id) == [("pass-span", "garage-a"),
                                                ("pass-span", "garage-b")]
    loaded = {}
    with tenant(app, tenant_id) as cursor:
        for garage in (A, B):
            _uuid, loaded[garage.id] = load_pass(cursor, tenant_id, uuids[garage.id], pass_.id)
        with pytest.raises(f.Refused) as refused:
            load_pass(cursor, tenant_id, uuids[C.id], pass_.id)
    app.rollback()
    assert loaded[A.id] == loaded[B.id] == pass_
    assert loaded[A.id].terms.lanes_at(B.id) == frozenset({"L2", "L3"})
    assert refused.value.code == f.REFUSAL_PASS_NOT_FOUND
    assert "'garage-c'" in refused.value.detail and "garage-a" in refused.value.detail


@pytest.mark.guarantee("G25")
@store_test
def test_a_pass_naming_a_asked_to_be_stored_at_b_is_refused_as_today(app, tenant_id):
    seed_garages(app, tenant_id, A, B)
    with pytest.raises(f.Refused) as refused:
        create(app, tenant_id, B, spanning(A))
    app.rollback()
    assert refused.value.code == f.REFUSAL_GARAGE_MISMATCH
    assert "'garage-b'" in refused.value.detail and "['garage-a']" in refused.value.detail
    assert pass_garage_rows(app, tenant_id) == [], "a refusal writes nothing"


@pytest.mark.guarantee("G25")
@store_test
def test_a_pass_naming_a_garage_the_tenant_does_not_have_is_refused_and_nothing_is_written(
    app, tenant_id
):
    seed_garages(app, tenant_id, A)
    with pytest.raises(f.Refused) as refused:
        create(app, tenant_id, A, spanning(A, ELSEWHERE))
    app.rollback()
    assert refused.value.code == f.REFUSAL_GARAGE_NOT_FOUND
    assert "'garage-elsewhere'" in refused.value.detail
    assert query(app, tenant_id, "SELECT count(*) FROM passes") == [(0,)]


@pytest.mark.guarantee("G25")
@store_test
def test_a_passs_external_id_is_unique_per_tenant_not_per_garage(app, tenant_id):
    """C4: EMP-1 at A and EMP-1 at B is one id twice, refused by name; the
    UNIQUE (tenant_id, external_id) is the backstop for a raw write."""
    import psycopg

    seed_garages(app, tenant_id, A, B)
    create(app, tenant_id, A, spanning(A, id="EMP-1"))
    with pytest.raises(f.Refused) as refused:
        create(app, tenant_id, B, spanning(B, id="EMP-1"))
    app.rollback()
    assert refused.value.code == f.REFUSAL_PASS_ALREADY_EXISTS
    with pytest.raises(psycopg.errors.UniqueViolation) as violation:
        with tenant(app, tenant_id) as cursor:
            cursor.execute(
                "INSERT INTO passes (tenant_id, external_id, label, holder_email, entry_allowed, "
                "exit_allowed, lanes_stated, state) VALUES (%s, 'EMP-1', 'l', 'h@example.com', "
                "true, true, false, 'draft')", (tenant_id,),
            )
    app.rollback()
    assert violation.value.diag.constraint_name == "passes_tenant_id_external_id_key"


@pytest.mark.guarantee("G25")
@pytest.mark.guarantee("G1")
@store_test
def test_one_redemption_on_a_three_garage_pass_writes_exactly_three_rows_and_covers_at_all(
    app, tenant_id
):
    """H5 control (a): exactly three registration rows, one per garage, and
    the car is covered at all three on the next access call."""
    seed_garages(app, tenant_id, *THREE)
    pass_ = spanning(*THREE)
    create(app, tenant_id, A, pass_)
    token = issue(app, tenant_id, A, pass_)["token"]
    out = redeem(app, tenant_id, A, token)
    assert out.redeemed and out.refusal is None, out.refusal
    assert out.registration["garages"] == ["garage-a", "garage-b", "garage-c"]
    day = date(2026, 6, 1)
    assert registration_rows(app, tenant_id) == [
        ("pass-span", "garage-a", "CAR-1", day, None),
        ("pass-span", "garage-b", "CAR-1", day, None),
        ("pass-span", "garage-c", "CAR-1", day, None),
    ]
    for garage in THREE:
        for direction in Direction:
            answer = access_from_store(app, tenant_id, garage.id, "CAR-1", "L1", direction,
                                       at(day, 13))
            assert answer.outcome is Outcome.COVERED, (garage, answer)
            assert answer.pass_id == pass_.id
    elsewhere = access_from_store(app, tenant_id, A.id, "CAR-1", "L1", Direction.ENTRY, at(day, 13))
    assert elsewhere.outcome is Outcome.COVERED
    # and revocation ends every one of them, at every garage, in one write
    from garage_pass.store.records import change_state

    with tenant(app, tenant_id) as cursor:
        out = change_state(cursor, tenant_id, B.id, pass_.id, State.REVOKED, by="owner",
                           at=at(day, 14), reason="left")
    app.commit()
    assert out["registrations_ended"] == 3
    assert {r[4] for r in registration_rows(app, tenant_id)} == {day}


@pytest.mark.guarantee("G25")
@pytest.mark.guarantee("G1")
@store_test
def test_a_collision_at_the_second_garage_refuses_the_whole_redemption_and_writes_nothing(
    app, tenant_id
):
    """H5 control (b): the car is already on another pass at B, the SECOND
    garage of {A, B, C}. The whole redemption is refused by name, naming B and
    the survivor, and ZERO rows are written anywhere -- the end state is
    asserted, not the exception."""
    seed_garages(app, tenant_id, *THREE)
    holder = spanning(B, id="pass-holder", state=State.ACTIVE)
    create(app, tenant_id, B, holder)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, B.id, holder.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    pass_ = spanning(*THREE, state=State.DRAFT)
    create(app, tenant_id, A, pass_)
    token = issue(app, tenant_id, A, pass_)["token"]
    before = registration_rows(app, tenant_id)
    out = redeem(app, tenant_id, A, token)
    assert not out.redeemed and out.refusal.code == f.REFUSAL_VEHICLE_ON_ANOTHER_PASS, out.refusal
    assert "'garage-b'" in out.refusal.detail and "'pass-holder'" in out.refusal.detail
    assert registration_rows(app, tenant_id) == before == [
        ("pass-holder", "garage-b", "CAR-1", date(2026, 1, 1), None)
    ], "zero rows written anywhere: partial enrolment is not an outcome"
    assert query(app, tenant_id, "SELECT state FROM enrolments") == [("issued",)]
    assert query(app, tenant_id, "SELECT state FROM passes WHERE external_id = 'pass-span'") == [
        ("draft",)
    ]
    # the same through register-vehicle directly, from the owner's side, at C
    with pytest.raises(f.Refused) as refused:
        with tenant(app, tenant_id) as cursor:
            register_vehicle(cursor, tenant_id, C.id, pass_.id, "CAR-1", date(2026, 6, 1))
    app.rollback()
    assert refused.value.code == f.REFUSAL_VEHICLE_ON_ANOTHER_PASS
    assert "'garage-b'" in refused.value.detail
    assert registration_rows(app, tenant_id) == before


@pytest.mark.guarantee("G25")
@pytest.mark.guarantee("G1")
@store_test
def test_the_exclude_holds_the_fan_out_with_the_named_refusal_removed(app, tenant_id, monkeypatch):
    """H5 control (d), first half: THE BACKSTOP, MEASURED ALONE. The module's
    collision check is monkeypatched to see no holder, so the fan-out reaches
    the database: A's row is written, B's meets the EXCLUDE, and the savepoint
    takes A's row back with it -- REFUSAL_CONSTRAINT by the constraint's name,
    and the rows after equal the rows before. A control run with the named
    refusal in place would prove nothing about the EXCLUDE."""
    from garage_pass.store import records

    seed_garages(app, tenant_id, *THREE)
    holder = spanning(B, id="pass-holder", state=State.ACTIVE)
    create(app, tenant_id, B, holder)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, B.id, holder.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    pass_ = spanning(*THREE)
    create(app, tenant_id, A, pass_)
    token = issue(app, tenant_id, A, pass_)["token"]
    before = registration_rows(app, tenant_id)
    monkeypatch.setattr(records, "_holders", lambda *args: [])
    out = redeem(app, tenant_id, A, token)
    assert not out.redeemed and out.refusal.code == f.REFUSAL_CONSTRAINT, out.refusal
    assert ONE_PASS_PER_GARAGE in out.refusal.detail and "'garage-b'" in out.refusal.detail
    assert registration_rows(app, tenant_id) == before, "never a partial fan-out"
    assert query(app, tenant_id, "SELECT state FROM enrolments") == [("issued",)]


@pytest.mark.guarantee("G25")
@pytest.mark.guarantee("G1")
@store_test
def test_the_named_refusal_holds_with_the_fan_outs_atomicity_removed(app, tenant_id):
    """H5 control (d), second half: THE PRIMARY, MEASURED ALONE. The savepoint
    a redemption sits under is turned into a no-op through the cursor, so
    nothing would take a partial fan-out back -- and the named refusal fires
    BEFORE the first INSERT, so there is nothing to take back: zero
    registration INSERTs were issued, and zero rows stand after the commit."""
    from garage_pass.store.enrolments import redeem_enrolment

    seed_garages(app, tenant_id, *THREE)
    holder = spanning(B, id="pass-holder", state=State.ACTIVE)
    create(app, tenant_id, B, holder)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, B.id, holder.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    pass_ = spanning(*THREE)
    create(app, tenant_id, A, pass_)
    token = issue(app, tenant_id, A, pass_)["token"]
    before = registration_rows(app, tenant_id)
    statements: list[str] = []

    class NoSavepoint:
        """The real cursor, with every SAVEPOINT verb dropped on the floor."""

        def __init__(self, real):
            self._real = real

        def execute(self, statement, parameters=None):
            statements.append(statement)
            if statement.lstrip().upper().startswith(("SAVEPOINT", "ROLLBACK TO", "RELEASE")):
                return None
            return self._real.execute(statement, parameters)

        def __getattr__(self, name):
            return getattr(self._real, name)

    with tenant(app, tenant_id) as cursor:
        out = redeem_enrolment(NoSavepoint(cursor), tenant_id, A.id, token, "CAR-1", "L1",
                               Direction.ENTRY, NOON_MONDAY)
    app.commit()
    assert not out.redeemed and out.refusal.code == f.REFUSAL_VEHICLE_ON_ANOTHER_PASS, out.refusal
    assert [s for s in statements if "INSERT INTO vehicle_registrations" in s] == [], (
        "the named refusal fires before the first row of the fan-out is written"
    )
    assert registration_rows(app, tenant_id) == before


@pytest.mark.guarantee("G25")
@pytest.mark.guarantee("G19")
@store_test
def test_two_lanes_one_token_on_a_three_garage_pass_exactly_one_redeems_three_rows_or_none(
    app, owner, tenant_id
):
    """H5 control (c): the G2 race, unchanged, on a three-garage pass. The
    winner writes three rows; the loser is refused ALREADY_USED by name and
    writes none -- never a partial fan-out. Deterministic interleaving: B
    blocks on A's lock, observed, never assumed."""
    from enrolment_harness import enrolment_row, race
    from garage_pass.store.enrolments import redeem_enrolment

    seed_garages(app, tenant_id, *THREE)
    pass_ = spanning(*THREE)
    create(app, tenant_id, A, pass_)
    token = issue(app, tenant_id, A, pass_)["token"]

    def lane(identity, lane_name):
        def run(cursor):
            return redeem_enrolment(cursor, tenant_id, A.id, token, identity, lane_name,
                                    Direction.ENTRY, NOON_MONDAY)
        return run

    a, b = race(owner, tenant_id, lane("CAR-A", "L1"), lane("CAR-B", "L2"))
    assert not isinstance(a, BaseException) and not isinstance(b, BaseException), (a, b)
    assert a.redeemed and not b.redeemed
    assert b.refusal.code == f.REFUSAL_CREDENTIAL_ALREADY_USED, b.refusal
    rows = registration_rows(app, tenant_id)
    assert [(r[1], r[2]) for r in rows] == [("garage-a", "CAR-A"), ("garage-b", "CAR-A"),
                                            ("garage-c", "CAR-A")]
    assert enrolment_row(app, tenant_id)[1] == "CAR-A"


@pytest.mark.guarantee("G25")
@store_test
def test_a_qr_and_a_holder_link_redeem_at_any_garage_the_pass_names_and_at_no_other(
    app, tenant_id
):
    """H5's cheap half: the two credential comparisons are membership tests.
    Issued at A, the QR redeems at B; a link issued at B redeems at A; at C
    both are refused GARAGE_MISMATCH naming the garage, the pass and its set,
    and nothing is written."""
    seed_garages(app, tenant_id, *THREE)
    pass_ = spanning(A, B)
    create(app, tenant_id, A, pass_)
    token = issue(app, tenant_id, A, pass_, "qr-1")["token"]
    refused = redeem(app, tenant_id, C, token)
    assert not refused.redeemed and refused.refusal.code == f.REFUSAL_GARAGE_MISMATCH
    assert "'garage-c'" in refused.refusal.detail and "garage-b" in refused.refusal.detail
    assert registration_rows(app, tenant_id) == []
    out = redeem(app, tenant_id, B, token)
    assert out.redeemed, out.refusal
    assert [r[1] for r in registration_rows(app, tenant_id)] == ["garage-a", "garage-b"]
    link = issue_link(app, tenant_id, B, pass_)["token"]
    with pytest.raises(f.Refused) as mismatch:
        redeem_link(app, tenant_id, C, link)
    app.rollback()
    assert mismatch.value.code == f.REFUSAL_GARAGE_MISMATCH
    assert "'garage-c'" in mismatch.value.detail
    assert query(app, tenant_id, "SELECT state FROM holder_links") == [("issued",)]
    redeemed = redeem_link(app, tenant_id, A, link, enrolment_external_id="qr-2")
    assert redeemed["pass"] == pass_.id and redeemed["enrolment"]["pass"] == pass_.id


@pytest.mark.guarantee("G25")
@pytest.mark.guarantee("G1")
@store_test
def test_ending_a_registration_ends_it_at_every_garage_of_the_pass(app, tenant_id):
    seed_garages(app, tenant_id, *THREE)
    pass_ = spanning(*THREE)
    create(app, tenant_id, A, pass_)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, B.id, pass_.id, "CAR-1", date(2026, 1, 1))
        out = end_registration(cursor, tenant_id, C.id, pass_.id, "CAR-1", date(2026, 6, 1))
    app.commit()
    assert out["garages"] == ["garage-a", "garage-b", "garage-c"]
    assert {r[4] for r in registration_rows(app, tenant_id)} == {date(2026, 6, 1)}
    for garage in THREE:
        answer = access_from_store(app, tenant_id, garage.id, "CAR-1", "L1", Direction.ENTRY,
                                   NOON_MONDAY)
        assert answer.outcome is Outcome.NOT_COVERED, (garage, answer)
        assert answer.reason == f.NO_PASS


@pytest.mark.guarantee("G25")
@store_test
def test_a_raw_registration_at_a_garage_the_pass_does_not_name_is_refused_by_the_database(
    app, tenant_id
):
    """The database says it, not only Python: a registration (and a lane row)
    naming a garage the pass does not hold is a foreign-key violation."""
    import psycopg

    uuids = seed_garages(app, tenant_id, A, B)
    pass_ = spanning(A)
    create(app, tenant_id, A, pass_)
    (pass_uuid,) = query(app, tenant_id, "SELECT id FROM passes")[0]
    for statement in (
        "INSERT INTO vehicle_registrations (tenant_id, garage_id, pass_id, vehicle_identity, "
        "effective_day) VALUES (%s, %s, %s, 'CAR-1', '2026-01-01')",
        "INSERT INTO pass_lanes (tenant_id, pass_id, garage_id, lane) VALUES (%s, %s, %s, 'L1')",
    ):
        with pytest.raises(psycopg.errors.ForeignKeyViolation) as violation:
            with tenant(app, tenant_id) as cursor:
                if "pass_lanes" in statement:
                    cursor.execute(statement, (tenant_id, pass_uuid, uuids[B.id]))
                else:
                    cursor.execute(statement, (tenant_id, uuids[B.id], pass_uuid))
        app.rollback()
        assert violation.value.diag.constraint_name.endswith("_garage_of_pass"), violation.value


@pytest.mark.guarantee("G25")
@store_test
def test_a_stored_pass_with_lanes_stated_and_none_at_one_of_its_garages_loads_unreadable(
    app, owner, tenant_id
):
    """A raw write leaves lanes stated at A only on a pass naming {A, B}: the
    load path re-validates and the pass degrades to a STATED answer at B --
    refused-to-answer at entry, not-covered at exit -- never an exception."""
    uuids = seed_garages(app, tenant_id, A, B)
    pass_ = spanning(A, B, terms=simple_terms(
        allowed_lanes=lanes_at(A.id, "L1") + lanes_at(B.id, "L1")))
    create(app, tenant_id, A, pass_)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, A.id, pass_.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    with owner.cursor() as cursor:
        cursor.execute("DELETE FROM pass_lanes WHERE tenant_id = %s AND garage_id = %s",
                       (tenant_id, uuids[B.id]))
    owner.commit()
    entry = access_from_store(app, tenant_id, B.id, "CAR-1", "L1", Direction.ENTRY, NOON_MONDAY)
    assert entry.outcome is Outcome.REFUSED_TO_ANSWER and entry.missing == f.UNREADABLE_TERMS
    assert f.REFUSAL_LANES_NOT_STATED_FOR_GARAGE in entry.detail and "'garage-b'" in entry.detail
    exit_ = access_from_store(app, tenant_id, B.id, "CAR-1", "L1", Direction.EXIT, NOON_MONDAY)
    assert exit_.outcome is Outcome.NOT_COVERED and exit_.reason == f.PASS_UNREADABLE


# ---------------------------------------------------------------------------
# The visit ledger is PER GARAGE (the L3's F2), and a membership row decides
# nothing recorded under it (the L3's F1).
# ---------------------------------------------------------------------------

from garage_pass.store.records import (  # noqa: E402
    ONE_OPEN_VISIT,
    record_entry,
    record_exit,
)


def _entry(app, tenant_id, garage: Garage, pass_: Pass, identity: str, hour: int) -> dict:
    with tenant(app, tenant_id) as cursor:
        out = record_entry(cursor, tenant_id, garage.id, pass_.id, identity, "L1",
                           at(date(2026, 6, 1), hour))
    app.commit()
    return out


def _exit(app, tenant_id, garage: Garage, pass_: Pass, identity: str, hour: int) -> dict:
    with tenant(app, tenant_id) as cursor:
        out = record_exit(cursor, tenant_id, garage.id, pass_.id, identity, "L1",
                          at(date(2026, 6, 1), hour))
    app.commit()
    return out


def ledger(app, tenant_id) -> list[tuple]:
    """(garage, identity, entry hour, exited?) -- every visit row, by garage."""
    return query(
        app, tenant_id,
        "SELECT g.external_id, v.vehicle_identity, v.entered_at, v.exited_at IS NOT NULL "
        "FROM visits v JOIN garages g ON g.id = v.garage_id ORDER BY 1, 3",
    )


@pytest.mark.guarantee("G25")
@store_test
def test_an_open_visit_at_one_garage_neither_refuses_an_entry_nor_closes_an_exit_at_another(
    app, tenant_id
):
    """Measured at the L3 on 0e72732: an entry at B was refused VISIT_ALREADY_OPEN
    for a visit open at A, and an exit at B CLOSED A's visit and wrote B's lane on
    it. Now: the open-visit lookup is keyed on the garage. The same-garage rule is
    the control -- entering A twice is still refused, with the same code, and the
    database's own index (re-keyed per garage in 0004) still names itself."""
    import psycopg

    uuids = seed_garages(app, tenant_id, A, B)
    pass_ = spanning(A, B, state=State.ACTIVE)
    create(app, tenant_id, A, pass_)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, A.id, pass_.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    _entry(app, tenant_id, A, pass_, "CAR-1", 8)
    # the control first: the SAME garage twice is refused as before, naming the garage
    with pytest.raises(f.Refused) as refused:
        _entry(app, tenant_id, A, pass_, "CAR-1", 9)
    app.rollback()
    assert refused.value.code == f.REFUSAL_VISIT_ALREADY_OPEN
    assert "'garage-a'" in refused.value.detail and "no recorded exit" in refused.value.detail
    # and the database's backstop for the same garage, by name
    (pass_uuid,) = query(app, tenant_id, "SELECT id FROM passes")[0]
    with pytest.raises(psycopg.errors.UniqueViolation) as violation:
        with tenant(app, tenant_id) as cursor:
            cursor.execute(
                "INSERT INTO visits (tenant_id, garage_id, pass_id, vehicle_identity, entry_lane, "
                "entered_at) VALUES (%s, %s, %s, 'CAR-1', 'L1', now())",
                (tenant_id, uuids[A.id], pass_uuid),
            )
    app.rollback()
    assert violation.value.diag.constraint_name == ONE_OPEN_VISIT
    # an exit at B with nothing open AT B: refused by name, naming B -- never A's visit closed
    with pytest.raises(f.Refused) as refused:
        _exit(app, tenant_id, B, pass_, "CAR-1", 9)
    app.rollback()
    assert refused.value.code == f.REFUSAL_NO_OPEN_VISIT
    assert "'garage-b'" in refused.value.detail
    assert ledger(app, tenant_id) == [("garage-a", "CAR-1", at(date(2026, 6, 1), 8), False)]
    # an entry at B while A's visit is still open: RECORDED, the ledger holds both.
    # Spelled as an assertion, so a refusal here -- the module's, or the database
    # index's if it were keyed per pass again -- is read as a red about the subject
    try:
        _entry(app, tenant_id, B, pass_, "CAR-1", 10)
    except f.Refused as refused:
        app.rollback()
        pytest.fail(f"an entry at B was refused for a visit open at A: {refused.code}: "
                    f"{refused.detail}")
    assert ledger(app, tenant_id) == [
        ("garage-a", "CAR-1", at(date(2026, 6, 1), 8), False),
        ("garage-b", "CAR-1", at(date(2026, 6, 1), 10), False),
    ]
    # each exit closes ITS garage's visit and no other
    _exit(app, tenant_id, B, pass_, "CAR-1", 11)
    assert ledger(app, tenant_id) == [
        ("garage-a", "CAR-1", at(date(2026, 6, 1), 8), False),
        ("garage-b", "CAR-1", at(date(2026, 6, 1), 10), True),
    ]
    _exit(app, tenant_id, A, pass_, "CAR-1", 12)
    assert all(exited for _g, _i, _e, exited in ledger(app, tenant_id))
    # G4, untouched: the access answer at EXIT at every garage of the set is an answer
    for garage in (A, B):
        answer = access_from_store(app, tenant_id, garage.id, "CAR-1", "L1", Direction.EXIT,
                                   at(date(2026, 6, 1), 13))
        assert answer.outcome is Outcome.COVERED and answer.exit_note


@pytest.mark.guarantee("G25")
@store_test
def test_the_store_hands_the_engine_each_visits_garage_and_the_stay_is_measured_there(
    app, owner, tenant_id
):
    """The whole path: the ledger's rows carry their garage, ``visits_on``
    hands the engine every garage's rows with the garage's external id, and
    the exit at B with an entry open only at A is answered with the stay
    UNMEASURED and named -- not OVER_MAX_STAY from A's instant. The control:
    the entry recorded at B is B's, and the exit there is OVER_MAX_STAY. G4
    at every garage of the set, and G17: the pass's stored terms made
    unreadable raw, the exit at A and at B still answered."""
    from datetime import timedelta

    from garage_pass.store.records import visits_on

    seed_garages(app, tenant_id, A, B)
    pass_ = spanning(A, B, state=State.ACTIVE, terms=simple_terms(max_stay=timedelta(hours=1)))
    create(app, tenant_id, A, pass_)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, A.id, pass_.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    _entry(app, tenant_id, A, pass_, "CAR-1", 1)   # eleven hours before noon, at A
    (pass_uuid,) = query(app, tenant_id, "SELECT id FROM passes")[0]
    with tenant(app, tenant_id) as cursor:
        handed = visits_on(cursor, tenant_id, pass_uuid, pass_.id)
    app.rollback()
    assert [(v.garage_id, v.is_open) for v in handed] == [(A.id, True)]
    at_b = access_from_store(app, tenant_id, B.id, "CAR-1", "L1", Direction.EXIT, NOON_MONDAY)
    assert at_b.outcome is Outcome.COVERED and at_b.exit_note, at_b
    assert at_b.unmeasured and "at this garage" in at_b.unmeasured
    assert "01:00" not in at_b.unmeasured, "A's entry instant was quoted at B"
    at_a = access_from_store(app, tenant_id, A.id, "CAR-1", "L1", Direction.EXIT, NOON_MONDAY)
    assert at_a.outcome is Outcome.NOT_COVERED and at_a.reason == f.OVER_MAX_STAY, at_a
    assert "11:00:00 elapsed" in at_a.detail and at_a.exit_note
    # G17 at exit at both garages: the stored terms made unreadable raw
    with owner.cursor() as cursor:
        cursor.execute("UPDATE passes SET allowance_count = 3, allowance_per = 'window' "
                       "WHERE tenant_id = %s AND id = %s", (tenant_id, pass_uuid))
    for garage in (A, B):
        answer = access_from_store(app, tenant_id, garage.id, "CAR-1", "L1", Direction.EXIT,
                                   NOON_MONDAY)
        assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.PASS_UNREADABLE
        assert answer.exit_note


@pytest.mark.guarantee("G25")
@store_test
def test_the_allowance_still_counts_every_garage_of_the_set_after_the_ledger_is_per_garage(
    app, tenant_id
):
    """C5, the control that stops the fix over-reaching: the open-visit lookup
    is per garage, the ALLOWANCE is not -- two entries, one at A and one at B,
    spend a two-visit allowance at both, and the sentence counts both."""
    seed_garages(app, tenant_id, A, B)
    pass_ = spanning(A, B, state=State.ACTIVE, terms=simple_terms(
        visit_allowance=VisitAllowance(count=2, per=AllowancePeriod.LIFE)))
    create(app, tenant_id, A, pass_)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, A.id, pass_.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    _entry(app, tenant_id, A, pass_, "CAR-1", 8)
    _exit(app, tenant_id, A, pass_, "CAR-1", 9)
    _entry(app, tenant_id, B, pass_, "CAR-1", 10)
    _exit(app, tenant_id, B, pass_, "CAR-1", 11)
    for garage in (A, B):
        answer = access_from_store(app, tenant_id, garage.id, "CAR-1", "L1", Direction.ENTRY,
                                   at(date(2026, 6, 1), 12))
        assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.OUT_OF_VISITS
        assert "2 of 2 visit(s) used; counted 2 recorded entries on pass" in answer.detail, answer
    # a per-garage count would have read 1 of 2 at both: the control on the control
    third = access_from_store(app, tenant_id, A.id, "CAR-2", "L1", Direction.ENTRY,
                              at(date(2026, 6, 1), 12))
    assert third.reason == f.NO_PASS


def _record(app, tenant_id, garage: Garage, pass_: Pass, identity: str, entered_at) -> None:
    """An entry and, half an hour later, its exit -- at ``garage``, at an instant
    given in full (the mixed-zone tests need the zone stated per entry)."""
    with tenant(app, tenant_id) as cursor:
        record_entry(cursor, tenant_id, garage.id, pass_.id, identity, "L1", entered_at)
        record_exit(cursor, tenant_id, garage.id, pass_.id, identity, "L1",
                    entered_at + timedelta(minutes=30))
    app.commit()


@pytest.mark.guarantee("G25")
@store_test
def test_the_store_hands_the_engine_every_garage_of_the_pass_and_each_entry_is_read_there(
    app, owner, tenant_id
):
    """The whole path on the mixed-zone pass: the ledger's Tokyo row, read by
    the store at Denver, is read on TOKYO'S clock -- the gate's case through
    ``access_from_store``, OUT_OF_VISITS at Denver on Monday morning with the
    sentence naming garage-far; and the mirror, a Sunday-evening Denver entry
    asked about at Tokyo on Monday, not counted. Then the far garage's stored
    zone made unreadable RAW (a stale row under a tzdata that lost the name):
    the entry at Denver is REFUSED naming garage-far and its field -- the
    store handed the engine an unreadable garage, the engine would not read
    Tokyo's entry on Denver's clock -- and the exit at Denver is still
    answered (G4). The repair makes it answer again."""
    from garage_pass.store.records import set_garage_timezone

    seed_garages(app, tenant_id, A, FAR)
    window = Window(days=frozenset({1, 2, 3, 4, 5}), start_minute=8 * 60, end_minute=18 * 60)
    pass_ = per_window(1, window, A, FAR, id="pass-mixed")
    create(app, tenant_id, A, pass_)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, A.id, pass_.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    monday = date(2026, 6, 1)
    _record(app, tenant_id, FAR, pass_, "CAR-1", at(monday, 9, timezone=FAR_ZONE))
    spent = access_from_store(app, tenant_id, A.id, "CAR-1", "L1", Direction.ENTRY, at(monday, 9))
    assert spent.reason == f.OUT_OF_VISITS, spent
    assert "1 of 1 visit(s) used; counted 1 recorded entry" in spent.detail
    assert "(garage-far: 1)" in spent.detail, spent.detail
    # the mirror, on its own pass: CAR-2's Sunday-evening Denver entry is
    # Monday 09:00 in Tokyo and is NOT in Monday's window, because it was
    # Sunday at the door it drove through
    mirror = per_window(1, window, A, FAR, id="pass-mirror")
    create(app, tenant_id, A, mirror)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, A.id, mirror.id, "CAR-2", date(2026, 1, 1))
    app.commit()
    _record(app, tenant_id, A, mirror, "CAR-2", at(date(2026, 5, 31), 18))
    free = access_from_store(app, tenant_id, FAR.id, "CAR-2", "L1", Direction.ENTRY,
                             at(monday, 17, timezone=FAR_ZONE))
    assert free.outcome is Outcome.COVERED, free
    assert "visit 1 of 1; counted 0 recorded entries" in free.covering_term
    # the same-zone reading, unchanged: asked at Denver, that entry is Sunday's
    sunday = access_from_store(app, tenant_id, A.id, "CAR-2", "L1", Direction.ENTRY,
                               at(monday, 9))
    assert sunday.outcome is Outcome.COVERED and "counted 0 recorded entries" in (
        sunday.covering_term)
    # G17, one garage over: the far garage's zone made unreadable raw
    with owner.cursor() as cursor:
        cursor.execute("UPDATE garages SET timezone = 'Mars/Olympus' WHERE tenant_id = %s "
                       "AND external_id = %s", (tenant_id, FAR.id))
        assert cursor.rowcount == 1
    refused = access_from_store(app, tenant_id, A.id, "CAR-1", "L1", Direction.ENTRY,
                                at(monday, 9))
    assert refused.outcome is Outcome.REFUSED_TO_ANSWER, refused
    assert refused.missing == f.MISSING_TIMEZONE, refused
    assert "garage 'garage-far': REFUSAL_TIMEZONE_UNKNOWN [garage.timezone]" in refused.detail
    assert "'Mars/Olympus'" in refused.detail
    exit_ = access_from_store(app, tenant_id, A.id, "CAR-1", "L1", Direction.EXIT, at(monday, 9))
    assert exit_.outcome is Outcome.COVERED and exit_.exit_note, exit_
    # repaired, it answers again
    with tenant(app, tenant_id) as cursor:
        set_garage_timezone(cursor, tenant_id, FAR.id, FAR_ZONE, by="owner", at=at(monday, 9),
                            reason="tzdata restored")
    app.commit()
    again = access_from_store(app, tenant_id, A.id, "CAR-1", "L1", Direction.ENTRY, at(monday, 9))
    assert again.reason == f.OUT_OF_VISITS, again


@pytest.mark.guarantee("G25")
@store_test
def test_the_store_renders_the_clock_not_here_refusal_the_same_under_three_session_zones(
    app, owner, tenant_id
):
    """The one clock-not-here refusal the store can reach -- a garage of the
    set stored unreadable raw -- read under THREE database session zones
    (UTC, Denver, Tokyo): the same bytes each time, the instant as UTC and
    said to be unrendered, and the decision unchanged (the same key, the
    same garage named). Measured before this: the session zone leaked into
    the sentence -- ``+03:00`` on the builder's machine, and under a Denver
    session the asking clock's day. Fails with ``entered_at.isoformat()``
    planted back, and only because three zones are compared: under any
    one zone alone the sentence reads plausibly."""
    seed_garages(app, tenant_id, A, FAR)
    window = Window(days=frozenset({1, 2, 3, 4, 5}), start_minute=8 * 60, end_minute=18 * 60)
    pass_ = per_window(1, window, A, FAR, id="pass-mixed")
    create(app, tenant_id, A, pass_)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, A.id, pass_.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    monday = date(2026, 6, 1)
    _record(app, tenant_id, FAR, pass_, "CAR-1", at(monday, 9, timezone=FAR_ZONE))
    with owner.cursor() as cursor:
        cursor.execute("UPDATE garages SET timezone = 'Mars/Olympus' WHERE tenant_id = %s "
                       "AND external_id = %s", (tenant_id, FAR.id))
        assert cursor.rowcount == 1
    readings = {}
    try:
        for zone_name in ("UTC", SHIFTING_ZONE, FAR_ZONE):
            with app.cursor() as cursor:
                cursor.execute("SELECT set_config('TimeZone', %s, false)", (zone_name,))
            app.commit()  # session-level, past the per-test rollback
            with app.cursor() as cursor:
                cursor.execute("SHOW TIME ZONE")
                assert cursor.fetchone() == (zone_name,), "the premise: this session zone"
            app.rollback()
            answer = access_from_store(app, tenant_id, A.id, "CAR-1", "L1", Direction.ENTRY,
                                       at(monday, 9))
            assert answer.outcome is Outcome.REFUSED_TO_ANSWER, (zone_name, answer)
            assert answer.missing == f.MISSING_TIMEZONE and answer.pass_id == pass_.id
            readings[zone_name] = (answer.missing, answer.pass_id, answer.detail)
    finally:
        app.rollback()
        with app.cursor() as cursor:
            cursor.execute("SET TIME ZONE DEFAULT")
        app.commit()
    assert len(set(readings.values())) == 1, readings
    (detail,) = {detail for _, _, detail in readings.values()}
    assert "recorded at garage 'garage-far' at 2026-06-01T00:00:00Z (UTC; unrendered on that " \
        "garage's wall clock, which is not here) must be read on that garage's clock" in detail
    assert "garage 'garage-far': REFUSAL_TIMEZONE_UNKNOWN [garage.timezone]" in detail
    for offset in ("+03:00", "+09:00", "+00:00", "-06:00", "2026-05-31"):
        assert offset not in detail, (offset, detail)


@pytest.mark.guarantee("G25")
@pytest.mark.guarantee("G5")
@store_test
def test_a_revocation_ends_each_garages_registrations_on_that_garages_day(app, tenant_id):
    """W2: one instant, 2026-06-01T20:00-06:00, is June 1 in Denver and June 2
    in Tokyo. Revoked FROM DENVER, the Denver row ends on June 1 and the Tokyo
    row on June 2; revoked FROM TOKYO with the same instant, the same -- the
    day is each garage's, never the asking garage's. The same-zone pass (A and
    B, both Denver) ends on June 1 at both, as before. And THE FREED-IDENTITY
    DAY, asserted directly: CAR-1 registers onto a fresh pass at Denver from
    June 1 and at Tokyo from June 2, and is refused at Tokyo from June 1 by
    name, naming the day the revoked registration ends there."""
    from garage_pass.store.records import ENDED_BY_REVOCATION, change_state

    seed_garages(app, tenant_id, A, B, FAR)
    revoke_at = at(date(2026, 6, 1), 20)
    assert at(date(2026, 6, 2), 11, timezone=FAR_ZONE) == revoke_at, "June 2 in Tokyo"

    def ended_days(pass_id: str) -> list[tuple]:
        return query(app, tenant_id,
                     "SELECT g.external_id, r.vehicle_identity, r.end_day, r.ended_reason "
                     "FROM vehicle_registrations r JOIN garages g ON g.id = r.garage_id "
                     "JOIN passes p ON p.id = r.pass_id WHERE p.external_id = %s ORDER BY 1, 2",
                     (pass_id,))

    for asked_from, pass_id in ((A, "from-denver"), (FAR, "from-tokyo")):
        pass_ = spanning(A, FAR, id=pass_id, state=State.ACTIVE)
        create(app, tenant_id, A, pass_)
        with tenant(app, tenant_id) as cursor:
            register_vehicle(cursor, tenant_id, A.id, pass_id, f"CAR-{pass_id}",
                             date(2026, 1, 1))
            out = change_state(cursor, tenant_id, asked_from.id, pass_id, State.REVOKED,
                               by="owner", at=revoke_at, reason="divorced")
        app.commit()
        assert out["registrations_ended"] == 2, out
        assert ended_days(pass_id) == [
            (A.id, f"CAR-{pass_id}", date(2026, 6, 1), ENDED_BY_REVOCATION),
            (FAR.id, f"CAR-{pass_id}", date(2026, 6, 2), ENDED_BY_REVOCATION),
        ], (asked_from.id, ended_days(pass_id))
    # the same-zone control: unchanged, June 1 at both
    same = spanning(A, B, id="same-zone", state=State.ACTIVE)
    create(app, tenant_id, A, same)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, A.id, same.id, "CAR-same", date(2026, 1, 1))
        change_state(cursor, tenant_id, B.id, same.id, State.REVOKED, by="owner", at=revoke_at,
                     reason="divorced")
    app.commit()
    assert [row[2] for row in ended_days(same.id)] == [date(2026, 6, 1), date(2026, 6, 1)]
    # the freed-identity day, directly: where is CAR-from-denver free from when?
    fresh = spanning(A, FAR, id="fresh", state=State.ACTIVE)
    create(app, tenant_id, A, fresh)
    with tenant(app, tenant_id) as cursor:
        with pytest.raises(f.Refused) as refused:
            register_vehicle(cursor, tenant_id, FAR.id, fresh.id, "CAR-from-denver",
                             date(2026, 6, 1))
    app.rollback()
    assert refused.value.code == f.REFUSAL_VEHICLE_ON_ANOTHER_PASS
    assert "'garage-far'" in refused.value.detail and "2026-06-02" in refused.value.detail, (
        refused.value.detail)
    with tenant(app, tenant_id) as cursor:
        out = register_vehicle(cursor, tenant_id, FAR.id, fresh.id, "CAR-from-denver",
                               date(2026, 6, 2))
    app.commit()
    assert sorted(out["garages"]) == [A.id, FAR.id], out


@pytest.mark.guarantee("G25")
@pytest.mark.guarantee("G5")
@store_test
def test_a_revocation_with_a_garage_of_the_pass_unreadable_is_refused_by_name_and_writes_nothing(
    app, owner, tenant_id
):
    """Every garage's day is derived BEFORE the first row changes: the far
    garage's stored zone made unreadable raw, the revocation from Denver is
    refused naming garage-far and the repair, and NOTHING moved -- the pass
    is still active, no history row, every registration open. The same-zone
    control in the same test: with the far garage repaired, it goes through."""
    from garage_pass.store.records import change_state, set_garage_timezone

    seed_garages(app, tenant_id, A, FAR)
    pass_ = spanning(A, FAR, state=State.ACTIVE)
    create(app, tenant_id, A, pass_)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, A.id, pass_.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    with owner.cursor() as cursor:
        cursor.execute("UPDATE garages SET timezone = 'Mars/Olympus' WHERE tenant_id = %s "
                       "AND external_id = %s", (tenant_id, FAR.id))
    before = (query(app, tenant_id, "SELECT state FROM passes"),
              query(app, tenant_id, "SELECT count(*) FROM pass_state_changes"),
              registration_rows(app, tenant_id))
    with tenant(app, tenant_id) as cursor:
        with pytest.raises(f.Refused) as refused:
            change_state(cursor, tenant_id, A.id, pass_.id, State.REVOKED, by="owner",
                         at=at(date(2026, 6, 1), 20), reason="divorced")
    app.rollback()
    assert refused.value.code == f.REFUSAL_TIMEZONE_UNKNOWN, refused.value
    assert "'garage-far'" in refused.value.detail and "set-garage-timezone" in (
        refused.value.detail)
    assert (query(app, tenant_id, "SELECT state FROM passes"),
            query(app, tenant_id, "SELECT count(*) FROM pass_state_changes"),
            registration_rows(app, tenant_id)) == before, "a refusal writes nothing"
    assert before[0] == [("active",)] and all(row[4] is None for row in before[2])
    with tenant(app, tenant_id) as cursor:
        set_garage_timezone(cursor, tenant_id, FAR.id, FAR_ZONE, by="owner",
                            at=at(date(2026, 6, 1), 20), reason="tzdata restored")
        out = change_state(cursor, tenant_id, A.id, pass_.id, State.REVOKED, by="owner",
                           at=at(date(2026, 6, 1), 20), reason="divorced")
    app.commit()
    assert out["registrations_ended"] == 2


@pytest.mark.guarantee("G25")
@store_test
def test_removing_a_garage_that_holds_a_visit_or_a_registration_fails_by_name(
    app, owner, tenant_id
):
    """The L3's F1, read the other way: with ON DELETE CASCADE a superuser delete
    of ONE pass_garages row took that garage's visits and registrations with
    it. Now RESTRICT, both keys, each named in the failure; and the control
    without which this only proves the table is unreachable -- a membership
    row with nothing under it still goes, and takes only its lane rows."""
    import psycopg

    uuids = seed_garages(app, tenant_id, A, B, C)
    pass_ = spanning(A, B, C, state=State.ACTIVE, terms=simple_terms(
        allowed_lanes=lanes_at(A.id, "L1") + lanes_at(B.id, "L1") + lanes_at(C.id, "L1")))
    create(app, tenant_id, A, pass_)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, A.id, pass_.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    _entry(app, tenant_id, B, pass_, "CAR-1", 8)
    _exit(app, tenant_id, B, pass_, "CAR-1", 9)
    (pass_uuid,) = query(app, tenant_id, "SELECT id FROM passes")[0]
    # B is left holding ONLY its visit: its registration row goes as the OWNER
    # (a redaction, the one route this module leaves), so that the visits key is
    # the only thing standing and the test measures IT, not the registrations key
    with owner.cursor() as cursor:
        cursor.execute("DELETE FROM vehicle_registrations WHERE tenant_id = %s AND garage_id = %s",
                       (tenant_id, uuids[B.id]))
        assert cursor.rowcount == 1

    def delete_membership(garage: Garage) -> None:
        with owner.cursor() as cursor:
            cursor.execute("DELETE FROM pass_garages WHERE tenant_id = %s AND pass_id = %s "
                           "AND garage_id = %s", (tenant_id, pass_uuid, uuids[garage.id]))
            assert cursor.rowcount == 1

    before = (ledger(app, tenant_id), registration_rows(app, tenant_id))
    # B holds only a visit: the VISITS key, by name
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as violation:
        delete_membership(B)
    assert violation.value.diag.constraint_name == "visits_garage_of_pass", violation.value
    # C holds only a registration (the fan-out): the REGISTRATIONS key, by name
    with pytest.raises(psycopg.errors.ForeignKeyViolation) as violation:
        delete_membership(C)
    assert violation.value.diag.constraint_name == "vehicle_registrations_garage_of_pass"
    assert (ledger(app, tenant_id), registration_rows(app, tenant_id)) == before
    # the control: end the registrations, delete the ledger as the OWNER (a
    # redaction, the one route this module leaves), and the membership goes --
    # with its lane row, and with nothing else
    with tenant(app, tenant_id) as cursor:
        end_registration(cursor, tenant_id, A.id, pass_.id, "CAR-1", date(2026, 7, 1))
    app.commit()
    with owner.cursor() as cursor:
        cursor.execute("DELETE FROM vehicle_registrations WHERE tenant_id = %s AND garage_id = %s",
                       (tenant_id, uuids[C.id]))
        assert cursor.rowcount == 1
    lanes_before = query(app, tenant_id, "SELECT count(*) FROM pass_lanes")
    delete_membership(C)
    assert query(app, tenant_id, "SELECT count(*) FROM pass_lanes") == [(lanes_before[0][0] - 1,)]
    assert pass_garage_rows(app, tenant_id) == [(pass_.id, A.id), (pass_.id, B.id)]
    assert ledger(app, tenant_id) == before[0], "a visit went with a membership it was not under"


# ---------------------------------------------------------------------------
# Migration 0004 BACKFILLS -- A1.1. Seeded at 0003, migrated, read back.
# ---------------------------------------------------------------------------


def _apply(cursor, path) -> None:
    from store_harness import MIGRATIONS

    cursor.execute((MIGRATIONS / path).read_text())


def _rebuild_to_0003(owner) -> None:
    from store_harness import MIGRATIONS

    with owner.cursor() as cursor:
        cursor.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name.startswith("0004"):
                continue
            cursor.execute(path.read_text())


def _try_0004(owner) -> str | None:
    """Apply 0004; the error's primary message when it refuses, else None."""
    import psycopg

    from store_harness import MIGRATIONS

    (path,) = [p for p in MIGRATIONS.glob("0004_*.sql")]
    with owner.cursor() as cursor:
        try:
            cursor.execute(path.read_text())
        except psycopg.Error as failure:
            cursor.execute("ROLLBACK")
            return (failure.diag.message_primary or str(failure)).strip()
    return None


@pytest.fixture
def at_0003(owner):
    """The schema at 0003 as the OWNER, under the cluster lock (0001 ALTERs
    the cluster-global role); rebuilt to the full schema afterwards so the
    module's other tests read the shape that ships."""
    from store_harness import DSN, cluster_lock, migrate

    with cluster_lock(DSN):
        _rebuild_to_0003(owner)
        yield owner
    migrate(DSN).close()


def _seed_at_0003(owner, tenant_id, passes: list[tuple[str, str, list[str]]],
                  garages: tuple[str, ...] = ("g-a", "g-b")) -> dict[str, object]:
    """Raw rows in the OLD shape: garages, passes each at ONE garage with
    lanes (stated) and two windows. Returns the garage uuids."""
    uuids = {}
    with owner.cursor() as cursor:
        for garage in garages:
            cursor.execute(
                "INSERT INTO garages (tenant_id, external_id, timezone, transient_available) "
                "VALUES (%s, %s, 'America/Denver', true) RETURNING id", (tenant_id, garage))
            uuids[garage] = cursor.fetchone()[0]
        for external_id, garage, lanes in passes:
            cursor.execute(
                "INSERT INTO passes (tenant_id, garage_id, external_id, label, holder_email, "
                "entry_allowed, exit_allowed, lanes_stated, state) VALUES (%s, %s, %s, 'l', "
                "'h@example.com', true, true, %s, 'active') RETURNING id",
                (tenant_id, uuids[garage], external_id, bool(lanes)))
            (pass_uuid,) = cursor.fetchone()
            for lane in lanes:
                cursor.execute("INSERT INTO pass_lanes (tenant_id, pass_id, lane) VALUES "
                               "(%s, %s, %s)", (tenant_id, pass_uuid, lane))
            for position, (start, end) in enumerate(((360, 720), (780, 1200))):
                cursor.execute(
                    "INSERT INTO pass_windows (tenant_id, pass_id, days, start_minute, "
                    "end_minute, position) VALUES (%s, %s, '{1,2,3}', %s, %s, %s)",
                    (tenant_id, pass_uuid, start, end, position))
    return uuids


@pytest.mark.guarantee("G25")
@store_test
def test_0004_backfills_every_pass_with_its_one_garage_and_every_lane_with_its_passs_garage(
    at_0003, tenant_id
):
    """A1.1 control (a): seeded at 0003 -- several passes, multi-lane, multi-
    window, at two garages -- then 0004. Every pass has exactly one
    pass_garages row naming its OLD garage, and every lane row carries its
    own pass's garage. Counts against the pre-migration counts, not a literal."""
    from store_harness import new_tenant

    owner = at_0003
    tenant_id = new_tenant(owner)
    _seed_at_0003(owner, tenant_id, [("p-1", "g-a", ["L1", "L2"]), ("p-2", "g-b", ["L1"]),
                                     ("p-3", "g-a", []), ("p-4", "g-b", ["L3", "L4", "L5"])])
    with owner.cursor() as cursor:
        cursor.execute("SELECT external_id, garage_id FROM passes WHERE tenant_id = %s "
                       "ORDER BY 1", (tenant_id,))
        old = cursor.fetchall()
        cursor.execute("SELECT count(*) FROM pass_lanes WHERE tenant_id = %s", (tenant_id,))
        (lanes_before,) = cursor.fetchone()
    assert len(old) == 4 and lanes_before == 6, "the premise: rows to backfill"
    failure = _try_0004(owner)
    if failure is not None:
        pytest.fail(f"0004 did not apply over rows seeded at 0003: {failure}")
    with owner.cursor() as cursor:
        cursor.execute(
            "SELECT p.external_id, array_agg(pg.garage_id) FROM passes p "
            "LEFT JOIN pass_garages pg ON pg.tenant_id = p.tenant_id AND pg.pass_id = p.id "
            "WHERE p.tenant_id = %s GROUP BY p.external_id ORDER BY 1", (tenant_id,))
        new = cursor.fetchall()
        cursor.execute(
            "SELECT count(*), count(*) FILTER (WHERE l.garage_id = pg.garage_id) "
            "FROM pass_lanes l JOIN pass_garages pg ON pg.tenant_id = l.tenant_id "
            "AND pg.pass_id = l.pass_id WHERE l.tenant_id = %s", (tenant_id,))
        lanes_after, lanes_at_their_passs_garage = cursor.fetchone()
        cursor.execute("SELECT count(*) FROM information_schema.columns WHERE table_name = "
                       "'passes' AND column_name = 'garage_id'")
        (column,) = cursor.fetchone()
    assert [(ext, garages) for ext, garages in new] == [(ext, [g]) for ext, g in old], (
        "every pass has exactly ONE pass_garages row, naming the garage it had")
    assert (lanes_after, lanes_at_their_passs_garage) == (lanes_before, lanes_before)
    assert column == 0, "passes.garage_id is gone"


@pytest.mark.guarantee("G25")
@store_test
def test_0004_on_an_empty_cluster_reads_as_the_catalogue_describes(at_0003):
    """A1.1 control (b): the empty case -- and each reading the other way at
    0003 in the same run, or the probe measured nothing."""
    owner = at_0003

    def catalogue():
        with owner.cursor() as cursor:
            cursor.execute("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                           "WHERE relname = 'pass_garages'")
            table = cursor.fetchone()
            cursor.execute("SELECT table_name, column_name FROM information_schema.columns "
                           "WHERE (table_name, column_name) IN (('passes', 'garage_id'), "
                           "('pass_lanes', 'garage_id')) ORDER BY 1")
            return table, cursor.fetchall()
    table_at_0003, columns_at_0003 = catalogue()
    assert table_at_0003 is None and columns_at_0003 == [("passes", "garage_id")]
    assert _try_0004(owner) is None
    table, columns = catalogue()
    assert table == ("pass_garages", True, True), "present, RLS enabled and forced"
    assert columns == [("pass_lanes", "garage_id")], (
        "passes.garage_id absent; pass_lanes.garage_id present")


@pytest.mark.guarantee("G25")
@store_test
def test_0004_refuses_to_drop_a_lane_row_whose_pass_does_not_exist(at_0003):
    """A1.1 control (c), THE LOUD FAILURE: an orphan lane row (a raw write
    with the constraint's triggers off -- a shape the product cannot make)
    makes 0004 FAIL naming the count, never drop the row."""
    from uuid import uuid4

    from store_harness import new_tenant

    owner = at_0003
    tenant_id = new_tenant(owner)
    _seed_at_0003(owner, tenant_id, [("p-1", "g-a", ["L1"])])
    with owner.cursor() as cursor:
        cursor.execute("ALTER TABLE pass_lanes DISABLE TRIGGER ALL")
        cursor.execute("INSERT INTO pass_lanes (tenant_id, pass_id, lane) VALUES (%s, %s, 'L9')",
                       (tenant_id, uuid4()))
        cursor.execute("ALTER TABLE pass_lanes ENABLE TRIGGER ALL")
    failure = _try_0004(owner)
    assert failure is not None, "0004 applied over an orphan lane row"
    assert "1 pass_lanes row(s) name a pass that does not exist" in failure, failure
    with owner.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pass_lanes WHERE lane = 'L9'")
        assert cursor.fetchone() == (1,), "the row was not dropped"


@pytest.mark.guarantee("G25")
@store_test
def test_0004_refuses_the_unique_tightening_by_name_and_never_picks_a_winner(at_0003):
    """A1.1 control (d): EMP-1 at g-a and EMP-1 at g-b, one tenant. 0004 FAILS
    naming the colliding id; both passes stand."""
    from store_harness import new_tenant

    owner = at_0003
    tenant_id = new_tenant(owner)
    _seed_at_0003(owner, tenant_id,
                  [("EMP-1", "g-a", []), ("EMP-1", "g-b", []), ("EMP-2", "g-a", [])])
    failure = _try_0004(owner)
    assert failure is not None, "0004 applied over two passes called EMP-1 in one tenant"
    assert "EMP-1 (2 passes)" in failure and "EMP-2" not in failure, failure
    with owner.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM passes WHERE tenant_id = %s AND external_id = 'EMP-1'",
                       (tenant_id,))
        assert cursor.fetchone() == (2,), "nothing was chosen for anyone"


# ---------------------------------------------------------------------------
# The command line: the full product walk over a three-garage pass, every
# new refusal rendered through main() -- 0 tracebacks, every exit status
# asserted, and the rendered collector sees every detail (G18 holds).
# ---------------------------------------------------------------------------


def _run(main, capsys, argv: list[str]) -> tuple[int, dict]:
    import json

    status = main(argv)
    out = capsys.readouterr()
    assert "Traceback" not in out.err and "Traceback" not in out.out, out
    return status, json.loads(out.out) if out.out.strip() else {}


@pytest.mark.guarantee("G25")
@pytest.mark.guarantee("G18")
@store_test
def test_the_product_walk_over_a_three_garage_pass_through_the_command_line(
    app, owner, tenant_id, tmp_path, capsys, monkeypatch
):
    """H7: create three garages, create the pass at one of them naming all
    three, enrol, redeem, access at each garage, swap the car, revoke --
    and every refusal this round adds, rendered with its documented exit
    code. Every status is asserted; a traceback anywhere is the failure."""
    import json

    import sweep_route_sentences as sweep

    from _rendered_sentences import rendered_so_far
    from enrolment_harness import app_dsn_into_the_environment
    from fixtures import pass_document
    from garage_pass.cli import main

    app_dsn_into_the_environment(monkeypatch)
    started = len(rendered_so_far())
    T = ["--tenant", str(tenant_id)]
    AT = "2026-06-01T12:00:00-06:00"

    def write(name: str, document) -> str:
        path = tmp_path / name
        path.write_text(json.dumps(document))
        return str(path)

    for garage in THREE:
        status, out = _run(main, capsys, ["create-garage", *T, "--garage", write(
            f"{garage.id}.json", {"id": garage.id, "timezone": garage.timezone,
                                  "transient_available": True, "enrols_at": "entry"})])
        assert status == 0 and out["stored"] == garage.id, out
    lanes = [{"garage_id": g.id, "lanes": ["L1", "L2"]} for g in THREE]
    document = pass_document(id="pass-span", garage_ids=[g.id for g in THREE],
                             terms={**pass_document()["terms"], "allowed_lanes": lanes})
    refusals: dict[str, tuple[int, dict]] = {}
    # the new refusals, each through main(): exit 3, the JSON refusal, the field
    refusals["no garage"] = _run(main, capsys, ["check-terms", "--pass", write(
        "no-garage.json", {**document, "garage_ids": []})])
    refusals["lanes at one garage only"] = _run(main, capsys, ["check-terms", "--pass", write(
        "one-garage-lanes.json", {**document, "terms": {**document["terms"],
                                                         "allowed_lanes": lanes[:1]}})])
    refusals["lanes at a garage not named"] = _run(main, capsys, ["check-terms", "--pass", write(
        "elsewhere-lanes.json", {**document, "terms": {**document["terms"], "allowed_lanes": [
            *lanes, {"garage_id": ELSEWHERE.id, "lanes": ["L1"]}]}})])
    refusals["a garage's lanes twice"] = _run(main, capsys, ["check-terms", "--pass", write(
        "twice.json", {**document, "terms": {**document["terms"], "allowed_lanes": [
            *lanes, {"garage_id": A.id, "lanes": ["L3"]}]}})])
    refusals["stored at a garage it does not name"] = _run(main, capsys, [
        "create-pass", *T, "--garage", ELSEWHERE.id, "--pass", write("span.json", document),
        "--by", "owner", "--at", AT])
    expected = {
        "no garage": (f.REFUSAL_PASS_NAMES_NO_GARAGE, "pass.garage_ids"),
        "lanes at one garage only": (f.REFUSAL_LANES_NOT_STATED_FOR_GARAGE, "allowed_lanes"),
        "lanes at a garage not named": (f.REFUSAL_LANES_AT_A_GARAGE_THE_PASS_DOES_NOT_NAME,
                                        "allowed_lanes"),
        "a garage's lanes twice": (f.REFUSAL_LANES_GARAGE_REPEATED, "allowed_lanes[3].garage_id"),
        "stored at a garage it does not name": (f.REFUSAL_GARAGE_NOT_FOUND, "garage"),
    }
    for name, (status, out) in refusals.items():
        assert status == 3 and (out["refused"], out["field"]) == expected[name], (name, out)
    # ELSEWHERE is not even a garage of this tenant: GARAGE_NOT_FOUND came first, by
    # the published order. Store it now, and the membership refusal is the one heard.
    _run(main, capsys, ["create-garage", *T, "--garage", write("elsewhere.json", {
        "id": ELSEWHERE.id, "timezone": ELSEWHERE.timezone, "transient_available": True,
        "enrols_at": "entry"})])
    status, out = _run(main, capsys, ["create-pass", *T, "--garage", ELSEWHERE.id, "--pass",
                                      write("span.json", document), "--by", "owner", "--at", AT])
    assert status == 3 and out["refused"] == f.REFUSAL_GARAGE_MISMATCH, out
    assert "'garage-elsewhere'" in out["detail"] and "garage-c" in out["detail"]
    # the walk: create at A, enrol, redeem at A, covered at A, B and C
    status, out = _run(main, capsys, ["create-pass", *T, "--garage", A.id, "--pass",
                                      write("span.json", document), "--by", "owner", "--at", AT])
    assert status == 0 and out["stored"] == "pass-span", out
    status, out = _run(main, capsys, ["issue-enrolment", *T, "--garage", B.id, "--pass-id",
                                      "pass-span", "--enrolment-id", "qr-1", "--starts-on",
                                      "2026-06-01", "--days-valid", "3", "--by", "owner",
                                      "--at", AT])
    assert status == 0 and out["pass"] == "pass-span", out
    token = out["token"]
    status, out = _run(main, capsys, ["redeem-enrolment", *T, "--garage", ELSEWHERE.id, "--token",
                                      token, "--vehicle", "CAR-1", "--lane", "L1", "--direction",
                                      "entry", "--at", AT])
    assert status == 1 and out["enrolment"]["refused"] == f.REFUSAL_GARAGE_MISMATCH, out
    assert out["answer"]["reason"] == f.NO_PASS, "the movement is answered beside the refusal"
    status, out = _run(main, capsys, ["redeem-enrolment", *T, "--garage", A.id, "--token", token,
                                      "--vehicle", "CAR-1", "--lane", "L1", "--direction", "entry",
                                      "--at", AT])
    assert status == 0 and out["enrolment"]["redeemed"] is True, out
    assert out["enrolment"]["registration"]["garages"] == [A.id, B.id, C.id]
    for garage in THREE:
        for direction, lane, want in (("entry", "L1", 0), ("exit", "L2", 0), ("entry", "L9", 1)):
            status, out = _run(main, capsys, ["access-in-store", *T, "--garage", garage.id,
                                              "--vehicle", "CAR-1", "--lane", lane,
                                              "--direction", direction, "--at", AT])
            assert status == want, (garage.id, direction, lane, out)
            if want:
                assert out["reason"] == f.WRONG_LANE and f"'{garage.id}'" in out["detail"]
    status, out = _run(main, capsys, ["access-in-store", *T, "--garage", ELSEWHERE.id,
                                      "--vehicle", "CAR-1", "--lane", "L1", "--direction", "entry",
                                      "--at", AT])
    assert status == 1 and out["reason"] == f.NO_PASS, out
    # a second car, registered by the owner at C: held at every garage, and a
    # register-vehicle at a garage the pass does not name is refused by name
    status, out = _run(main, capsys, ["register-vehicle", *T, "--garage", C.id, "--pass-id",
                                      "pass-span", "--vehicle", "CAR-2", "--effective-day",
                                      "2026-06-01"])
    assert status == 0 and out["garages"] == [A.id, B.id, C.id], out
    status, out = _run(main, capsys, ["register-vehicle", *T, "--garage", ELSEWHERE.id,
                                      "--pass-id", "pass-span", "--vehicle", "CAR-3",
                                      "--effective-day", "2026-06-01"])
    assert status == 3 and out["refused"] == f.REFUSAL_PASS_NOT_FOUND, out
    assert "garage-elsewhere" in out["detail"] and "garage-a" in out["detail"]
    # the swap: end CAR-1 everywhere, a new QR, the new car
    status, out = _run(main, capsys, ["end-registration", *T, "--garage", B.id, "--pass-id",
                                      "pass-span", "--vehicle", "CAR-1", "--end-day",
                                      "2026-06-02"])
    assert status == 0 and out["garages"] == [A.id, B.id, C.id], out
    status, out = _run(main, capsys, ["issue-enrolment", *T, "--garage", C.id, "--pass-id",
                                      "pass-span", "--enrolment-id", "qr-2", "--starts-on",
                                      "2026-06-02", "--days-valid", "3", "--by", "owner",
                                      "--at", AT])
    assert status == 0
    status, out = _run(main, capsys, ["redeem-enrolment", *T, "--garage", C.id, "--token",
                                      out["token"], "--vehicle", "CAR-1-NEW", "--lane", "L2",
                                      "--direction", "entry", "--at", "2026-06-02T09:00:00-06:00"])
    assert status == 0 and out["enrolment"]["redeemed"] is True, out
    status, out = _run(main, capsys, ["access-in-store", *T, "--garage", A.id, "--vehicle",
                                      "CAR-1", "--lane", "L1", "--direction", "entry", "--at",
                                      "2026-06-02T09:00:00-06:00"])
    assert status == 1 and out["reason"] == f.NO_PASS and "ended on 2026-06-02" in out["detail"]
    # revoke: every registration at every garage ends, every credential dies
    status, out = _run(main, capsys, ["set-state", *T, "--garage", B.id, "--pass-id",
                                      "pass-span", "--state", "revoked", "--by", "owner",
                                      "--reason", "left", "--at", "2026-06-03T09:00:00-06:00"])
    assert status == 0 and out["registrations_ended"] == 6, out
    for garage in THREE:
        status, out = _run(main, capsys, ["access-in-store", *T, "--garage", garage.id,
                                          "--vehicle", "CAR-2", "--lane", "L1", "--direction",
                                          "exit", "--at", "2026-06-04T09:00:00-06:00"])
        assert status == 1 and out["reason"] == f.REVOKED, (garage.id, out)
    # the rendered collector saw every refusal detail this walk printed
    rendered = rendered_so_far()[started:]
    for name, (_status, out) in refusals.items():
        assert any(out["detail"] == d for d, _stack in rendered), f"{name} was not collected"
    status, result = sweep.judge_rendered(list(rendered))
    assert result["unjudged"] == [] and result["false"] == [], sweep.report_rendered(result)


# ---------------------------------------------------------------------------
# The documents door: --garages hands the engine the other garages' clocks.
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G25")
@pytest.mark.guarantee("G18")
def test_the_documents_door_reads_each_entry_on_its_own_garages_clock_with_garages_handed_in(
    tmp_path, capsys
):
    """The gate's case through ``garage-pass access``: a Denver garage
    document, a pass document naming Denver and Tokyo with one visit per
    window, a visits document holding the Tokyo entry at 09:00 Monday Tokyo
    time. With ``--garages`` handing in the Tokyo document, the entry at
    Denver on Monday morning is OUT_OF_VISITS, exit 1, the sentence naming
    garage-far. WITHOUT it, the entry is refused to answer naming ``garages``
    (exit 2) -- never read on Denver's clock -- and the EXIT without it is
    answered, covered, exit 0 (G4: no exit counts an allowance). A malformed
    member of ``--garages`` is the same door as ``--garage``: refused at an
    entry, answered RECORD_UNREADABLE at an exit; not a JSON list, the same
    two readings naming the option -- exactly ``--registrations``' door."""
    import json

    import sweep_route_sentences as sweep

    from _rendered_sentences import rendered_so_far
    from fixtures import pass_document
    from garage_pass.cli import main

    started = len(rendered_so_far())

    def write(name: str, document: object) -> str:
        (tmp_path / name).write_text(json.dumps(document))
        return str(tmp_path / name)

    denver = write("denver.json", {"id": A.id, "timezone": SHIFTING_ZONE,
                                   "transient_available": True})
    tokyo = write("tokyo.json", [{"id": FAR.id, "timezone": FAR_ZONE, "transient_available": True}])
    pass_ = write("pass.json", pass_document(
        id="pass-span", garage_ids=[A.id, FAR.id],
        terms={**pass_document()["terms"], "allowed_lanes": None,
               "windows": [{"days": [1, 2, 3, 4, 5], "start_minute": 480, "end_minute": 1080}],
               "visit_allowance": {"count": 1, "per": "window"}, "max_stay_minutes": None}))
    registrations = write("r.json", [{"pass_id": "pass-span", "vehicle_identity": "CAR-1",
                                      "effective_day": "2026-01-01"}])
    visits = write("v.json", [{"pass_id": "pass-span", "garage_id": FAR.id,
                               "vehicle_identity": "CAR-1", "entry_lane": "L1",
                               "entered_at": "2026-06-01T09:00:00+09:00",
                               "exited_at": "2026-06-01T10:00:00+09:00", "exit_lane": "L1"}])
    base = ["access", "--garage", denver, "--pass", pass_, "--registrations", registrations,
            "--visits", visits, "--vehicle", "CAR-1", "--lane", "L1"]
    entry = ["--direction", "entry", "--at", "2026-06-01T09:00:00-06:00"]
    exit_ = ["--direction", "exit", "--at", "2026-06-01T09:00:00-06:00"]
    status, out = _run(main, capsys, [*base, "--garages", tokyo, *entry])
    assert status == 1 and out["reason"] == f.OUT_OF_VISITS, out
    assert "(garage-far: 1)" in out["detail"], out["detail"]
    status, out = _run(main, capsys, [*base, *entry])
    assert status == 2 and out["outcome"] == "refused_to_answer", out
    assert out["missing"] == f.MISSING_GARAGE_HANDED_IN and "'garage-far'" in out["detail"]
    status, out = _run(main, capsys, [*base, *exit_])
    assert status == 0 and out["outcome"] == "covered" and out["exit_note"], out
    # a member of --garages the module cannot read: the --garage door, one garage over
    stale = write("stale.json", [{"id": FAR.id, "timezone": "Mars/Olympus",
                                  "transient_available": True}])
    status, out = _run(main, capsys, [*base, "--garages", stale, *entry])
    assert status == 3 and out["refused"] == f.REFUSAL_TIMEZONE_UNKNOWN, out
    status, out = _run(main, capsys, [*base, "--garages", stale, *exit_])
    assert status == 0 and out["outcome"] == "covered", out  # unreadable, and not needed
    malformed = write("malformed.json", [{"id": FAR.id}])
    status, out = _run(main, capsys, [*base, "--garages", malformed, *entry])
    assert status == 3 and out["refused"] == f.REFUSAL_FIELD_BLANK, out
    status, out = _run(main, capsys, [*base, "--garages", malformed, *exit_])
    assert status == 1 and out["reason"] == f.RECORD_UNREADABLE, out
    assert "garages[0].timezone" in out["detail"], out["detail"]
    not_a_list = write("dict.json", {"id": FAR.id})
    status, out = _run(main, capsys, [*base, "--garages", not_a_list, *entry])
    assert status == 3 and out["field"] == "--garages" and "JSON list" in out["detail"], out
    status, out = _run(main, capsys, [*base, "--garages", not_a_list, *exit_])
    assert status == 1 and out["reason"] == f.RECORD_UNREADABLE and "--garages" in out["detail"]
    # every refusal this printed was collected and judged
    status, result = sweep.judge_rendered(list(rendered_so_far()[started:]))
    assert result["unjudged"] == [] and result["false"] == [], sweep.report_rendered(result)
