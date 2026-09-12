"""G1 -- one car, one pass per garage. His ruling: "one car pass".

The store refuses a second registration BY NAME before the database's EXCLUDE
has to, naming the pass that holds the identity and the day that registration
ends; a refusal writes nothing; the constraint is proven to be there by
bypassing the module with a raw insert as the application role.

**ENDING AND RE-REGISTERING ON THE SAME DAY HAS ONE ANSWER, AND THIS FILE
STATES IT:** a registration ended on day D covers the vehicle up to and NOT
including D, and the identity is free FROM D -- a registration elsewhere
effective D is accepted. Half-open, like every day range in this project.

**THE TARGET PASS'S STATE IS READ.** A registration onto a suspended, revoked
or expired pass is refused BY NAME, naming the state; draft, awaiting
enrolment and active take registrations (enrolment depends on the first two).
Measured before this: the command line registered a car onto a REVOKED pass,
the overlap check skipped holders on revoked passes, and the same car
registered onto a live pass met the EXCLUDE with race advice where there was
no race. No test in this file had registered onto a revoked pass; that
absence is why four review layers missed it, and the tests below are that
path. The constraint's race wording is now reachable only in a genuine race
(the raced test at the end) or by a raw write past the module.

Controls: the module's refusal planted away (the second pass takes the
vehicle -- and then the EXCLUDE fires as a raw constraint, which is the
traceback-not-refusal defect); the overlap query planted to look only at
open-ended registrations; the holder-skip on revoked passes planted back (a
registration a raw write left open on a revoked pass is invisible, and the
live pass meets the constraint instead of the name); the target-state check
planted away (a car is registered onto a revoked pass again); the deadlock
catch planted away (the race's other shape is a traceback again); the EXCLUDE
removed from the migration (the raw insert is accepted).
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from fixtures import NOON_MONDAY, a_pass, at, simple_terms, transient_garage
from garage_pass import findings as f
from garage_pass.access import Outcome
from garage_pass.passes import State
from garage_pass.store.access import access_from_store
from garage_pass.store.postgres import set_tenant, tenant
from garage_pass.store.records import (
    ENDED_BY_EXPIRY,
    ENDED_BY_OWNER,
    ONE_PASS_PER_GARAGE,
    end_registration,
    register_vehicle,
)
from garage_pass.terms import Direction
from store_harness import needs_postgres, query, seed

pytestmark = needs_postgres

GARAGE = transient_garage()
A = a_pass(id="pass-a", label="Employee A")
Z = a_pass(id="pass-z", label="Vendor Z")
JAN_1 = date(2026, 1, 1)


def register(app, tenant_id, pass_, identity="CAR-1", effective=JAN_1, end=None):
    with tenant(app, tenant_id) as cursor:
        out = register_vehicle(cursor, tenant_id, GARAGE.id, pass_.id, identity, effective, end)
    app.commit()
    return out


def registrations(app, tenant_id):
    return query(
        app, tenant_id,
        "SELECT p.external_id, r.vehicle_identity, r.effective_day, r.end_day, r.ended_reason "
        "FROM vehicle_registrations r JOIN passes p ON p.id = r.pass_id ORDER BY 1, 3",
    )


@pytest.mark.guarantee("G1")
def test_a_second_pass_is_refused_by_name_naming_the_holder_and_that_it_has_no_end_day(
    app, tenant_id
):
    seed(app, tenant_id, GARAGE, (A, Z))
    register(app, tenant_id, A)
    with pytest.raises(f.Refused) as refused:
        register(app, tenant_id, Z)
    app.rollback()
    assert refused.value.code == f.REFUSAL_VEHICLE_ON_ANOTHER_PASS
    assert refused.value.field == "vehicle_identity"
    assert "'pass-a'" in refused.value.detail and "Employee A" in refused.value.detail
    assert "has no end day" in refused.value.detail
    assert registrations(app, tenant_id) == [("pass-a", "CAR-1", JAN_1, None, None)], (
        "the refused registration was written anyway"
    )


@pytest.mark.guarantee("G1")
def test_the_refusal_names_the_day_the_holding_registration_ends(app, tenant_id):
    seed(app, tenant_id, GARAGE, (A, Z))
    register(app, tenant_id, A, end=date(2026, 7, 1))
    with pytest.raises(f.Refused) as refused:
        register(app, tenant_id, Z)
    app.rollback()
    assert "ends on 2026-07-01" in refused.value.detail


@pytest.mark.guarantee("G1")
def test_the_refusal_names_the_passs_valid_to_when_the_registration_runs_to_it(app, tenant_id):
    bounded = a_pass(id="pass-b", terms=simple_terms(valid_from=JAN_1, valid_to=date(2026, 3, 31)))
    seed(app, tenant_id, GARAGE, (bounded, Z))
    register(app, tenant_id, bounded)
    with pytest.raises(f.Refused) as refused:
        register(app, tenant_id, Z, effective=date(2026, 2, 1))
    app.rollback()
    assert "valid_to 2026-03-31, so ends on 2026-04-01" in refused.value.detail


@pytest.mark.guarantee("G1")
def test_a_refusal_writes_nothing_even_inside_a_transaction_that_then_commits(app, tenant_id):
    """The order matters: the check runs before any row changes, so a caller
    that catches the refusal and commits has committed nothing of it."""
    seed(app, tenant_id, GARAGE, (A, Z))
    register(app, tenant_id, A)
    with tenant(app, tenant_id) as cursor:
        with pytest.raises(f.Refused):
            register_vehicle(cursor, tenant_id, GARAGE.id, Z.id, "CAR-1", JAN_1, None)
        cursor.execute("SELECT count(*) FROM vehicle_registrations")
        (count,) = cursor.fetchone()
    app.commit()
    assert count == 1
    assert registrations(app, tenant_id) == [("pass-a", "CAR-1", JAN_1, None, None)]


@pytest.mark.guarantee("G1")
def test_ending_on_day_d_frees_the_identity_from_d_and_the_old_pass_covers_up_to_d(
    app, tenant_id
):
    """THE STATED ANSWER for the same-day question."""
    seed(app, tenant_id, GARAGE, (A, Z))
    register(app, tenant_id, A)
    d = date(2026, 6, 1)  # NOON_MONDAY's day
    with tenant(app, tenant_id) as cursor:
        end_registration(cursor, tenant_id, GARAGE.id, A.id, "CAR-1", d)
    app.commit()
    register(app, tenant_id, Z, effective=d)
    assert registrations(app, tenant_id) == [
        ("pass-a", "CAR-1", JAN_1, d, ENDED_BY_OWNER),
        ("pass-z", "CAR-1", d, None, None),
    ]
    day_before = at(date(2026, 5, 31), 23, 30)
    before = access_from_store(app, tenant_id, GARAGE.id, "CAR-1", "L1", Direction.ENTRY,
                               day_before)
    assert before.outcome is Outcome.COVERED and before.pass_id == "pass-a"
    on_d = access_from_store(app, tenant_id, GARAGE.id, "CAR-1", "L1", Direction.ENTRY,
                             NOON_MONDAY)
    assert on_d.outcome is Outcome.COVERED and on_d.pass_id == "pass-z"


@pytest.mark.guarantee("G1")
def test_a_registration_on_an_expired_pass_is_released_to_the_next_pass(app, tenant_id):
    """Expiry is derived, so nobody ends the registration; the next
    registration attempt that meets it ends it on the day after valid_to."""
    bounded = a_pass(id="pass-b", terms=simple_terms(valid_from=JAN_1, valid_to=date(2026, 3, 31)))
    seed(app, tenant_id, GARAGE, (bounded, Z))
    register(app, tenant_id, bounded)
    register(app, tenant_id, Z, effective=date(2026, 4, 1))
    assert registrations(app, tenant_id) == [
        ("pass-b", "CAR-1", JAN_1, date(2026, 4, 1), ENDED_BY_EXPIRY),
        ("pass-z", "CAR-1", date(2026, 4, 1), None, None),
    ]


@pytest.mark.guarantee("G1")
def test_the_same_pass_twice_is_refused_naming_itself(app, tenant_id):
    seed(app, tenant_id, GARAGE, (A,))
    register(app, tenant_id, A)
    with pytest.raises(f.Refused) as refused:
        register(app, tenant_id, A, effective=date(2026, 2, 1))
    app.rollback()
    assert refused.value.code == f.REFUSAL_VEHICLE_ON_ANOTHER_PASS
    assert "'pass-a'" in refused.value.detail


@pytest.mark.guarantee("G1")
def test_a_pass_may_carry_many_vehicles(app, tenant_id):
    seed(app, tenant_id, GARAGE, (A,))
    for identity in ("CAR-1", "CAR-2", "CAR-3"):
        register(app, tenant_id, A, identity)
    assert [r[1] for r in registrations(app, tenant_id)] == ["CAR-1", "CAR-2", "CAR-3"]


@pytest.mark.guarantee("G1")
def test_a_raw_insert_as_the_application_role_hits_the_exclusion_backstop(app, tenant_id):
    garage_uuid = seed(app, tenant_id, GARAGE, (A, Z))
    register(app, tenant_id, A)
    (z_uuid,) = query(app, tenant_id, "SELECT id FROM passes WHERE external_id = 'pass-z'")[0]
    with pytest.raises(psycopg.errors.ExclusionViolation) as violation:
        with tenant(app, tenant_id) as cursor:
            cursor.execute(
                "INSERT INTO vehicle_registrations (tenant_id, garage_id, pass_id, "
                "vehicle_identity, effective_day) VALUES (%s, %s, %s, 'CAR-1', '2026-03-01')",
                (tenant_id, garage_uuid, z_uuid),
            )
    app.rollback()
    assert violation.value.diag.constraint_name == ONE_PASS_PER_GARAGE


@pytest.mark.guarantee("G1")
def test_the_constraint_is_reported_as_a_refusal_when_a_race_beats_the_check(app, tenant_id):
    """Two writers: the second's check ran before the first committed. The
    EXCLUDE then fires at the second's INSERT, and the module names it."""
    from store_harness import DSN, app_connection

    seed(app, tenant_id, GARAGE, (A, Z))
    other = app_connection(DSN)
    try:
        with tenant(other, tenant_id) as cursor:
            register_vehicle(cursor, tenant_id, GARAGE.id, A.id, "CAR-1", JAN_1, None)
            # not committed yet: the check on `app` sees nothing to refuse
        with tenant(app, tenant_id) as cursor:
            cursor.execute("SELECT count(*) FROM vehicle_registrations")
            assert cursor.fetchone() == (0,)
        other.commit()
        with pytest.raises(f.Refused) as refused:
            with tenant(app, tenant_id) as cursor:
                register_vehicle(cursor, tenant_id, GARAGE.id, Z.id, "CAR-1", JAN_1, None)
        app.rollback()
        assert refused.value.code == f.REFUSAL_VEHICLE_ON_ANOTHER_PASS, (
            "with the other side committed, the ordinary check sees it; this asserts the "
            "test's own premise before the raced variant below"
        )
    finally:
        other.close()


