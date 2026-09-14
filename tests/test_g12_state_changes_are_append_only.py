"""G12 -- every state change records who, when and why into an append-only
history; the transitions are the published ones; expired is derived.

And the store half of G5: revoking a pass ends its registrations on the
revocation day in the garage's local calendar.

**AND NO ROUTE AROUND THE GRANT.** The history cascades from ``passes`` and
``tenants``; a DELETE on either would erase it. The module issues no DELETE at
all, on any table -- a measured property of the code -- so the assertion is
the strong one: **the application role holds DELETE on NO table in the
schema**, every table read from the catalogue, with no hand list and no walk
to miss a leaf. The first cut asserted it only of the tables that cascade
into a history, walked transitively; that walk cannot see a leaf child of
``passes`` (``enrolments``, ``holder_links`` -- measured, G2's brief
correction 1), so a DELETE granted there would have passed. The walk is KEPT,
inside the same test, for what the red says: DELETE on ``passes`` erases the
history and the failure names it; DELETE on ``enrolments`` is a leaf and the
failure names the leaf. Measured before the fix: ``DELETE FROM passes`` as the
application role took the history from one row to none. **AND "LEAF" IS READ
FROM THE CATALOGUE**: a table nothing references. Measured at the G3a L3: the
red on a planted DELETE grant called ``pass_garages`` -- three children -- "a
leaf: the walk into a history would not have seen it", true of the walk and
false of the table. An offending table is now named in one of three ways: it
erases a history; nothing references it (a leaf); or it is the parent of the
tables that reference it, none a history.

**AND THE GARAGE REPAIRS ARE RECORDED THE SAME WAY** (migrations 0002 and
0003). ``set_garage_timezone`` changes how every pass at the garage is read,
and it left no record but the row -- measured at the re-gate. Now who, when,
why, the old value and the new go into ``garage_changes``, append-only by the
same grant, cascading from ``garages`` and ``tenants`` on which the application
role holds no DELETE. ``set_garage_enrols_at`` -- where a QR may be redeemed
-- is the second repair, recorded into the same history with ``field =
'enrols_at'`` (0003 widens the CHECK that 0002 wrote so a second repair would
be a migration), refusing the R1 contradiction by name as creation does. The
set of histories is DERIVED: every table the role may only SELECT and INSERT
on, read from the catalogue, must be exactly the two published ones, and each
is walked for cascade parents.

Controls: the INSERT of the history row planted away; the grant on the
history widened to UPDATE in the migration; the who/why check planted away;
the revocation's registration update planted away; DELETE on ``passes`` granted
back to the application role (the red names the history it erases); DELETE on
``enrolments`` granted (the red names the leaf); the garage history's INSERT
planted away; its grant widened; the repair's who/why check planted away; the
enrols-at repair's contradiction check planted away; its history row planted
away; the catalogue read of a table's children planted empty (every table a
leaf again).
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


HISTORIES = {"pass_state_changes": {"passes", "tenants"}, "garage_changes": {"garages", "tenants"}}


def what_a_delete_there_does(app, table: str, erases: dict[str, list[str]]) -> str:
    """The sentence the red names an offending table with -- THREE classes, and
    the third is read from the catalogue, never assumed: a table that cascades
    into a history erases it; a table nothing references is a leaf; and a
    table with children of its own that are NOT histories is named as their
    parent. Measured before this (the G3a L3): ``pass_garages``, with three
    children, was called "a leaf: the walk into a history would not have seen
    it" -- true of the walk, false of the table."""
    from garage_pass.store.postgres import tables_referencing

    if table in erases:
        return f"a DELETE there erases {', '.join(sorted(erases[table]))}"
    children = tables_referencing(app, table)
    if children:
        return (f"a parent of {', '.join(sorted(children))}, none a history: the walk into a "
                "history would not have seen it, and what a DELETE there reaches is theirs")
    return "a leaf: nothing references it, and the walk into a history would not have seen it"


