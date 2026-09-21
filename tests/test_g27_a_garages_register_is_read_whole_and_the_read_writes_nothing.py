"""G27 -- a garage's register can be read whole, by any reader, without
knowing a pass id first, and the read writes nothing.

``show-garage-register`` is the one read of a garage's register: every
registration recorded at the garage, history included, and the state and two
valid days of every pass those rows name -- sorted in Python by code point, and
nothing else. It exists because ``show-pass`` (G26) takes a pass id, and a
reader that has to hold every entitlement at a garage was never told one.
Each claim below is proven with a control in the same run, and each has a
plant in ``scripts/fail_controls.py`` that turns it red:

* the whole register at each garage of a two-zone pass, ended and future rows
  included, beside a second pass at one garage only; the same bytes through
  the library and the command line;
* the ORDER is the module's, not the database's: the rows are inserted in an
  order the database returns unsorted, asserted before the sort is trusted;
* the read writes nothing, by row counts and row digests of every table in the
  catalogue before and after -- with a real write as the positive control;
* what does not travel: the holder, the terms, the label, the credentials AND
  the pass's other garages -- asserted absent from the printed text with the
  stored rows as the control that they are there to be leaked;
* unreadable data stops no read: a pass stored unreadable (G17's raw row) and
  the garage itself stored with a zone the system does not carry are both
  shown and named with their code, while a WRITE at the same garage refuses;
* the refusals a read can meet, and the one it does not: no such garage; a
  garage with no registration answers an empty register;
* another tenant's garage with the same id: not read beside a known-shown
  control, with row-level security on AND off;
* a registration whose pass does not name the garage: refused by the
  constraint, and planted past it, shown and its pass named;
* every writer of the register, from G26's census, is reflected here too.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from fixtures import a_pass, everything_terms
from garage_pass import findings as f
from garage_pass.cli import _plain, main
from garage_pass.garage import Garage
from garage_pass.store.enrolments import issue_enrolment, issue_holder_link
from garage_pass.store.postgres import all_tables, tenant
from garage_pass.store.records import (
    create_pass,
    register_vehicle,
    show_garage_register,
    store_garage,
)
from store_harness import CREATED_AT, new_tenant, query, store_test
from test_g26_a_pass_is_read_whole_and_the_read_writes_nothing import (
    DENVER,
    ELSEWHERE,
    OUTSIDE,
    REGISTRATIONS,
    TOKYO,
    _dsn_for_the_app,
    _rls,
    digests,
    register_writers,
)

#: A second pass at Denver only, whose id sorts BEFORE ``pass-1`` by code
#: point (``P`` 80 < ``p`` 112) and after it under en_US on glibc.
ONLY_DENVER = "Pass-0"

KEYS = {"garage", "unreadable_garage", "passes", "passes_not_naming_garage", "registrations"}
ROW_KEYS = {"vehicle_identity", "pass", "effective_day", "end_day", "ended_reason"}
PASS_KEYS = {"pass", "state", "valid_from", "valid_to", "unreadable"}


def seed_two_passes(app, tenant_id, *, extra: tuple[Garage, ...] = (), terms=None):
    """``pass-1`` over Denver and Tokyo with G26's four registrations, and
    ``Pass-0`` at Denver only with one car of its own, committed."""
    two_zone = a_pass(id="pass-1", garage_ids={DENVER.id, TOKYO.id}, terms=terms)
    denver_only = a_pass(id=ONLY_DENVER, garage_ids={DENVER.id})
    with tenant(app, tenant_id) as cursor:
        for garage in (DENVER, TOKYO, *extra):
            store_garage(cursor, tenant_id, garage)
        create_pass(cursor, tenant_id, DENVER.id, two_zone, by="seed", at=CREATED_AT)
        create_pass(cursor, tenant_id, DENVER.id, denver_only, by="seed", at=CREATED_AT)
        for identity, effective, end in REGISTRATIONS:
            register_vehicle(cursor, tenant_id, DENVER.id, two_zone.id, identity, effective, end)
        register_vehicle(cursor, tenant_id, DENVER.id, denver_only.id, "CAR-D", date(2026, 4, 1))
    app.commit()
    return two_zone, denver_only


def read(app, tenant_id, garage_id: str) -> dict:
    with tenant(app, tenant_id) as cursor:
        out = show_garage_register(cursor, tenant_id, garage_id)
    app.rollback()
    return out


def read_or_refused(app, tenant_id, garage_id: str) -> dict:
    """The read's outcome as data, so a refusal is compared, never raised."""
    try:
        return read(app, tenant_id, garage_id)
    except f.Refused as refused:
        app.rollback()
        return {"refused": refused.code, "detail": refused.detail}