@pytest.mark.guarantee("G1")
def test_a_race_that_beats_the_check_is_named_by_constraint_not_a_traceback(app, tenant_id):
    """THE ONE PATH TO THE CONSTRAINT'S RACE WORDING THROUGH THE MODULE. With
    the target pass's state read and every open registration a holder, the
    "another registration landed first, roll back and read again" refusal is
    reachable only when two writers genuinely race -- made deterministic here
    with a pinned snapshot -- or by a raw write past the module (the test
    after the state tests below). Before this round it was also reached with
    no race at all, through a registration the module had accepted onto a
    revoked pass."""
    from store_harness import DSN, app_connection

    seed(app, tenant_id, GARAGE, (A, Z))
    other = app_connection(DSN)
    try:
        with app.cursor() as cursor:
            # REPEATABLE READ pins app's snapshot before the other side commits,
            # so the module's check cannot see the row and the INSERT meets it
            # at the constraint -- the race, made deterministic. Set before the
            # tenant context, which is itself a query.
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            set_tenant(cursor, tenant_id)
            cursor.execute("SELECT count(*) FROM vehicle_registrations")
            assert cursor.fetchone() == (0,)
            with tenant(other, tenant_id) as theirs:
                register_vehicle(theirs, tenant_id, GARAGE.id, A.id, "CAR-1", JAN_1, None)
            other.commit()
            with pytest.raises(f.Refused) as refused:
                register_vehicle(cursor, tenant_id, GARAGE.id, Z.id, "CAR-1", JAN_1, None)
        app.rollback()
    finally:
        other.close()
    assert refused.value.code == f.REFUSAL_CONSTRAINT
    assert ONE_PASS_PER_GARAGE in refused.value.detail


