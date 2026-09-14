"""G17 -- a stored pass or garage this module cannot read degrades to a STATED
answer, never an exception: at an entry refused-to-answer naming the field; at
an exit not-covered naming the pass and the field. A car still gets out.

**WHY THE LOAD PATH IS THE PLACE.** Terms and the holder are re-validated on
every load (``Terms.__post_init__``, ``Holder.__post_init__``). Three
contradictions span two tables and no CHECK can reach them (the migration says
which), so a raw row can pass every CHECK and fail the validator. And **any
future tightening of the validator strands every stored pass it no longer
accepts.** Measured before the fix: four such rows made every access call on
the pass raise -- an exception at an exit is a car that cannot leave.

**AN UNREADABLE PASS AT AN EXIT IS NOT-COVERED, WHICH MEANS CHARGEABLE** at a
transient garage. Stated out loud, and the answer names the pass AND the field
so an operator can find the row and undo the charge. Revoked outranks it; it
outranks expiry, which cannot be derived without the terms.

The garage takes the same shape: a stored timezone the system does not carry
is refused where it is WRITTEN, and an existing bad row answers first --
entry refused naming ``garage.timezone``, exit not-covered naming it.

**AND A WRITE AGAINST AN UNREADABLE GARAGE IS REFUSED BY NAME, LIKE A WRITE
AGAINST AN UNREADABLE PASS -- WITH THE ONE CARVE-OUT THAT MAKES THAT SAFE.**
Measured before this: ``create_pass`` and ``register_vehicle`` succeeded at a
garage stored with ``Mars/Olympus`` while every write against an unreadable
pass was refused. Now every write that takes a garage refuses an unreadable
one, naming the refusal and the repair -- and ``set_garage_timezone`` IS the
repair: the one write an unreadable garage takes, because refusing every write
without it would make an unreadable garage permanently unfixable, a trap worse
than the inconsistency. The set of writes is DERIVED from the store's own
signatures, so a write added later is covered or the test fails.

Controls: the load path's catch planted away (a stored contradiction raises
again); the garage's catch planted away; the write gate on an unreadable
garage planted open; the repair's validation of the new zone planted away
(the repair could then store the defect it repairs).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from fixtures import (
    NOON_MONDAY,
    TWO_HOURS_BEFORE,
    a_pass,
    at,
    registered,
    simple_terms,
    transient_garage,
    unstated_garage,
)
from garage_pass import findings as f
from garage_pass.access import Outcome, access
from garage_pass.garage import Garage, garage_from_stored
from garage_pass.localday import UnknownTimezone
from garage_pass.passes import Pass, State, Visit
from garage_pass.store import enrolments
from garage_pass.terms import Direction

GARAGE = transient_garage()


def answered(call, *args, **kwargs):
    """The subject of this guarantee is 'no exception': an exception here is
    the failure, asserted as one -- not a traceback the runner cannot read."""
    try:
        return call(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 -- any exception is the defect
        pytest.fail(f"an access call raised instead of answering: {exc!r}")


STRANDED = f.Unreadable(
    code=f.REFUSAL_WINDOW_NEVER_OCCURS, field="windows[0].days",
    detail="windows[0] names Sat,Sun 00:00-24:00 but 2026-06-01..2026-06-02 contains only Mon,Tue.",
)


def unreadable_pass(state: State = State.ACTIVE, id: str = "pass-1") -> Pass:
    """What the store's load path builds for a row it refuses to read."""
    return Pass(id=id, garage_ids={GARAGE.id}, label="Employee", holder=None, terms=None,
                state=state, unreadable=STRANDED)


def ask(pass_, direction, garage=GARAGE, identity="CAR-1"):
    return answered(
        access,
        garage=garage, passes=[pass_], registrations=[registered(pass_, "CAR-1")],
        visits=[Visit(pass_id=pass_.id, garage_id=garage.id, vehicle_identity="CAR-1",
                      entry_lane="L1", entered_at=TWO_HOURS_BEFORE)],
        vehicle_identity=identity, lane="L1", direction=direction, at=NOON_MONDAY,
    )