def run(argv: list[str], capsys) -> tuple[int, dict]:
    status = main(argv)
    out = capsys.readouterr()
    assert out.err == "", out.err
    return status, json.loads(out.out)


def expected_rows(garage: Garage) -> list[dict]:
    rows = [
        {"vehicle_identity": identity, "pass": "pass-1", "effective_day": effective,
         "end_day": end, "ended_reason": "ended" if end else None}
        for identity, effective, end in REGISTRATIONS
    ]
    if garage is DENVER:
        rows.append({"vehicle_identity": "CAR-D", "pass": ONLY_DENVER,
                     "effective_day": date(2026, 4, 1), "end_day": None, "ended_reason": None})
    return sorted(rows, key=lambda r: (r["vehicle_identity"], r["effective_day"], r["pass"]))


def a_pass_entry(pass_id: str, **overrides) -> dict:
    return {"pass": pass_id, "state": "active", "valid_from": None, "valid_to": None,
            "unreadable": None, **overrides}


# ---------------------------------------------------------------------------
# the whole register, in the module's order, the same bytes on both doors
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G27")
@store_test
def test_the_read_shows_every_registration_at_the_garage_history_included_sorted_by_code_point(
    app, tenant_id, capsys, monkeypatch
):
    seed_two_passes(app, tenant_id)
    denver_rows = expected_rows(DENVER)
    assert [r["vehicle_identity"] for r in denver_rows] == [
        "CAR-A", "CAR-D", "Car-C", "car-b", "car-b"]
    assert {r["end_day"] is not None for r in denver_rows} == {True, False}, "ended AND open"
    assert max(r["effective_day"] for r in denver_rows) > date(2026, 12, 31), "a future row"
    # THE PREMISE of the sort control: the database's own unsorted order is
    # not the published one, so removing the sort would be seen
    raw = query(app, tenant_id, "SELECT vehicle_identity FROM vehicle_registrations r "
                                "JOIN garages g ON g.id = r.garage_id "
                                "WHERE g.external_id = %s", (DENVER.id,))
    assert [r[0] for r in raw] != [r["vehicle_identity"] for r in denver_rows], (
        "the heap order coincides with the code-point order; the sort control cannot see "
        "its subject on this database"
    )
    out = read(app, tenant_id, DENVER.id)
    assert set(out) == KEYS, sorted(out)
    assert out["garage"] == DENVER.id and out["unreadable_garage"] is None
    assert out["passes"] == [a_pass_entry(ONLY_DENVER), a_pass_entry("pass-1")], (
        "code point: P before p")
    assert out["passes_not_naming_garage"] == []
    assert out["registrations"] == denver_rows
    assert all(set(r) == ROW_KEYS for r in out["registrations"])
    assert all(set(p) == PASS_KEYS for p in out["passes"])
    # at the other garage of the two-zone pass: its rows, and not Denver's own pass
    tokyo = read(app, tenant_id, TOKYO.id)
    assert tokyo["garage"] == TOKYO.id
    assert tokyo["passes"] == [a_pass_entry("pass-1")]
    assert tokyo["registrations"] == expected_rows(TOKYO)
    assert len(tokyo["registrations"]) == 4 and len(out["registrations"]) == 5
    # the command line prints the same value, through the same function
    _dsn_for_the_app(monkeypatch)
    status, printed = run(["show-garage-register", "--tenant", str(tenant_id),
                           "--garage", DENVER.id], capsys)
    assert status == 0
    assert printed == _plain(read(app, tenant_id, DENVER.id))
    assert printed["registrations"][0]["effective_day"] == "2026-03-01"