@pytest.mark.guarantee("G1")
@pytest.mark.parametrize(
    "what,effective,end,code",
    [
        ("ends before it starts", date(2026, 2, 1), date(2026, 2, 1),
         f.REFUSAL_REGISTRATION_ENDS_BEFORE_IT_STARTS),
        ("outlives the pass", date(2026, 2, 1), date(2026, 5, 1),
         f.REFUSAL_REGISTRATION_OUTLIVES_THE_PASS),
    ],
)
def test_a_registration_that_cannot_cover_a_day_is_refused(app, tenant_id, what, effective,
                                                           end, code):
    bounded = a_pass(id="pass-b", terms=simple_terms(valid_from=JAN_1, valid_to=date(2026, 3, 31)))
    seed(app, tenant_id, GARAGE, (bounded,))
    with pytest.raises(f.Refused) as refused:
        register(app, tenant_id, bounded, effective=effective, end=end)
    app.rollback()
    assert refused.value.code == code, what
    assert refused.value.field == "end_day"


@pytest.mark.guarantee("G1")
def test_ending_twice_or_ending_nothing_is_refused(app, tenant_id):
    seed(app, tenant_id, GARAGE, (A,))
    with pytest.raises(f.Refused) as refused:
        with tenant(app, tenant_id) as cursor:
            end_registration(cursor, tenant_id, GARAGE.id, A.id, "CAR-1", date(2026, 6, 1))
    app.rollback()
    assert refused.value.code == f.REFUSAL_REGISTRATION_NOT_FOUND
    register(app, tenant_id, A)
    with tenant(app, tenant_id) as cursor:
        end_registration(cursor, tenant_id, GARAGE.id, A.id, "CAR-1", date(2026, 6, 1))
    app.commit()
    with pytest.raises(f.Refused) as refused:
        with tenant(app, tenant_id) as cursor:
            end_registration(cursor, tenant_id, GARAGE.id, A.id, "CAR-1", date(2026, 7, 1))
    app.rollback()
    assert refused.value.code == f.REFUSAL_REGISTRATION_ALREADY_ENDED