@pytest.mark.guarantee("G17")
def test_an_unreadable_pass_at_entry_is_refused_an_answer_naming_the_pass_and_the_field():
    answer = ask(unreadable_pass(), Direction.ENTRY)
    assert answer.outcome is Outcome.REFUSED_TO_ANSWER
    assert answer.missing == f.UNREADABLE_TERMS and answer.pass_id == "pass-1"
    assert "'pass-1'" in answer.detail and "windows[0].days" in answer.detail
    assert f.REFUSAL_WINDOW_NEVER_OCCURS in answer.detail


@pytest.mark.guarantee("G17")
def test_an_unreadable_pass_at_exit_is_not_covered_naming_the_pass_and_the_field():
    """Not covered means EXIT_OUT_OF_TERMS -- chargeable at a transient garage.
    Named so the operator can find the row."""
    answer = ask(unreadable_pass(), Direction.EXIT)
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.PASS_UNREADABLE
    assert answer.means == f.MEANS_EXIT_OUT_OF_TERMS
    assert answer.exit_note == f.EXIT_IS_NEVER_REFUSED
    assert answer.pass_id == "pass-1" and answer.pass_label == "Employee"
    assert "'pass-1'" in answer.detail and "windows[0].days" in answer.detail


@pytest.mark.guarantee("G17")
@pytest.mark.parametrize("direction", list(Direction), ids=[d.value for d in Direction])
def test_revoked_outranks_unreadable_and_unreadable_outranks_the_rest(direction):
    revoked = ask(unreadable_pass(State.REVOKED), direction)
    assert revoked.outcome is Outcome.NOT_COVERED and revoked.reason == f.REVOKED
    for state in (State.DRAFT, State.AWAITING_ENROLMENT, State.ACTIVE, State.SUSPENDED):
        answer = ask(unreadable_pass(state), direction)
        if direction is Direction.EXIT:
            assert answer.reason == f.PASS_UNREADABLE, (state, answer)
        else:
            assert answer.missing == f.UNREADABLE_TERMS, (state, answer)


@pytest.mark.guarantee("G17")
def test_an_unreadable_pass_that_is_not_the_one_holding_the_vehicle_changes_nothing():
    good = a_pass(id="pass-good")
    answer = access(
        garage=GARAGE, passes=[unreadable_pass(id="pass-broken"), good],
        registrations=[registered(good, "CAR-1"), registered(unreadable_pass(id="pass-broken"),
                                                             "CAR-2")],
        visits=[], vehicle_identity="CAR-1", lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY,
    )
    assert answer.outcome is Outcome.COVERED and answer.pass_id == "pass-good"


@pytest.mark.guarantee("G17")
def test_a_pass_is_never_built_unreadable_by_a_caller():
    """Only the load path sets it: a caller must hand in readable terms and a
    holder, and the value refuses the half-built shapes."""
    with pytest.raises(TypeError, match="terms must be a Terms"):
        Pass(id="p", garage_ids={"g"}, label="x", holder=a_pass().holder, terms=None)
    with pytest.raises(TypeError, match="holder must be a Holder"):
        Pass(id="p", garage_ids={"g"}, label="x", holder=None, terms=simple_terms())
    with pytest.raises(TypeError, match="unreadable must be an Unreadable"):
        Pass(id="p", garage_ids={"g"}, label="x", holder=None, terms=None, unreadable="broken")


# ---------------------------------------------------------------------------
# the garage
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G17")
def test_an_unknown_timezone_is_refused_where_the_garage_is_written():
    with pytest.raises(UnknownTimezone):
        Garage(id="g", timezone="Mars/Olympus", transient_available=True)


@pytest.mark.guarantee("G17")
@pytest.mark.parametrize("stated", [True, False, None],
                         ids=["transient", "no-transient", "unstated"])