# ---------------------------------------------------------------------------
# the read writes nothing: row counts and row digests, every table
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G27")
@store_test
def test_the_read_writes_nothing_by_row_counts_and_digests_of_every_table(
    app, owner, tenant_id, capsys, monkeypatch
):
    seed_two_passes(app, tenant_id)
    _dsn_for_the_app(monkeypatch)
    tables = all_tables(owner)
    assert len(tables) >= 12 and "vehicle_registrations" in tables, tables
    before = digests(owner)
    for garage, count in ((DENVER, 5), (TOKYO, 4)):
        status, printed = run(["show-garage-register", "--tenant", str(tenant_id),
                               "--garage", garage.id], capsys)
        assert status == 0 and len(printed["registrations"]) == count
    after = digests(owner)
    assert after == before, {t: (before[t], after[t]) for t in before if before[t] != after[t]}
    # THE CONTROL: the instrument sees a write. One more registration, and the
    # digest of exactly that table moves.
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, DENVER.id, ONLY_DENVER, "CAR-Z", date(2026, 9, 1))
    app.commit()
    moved = {t for t in before if digests(owner)[t] != before[t]}
    assert moved == {"vehicle_registrations"}, moved


# ---------------------------------------------------------------------------
# what does not travel
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G27")
@store_test
def test_the_holder_the_terms_the_label_the_credentials_and_the_other_garages_do_not_travel(
    app, owner, tenant_id, capsys, monkeypatch
):
    """Every term present at once (``everything_terms``): the two valid days
    travel and NOTHING else of the terms does; nor the holder, the label, the
    credentials -- nor the pass's OTHER garage: asked at Denver, Tokyo's id is
    not in the text, though the pass names it (the control)."""
    import dataclasses

    from fixtures import lanes_at
    from garage_pass.terms import Terms

    every = everything_terms(DENVER.id)
    every = dataclasses.replace(every, allowed_lanes=lanes_at(DENVER.id, "L1", "L2")
                                + lanes_at(TOKYO.id, "L1"),
                                valid_to=date(2027, 12, 31))  # past the fixture's future row
    two_zone, _ = seed_two_passes(app, tenant_id, terms=every)
    with tenant(app, tenant_id) as cursor:
        token = issue_enrolment(cursor, tenant_id, DENVER.id, two_zone.id, "qr-1",
                                date(2026, 6, 1), 3, by="owner", at=CREATED_AT,
                                vehicle_description="silver")
        link = issue_holder_link(cursor, tenant_id, DENVER.id, two_zone.id, "link-1",
                                 date(2026, 6, 1), 3, by="owner", at=CREATED_AT)
    app.commit()
    _dsn_for_the_app(monkeypatch)
    status, printed = run(["show-garage-register", "--tenant", str(tenant_id),
                           "--garage", DENVER.id], capsys)
    text = json.dumps(printed)
    assert status == 0 and set(printed) == KEYS
    from garage_pass.enrolment import digest

    entry = next(p for p in printed["passes"] if p["pass"] == "pass-1")
    assert entry["valid_from"] == "2026-01-01" and entry["valid_to"] == "2027-12-31"
    other_terms = sorted(set(Terms.__dataclass_fields__) - {"valid_from", "valid_to"})
    assert len(other_terms) == 5, other_terms  # the premise: five terms besides the two
    must_not_travel = {
        "holder name": two_zone.holder.name, "holder phone": two_zone.holder.phone,
        "holder email": two_zone.holder.email, "label": two_zone.label,
        "enrolment id": "qr-1", "vehicle description": "silver", "link id": "link-1",
        "enrolment token": token["token"], "link token": link["token"],
        "enrolment digest": digest(token["token"]), "link digest": digest(link["token"]),
        **{f"term {name}": f'"{name}"' for name in other_terms},
        "the stated lanes": '"L1"', "the allowance's count": '"count"',
        "the window's minutes": '"start_minute"',
        "the pass's other garage": TOKYO.id,
    }
    for what, value in must_not_travel.items():
        assert value not in text, f"the {what} travelled: {value!r}"
    # THE CONTROL: every one of them IS stored, in this tenant, to be leaked
    (label, name, phone, email) = query(
        app, tenant_id, "SELECT label, holder_name, holder_phone, holder_email FROM passes "
                        "WHERE external_id = 'pass-1'")[0]
    assert (label, name, phone, email) == (two_zone.label, two_zone.holder.name,
                                           two_zone.holder.phone, two_zone.holder.email)
    assert query(app, tenant_id, "SELECT external_id, vehicle_description FROM enrolments") == [
        ("qr-1", "silver")]
    assert query(app, tenant_id, "SELECT external_id FROM holder_links") == [("link-1",)]
    assert sorted(g for (g,) in query(
        app, tenant_id, "SELECT g.external_id FROM pass_garages pg JOIN garages g "
                        "ON g.id = pg.garage_id JOIN passes p ON p.id = pg.pass_id "
                        "WHERE p.external_id = 'pass-1'")) == [TOKYO.id, DENVER.id]