@pytest.mark.guarantee("G1")
def test_a_revoked_pass_does_not_hold_its_vehicle(app, tenant_id):
    """Revocation ends the registration (G5, store half in G12's module); the
    next pass takes the vehicle from the revocation day."""
    from garage_pass.store.records import change_state

    seed(app, tenant_id, GARAGE, (A, Z))
    register(app, tenant_id, A)
    with tenant(app, tenant_id) as cursor:
        change_state(cursor, tenant_id, GARAGE.id, A.id, State.REVOKED, by="owner",
                     at=NOON_MONDAY, reason="left the company")
    app.commit()
    register(app, tenant_id, Z, effective=date(2026, 6, 1))
    assert [r[0] for r in registrations(app, tenant_id)] == ["pass-a", "pass-z"]


@pytest.mark.guarantee("G1")
def test_the_other_shape_of_the_race_a_deadlock_is_named_as_the_constraint_not_a_traceback(
    app, owner, tenant_id
):
    """Two writers each hold an uncommitted registration and each then
    registers the OTHER's identity: each INSERT waits on the other's
    in-progress row at the EXCLUDE and the database rolls one back with
    DeadlockDetected. Measured on the L3's 120-round race probe as 1-3 in 120
    on one cluster (0 in 120 on two others) -- and it reached the caller as a
    traceback. The loser is refused by the constraint's name, with the same
    advice; the winner's registration lands."""
    import threading
    import time

    from store_harness import DSN, app_connection

    seed(app, tenant_id, GARAGE, (A, Z))
    other = app_connection(DSN)
    outcome: dict = {}

    def theirs():
        try:
            with tenant(other, tenant_id) as cursor:
                register_vehicle(cursor, tenant_id, GARAGE.id, Z.id, "CAR-1", JAN_1, None)
            outcome["other"] = "accepted"
        except BaseException as exc:  # noqa: BLE001 -- recorded, judged below
            outcome["other"] = exc
            other.rollback()

    def blocked_inserts() -> int:
        with owner.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' "
                "AND query ILIKE 'INSERT INTO vehicle_registrations%%'"
            )
            return cursor.fetchone()[0]

    thread = threading.Thread(target=theirs)
    try:
        with tenant(other, tenant_id) as cursor:  # other holds CAR-9, uncommitted
            register_vehicle(cursor, tenant_id, GARAGE.id, Z.id, "CAR-9", JAN_1, None)
        with tenant(app, tenant_id) as cursor:  # app holds CAR-1, uncommitted
            register_vehicle(cursor, tenant_id, GARAGE.id, A.id, "CAR-1", JAN_1, None)
            thread.start()  # other now waits on app's CAR-1
            deadline = time.monotonic() + 10
            while blocked_inserts() == 0 and time.monotonic() < deadline:
                time.sleep(0.02)
            assert blocked_inserts() == 1, "the premise: the other writer is waiting on ours"
            try:  # and ours now waits on theirs: the deadlock
                register_vehicle(cursor, tenant_id, GARAGE.id, A.id, "CAR-9", JAN_1, None)
                outcome["app"] = "accepted"
            except BaseException as exc:  # noqa: BLE001
                outcome["app"] = exc
        app.rollback()
        thread.join(timeout=15)
        assert not thread.is_alive(), "the other writer never came back"
    finally:
        other.close()
    losers = [side for side, result in outcome.items() if result != "accepted"]
    assert len(losers) == 1, f"exactly one side is rolled back: {outcome}"
    loser = outcome[losers[0]]
    assert isinstance(loser, f.Refused), (
        f"the rolled-back writer got a traceback, not a refusal: {loser!r}"
    )
    assert loser.code == f.REFUSAL_CONSTRAINT and ONE_PASS_PER_GARAGE in loser.detail
    assert "deadlock" in loser.detail and "Roll back and read again" in loser.detail
    assert "waits for" in loser.detail, "PostgreSQL's DETAIL, the account of the cycle, is carried"