def test_a_stored_garage_with_an_unknown_timezone_answers_first_naming_the_field(stated):
    """Ahead of every term, and ahead of the transient mode: without a clock
    nothing else can be evaluated. Exit not-covered, entry refused."""
    garage = answered(garage_from_stored, "g-badtz", "Mars/Olympus", stated)
    assert garage.unreadable is not None and garage.unreadable.field == "garage.timezone"
    pass_ = a_pass(garage_ids={"g-badtz"})
    exit_ = ask(pass_, Direction.EXIT, garage=garage)
    assert exit_.outcome is Outcome.NOT_COVERED and exit_.reason == f.GARAGE_UNREADABLE
    assert exit_.means == f.MEANS_EXIT_OUT_OF_TERMS and "Mars/Olympus" in exit_.detail
    assert exit_.exit_note == f.EXIT_IS_NEVER_REFUSED
    entry = ask(pass_, Direction.ENTRY, garage=garage)
    assert entry.outcome is Outcome.REFUSED_TO_ANSWER and entry.missing == f.MISSING_TIMEZONE
    assert "Mars/Olympus" in entry.detail
    # and a blank identity at that garage still gets the garage's answer first
    blank = ask(pass_, Direction.EXIT, garage=garage, identity="  ")
    assert blank.reason == f.GARAGE_UNREADABLE


@pytest.mark.guarantee("G17")
def test_a_readable_garage_is_built_readable_by_the_same_constructor():
    garage = garage_from_stored("g", "America/Denver", None)
    assert garage.unreadable is None and garage == unstated_garage().__class__(
        id="g", timezone="America/Denver", transient_available=None)


# ---------------------------------------------------------------------------
# the store: raw rows the CHECKs cannot reach, and a tightened validator
# ---------------------------------------------------------------------------

from garage_pass.store.access import access_from_store  # noqa: E402
from garage_pass.store.postgres import tenant  # noqa: E402
from garage_pass.store.records import register_vehicle  # noqa: E402
from store_harness import query, seed, store_test  # noqa: E402


def _raw_pass(owner, app, tenant_id, **columns):
    """A pass row written as the OWNER, past the module, naming the one
    garage (``pass_garages``), with a registration there."""
    (garage_uuid,) = query(app, tenant_id, "SELECT id FROM garages")[0]
    base = dict(tenant_id=tenant_id, external_id="raw", label="Raw",
                holder_email="h@example.com", entry_allowed=True, exit_allowed=True,
                lanes_stated=False, state="active")
    base.update(columns)
    with owner.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO passes ({', '.join(base)}) VALUES ({', '.join('%s' for _ in base)}) "
            "RETURNING id",
            tuple(base.values()),
        )
        (pass_uuid,) = cursor.fetchone()
        cursor.execute(
            "INSERT INTO pass_garages (tenant_id, pass_id, garage_id) VALUES (%s, %s, %s)",
            (tenant_id, pass_uuid, garage_uuid),
        )
        cursor.execute(
            "INSERT INTO vehicle_registrations (tenant_id, garage_id, pass_id, vehicle_identity, "
            "effective_day) VALUES (%s, %s, %s, 'CAR-1', '2026-01-01')",
            (tenant_id, garage_uuid, pass_uuid),
        )
    return pass_uuid


def _window(owner, tenant_id, pass_uuid, days, start, end):
    with owner.cursor() as cursor:
        cursor.execute(
            "INSERT INTO pass_windows (tenant_id, pass_id, days, start_minute, end_minute, "
            "position) VALUES (%s, %s, %s, %s, %s, 0)",
            (tenant_id, pass_uuid, days, start, end),
        )


RAW_ROWS = {
    "lanes stated, no lane rows": (dict(lanes_stated=True), None,
                                   f.REFUSAL_LANES_STATED_BUT_EMPTY, "allowed_lanes"),
    "per-window allowance, no windows": (dict(allowance_count=2, allowance_per="window"), None,
                                         f.REFUSAL_ALLOWANCE_PER_WINDOW_WITHOUT_WINDOWS,
                                         "visit_allowance.per"),
    "weekend window on a Mon-Tue pass": (dict(valid_from=date(2026, 6, 1),
                                              valid_to=date(2026, 6, 2)),
                                         ([6, 7], 0, 1440),
                                         f.REFUSAL_WINDOW_NEVER_OCCURS, "windows[0].days"),
}