# ---------------------------------------------------------------------------
# unreadable data stops no read
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G27")
@store_test
def test_a_pass_stored_unreadable_is_still_shown_and_the_field_is_named(app, owner, tenant_id):
    """G17's raw row: ``lanes_stated`` with no lane rows loads unreadable.
    The read shows the register and names the refusal on that pass beside the
    readable one; a write against the same pass is refused (the control)."""
    two_zone, _ = seed_two_passes(app, tenant_id)
    with owner.cursor() as cursor:
        cursor.execute("UPDATE passes SET lanes_stated = true WHERE external_id = %s "
                       "AND tenant_id = %s", (two_zone.id, tenant_id))
        assert cursor.rowcount == 1
    out = read_or_refused(app, tenant_id, DENVER.id)
    assert set(out) == KEYS, f"the read refused on unreadable data: {out}"
    assert out["registrations"] == expected_rows(DENVER)
    readable, unreadable = out["passes"]
    assert readable == a_pass_entry(ONLY_DENVER)
    assert unreadable["pass"] == "pass-1" and unreadable["state"] == "active"
    assert unreadable["valid_from"] is None and unreadable["valid_to"] is None, (
        "unreadable terms: both null")
    assert unreadable["unreadable"].code == f.REFUSAL_LANES_STATED_BUT_EMPTY
    assert unreadable["unreadable"].field == "allowed_lanes"
    with tenant(app, tenant_id) as cursor, pytest.raises(f.Refused) as refused:
        register_vehicle(cursor, tenant_id, DENVER.id, two_zone.id, "CAR-Z", date(2026, 9, 1))
    app.rollback()
    assert refused.value.code == f.REFUSAL_LANES_STATED_BUT_EMPTY, "the control: a write refuses"


@pytest.mark.guarantee("G27")
@store_test
def test_the_garage_stored_with_a_zone_the_system_does_not_carry_stops_no_read(
    app, owner, tenant_id
):
    two_zone, _ = seed_two_passes(app, tenant_id)
    with owner.cursor() as cursor:
        cursor.execute("UPDATE garages SET timezone = 'Mars/Olympus' WHERE external_id = %s "
                       "AND tenant_id = %s", (TOKYO.id, tenant_id))
        assert cursor.rowcount == 1
    out = read_or_refused(app, tenant_id, TOKYO.id)
    assert set(out) == KEYS, f"the read refused at the unreadable garage: {out}"
    assert out["registrations"] == expected_rows(TOKYO)
    assert out["passes"] == [a_pass_entry("pass-1")]
    named = out["unreadable_garage"]
    assert named is not None
    assert named.code == f.REFUSAL_TIMEZONE_UNKNOWN and named.field == "garage.timezone"
    assert "Mars/Olympus" in named.detail
    # and the readable garage of the same pass reads as before, naming nothing
    assert read(app, tenant_id, DENVER.id)["unreadable_garage"] is None
    # THE CONTROL: a write at the unreadable garage is refused by name, today's rule
    with tenant(app, tenant_id) as cursor, pytest.raises(f.Refused) as refused:
        register_vehicle(cursor, tenant_id, TOKYO.id, two_zone.id, "CAR-Z", date(2026, 9, 1))
    app.rollback()
    assert refused.value.code == f.REFUSAL_TIMEZONE_UNKNOWN
    assert "set-garage-timezone" in refused.value.detail