def append_only_tables(app) -> set[str]:
    """Every table the application role may only SELECT and INSERT on -- the
    histories, read from the catalogue rather than typed."""
    from garage_pass.store.postgres import tables_with_tenant_column

    return {t for t in tables_with_tenant_column(app) if grants_on(app, t) == {"SELECT", "INSERT"}}


@pytest.mark.guarantee("G12")
@store_test
def test_the_append_only_histories_are_exactly_the_published_two(app):
    assert append_only_tables(app) == set(HISTORIES)


@pytest.mark.guarantee("G12")
@store_test
def test_the_application_role_holds_delete_on_no_table_in_the_schema(app, tenant_id):
    """THE STRONG ASSERTION, over every table in the catalogue: no hand list,
    no walk to miss a leaf. The cascade walk is kept beside it for what the
    red SAYS -- a DELETE grant on a table that cascades into an append-only
    history is named as erasing that history; one on a leaf is named as the
    leaf -- and for its own control that the known parents are found."""
    from garage_pass.store.postgres import all_tables

    tables = all_tables(app)
    assert len(tables) >= 11, f"the catalogue scan found only {tables}"
    assert {"passes", "enrolments", "holder_links", *HISTORIES} <= set(tables)
    erases = {}
    for history in HISTORIES:
        cascading = tables_cascading_into(app, history)
        assert HISTORIES[history] <= cascading, (
            f"the walk did not find the known parents of {history}; found {sorted(cascading)}"
        )
        for table in cascading:
            erases.setdefault(table, []).append(history)
    assert "garages" not in erases.get("pass_state_changes", []), (
        "garages -> passes is RESTRICT; the walk over-reached"
    )
    offenders = [
        f"{table} ({what_a_delete_there_does(app, table, erases)})"
        for table in tables if "DELETE" in grants_on(app, table)
    ]
    assert offenders == [], f"the application role holds DELETE on: {offenders}"
    # and it really cannot: the way the code would make the call, at its role --
    # an ancestor of a history, and a leaf
    seed(app, tenant_id, GARAGE, (a_pass(),))
    for statement in ("DELETE FROM passes", "DELETE FROM enrolments"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with tenant(app, tenant_id) as cursor:
                cursor.execute(statement)
        app.rollback()
    assert query(app, tenant_id, "SELECT count(*) FROM pass_state_changes") == [(1,)]


@pytest.mark.guarantee("G12")
@store_test
def test_an_offending_table_is_named_by_what_a_delete_there_reaches(app):
    """The three classes, each on a real table of the shipped schema, and the
    parent class on the table that was misnamed: ``pass_garages`` is named as
    the parent of its three children (``pass_lanes``, ``vehicle_registrations``,
    ``visits``) and never as a leaf; ``enrolments`` (nothing references it) is
    the leaf; ``passes`` erases ``pass_state_changes``."""
    from garage_pass.store.postgres import tables_referencing

    erases = {}
    for history in HISTORIES:
        for table in tables_cascading_into(app, history):
            erases.setdefault(table, []).append(history)
    assert tables_referencing(app, "pass_garages") == {
        "pass_lanes", "vehicle_registrations", "visits"
    }
    assert tables_referencing(app, "enrolments") == frozenset()
    parent = what_a_delete_there_does(app, "pass_garages", erases)
    assert parent.startswith("a parent of pass_lanes, vehicle_registrations, visits"), parent
    assert "leaf" not in parent.split(":")[0]
    leaf = what_a_delete_there_does(app, "enrolments", erases)
    assert leaf.startswith("a leaf: nothing references"), leaf
    assert what_a_delete_there_does(app, "passes", erases) == (
        "a DELETE there erases pass_state_changes"
    )


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


# ---------------------------------------------------------------------------
# the garage repair is recorded (migration 0002)
# ---------------------------------------------------------------------------


def garage_history(app, tenant_id):
    return query(
        app, tenant_id,
        "SELECT field, old_value, new_value, changed_by, changed_at, reason FROM garage_changes "
        "ORDER BY changed_at, created_at",
    )


@pytest.mark.guarantee("G12")
@store_test
def test_the_repair_records_who_when_why_the_old_value_and_the_new(app, owner, tenant_id):
    from garage_pass.store.records import set_garage_timezone

    with owner.cursor() as cursor:
        cursor.execute(
            "INSERT INTO garages (tenant_id, external_id, timezone, transient_available) "
            "VALUES (%s, 'g-badtz', 'Mars/Olympus', true)", (tenant_id,),
        )
    assert garage_history(app, tenant_id) == []
    with tenant(app, tenant_id) as cursor:
        set_garage_timezone(cursor, tenant_id, "g-badtz", "America/Denver", by="operator",
                            at=at(date(2026, 6, 2), 9), reason="stored from a laptop")
        set_garage_timezone(cursor, tenant_id, "g-badtz", "America/Phoenix", by="owner",
                            at=at(date(2026, 6, 3), 9), reason="the garage moved")
    app.commit()
    assert garage_history(app, tenant_id) == [
        ("timezone", "Mars/Olympus", "America/Denver", "operator", at(date(2026, 6, 2), 9),
         "stored from a laptop"),
        ("timezone", "America/Denver", "America/Phoenix", "owner", at(date(2026, 6, 3), 9),
         "the garage moved"),
    ]
    assert query(app, tenant_id, "SELECT timezone FROM garages") == [("America/Phoenix",)]


@pytest.mark.guarantee("G12")
@store_test
@pytest.mark.parametrize("by,reason,field", [("", "r", "changed_by"), ("owner", " ", "reason"),
                                             (None, "r", "changed_by")])
def test_a_repair_without_who_or_why_is_refused_and_changes_nothing(
    app, owner, tenant_id, by, reason, field
):
    from garage_pass.store.records import set_garage_timezone

    with owner.cursor() as cursor:
        cursor.execute(
            "INSERT INTO garages (tenant_id, external_id, timezone, transient_available) "
            "VALUES (%s, 'g-badtz', 'Mars/Olympus', true)", (tenant_id,),
        )
    with pytest.raises(f.Refused) as refused:
        with tenant(app, tenant_id) as cursor:
            set_garage_timezone(cursor, tenant_id, "g-badtz", "America/Denver", by=by,
                                at=NOON_MONDAY, reason=reason)
    app.rollback()
    assert refused.value.code == f.REFUSAL_REPAIR_NEEDS_WHO_AND_WHY
    assert refused.value.field == field
    assert query(app, tenant_id, "SELECT timezone FROM garages") == [("Mars/Olympus",)]
    assert garage_history(app, tenant_id) == []


@pytest.mark.guarantee("G12")
@store_test
def test_the_garage_history_is_append_only_by_grant_and_by_a_refused_update(app, tenant_id):
    assert grants_on(app, "garage_changes") == {"SELECT", "INSERT"}
    assert "UPDATE" in grants_on(app, "garages"), "the control: the query sees UPDATE elsewhere"
    seed(app, tenant_id, GARAGE, ())
    for statement in ("UPDATE garage_changes SET reason = 'edited'",
                      "DELETE FROM garage_changes", "DELETE FROM garages"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with tenant(app, tenant_id) as cursor:
                cursor.execute(statement)
        app.rollback()


# ---------------------------------------------------------------------------
# the second garage repair -- where it enrols -- is recorded (migration 0003)
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G12")
@store_test
def test_the_enrols_at_repair_records_who_when_why_the_old_value_and_the_new(app, tenant_id):
    from garage_pass.store.records import set_garage_enrols_at

    seed(app, tenant_id, GARAGE, ())  # transient, enrols_at unstated
    assert query(app, tenant_id, "SELECT enrols_at FROM garages") == [(None,)]
    with tenant(app, tenant_id) as cursor:
        set_garage_enrols_at(cursor, tenant_id, GARAGE.id, "exit", by="owner",
                             at=at(date(2026, 6, 2), 9), reason="stated at go-live")
        set_garage_enrols_at(cursor, tenant_id, GARAGE.id, "entry", by="operator",
                             at=at(date(2026, 6, 3), 9), reason="the exit readers were removed")
    app.commit()
    assert garage_history(app, tenant_id) == [
        ("enrols_at", None, "exit", "owner", at(date(2026, 6, 2), 9), "stated at go-live"),
        ("enrols_at", "exit", "entry", "operator", at(date(2026, 6, 3), 9),
         "the exit readers were removed"),
    ]
    assert query(app, tenant_id, "SELECT enrols_at FROM garages") == [("entry",)]


@pytest.mark.guarantee("G12")
@store_test
@pytest.mark.parametrize("by,reason,field", [("", "r", "changed_by"), ("owner", " ", "reason"),
                                             (None, "r", "changed_by")])
def test_an_enrols_at_repair_without_who_or_why_is_refused_and_changes_nothing(
    app, tenant_id, by, reason, field
):
    from garage_pass.store.records import set_garage_enrols_at

    seed(app, tenant_id, GARAGE, ())
    with pytest.raises(f.Refused) as refused:
        with tenant(app, tenant_id) as cursor:
            set_garage_enrols_at(cursor, tenant_id, GARAGE.id, "exit", by=by, at=NOON_MONDAY,
                                 reason=reason)
    app.rollback()
    assert refused.value.code == f.REFUSAL_REPAIR_NEEDS_WHO_AND_WHY
    assert refused.value.field == field
    assert query(app, tenant_id, "SELECT enrols_at FROM garages") == [(None,)]
    assert garage_history(app, tenant_id) == []


@pytest.mark.guarantee("G12")
@store_test
def test_the_enrols_at_repair_refuses_the_r1_contradiction_by_name_and_changes_nothing(
    app, tenant_id
):
    """No transient, enrols at exit: refused on the repair as on creation,
    naming garage.enrols_at; the row and the history are untouched. And a
    value that is neither end is refused naming the field."""
    from fixtures import no_transient_garage
    from garage_pass.store.records import set_garage_enrols_at

    garage = no_transient_garage()
    seed(app, tenant_id, garage, ())
    for value, code in (("exit", f.REFUSAL_ENROLS_AT_CONTRADICTS_TRANSIENT),
                        ("middle", f.REFUSAL_FIELD_BLANK), ("", f.REFUSAL_FIELD_BLANK)):
        try:
            with tenant(app, tenant_id) as cursor:
                set_garage_enrols_at(cursor, tenant_id, garage.id, value, by="owner",
                                     at=NOON_MONDAY, reason="trying")
        except f.Refused as refused:
            app.rollback()
            assert refused.code == code, value
            assert refused.field == "garage.enrols_at", value
        except Exception as exc:  # noqa: BLE001 -- the subject is "by name, not the CHECK"
            app.rollback()
            pytest.fail(f"the repair reached the database instead of refusing by name: {exc!r}")
        else:
            app.rollback()
            pytest.fail(f"the repair accepted {value!r}")
    assert query(app, tenant_id, "SELECT enrols_at FROM garages") == [(None,)]
    assert garage_history(app, tenant_id) == []
    # the control: 'entry' at the same garage is accepted and recorded
    with tenant(app, tenant_id) as cursor:
        out = set_garage_enrols_at(cursor, tenant_id, garage.id, "entry", by="owner",
                                   at=NOON_MONDAY, reason="stated")
    app.commit()
    assert out == {"garage": garage.id, "enrols_at": "entry", "was": None, "changed_by": "owner",
                   "changed_at": NOON_MONDAY, "reason": "stated"}
    assert [r[:3] for r in garage_history(app, tenant_id)] == [("enrols_at", None, "entry")]
