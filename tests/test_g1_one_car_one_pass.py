"""G1 -- one car, one pass per garage. His ruling: "one car pass".

The store refuses a second registration BY NAME before the database's EXCLUDE
has to, naming the pass that holds the identity and the day that registration
ends; a refusal writes nothing; the constraint is proven to be there by
bypassing the module with a raw insert as the application role.

**ENDING AND RE-REGISTERING ON THE SAME DAY HAS ONE ANSWER, AND THIS FILE
STATES IT:** a registration ended on day D covers the vehicle up to and NOT
including D, and the identity is free FROM D -- a registration elsewhere
effective D is accepted. Half-open, like every day range in this project.

Controls: the module's refusal planted away (the second pass takes the
vehicle -- and then the EXCLUDE fires as a raw constraint, which is the
traceback-not-refusal defect); the overlap query planted to look only at
open-ended registrations; the EXCLUDE removed from the migration (the raw
insert is accepted).
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