# ---------------------------------------------------------------------------
# the refusal a read can meet, and the empty register that is not one
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G27")
@store_test
def test_no_such_garage_is_refused_by_name_and_a_garage_with_no_registration_answers_empty(
    app, tenant_id, capsys, monkeypatch
):
    seed_two_passes(app, tenant_id, extra=(ELSEWHERE,))
    control = read_or_refused(app, tenant_id, DENVER.id)
    assert "registrations" in control and len(control["registrations"]) == 5
    nowhere = read_or_refused(app, tenant_id, "garage-nowhere")
    assert nowhere == {"refused": f.REFUSAL_GARAGE_NOT_FOUND,
                       "detail": "no garage 'garage-nowhere'."}
    # a garage the tenant has and no pass names: an empty register, exit 0,
    # never a refusal -- there is nothing to refuse, and the reader's cache
    # for that garage is legitimately empty
    empty = read_or_refused(app, tenant_id, ELSEWHERE.id)
    assert empty == {"garage": ELSEWHERE.id, "unreadable_garage": None, "passes": [],
                     "passes_not_naming_garage": [], "registrations": []}
    _dsn_for_the_app(monkeypatch)
    status, printed = run(["show-garage-register", "--tenant", str(tenant_id),
                           "--garage", ELSEWHERE.id], capsys)
    assert status == 0 and printed["registrations"] == [] and printed["passes"] == []


# ---------------------------------------------------------------------------
# another tenant's garage with the same id
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G27")
@store_test
def test_another_tenants_garage_with_the_same_id_is_not_read_with_rls_on_and_with_it_off(
    app, owner, tenant_id
):
    """Two tenants, one garage id, different cars. Each tenant reads its own
    register and never the other's -- beside its own as the known-shown
    control -- with row-level security on (the product's state), and then
    with it OFF on every table, so the read's own tenant predicate is proven
    to hold alone. A third tenant with no such garage is refused by name."""
    other = new_tenant(owner)
    third = new_tenant(owner)
    cars = {tenant_id: "CAR-MINE", other: "CAR-THEIRS"}
    for t, car in cars.items():
        pass_ = a_pass(id="pass-1", garage_ids={DENVER.id})
        with tenant(app, t) as cursor:
            store_garage(cursor, t, DENVER)
            create_pass(cursor, t, DENVER.id, pass_, by="seed", at=CREATED_AT)
            register_vehicle(cursor, t, DENVER.id, "pass-1", car, date(2026, 1, 1))
        app.commit()

    def reading() -> dict:
        out = {}
        for t in (tenant_id, other, third):
            got = read_or_refused(app, t, DENVER.id)
            out[t] = sorted({r["vehicle_identity"] for r in got["registrations"]}) \
                if "registrations" in got else got["refused"]
        return out

    expected = {tenant_id: ["CAR-MINE"], other: ["CAR-THEIRS"], third: f.REFUSAL_GARAGE_NOT_FOUND}
    assert reading() == expected, "with row-level security ON"

    def both_visible_to_the_app() -> bool:
        """A bare query as the application role, no tenant set: the two
        tenants' rows are visible only with the policy off."""
        with app.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM garages WHERE external_id = %s "
                           "AND tenant_id = ANY(%s)", (DENVER.id, [tenant_id, other]))
            (count,) = cursor.fetchone()
        app.rollback()  # the connection holds no lock while the tables are altered
        return count == 2

    assert not both_visible_to_the_app()
    _rls(owner, False)
    try:
        assert both_visible_to_the_app(), "the premise: row-level security is really off"
        assert reading() == expected, "with row-level security OFF: the read's own predicate"
    finally:
        app.rollback()
        _rls(owner, True)
    assert not both_visible_to_the_app(), "row-level security was not restored"