@pytest.mark.guarantee("G17")
@store_test
@pytest.mark.parametrize("name", list(RAW_ROWS))
def test_a_raw_row_no_check_can_reach_loads_unreadable_and_the_exit_is_answered(
    app, owner, tenant_id, name
):
    columns, window, code, field = RAW_ROWS[name]
    seed(app, tenant_id, GARAGE, ())
    pass_uuid = _raw_pass(owner, app, tenant_id, **columns)
    if window:
        _window(owner, tenant_id, pass_uuid, *window)
    exit_ = answered(access_from_store, app, tenant_id, GARAGE.id, "CAR-1", "L1", Direction.EXIT,
                              NOON_MONDAY)
    assert exit_.outcome is Outcome.NOT_COVERED and exit_.reason == f.PASS_UNREADABLE, exit_
    assert exit_.pass_id == "raw" and code in exit_.detail and field in exit_.detail
    entry = answered(access_from_store, app, tenant_id, GARAGE.id, "CAR-1", "L1", Direction.ENTRY,
                              NOON_MONDAY)
    assert entry.outcome is Outcome.REFUSED_TO_ANSWER and entry.missing == f.UNREADABLE_TERMS
    assert code in entry.detail


@pytest.mark.guarantee("G17")
@store_test
def test_the_email_check_is_now_the_schemas_own_and_a_bare_at_sign_cannot_be_stored(
    app, owner, tenant_id
):
    """The single-table contradiction the first cut's CHECK let through: 'a@'
    passed `position('@') > 1` and raised at load. Now refused where written."""
    import psycopg

    seed(app, tenant_id, GARAGE, ())
    with pytest.raises(psycopg.errors.CheckViolation):
        _raw_pass(owner, app, tenant_id, holder_email="a@")
    owner.rollback() if not owner.autocommit else None


@pytest.mark.guarantee("G17")
@store_test
def test_a_validator_tightened_after_a_pass_was_stored_strands_it_into_a_stated_answer(
    app, tenant_id, monkeypatch
):
    """THE RULE THIS GUARANTEE EARNS. A pass stored with an 8-hour maximum;
    then the validator is tightened to refuse anything over an hour. The pass
    is stranded -- and the exit still answers, naming the pass and the field."""
    from garage_pass import terms as terms_module

    pass_ = a_pass(terms=simple_terms(max_stay=timedelta(hours=8)))
    seed(app, tenant_id, GARAGE, (pass_,))
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, GARAGE.id, pass_.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    before = answered(access_from_store, app, tenant_id, GARAGE.id, "CAR-1", "L1", Direction.EXIT,
                               NOON_MONDAY)
    assert before.outcome is Outcome.COVERED, "the premise: readable before the tightening"

    original = terms_module.check_terms

    def tightened(terms):
        original(terms)
        if terms.max_stay is not None and terms.max_stay > timedelta(hours=1):
            raise f.Refused(f.REFUSAL_MAX_STAY_NOT_POSITIVE, "max_stay",
                            f"TIGHTENED: max_stay {terms.max_stay} is over an hour.")

    monkeypatch.setattr(terms_module, "check_terms", tightened)
    exit_ = answered(access_from_store, app, tenant_id, GARAGE.id, "CAR-1", "L1", Direction.EXIT,
                              NOON_MONDAY)
    assert exit_.outcome is Outcome.NOT_COVERED and exit_.reason == f.PASS_UNREADABLE, exit_
    assert exit_.pass_id == "pass-1" and "max_stay" in exit_.detail and "TIGHTENED" in exit_.detail
    assert exit_.exit_note == f.EXIT_IS_NEVER_REFUSED
    entry = answered(access_from_store, app, tenant_id, GARAGE.id, "CAR-1", "L1", Direction.ENTRY,
                              NOON_MONDAY)
    assert entry.outcome is Outcome.REFUSED_TO_ANSWER and entry.missing == f.UNREADABLE_TERMS
    # nothing can be registered against a stranded pass, by the same name
    with pytest.raises(f.Refused) as refused:
        with tenant(app, tenant_id) as cursor:
            register_vehicle(cursor, tenant_id, GARAGE.id, pass_.id, "CAR-2", date(2026, 1, 1))
    app.rollback()
    assert refused.value.code == f.REFUSAL_MAX_STAY_NOT_POSITIVE
    assert "stored unreadable" in refused.value.detail


