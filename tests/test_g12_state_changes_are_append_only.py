"""G12 -- every state change records who, when and why into an append-only
history; the transitions are the published ones; expired is derived.

And the store half of G5: revoking a pass ends its registrations on the
revocation day in the garage's local calendar.

**AND NO ROUTE AROUND THE GRANT.** The history cascades from ``passes`` and
``tenants``; a DELETE on either would erase it. The application role holds no
DELETE on any table whose deletion cascades into the history -- the set is read
from the catalogue and walked transitively, never typed -- and the module
issues no DELETE at all. Measured before the fix: ``DELETE FROM passes`` as the
application role took the history from one row to none.

Controls: the INSERT of the history row planted away; the grant on the
history widened to UPDATE in the migration; the who/why check planted away;
the revocation's registration update planted away; DELETE on ``passes`` granted
back to the application role.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from fixtures import NOON_MONDAY, a_pass, at, transient_garage
from garage_pass import findings as f
from garage_pass.passes import EXPIRED, State
from garage_pass.states import ALLOWED_TRANSITIONS, effective_state, parse_state, transition
from garage_pass.store.postgres import grants_on, tables_cascading_into, tenant
from garage_pass.store.records import ENDED_BY_REVOCATION, change_state, register_vehicle
from store_harness import query, seed, store_test

GARAGE = transient_garage()


def move(app, tenant_id, pass_, to, by="owner", reason="because", when=NOON_MONDAY):
    with tenant(app, tenant_id) as cursor:
        out = change_state(cursor, tenant_id, GARAGE.id, pass_.id, to, by=by, at=when,
                           reason=reason)
    app.commit()
    return out


def history(app, tenant_id):
    return query(
        app, tenant_id,
        "SELECT from_state, to_state, changed_by, changed_at, reason FROM pass_state_changes "
        "ORDER BY changed_at, created_at",
    )


# ---------------------------------------------------------------------------
# pure
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G12")
@pytest.mark.parametrize("frm", list(State), ids=[s.value for s in State])
@pytest.mark.parametrize("to", list(State), ids=[s.value for s in State])
def test_every_pair_is_either_allowed_or_refused_by_name(frm, to):
    pass_ = a_pass(state=frm)
    if to in ALLOWED_TRANSITIONS[frm]:
        moved, change = transition(pass_, to, by="owner", at=NOON_MONDAY, reason="r")
        assert moved.state is to and change.from_state is frm and change.to_state is to
    else:
        with pytest.raises(f.Refused) as refused:
            transition(pass_, to, by="owner", at=NOON_MONDAY, reason="r")
        expected = (
            f.REFUSAL_REVOKED_IS_TERMINAL if frm is State.REVOKED
            else f.REFUSAL_STATE_TRANSITION_NOT_ALLOWED
        )
        assert refused.value.code == expected


@pytest.mark.guarantee("G12")
def test_the_published_transitions_are_the_minimum_set_and_no_more():
    assert ALLOWED_TRANSITIONS == {
        State.DRAFT: {State.AWAITING_ENROLMENT, State.ACTIVE, State.REVOKED},
        State.AWAITING_ENROLMENT: {State.ACTIVE, State.REVOKED},
        State.ACTIVE: {State.SUSPENDED, State.REVOKED},
        State.SUSPENDED: {State.ACTIVE, State.REVOKED},
        State.REVOKED: set(),
    }


@pytest.mark.guarantee("G12")
@pytest.mark.parametrize("by,reason,field", [("", "r", "changed_by"), ("owner", " ", "reason")])
def test_a_change_without_who_or_why_is_refused_naming_which(by, reason, field):
    with pytest.raises(f.Refused) as refused:
        transition(a_pass(), State.SUSPENDED, by=by, at=NOON_MONDAY, reason=reason)
    assert refused.value.code == f.REFUSAL_STATE_CHANGE_NEEDS_WHO_AND_WHY
    assert refused.value.field == field


@pytest.mark.guarantee("G12")
def test_expired_is_derived_and_cannot_be_typed():
    from fixtures import simple_terms

    with pytest.raises(f.Refused) as refused:
        parse_state(EXPIRED)
    assert refused.value.code == f.REFUSAL_EXPIRED_IS_DERIVED
    past = simple_terms(valid_from=date(2025, 1, 1), valid_to=date(2025, 12, 31))
    assert effective_state(a_pass(terms=past), date(2026, 6, 1)) == EXPIRED
    assert effective_state(a_pass(terms=past, state=State.SUSPENDED), date(2026, 6, 1)) == EXPIRED
    assert effective_state(a_pass(terms=past, state=State.REVOKED), date(2026, 6, 1)) == "revoked"
    assert effective_state(a_pass(terms=past), date(2025, 12, 31)) == "active"


# ---------------------------------------------------------------------------
# the store
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G12")
@store_test
def test_every_change_lands_in_the_history_with_who_when_and_why(app, tenant_id):
    pass_ = a_pass(state=State.DRAFT)
    seed(app, tenant_id, GARAGE, (pass_,))
    move(app, tenant_id, pass_, State.ACTIVE, by="owner", reason="issued")
    move(app, tenant_id, pass_, State.SUSPENDED, by="manager", reason="unpaid",
         when=at(date(2026, 6, 2), 9))
    rows = history(app, tenant_id)
    assert [(r[0], r[1], r[2], r[4]) for r in rows] == [
        (None, "draft", "seed", "created"),
        ("draft", "active", "owner", "issued"),
        ("active", "suspended", "manager", "unpaid"),
    ]
    assert rows[2][3] == at(date(2026, 6, 2), 9)
    assert query(app, tenant_id, "SELECT state FROM passes") == [("suspended",)]


@pytest.mark.guarantee("G12")
@store_test
def test_the_history_is_append_only_by_grant_and_by_a_refused_update(app, tenant_id):
    assert grants_on(app, "pass_state_changes") == {"SELECT", "INSERT"}
    assert "UPDATE" in grants_on(app, "passes"), "the control: the same query sees UPDATE elsewhere"
    seed(app, tenant_id, GARAGE, (a_pass(),))
    for statement in ("UPDATE pass_state_changes SET reason = 'edited'",
                      "DELETE FROM pass_state_changes"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with tenant(app, tenant_id) as cursor:
                cursor.execute(statement)
        app.rollback()


@pytest.mark.guarantee("G12")
@store_test
def test_no_table_whose_deletion_cascades_into_the_history_grants_the_app_role_delete(
    app, tenant_id
):
    """Derived, not listed: every ancestor by ON DELETE CASCADE, transitively."""
    cascading = tables_cascading_into(app, "pass_state_changes")
    assert {"passes", "tenants"} <= cascading, (
        f"the walk did not find the two known parents; found {sorted(cascading)}"
    )
    assert "garages" not in cascading, "garages -> passes is RESTRICT; the walk over-reached"
    offenders = sorted(t for t in cascading if "DELETE" in grants_on(app, t))
    assert offenders == [], f"the application role can erase the history through {offenders}"
    # and it really cannot: the way the code would make the call, at its role
    seed(app, tenant_id, GARAGE, (a_pass(),))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant(app, tenant_id) as cursor:
            cursor.execute("DELETE FROM passes")
    app.rollback()
    assert query(app, tenant_id, "SELECT count(*) FROM pass_state_changes") == [(1,)]


@pytest.mark.guarantee("G12")
@store_test
def test_the_cascade_walk_can_see_a_new_parent(owner):
    """The control on the walk: a scratch table that passes cascade into is
    reported as an ancestor, transitively, then dropped."""
    with owner.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE _l3_root (id uuid PRIMARY KEY DEFAULT gen_random_uuid()); "
            "ALTER TABLE passes ADD COLUMN _l3_root_id uuid "
            "REFERENCES _l3_root(id) ON DELETE CASCADE"
        )
        try:
            assert "_l3_root" in tables_cascading_into(owner, "pass_state_changes")
        finally:
            cursor.execute("ALTER TABLE passes DROP COLUMN _l3_root_id; DROP TABLE _l3_root")
    assert "_l3_root" not in tables_cascading_into(owner, "pass_state_changes")


@pytest.mark.guarantee("G12")
@store_test
def test_a_refused_transition_writes_no_history(app, tenant_id):
    pass_ = a_pass(state=State.REVOKED)
    seed(app, tenant_id, GARAGE, (pass_,))
    with pytest.raises(f.Refused):
        move(app, tenant_id, pass_, State.ACTIVE)
    app.rollback()
    assert [r[1] for r in history(app, tenant_id)] == ["revoked"]


@pytest.mark.guarantee("G5")
@store_test
def test_revoking_ends_the_passs_registrations_on_the_revocation_day(app, tenant_id):
    """In the garage's local day: 23:30 Denver on June 1st is June 2nd in UTC,
    and the registration ends on June 1st. A registration that had not yet
    taken effect ends on its own effective day -- an empty range."""
    pass_ = a_pass()
    seed(app, tenant_id, GARAGE, (pass_,))
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, GARAGE.id, pass_.id, "CAR-1", date(2026, 1, 1))
        register_vehicle(cursor, tenant_id, GARAGE.id, pass_.id, "CAR-2", date(2026, 7, 1))
    app.commit()
    out = move(app, tenant_id, pass_, State.REVOKED, reason="divorced",
               when=at(date(2026, 6, 1), 23, 30))
    assert out["registrations_ended"] == 2
    assert query(
        app, tenant_id,
        "SELECT vehicle_identity, end_day, ended_reason FROM vehicle_registrations ORDER BY 1",
    ) == [
        ("CAR-1", date(2026, 6, 1), ENDED_BY_REVOCATION),
        ("CAR-2", date(2026, 7, 1), ENDED_BY_REVOCATION),
    ]