# ---------------------------------------------------------------------------
# a registration whose pass does not name the garage
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G27")
@store_test
def test_a_row_whose_pass_does_not_name_the_garage_is_refused_by_the_constraint_or_shown_if_planted(
    app, owner, tenant_id
):
    import psycopg

    seed_two_passes(app, tenant_id, extra=(ELSEWHERE,))
    ids = dict(query(app, tenant_id, "SELECT external_id, id FROM garages"))
    (pass_uuid,) = query(app, tenant_id, "SELECT id FROM passes WHERE external_id = 'pass-1'")[0]
    insert = ("INSERT INTO vehicle_registrations (tenant_id, garage_id, pass_id, "
              "vehicle_identity, effective_day) VALUES (%s, %s, %s, 'CAR-OUT', '2026-01-01')")
    # 1. the constraint, by name: a raw insert as the OWNER at a garage the
    #    pass does not name is refused -- so the register at that garage stays empty
    with owner.cursor() as cursor, pytest.raises(psycopg.errors.ForeignKeyViolation) as raised:
        cursor.execute(insert, (tenant_id, ids[ELSEWHERE.id], pass_uuid))
    assert raised.value.diag.constraint_name == OUTSIDE
    assert read(app, tenant_id, ELSEWHERE.id)["registrations"] == []
    # the control: the same insert at a garage the pass names is accepted and read
    with owner.cursor() as cursor:
        cursor.execute(insert.replace("CAR-OUT", "CAR-IN"), (tenant_id, ids[TOKYO.id], pass_uuid))
    assert [r["vehicle_identity"] for r in read(app, tenant_id, TOKYO.id)["registrations"]] == [
        "CAR-A", "CAR-IN", "Car-C", "car-b", "car-b"]
    # 2. planted PAST the constraint -- its triggers disabled, which only a
    #    superuser may do -- the read at that garage shows the row and names the pass
    with owner.cursor() as cursor:
        cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        assert cursor.fetchone() == (True,), "the owner must be a superuser to plant this"
        cursor.execute("ALTER TABLE vehicle_registrations DISABLE TRIGGER ALL")
        try:
            cursor.execute(insert, (tenant_id, ids[ELSEWHERE.id], pass_uuid))
        finally:
            cursor.execute("ALTER TABLE vehicle_registrations ENABLE TRIGGER ALL")
    out = read(app, tenant_id, ELSEWHERE.id)
    assert [(r["vehicle_identity"], r["pass"]) for r in out["registrations"]] == [
        ("CAR-OUT", "pass-1")], "the row was dropped"
    assert out["passes"] == [a_pass_entry("pass-1")]
    assert out["passes_not_naming_garage"] == ["pass-1"]
    # and at a garage the pass does name, nothing is named
    assert read(app, tenant_id, DENVER.id)["passes_not_naming_garage"] == []