@pytest.mark.guarantee("G1")
def test_a_deadlock_from_a_lock_the_module_never_takes_names_no_cause_and_carries_the_detail(
    app, owner, tenant_id
):
    """THE DEADLOCK SHAPE THAT IS NOT A RACE. The module issues no FOR UPDATE,
    FOR SHARE or LOCK (measured); another transaction takes a raw
    ``SELECT ... FOR UPDATE`` on the target pass's row, then waits on a row
    THIS transaction holds; this transaction's INSERT then waits on that raw
    lock through the pass foreign key (KEY SHARE against FOR UPDATE). No second
    registration of the identity exists anywhere. Measured before this: the
    caller was told "two registrations of 'CAR-1' raced" -- a cause that did
    not happen -- and PostgreSQL's DETAIL was dropped. Now the refusal says
    only that the database rolled this write back, carries the DETAIL, and is
    still a named refusal rather than a traceback.

    THE VICTIM IS MADE DETERMINISTIC: PostgreSQL's deadlock check runs once in
    each waiter, ``deadlock_timeout`` after it starts waiting, and the waiter
    whose check FINDS the cycle is the one rolled back. The raw transaction
    waits first and its check runs before the cycle exists; the module's
    INSERT waits last, its check finds the cycle, and it is the victim."""
    import time

    from garage_pass.store.postgres import connect
    from garage_pass.store.records import change_state
    from store_harness import DSN

    seed(app, tenant_id, GARAGE, (A, Z))
    with owner.cursor() as cursor:
        cursor.execute("SHOW deadlock_timeout")
        (timeout,) = cursor.fetchone()
    assert timeout == "1s", f"the timing below assumes the default deadlock_timeout, not {timeout}"
    ids = dict(query(app, tenant_id, "SELECT external_id, id FROM passes"))
    raw = connect(DSN)  # the owner: a raw transaction past the module, as the walk's was
    try:
        with tenant(app, tenant_id) as cursor:
            # ours holds a row lock on Z (an ordinary write of this module)
            change_state(cursor, tenant_id, GARAGE.id, Z.id, State.SUSPENDED, by="owner",
                         at=NOON_MONDAY, reason="hold")
        with raw.cursor() as cursor:
            # theirs: the lock this module never takes, on the pass we will register onto
            cursor.execute("SELECT id FROM passes WHERE id = %s FOR UPDATE", (ids["pass-a"],))
            assert cursor.fetchone() is not None
        # theirs now waits on ours (Z's row), in a thread so this test keeps the clock
        import threading

        theirs: dict = {}

        def wait_on_ours():
            try:
                with raw.cursor() as cursor:
                    cursor.execute("SELECT id FROM passes WHERE id = %s FOR UPDATE",
                                   (ids["pass-z"],))
                theirs["result"] = "acquired"
            except BaseException as exc:  # noqa: BLE001 -- recorded, judged below
                theirs["result"] = exc

        thread = threading.Thread(target=wait_on_ours)
        thread.start()

        def raw_is_waiting() -> bool:
            with owner.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' "
                    "AND query ILIKE 'SELECT id FROM passes%%FOR UPDATE'"
                )
                return cursor.fetchone()[0] == 1

        deadline = time.monotonic() + 10
        while not raw_is_waiting() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert raw_is_waiting(), "the premise: the raw transaction is waiting on ours"
        time.sleep(1.5)  # past its deadlock_timeout: its one check has run and found no cycle
        assert raw_is_waiting(), "it is still waiting; the cycle does not exist yet"
        try:  # ours: the INSERT waits on the raw lock, and is the victim
            with tenant(app, tenant_id) as cursor:
                register_vehicle(cursor, tenant_id, GARAGE.id, A.id, "CAR-1", JAN_1, None)
            ours: object = "accepted"
        except BaseException as exc:  # noqa: BLE001 -- recorded, judged below
            ours = exc
        app.rollback()
        thread.join(timeout=15)
        assert theirs.get("result") == "acquired", f"the raw side was the victim: {theirs}"
        raw.rollback()
    finally:
        raw.close()
    assert isinstance(ours, f.Refused), (
        f"the rolled-back writer got a traceback, not a refusal: {ours!r}"
    )
    detail = ours.detail
    assert ours.code == f.REFUSAL_CONSTRAINT and ONE_PASS_PER_GARAGE in detail
    assert "deadlock" in detail and "Roll back and read again" in detail
    assert "raced" not in detail, f"a cause the module did not observe was asserted: {detail}"
    assert "waits for" in detail and "blocked by process" in detail, (
        f"PostgreSQL's DETAIL is not carried: {detail}"
    )
    assert query(app, tenant_id, "SELECT count(*) FROM vehicle_registrations") == [(0,)], (
        "the premise: no registration of CAR-1 existed anywhere, so 'raced' would have been false"
    )