@pytest.mark.guarantee("G17")
@store_test
def test_a_stored_garage_with_an_unknown_timezone_answers_through_the_store(
    app, owner, tenant_id
):
    with owner.cursor() as cursor:
        cursor.execute(
            "INSERT INTO garages (tenant_id, external_id, timezone, transient_available) "
            "VALUES (%s, 'g-badtz', 'Mars/Olympus', true)",
            (tenant_id,),
        )
    exit_ = answered(access_from_store, app, tenant_id, "g-badtz", "CAR-1", "L1", Direction.EXIT,
                              NOON_MONDAY)
    assert exit_.outcome is Outcome.NOT_COVERED and exit_.reason == f.GARAGE_UNREADABLE
    entry = answered(access_from_store, app, tenant_id, "g-badtz", "CAR-1", "L1", Direction.ENTRY,
                              NOON_MONDAY)
    assert entry.outcome is Outcome.REFUSED_TO_ANSWER and entry.missing == f.MISSING_TIMEZONE
    # and writing one is refused where it is written
    with pytest.raises(UnknownTimezone):
        seed(app, tenant_id, Garage(id="g2", timezone="Mars/Olympus", transient_available=True))


@pytest.mark.guarantee("G17")
@store_test
def test_the_stranding_test_would_have_seen_an_exception(app, tenant_id, monkeypatch):
    """The control on the premise: with the tightening in place, building the
    Terms directly DOES raise -- so the stated answer above came from the load
    path catching it, not from the tightening failing to bite."""
    from garage_pass import terms as terms_module

    original = terms_module.check_terms

    def tightened(terms):
        original(terms)
        if terms.max_stay is not None:
            raise f.Refused(f.REFUSAL_MAX_STAY_NOT_POSITIVE, "max_stay", "TIGHTENED")

    monkeypatch.setattr(terms_module, "check_terms", tightened)
    with pytest.raises(f.Refused):
        simple_terms(max_stay=timedelta(hours=8))
    assert at(date(2026, 6, 1), 12) == NOON_MONDAY  # the fixture instant, unchanged


# ---------------------------------------------------------------------------
# writes against an unreadable garage, and the repair
# ---------------------------------------------------------------------------

from garage_pass.store import records  # noqa: E402

REPAIR = "set_garage_timezone"
WHO_WHEN_WHY = dict(by="operator", at=NOON_MONDAY, reason="stored from a laptop, fixed")


def writes_against_a_garage() -> list[str]:
    """Every public function in the store -- both its modules, ``records`` and
    ``enrolments`` -- whose third parameter is the garage's external id: the
    writes a garage takes, read from the signatures, not typed.
    ``load_garage``/``registrations_of`` take a uuid or are named differently,
    and are reads."""
    import inspect

    from garage_pass.store import enrolments

    found = []
    for module in (records, enrolments):
        for name, function in vars(module).items():
            if name.startswith("_") or not inspect.isfunction(function):
                continue
            if function.__module__ != module.__name__:
                continue  # imported from the other module: counted once, there
            parameters = list(inspect.signature(function).parameters)
            if len(parameters) >= 3 and parameters[2] == "garage_external_id":
                found.append(name)
    return sorted(found)


def _raw_bad_garage(owner, tenant_id, external_id="g-badtz"):
    with owner.cursor() as cursor:
        cursor.execute(
            "INSERT INTO garages (tenant_id, external_id, timezone, transient_available) "
            "VALUES (%s, %s, 'Mars/Olympus', true)",
            (tenant_id, external_id),
        )