# ---------------------------------------------------------------------------
# every writer of the register, from G26's census, is reflected by this read
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G27")
@store_test
def test_every_writer_of_the_register_is_reflected_by_the_read(app, tenant_id):
    """G26's census names the five write sites; the same scenario, read
    BY GARAGE: the expiry release, end_registration's UPDATE and the
    revocation's UPDATE each show at each garage with their ``ended_reason``,
    and the pass list carries the revoked state as stored."""
    from fixtures import BOTH, at
    from garage_pass.passes import State
    from garage_pass.store.records import change_state, end_registration
    from garage_pass.terms import Terms

    assert len(register_writers()) == 5, (
        "a writer of the register or the set was added or moved: prove this read reflects it")
    expiring = a_pass(id="pass-expiring", garage_ids={DENVER.id, TOKYO.id},
                      terms=Terms(directions=BOTH, valid_to=date(2026, 6, 30)))
    successor = a_pass(id="pass-successor", garage_ids={DENVER.id, TOKYO.id})
    with tenant(app, tenant_id) as cursor:
        for garage in (DENVER, TOKYO):
            store_garage(cursor, tenant_id, garage)
        for pass_ in (expiring, successor):
            create_pass(cursor, tenant_id, DENVER.id, pass_, by="seed", at=CREATED_AT)
        register_vehicle(cursor, tenant_id, DENVER.id, expiring.id, "CAR-X", date(2026, 1, 1))
        register_vehicle(cursor, tenant_id, TOKYO.id, successor.id, "CAR-X", date(2026, 8, 1))
        register_vehicle(cursor, tenant_id, DENVER.id, successor.id, "CAR-Y", date(2026, 8, 1))
        end_registration(cursor, tenant_id, TOKYO.id, successor.id, "CAR-Y", date(2026, 8, 15))
        change_state(cursor, tenant_id, DENVER.id, successor.id, State.REVOKED, by="owner",
                     at=at(date(2026, 9, 1), 2), reason="divorced")
    app.commit()
    for garage in (DENVER, TOKYO):
        out = read(app, tenant_id, garage.id)
        assert [(p["pass"], p["state"], p["valid_to"]) for p in out["passes"]] == [
            ("pass-expiring", "active", date(2026, 6, 30)),
            ("pass-successor", "revoked", None),
        ], garage.id
        assert [(r["vehicle_identity"], r["pass"], r["effective_day"], r["end_day"],
                 r["ended_reason"]) for r in out["registrations"]] == [
            ("CAR-X", "pass-expiring", date(2026, 1, 1), date(2026, 7, 1),
             "pass valid_to passed"),
            ("CAR-X", "pass-successor", date(2026, 8, 1), date(2026, 9, 1), "pass revoked"),
            ("CAR-Y", "pass-successor", date(2026, 8, 1), date(2026, 8, 15), "ended"),
        ], garage.id


# ---------------------------------------------------------------------------
# the two valid days travel, and the read uses no clock
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G27")
@store_test
def test_the_two_valid_days_travel_and_the_stored_state_is_shown_whatever_the_day_says(
    app, tenant_id, capsys, monkeypatch
):
    """A pass stored ``active`` whose ``valid_to`` is long past, and one whose
    ``valid_from`` has not come, each with a car at Denver: shown with their
    bounds and their STORED state -- the read derives nothing from a day it
    does not have -- and an ended row beside an open one, both shown."""
    from fixtures import BOTH
    from garage_pass.terms import Terms

    over = a_pass(id="pass-over", garage_ids={DENVER.id},
                  terms=Terms(directions=BOTH, valid_from=date(2020, 1, 1),
                              valid_to=date(2020, 12, 31)))
    ahead = a_pass(id="pass-ahead", garage_ids={DENVER.id},
                   terms=Terms(directions=BOTH, valid_from=date(2099, 1, 1)))
    with tenant(app, tenant_id) as cursor:
        store_garage(cursor, tenant_id, DENVER)
        for pass_ in (over, ahead):
            create_pass(cursor, tenant_id, DENVER.id, pass_, by="seed", at=CREATED_AT)
        register_vehicle(cursor, tenant_id, DENVER.id, over.id, "CAR-OVER", date(2020, 1, 1),
                         date(2020, 6, 1))
        register_vehicle(cursor, tenant_id, DENVER.id, ahead.id, "CAR-AHEAD", date(2099, 1, 1))
    app.commit()
    _dsn_for_the_app(monkeypatch)
    status, printed = run(["show-garage-register", "--tenant", str(tenant_id),
                           "--garage", DENVER.id], capsys)
    assert status == 0 and set(printed) == KEYS
    assert printed["passes"] == [
        {"pass": "pass-ahead", "state": "active", "valid_from": "2099-01-01", "valid_to": None,
         "unreadable": None},
        {"pass": "pass-over", "state": "active", "valid_from": "2020-01-01",
         "valid_to": "2020-12-31", "unreadable": None},
    ], "the stored state, not a derived expired"
    assert [(r["vehicle_identity"], r["end_day"]) for r in printed["registrations"]] == [
        ("CAR-AHEAD", None), ("CAR-OVER", "2020-06-01")], "the ended row is not dropped"
    # and nothing else of either pass's terms is in the text
    assert '"directions"' not in json.dumps(printed)