# ---------------------------------------------------------------------------
# The target pass's state. No test above registered onto a revoked pass, and
# that absence is how a registration onto one shipped and reached the gate.
# ---------------------------------------------------------------------------


def _revoke(app, tenant_id, pass_):
    from garage_pass.store.records import change_state

    with tenant(app, tenant_id) as cursor:
        change_state(cursor, tenant_id, GARAGE.id, pass_.id, State.REVOKED, by="owner",
                     at=NOON_MONDAY, reason="they got divorced")
    app.commit()


def _suspend(app, tenant_id, pass_):
    from garage_pass.store.records import change_state

    with tenant(app, tenant_id) as cursor:
        change_state(cursor, tenant_id, GARAGE.id, pass_.id, State.SUSPENDED, by="owner",
                     at=NOON_MONDAY, reason="a hold")
    app.commit()


@pytest.mark.guarantee("G1")
@pytest.mark.parametrize("state", ["revoked", "suspended", "expired"])
def test_a_registration_onto_a_pass_that_is_not_registrable_is_refused_naming_the_state(
    app, tenant_id, state
):
    """Refused BY NAME, naming the state -- and nothing is written. Expired is
    derived, as everywhere: valid_to before the registration's effective day."""
    if state == "expired":
        target = a_pass(id="pass-x", terms=simple_terms(valid_from=JAN_1,
                                                          valid_to=date(2026, 3, 31)))
        seed(app, tenant_id, GARAGE, (target,))
        effective = date(2026, 4, 1)
    else:
        target = A
        seed(app, tenant_id, GARAGE, (A,))
        (_revoke if state == "revoked" else _suspend)(app, tenant_id, A)
        effective = date(2026, 6, 2)
    with pytest.raises(f.Refused) as refused:
        register(app, tenant_id, target, "CAR-9", effective=effective)
    app.rollback()
    assert refused.value.code == f.REFUSAL_PASS_NOT_REGISTRABLE
    assert refused.value.field == "pass.state"
    assert f"'{target.id}' is {state}" in refused.value.detail, refused.value.detail
    assert [r for r in registrations(app, tenant_id) if r[1] == "CAR-9"] == [], (
        "the refused registration was written anyway"
    )