@pytest.mark.guarantee("G17")
@store_test
def test_every_write_against_an_unreadable_garage_is_refused_by_name_and_the_repair_works(
    app, owner, tenant_id
):
    from garage_pass.store.records import change_state, end_registration, record_exit

    _raw_bad_garage(owner, tenant_id)
    pass_ = a_pass(garage_ids={"g-badtz"})
    calls = {
        "create_pass": lambda c: records.create_pass(c, tenant_id, "g-badtz", pass_, by="owner",
                                                     at=NOON_MONDAY),
        "register_vehicle": lambda c: register_vehicle(c, tenant_id, "g-badtz", pass_.id,
                                                       "CAR-1", date(2026, 1, 1)),
        "end_registration": lambda c: end_registration(c, tenant_id, "g-badtz", pass_.id,
                                                       "CAR-1", date(2026, 6, 1)),
        "change_state": lambda c: change_state(c, tenant_id, "g-badtz", pass_.id,
                                               State.SUSPENDED, by="owner", at=NOON_MONDAY,
                                               reason="hold"),
        "record_entry": lambda c: records.record_entry(c, tenant_id, "g-badtz", pass_.id,
                                                       "CAR-1", "L1", TWO_HOURS_BEFORE),
        "record_exit": lambda c: record_exit(c, tenant_id, "g-badtz", pass_.id, "CAR-1", "L1",
                                             NOON_MONDAY),
        # 0003: the second garage repair, and the credentials (their garage is
        # read through the pass, but each names the garage it is asked at)
        "set_garage_enrols_at": lambda c: records.set_garage_enrols_at(
            c, tenant_id, "g-badtz", "entry", **WHO_WHEN_WHY),
        "issue_enrolment": lambda c: enrolments.issue_enrolment(
            c, tenant_id, "g-badtz", pass_.id, "e-1", date(2026, 6, 1), 3, by="owner",
            at=NOON_MONDAY),
        "issue_holder_link": lambda c: enrolments.issue_holder_link(
            c, tenant_id, "g-badtz", pass_.id, "l-1", date(2026, 6, 1), 3, by="owner",
            at=NOON_MONDAY),
        "redeem_holder_link": lambda c: enrolments.redeem_holder_link(
            c, tenant_id, "g-badtz", "no-such-token", name="A", phone="1",
            enrolment_external_id="e-1", starts_on=date(2026, 6, 1), days_valid=3,
            at=NOON_MONDAY),
    }
    # the redemption is the one write that CARRIES its refusal instead of raising
    # it, because the lane must still be answered: exercised below on its own
    assert sorted([*calls, REPAIR, "redeem_enrolment"]) == writes_against_a_garage(), (
        "a write against a garage exists that this test does not exercise"
    )
    for name, call in calls.items():
        with pytest.raises(f.Refused) as refused:
            with tenant(app, tenant_id) as cursor:
                call(cursor)
        app.rollback()
        assert refused.value.code == f.REFUSAL_TIMEZONE_UNKNOWN, (name, refused.value)
        assert refused.value.field == "garage.timezone", name
        assert "'g-badtz' is stored unreadable" in refused.value.detail, name
        assert "Mars/Olympus" in refused.value.detail and "set-garage-timezone" in (
            refused.value.detail
        ), name
    for direction in Direction:
        with tenant(app, tenant_id) as cursor:
            redemption = enrolments.redeem_enrolment(
                cursor, tenant_id, "g-badtz", "no-such-token", "CAR-1", "L1", direction,
                NOON_MONDAY,
            )
        app.rollback()
        assert not redemption.redeemed and redemption.refusal is not None
        assert redemption.refusal.code == f.REFUSAL_TIMEZONE_UNKNOWN
        assert "'g-badtz' is stored unreadable" in redemption.refusal.detail
        assert "set-garage-timezone" in redemption.refusal.detail
        # and the movement is still answered -- at an exit, never refused
        if direction is Direction.EXIT:
            assert redemption.answer.outcome is Outcome.NOT_COVERED
            assert redemption.answer.reason == f.GARAGE_UNREADABLE
        else:
            assert redemption.answer.outcome is Outcome.REFUSED_TO_ANSWER
            assert redemption.answer.missing == f.MISSING_TIMEZONE
    assert query(app, tenant_id, "SELECT count(*) FROM passes") == [(0,)], "a write landed"
    assert query(app, tenant_id, "SELECT count(*) FROM enrolments") == [(0,)], "a write landed"
    # the exit still answers about it, as before
    exit_ = answered(access_from_store, app, tenant_id, "g-badtz", "CAR-1", "L1", Direction.EXIT,
                              NOON_MONDAY)
    assert exit_.reason == f.GARAGE_UNREADABLE
    # THE REPAIR: the one write an unreadable garage takes
    with tenant(app, tenant_id) as cursor:
        out = records.set_garage_timezone(cursor, tenant_id, "g-badtz", "America/Denver",
                                          **WHO_WHEN_WHY)
    app.commit()
    assert out == {"garage": "g-badtz", "timezone": "America/Denver", "was": "Mars/Olympus",
                   "was_readable": False, "changed_by": "operator", "changed_at": NOON_MONDAY,
                   "reason": "stored from a laptop, fixed"}
    with tenant(app, tenant_id) as cursor:
        records.create_pass(cursor, tenant_id, "g-badtz", pass_, by="owner", at=NOON_MONDAY)
        register_vehicle(cursor, tenant_id, "g-badtz", pass_.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    entry = answered(access_from_store, app, tenant_id, "g-badtz", "CAR-1", "L1", Direction.ENTRY,
                              NOON_MONDAY)
    assert entry.outcome is Outcome.COVERED, entry


@pytest.mark.guarantee("G17")
@store_test
def test_the_repair_refuses_a_zone_the_system_does_not_carry_and_changes_nothing(
    app, owner, tenant_id
):
    """The repair cannot store the defect it repairs: an unknown zone is
    refused by name, naming the value, and the row is untouched. A readable
    garage may be repaired too (a wrong-but-known zone is still wrong)."""
    _raw_bad_garage(owner, tenant_id)
    with pytest.raises(f.Refused) as refused:
        with tenant(app, tenant_id) as cursor:
            records.set_garage_timezone(cursor, tenant_id, "g-badtz", "Mars/Tharsis",
                                        **WHO_WHEN_WHY)
    app.rollback()
    assert refused.value.code == f.REFUSAL_TIMEZONE_UNKNOWN
    assert refused.value.field == "garage.timezone" and "Mars/Tharsis" in refused.value.detail
    assert query(app, tenant_id, "SELECT timezone FROM garages") == [("Mars/Olympus",)]
    with pytest.raises(f.Refused) as refused:
        with tenant(app, tenant_id) as cursor:
            records.set_garage_timezone(cursor, tenant_id, "g-nowhere", "America/Denver",
                                        **WHO_WHEN_WHY)
    app.rollback()
    assert refused.value.code == f.REFUSAL_GARAGE_NOT_FOUND
    seed(app, tenant_id, GARAGE, ())
    with tenant(app, tenant_id) as cursor:
        out = records.set_garage_timezone(cursor, tenant_id, GARAGE.id, "America/Phoenix",
                                          **WHO_WHEN_WHY)
    app.commit()
    assert out["was"] == "America/Denver" and out["was_readable"] is True
    assert query(app, tenant_id, "SELECT timezone FROM garages WHERE external_id = %s",
                 (GARAGE.id,)) == [("America/Phoenix",)]


# ---------------------------------------------------------------------------
# the zone check is case-exact and platform-independent; no tz database is
# named as that, never as an unknown zone
# ---------------------------------------------------------------------------

from garage_pass import localday  # noqa: E402


@pytest.mark.guarantee("G17")
@pytest.mark.parametrize("spelling", ["america/denver", "AMERICA/DENVER", "America/denver",
                                      "utc", "europe/istanbul"])
def test_a_case_folded_zone_name_is_refused_by_name_and_the_exact_one_accepted(spelling):
    """Measured before this on a Mac (case-insensitive APFS): ``zone()``
    validated by opening the tz FILE, so every spelling here was ACCEPTED and
    stored as typed -- and a case-sensitive server refused the stored row. The
    check is now membership in ``zoneinfo.available_timezones()``, a listing
    of names, which gives the same answer on either filesystem."""
    exact = {"america/denver": "America/Denver", "AMERICA/DENVER": "America/Denver",
             "America/denver": "America/Denver", "utc": "UTC",
             "europe/istanbul": "Europe/Istanbul"}[spelling]
    with pytest.raises(UnknownTimezone) as refused:
        localday.zone(spelling)
    assert refused.value.code == f.REFUSAL_TIMEZONE_UNKNOWN
    assert repr(spelling) in refused.value.detail
    assert str(localday.zone(exact)) == exact  # the control, in the same run
    with pytest.raises(UnknownTimezone):
        Garage(id="g", timezone=spelling, transient_available=True)


@pytest.mark.guarantee("G17")
def test_the_zone_check_does_not_consult_the_filesystem_so_it_cannot_vary_with_it(monkeypatch):
    """THE PROPERTY, measured directly rather than on two machines: with
    ``ZoneInfo`` replaced by one that opens ANY name -- what a case-insensitive
    filesystem does for a folded name -- the folded spelling is still refused
    and the exact one still accepted. The refusal comes from the name set, so
    the filesystem's case rule cannot change it."""
    from zoneinfo import ZoneInfo

    opened: list[str] = []

    class OpensAnything:
        def __init__(self, name):
            opened.append(name)
            self.key = "America/Denver"

    monkeypatch.setattr(localday, "ZoneInfo", OpensAnything)
    with pytest.raises(UnknownTimezone):
        localday.zone("america/denver")
    assert opened == [], "the folded name reached the file open; the check is the filesystem's"
    assert localday.zone("America/Denver").key == "America/Denver"
    assert opened == ["America/Denver"]
    monkeypatch.undo()
    assert isinstance(localday.zone("America/Denver"), ZoneInfo)


@pytest.mark.guarantee("G17")
def test_a_machine_with_no_tz_database_is_named_as_that_never_as_an_unknown_zone(monkeypatch):
    """An empty ``available_timezones()`` is the MACHINE's condition, not the
    value's. A validator that asked only "is the name in the set" would refuse
    ``America/Denver`` as unknown on a bare server -- blaming a good input for
    missing data, and worse than the bug it fixed. Distinct error, by name;
    the same name on a machine that has the database is the control."""
    from garage_pass.localday import TimezoneDatabaseUnavailable

    def what_is_raised(call, *args, **kwargs):
        """The class is the subject, so a different class is an ASSERTION
        failure and not an exception the runner cannot read."""
        try:
            call(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 -- judged below
            return exc
        pytest.fail("nothing was raised on a machine with no tz database")

    assert localday.zone("America/Denver")  # the control: the database is here
    monkeypatch.setattr(localday, "_tz_names", lambda: frozenset())
    raised = what_is_raised(localday.zone, "America/Denver")
    assert isinstance(raised, TimezoneDatabaseUnavailable), f"blamed the value: {raised!r}"
    assert not isinstance(raised, f.Refused), "it is not a refusal of the value"
    assert "no timezone database" in str(raised) and "tzdata" in str(raised)
    raised = what_is_raised(Garage, id="g", timezone="America/Denver", transient_available=True)
    assert isinstance(raised, TimezoneDatabaseUnavailable), f"blamed the value: {raised!r}"
    # and it does NOT hide behind the unreadable shape: the store's load path
    # carries an UNKNOWN zone as unreadable, a missing DATABASE is raised
    raised = what_is_raised(garage_from_stored, "g", "America/Denver", True)
    assert isinstance(raised, TimezoneDatabaseUnavailable), f"blamed the value: {raised!r}"


@pytest.mark.guarantee("G17")
def test_the_name_set_is_the_tz_databases_own_and_carries_the_exact_spellings():
    """The instrument's premise: the set this process reads is non-empty and
    spells the names the way the database does."""
    names = localday._tz_names()
    assert len(names) > 100 and "America/Denver" in names and "UTC" in names
    assert "america/denver" not in names and "utc" not in names