@pytest.mark.guarantee("G1")
@pytest.mark.parametrize("state", [State.DRAFT, State.AWAITING_ENROLMENT, State.ACTIVE],
                         ids=lambda s: s.value)
def test_a_draft_awaiting_or_active_pass_takes_a_registration(app, tenant_id, state):
    """The control on the refusal above, and what enrolment depends on: a
    registration onto a draft or an awaiting-enrolment pass keeps working."""
    target = a_pass(id="pass-s", state=state)
    seed(app, tenant_id, GARAGE, (target,))
    out = register(app, tenant_id, target, "CAR-9")
    assert out["pass"] == "pass-s" and out["vehicle_identity"] == "CAR-9"
    assert [r for r in registrations(app, tenant_id) if r[1] == "CAR-9"] == [
        ("pass-s", "CAR-9", JAN_1, None, None)
    ]


@pytest.mark.guarantee("G1")
def test_a_registration_a_raw_write_left_open_on_a_revoked_pass_is_named_not_met_at_the_constraint(
    app, owner, tenant_id
):
    """SEEDED BY A RAW WRITE, and that is the point. The module now refuses to
    register onto a revoked pass, so the only way this state exists is a row
    written past the module -- by a raw write, an older version, or a future
    bug -- and the by-name refusal must still fire against it, naming the
    survivor and its state, instead of the EXCLUDE firing with race advice
    where there is no race. Measured before the fix: REFUSAL_CONSTRAINT,
    "another registration of 'CAR-1' landed first. Roll back and read again."
    """
    garage_uuid = seed(app, tenant_id, GARAGE, (A, Z))
    _revoke(app, tenant_id, A)
    (a_uuid,) = query(app, tenant_id, "SELECT id FROM passes WHERE external_id = 'pass-a'")[0]
    with owner.cursor() as cursor:  # the owner is not bound by the module
        cursor.execute(
            "INSERT INTO vehicle_registrations (tenant_id, garage_id, pass_id, "
            "vehicle_identity, effective_day, end_day) VALUES (%s, %s, %s, 'CAR-1', %s, NULL)",
            (tenant_id, garage_uuid, a_uuid, date(2026, 6, 2)),
        )
    assert registrations(app, tenant_id) == [("pass-a", "CAR-1", date(2026, 6, 2), None, None)]
    with pytest.raises(f.Refused) as refused:
        register(app, tenant_id, Z, effective=date(2026, 6, 3))
    app.rollback()
    assert refused.value.code == f.REFUSAL_VEHICLE_ON_ANOTHER_PASS, refused.value.detail
    assert "'pass-a'" in refused.value.detail and "revoked" in refused.value.detail
    assert "has no end day" in refused.value.detail
    assert "Roll back and read again" not in refused.value.detail
    # the operator's undo, then the live pass takes the vehicle
    with tenant(app, tenant_id) as cursor:
        end_registration(cursor, tenant_id, GARAGE.id, A.id, "CAR-1", date(2026, 6, 3))
    app.commit()
    register(app, tenant_id, Z, effective=date(2026, 6, 3))
    assert [r[0] for r in registrations(app, tenant_id)] == ["pass-a", "pass-z"]
