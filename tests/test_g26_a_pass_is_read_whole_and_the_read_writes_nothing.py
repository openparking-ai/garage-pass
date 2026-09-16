"""G26 -- a pass can be read whole, by any reader, and the read writes nothing.

``show-pass`` is the one read: the pass id, its stored state, the garages it
names and EVERY registration it holds, history included, sorted in Python by
code point -- and nothing else. Each claim below is proven with a control in
the same run, and each has a plant in ``scripts/fail_controls.py`` that turns
it red:

* the whole register, ended and future rows included, at every garage of a
  two-zone pass; the same bytes through the library and the command line;
* the ORDER is the module's, not the database's: the rows are inserted in an
  order the database returns unsorted, and the test asserts that raw order
  differs from the published one before trusting the sort (a premise);
* the read writes nothing, by row counts and row digests of every table in the
  catalogue before and after -- with a real write as the positive control that
  the digest instrument sees a change;
* what does not travel: the holder, the terms, the label, the credentials --
  asserted absent from the printed text with the stored row as the control
  that they are there to be leaked;
* unreadable data stops no read: a pass stored unreadable (G17's raw row) and
  a garage of the set stored with a zone the system does not carry are both
  shown and named with their code, while a WRITE against the same garage is
  refused (the control);
* the refusals a read can meet: no such pass, no such garage, a garage the
  pass does not name (G25's membership, naming the set);
* another tenant's pass with the same id: not shown beside a known-shown
  control, with row-level security on AND with it off (the read's own tenant
  predicate holds alone);
* a registration outside the pass's garage set: the constraint refuses the
  raw insert and refuses to remove the membership row from under a
  registration, by name -- and, planted past the constraint with its
  triggers disabled, the read still shows the row and names the garage;
* every writer of the register and of the garage set, derived from the
  source by a census that fails when one is added, is exercised and read
  back -- the three UPDATEs told apart by ``ended_reason``.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from fixtures import a_pass
from garage_pass import findings as f
from garage_pass.cli import _plain, main
from garage_pass.garage import Garage
from garage_pass.store.enrolments import issue_enrolment, issue_holder_link
from garage_pass.store.postgres import all_tables, tenant
from garage_pass.store.records import (
    create_pass,
    register_vehicle,
    show_pass,
    store_garage,
)
from store_harness import APP_PASSWORD, CREATED_AT, new_tenant, query, store_test

#: Two zones, and ids whose code-point order is NOT the collation's: ``G`` (71)
#: sorts before ``g`` (103) by code point, after it under en_US on glibc.
DENVER = Garage(id="garage-denver", timezone="America/Denver", transient_available=True)
TOKYO = Garage(id="Garage-tokyo", timezone="Asia/Tokyo", transient_available=True)
ELSEWHERE = Garage(id="garage-elsewhere", timezone="America/Denver", transient_available=True)

#: (identity, effective day, end day) -- IN INSERTION ORDER, chosen so the heap
#: order is not the code-point order: ``CAR-A`` < ``Car-C`` < ``car-b``.
REGISTRATIONS = (
    ("Car-C", date(2027, 1, 1), None),            # starts on a future day
    ("CAR-A", date(2026, 3, 1), None),            # current
    ("car-b", date(2026, 1, 1), date(2026, 2, 1)),  # ended
    ("car-b", date(2026, 6, 1), None),            # the same identity again, later
)

KEYS = {"pass", "state", "garages", "garages_not_named", "unreadable", "unreadable_garages",
        "registrations"}
ROW_KEYS = {"vehicle_identity", "garage", "effective_day", "end_day", "ended_reason"}


def _dsn_for_the_app(monkeypatch):
    from psycopg import conninfo

    from garage_pass.store.postgres import APP_ROLE
    from store_harness import DSN

    params = conninfo.conninfo_to_dict(DSN)
    monkeypatch.setenv("GARAGE_PASS_DSN", conninfo.make_conninfo(
        **{**params, "user": APP_ROLE, "password": APP_PASSWORD}))


def seed_two_zone_pass(app, tenant_id, *, id: str = "pass-1", extra: tuple[Garage, ...] = ()):
    """A pass over Denver and Tokyo with the four registrations, committed."""
    pass_ = a_pass(id=id, garage_ids={DENVER.id, TOKYO.id})
    with tenant(app, tenant_id) as cursor:
        for garage in (DENVER, TOKYO, *extra):
            store_garage(cursor, tenant_id, garage)
        create_pass(cursor, tenant_id, DENVER.id, pass_, by="seed", at=CREATED_AT)
        for identity, effective, end in REGISTRATIONS:
            register_vehicle(cursor, tenant_id, DENVER.id, pass_.id, identity, effective, end)
    app.commit()
    return pass_


def shown(app, tenant_id, garage_id: str, pass_id: str) -> dict:
    with tenant(app, tenant_id) as cursor:
        out = show_pass(cursor, tenant_id, garage_id, pass_id)
    app.rollback()
    return out


def shown_or_refused(app, tenant_id, garage_id: str, pass_id: str) -> dict:
    """The read's outcome as data, so a refusal is compared, never raised."""
    try:
        return shown(app, tenant_id, garage_id, pass_id)
    except f.Refused as refused:
        app.rollback()
        return {"refused": refused.code, "detail": refused.detail}


def run(argv: list[str], capsys) -> tuple[int, dict]:
    status = main(argv)
    out = capsys.readouterr()
    assert out.err == "", out.err
    return status, json.loads(out.out)


def expected_rows() -> list[dict]:
    rows = []
    for identity, effective, end in REGISTRATIONS:
        for garage in (DENVER, TOKYO):
            rows.append({"vehicle_identity": identity, "garage": garage.id,
                         "effective_day": effective, "end_day": end,
                         "ended_reason": "ended" if end else None})
    return sorted(rows, key=lambda r: (r["vehicle_identity"], r["effective_day"], r["garage"]))


# ---------------------------------------------------------------------------
# the whole register, in the module's order, the same bytes on both doors
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G26")
@store_test
def test_the_read_shows_every_registration_history_included_sorted_by_code_point(
    app, tenant_id, capsys, monkeypatch
):
    pass_ = seed_two_zone_pass(app, tenant_id)
    rows = expected_rows()
    assert [r["vehicle_identity"] for r in rows][::2] == ["CAR-A", "Car-C", "car-b", "car-b"]
    assert {r["end_day"] is not None for r in rows} == {True, False}, "ended AND open rows"
    assert max(r["effective_day"] for r in rows) > date(2026, 12, 31), "a future row"
    # THE PREMISE of the sort control: the database's own unsorted order is
    # not the published one, so removing the sort would be seen
    raw = query(app, tenant_id, "SELECT vehicle_identity, effective_day, garage_id::text "
                                "FROM vehicle_registrations")
    assert [r[0] for r in raw] != [r["vehicle_identity"] for r in rows], (
        "the heap order coincides with the code-point order; the sort control cannot see "
        "its subject on this database"
    )
    for garage in (DENVER, TOKYO):  # at either garage of the set, the same reading
        out = shown(app, tenant_id, garage.id, pass_.id)
        assert set(out) == KEYS, sorted(out)
        assert out["pass"] == "pass-1" and out["state"] == "active"
        assert out["garages"] == ["Garage-tokyo", "garage-denver"], "code point: G before g"
        assert out["garages_not_named"] == []
        assert out["unreadable"] is None and out["unreadable_garages"] == {}
        assert out["registrations"] == rows
        assert all(set(r) == ROW_KEYS for r in out["registrations"])
    # the command line prints the same value, through the same function
    _dsn_for_the_app(monkeypatch)
    status, printed = run(["show-pass", "--tenant", str(tenant_id), "--garage", TOKYO.id,
                           "--pass-id", pass_.id], capsys)
    assert status == 0
    assert printed == _plain(shown(app, tenant_id, TOKYO.id, pass_.id))
    assert printed["registrations"][0]["effective_day"] == "2026-03-01"


# ---------------------------------------------------------------------------
# the read writes nothing: row counts and row digests, every table
# ---------------------------------------------------------------------------


def digests(owner) -> dict[str, tuple[int, str | None]]:
    """Per table: the row count and a digest of every row's text, in an order
    the digest does not depend on -- read as the owner, every tenant."""
    out = {}
    with owner.cursor() as cursor:
        for table in all_tables(owner):
            cursor.execute(
                f"SELECT count(*), md5(string_agg(t::text, '|' ORDER BY t::text)) "
                f'FROM "{table}" t'
            )
            out[table] = cursor.fetchone()
    return out


@pytest.mark.guarantee("G26")
@store_test
def test_the_read_writes_nothing_by_row_counts_and_digests_of_every_table(
    app, owner, tenant_id, capsys, monkeypatch
):
    pass_ = seed_two_zone_pass(app, tenant_id)
    _dsn_for_the_app(monkeypatch)
    tables = all_tables(owner)
    assert len(tables) >= 12 and "vehicle_registrations" in tables, tables
    before = digests(owner)
    for garage in (DENVER, TOKYO):
        status, printed = run(["show-pass", "--tenant", str(tenant_id), "--garage", garage.id,
                               "--pass-id", pass_.id], capsys)
        assert status == 0 and len(printed["registrations"]) == 8
    after = digests(owner)
    assert after == before, {t: (before[t], after[t]) for t in before if before[t] != after[t]}
    # THE CONTROL: the instrument sees a write. One more registration, and the
    # digest of exactly that table moves.
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, DENVER.id, pass_.id, "CAR-Z", date(2026, 9, 1))
    app.commit()
    moved = {t for t in before if digests(owner)[t] != before[t]}
    assert moved == {"vehicle_registrations"}, moved


# ---------------------------------------------------------------------------
# what does not travel
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G26")
@store_test
def test_the_holder_the_terms_the_label_and_the_credentials_do_not_travel(
    app, owner, tenant_id, capsys, monkeypatch
):
    pass_ = seed_two_zone_pass(app, tenant_id)
    with tenant(app, tenant_id) as cursor:
        token = issue_enrolment(cursor, tenant_id, DENVER.id, pass_.id, "qr-1", date(2026, 6, 1),
                                3, by="owner", at=CREATED_AT, vehicle_description="silver")
        link = issue_holder_link(cursor, tenant_id, DENVER.id, pass_.id, "link-1",
                                 date(2026, 6, 1), 3, by="owner", at=CREATED_AT)
    app.commit()
    _dsn_for_the_app(monkeypatch)
    status, printed = run(["show-pass", "--tenant", str(tenant_id), "--garage", DENVER.id,
                           "--pass-id", pass_.id], capsys)
    text = json.dumps(printed)
    assert status == 0 and set(printed) == KEYS
    from garage_pass.enrolment import digest

    must_not_travel = {
        "holder name": pass_.holder.name, "holder phone": pass_.holder.phone,
        "holder email": pass_.holder.email, "label": pass_.label,
        "enrolment id": "qr-1", "vehicle description": "silver", "link id": "link-1",
        "enrolment token": token["token"], "link token": link["token"],
        "enrolment digest": digest(token["token"]), "link digest": digest(link["token"]),
        "terms": "valid_from",
    }
    for what, value in must_not_travel.items():
        assert value not in text, f"the {what} travelled: {value!r}"
    # THE CONTROL: every one of them IS stored, in this tenant, to be leaked
    (label, name, phone, email) = query(
        app, tenant_id, "SELECT label, holder_name, holder_phone, holder_email FROM passes")[0]
    assert (label, name, phone, email) == (pass_.label, pass_.holder.name, pass_.holder.phone,
                                           pass_.holder.email)
    assert query(app, tenant_id, "SELECT external_id, vehicle_description FROM enrolments") == [
        ("qr-1", "silver")]
    assert query(app, tenant_id, "SELECT external_id FROM holder_links") == [("link-1",)]


# ---------------------------------------------------------------------------
# unreadable data stops no read
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G26")
@store_test
def test_a_pass_stored_unreadable_is_still_shown_and_the_field_is_named(app, owner, tenant_id):
    """G17's raw row: ``lanes_stated`` with no lane rows loads unreadable.
    The read shows state, garages and every registration, and names the
    refusal; a write against the same pass is refused (the control)."""
    pass_ = seed_two_zone_pass(app, tenant_id)
    with owner.cursor() as cursor:
        cursor.execute("UPDATE passes SET lanes_stated = true WHERE external_id = %s "
                       "AND tenant_id = %s", (pass_.id, tenant_id))
        assert cursor.rowcount == 1
    out = shown_or_refused(app, tenant_id, DENVER.id, pass_.id)
    assert set(out) == KEYS, f"the read refused on unreadable data: {out}"
    assert out["state"] == "active" and out["garages"] == ["Garage-tokyo", "garage-denver"]
    assert out["registrations"] == expected_rows()
    assert out["unreadable"] is not None
    assert out["unreadable"].code == f.REFUSAL_LANES_STATED_BUT_EMPTY
    assert out["unreadable"].field == "allowed_lanes"
    with tenant(app, tenant_id) as cursor, pytest.raises(f.Refused) as refused:
        register_vehicle(cursor, tenant_id, DENVER.id, pass_.id, "CAR-Z", date(2026, 9, 1))
    app.rollback()
    assert refused.value.code == f.REFUSAL_LANES_STATED_BUT_EMPTY, "the control: a write refuses"


@pytest.mark.guarantee("G26")
@store_test
def test_a_garage_of_the_set_stored_with_a_zone_the_system_does_not_carry_stops_no_read(
    app, owner, tenant_id
):
    pass_ = seed_two_zone_pass(app, tenant_id)
    with owner.cursor() as cursor:
        cursor.execute("UPDATE garages SET timezone = 'Mars/Olympus' WHERE external_id = %s "
                       "AND tenant_id = %s", (TOKYO.id, tenant_id))
        assert cursor.rowcount == 1
    # asked at the readable garage, and at the unreadable one itself: shown both ways
    for asked_at in (DENVER, TOKYO):
        out = shown_or_refused(app, tenant_id, asked_at.id, pass_.id)
        assert set(out) == KEYS, f"the read refused at {asked_at.id!r}: {out}"
        assert out["unreadable"] is None
        assert out["registrations"] == expected_rows()
        assert list(out["unreadable_garages"]) == [TOKYO.id]
        named = out["unreadable_garages"][TOKYO.id]
        assert named.code == f.REFUSAL_TIMEZONE_UNKNOWN and named.field == "garage.timezone"
        assert "Mars/Olympus" in named.detail
    # THE CONTROL: a write at the unreadable garage is refused by name, today's rule
    with tenant(app, tenant_id) as cursor, pytest.raises(f.Refused) as refused:
        register_vehicle(cursor, tenant_id, TOKYO.id, pass_.id, "CAR-Z", date(2026, 9, 1))
    app.rollback()
    assert refused.value.code == f.REFUSAL_TIMEZONE_UNKNOWN
    assert "set-garage-timezone" in refused.value.detail


# ---------------------------------------------------------------------------
# the refusals a read can meet
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G26")
@store_test
def test_no_such_pass_no_such_garage_and_a_garage_the_pass_does_not_name_are_refused_by_name(
    app, tenant_id
):
    pass_ = seed_two_zone_pass(app, tenant_id, extra=(ELSEWHERE,))
    control = shown_or_refused(app, tenant_id, DENVER.id, pass_.id)
    assert "registrations" in control and len(control["registrations"]) == 8
    nobody = shown_or_refused(app, tenant_id, DENVER.id, "pass-nobody")
    assert nobody == {"refused": f.REFUSAL_PASS_NOT_FOUND, "detail": "no pass 'pass-nobody'."}
    nowhere = shown_or_refused(app, tenant_id, "garage-nowhere", pass_.id)
    assert nowhere == {"refused": f.REFUSAL_GARAGE_NOT_FOUND,
                       "detail": "no garage 'garage-nowhere'."}
    # a garage the tenant has, that the pass does not name: G25's membership,
    # naming the set -- the read is not a way round it
    elsewhere = shown_or_refused(app, tenant_id, ELSEWHERE.id, pass_.id)
    assert elsewhere.get("refused") == f.REFUSAL_PASS_NOT_FOUND, elsewhere
    assert "'garage-elsewhere'" in elsewhere["detail"]
    assert "garage-denver" in elsewhere["detail"] and "Garage-tokyo" in elsewhere["detail"]


# ---------------------------------------------------------------------------
# another tenant's pass with the same id
# ---------------------------------------------------------------------------


def _rls(owner, enabled: bool) -> None:
    verb = "ENABLE" if enabled else "DISABLE"
    with owner.cursor() as cursor:
        for table in all_tables(owner):
            cursor.execute(f'ALTER TABLE "{table}" {verb} ROW LEVEL SECURITY')


@pytest.mark.guarantee("G26")
@store_test
def test_another_tenants_pass_with_the_same_id_is_not_shown_with_rls_on_and_with_it_off(
    app, owner, tenant_id
):
    """Two tenants, one pass id, different cars. Each tenant reads its own
    rows and never the other's -- beside its own as the known-shown control
    -- with row-level security on (the product's state), and then with it
    OFF on every table, so the read's own tenant predicate is proven to hold
    alone. A third tenant with no such pass is refused by name."""
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
            got = shown_or_refused(app, t, DENVER.id, "pass-1")
            out[t] = sorted({r["vehicle_identity"] for r in got["registrations"]}) \
                if "registrations" in got else got["refused"]
        return out

    expected = {tenant_id: ["CAR-MINE"], other: ["CAR-THEIRS"], third: f.REFUSAL_GARAGE_NOT_FOUND}
    assert reading() == expected, "with row-level security ON"
    def both_visible_to_the_app() -> bool:
        """A bare query as the application role, no tenant set: the two
        tenants' rows are visible only with the policy off."""
        with app.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM passes WHERE external_id = 'pass-1' "
                           "AND tenant_id = ANY(%s)", ([tenant_id, other],))
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
# a registration outside the pass's garage set
# ---------------------------------------------------------------------------

OUTSIDE = "vehicle_registrations_garage_of_pass"


@pytest.mark.guarantee("G26")
@store_test
def test_a_registration_outside_the_set_is_refused_by_the_constraint_and_shown_if_planted_past_it(
    app, owner, tenant_id
):
    import psycopg

    pass_ = seed_two_zone_pass(app, tenant_id, extra=(ELSEWHERE,))
    ids = dict(query(app, tenant_id, "SELECT external_id, id FROM garages"))
    (pass_uuid,) = query(app, tenant_id, "SELECT id FROM passes")[0]
    insert = ("INSERT INTO vehicle_registrations (tenant_id, garage_id, pass_id, "
              "vehicle_identity, effective_day) VALUES (%s, %s, %s, 'CAR-OUT', '2026-01-01')")
    # 1. the constraint, by name: a raw insert as the OWNER at a garage the
    #    pass does not name is refused
    with owner.cursor() as cursor, pytest.raises(psycopg.errors.ForeignKeyViolation) as raised:
        cursor.execute(insert, (tenant_id, ids[ELSEWHERE.id], pass_uuid))
    assert raised.value.diag.constraint_name == OUTSIDE
    # 2. and the membership row under a registration cannot be removed
    with owner.cursor() as cursor, pytest.raises(psycopg.errors.ForeignKeyViolation) as raised:
        cursor.execute("DELETE FROM pass_garages WHERE tenant_id = %s AND pass_id = %s "
                       "AND garage_id = %s", (tenant_id, pass_uuid, ids[TOKYO.id]))
    assert raised.value.diag.constraint_name == OUTSIDE
    # the control for both: the same insert INSIDE the set is accepted
    with owner.cursor() as cursor:
        cursor.execute(insert.replace("CAR-OUT", "CAR-IN"), (tenant_id, ids[DENVER.id], pass_uuid))
    assert len(shown(app, tenant_id, DENVER.id, pass_.id)["registrations"]) == 9
    # 3. planted PAST the constraint -- its triggers disabled, which only a
    #    superuser may do -- the read shows the row and names the garage
    with owner.cursor() as cursor:
        cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        assert cursor.fetchone() == (True,), "the owner must be a superuser to plant this"
        cursor.execute("ALTER TABLE vehicle_registrations DISABLE TRIGGER ALL")
        try:
            cursor.execute(insert, (tenant_id, ids[ELSEWHERE.id], pass_uuid))
        finally:
            cursor.execute("ALTER TABLE vehicle_registrations ENABLE TRIGGER ALL")
    out = shown(app, tenant_id, DENVER.id, pass_.id)
    outside = [r for r in out["registrations"] if r["garage"] == ELSEWHERE.id]
    assert len(out["registrations"]) == 10 and len(outside) == 1, "the row was dropped"
    assert outside[0]["vehicle_identity"] == "CAR-OUT"
    assert out["garages"] == ["Garage-tokyo", "garage-denver"]
    assert out["garages_not_named"] == [ELSEWHERE.id]


# ---------------------------------------------------------------------------
# every writer of the register and of the garage set, derived from the source,
# and the read reflects each
# ---------------------------------------------------------------------------

WRITES = re.compile(r"(INSERT INTO|UPDATE) (vehicle_registrations|pass_garages)\b")


def register_writers() -> list[tuple[str, str]]:
    """Every statement in the package that writes ``vehicle_registrations`` or
    ``pass_garages``: (verb, table), in source order -- read from the source,
    never typed, so a writer added tomorrow fails the census below until the
    read is proven to reflect it."""
    src = Path(__file__).resolve().parent.parent / "src" / "garage_pass"
    found = []
    for path in sorted(src.rglob("*.py")):
        found += [m.groups() for m in WRITES.finditer(path.read_text())]
    return found


@pytest.mark.guarantee("G26")
@store_test
def test_every_writer_of_the_register_is_reflected_by_the_read(app, tenant_id):
    """The census: five write sites -- the set's INSERT (create_pass), the
    register's INSERT (register_vehicle, which redeem_enrolment goes through),
    and its three UPDATEs (the revocation's, the expiry release's, and
    end_registration's). Each is exercised and its effect read back:
    ``ended_reason`` tells the three UPDATEs apart."""
    from fixtures import BOTH, at
    from garage_pass.passes import State
    from garage_pass.store.records import change_state, end_registration
    from garage_pass.terms import Terms

    assert register_writers() == [
        ("INSERT INTO", "pass_garages"),
        ("UPDATE", "vehicle_registrations"),  # change_state -> revoked
        ("UPDATE", "vehicle_registrations"),  # register_vehicle: the expiry release
        ("INSERT INTO", "vehicle_registrations"),  # register_vehicle
        ("UPDATE", "vehicle_registrations"),  # end_registration
    ], "a writer of the register or the set was added or moved: prove the read reflects it"
    expiring = a_pass(id="pass-expiring", garage_ids={DENVER.id, TOKYO.id},
                      terms=Terms(directions=BOTH, valid_to=date(2026, 6, 30)))
    successor = a_pass(id="pass-successor", garage_ids={DENVER.id, TOKYO.id})
    with tenant(app, tenant_id) as cursor:
        for garage in (DENVER, TOKYO):
            store_garage(cursor, tenant_id, garage)
        for pass_ in (expiring, successor):  # the set's INSERT, twice
            create_pass(cursor, tenant_id, DENVER.id, pass_, by="seed", at=CREATED_AT)
        # the register's INSERT: CAR-X on the expiring pass, open
        register_vehicle(cursor, tenant_id, DENVER.id, expiring.id, "CAR-X", date(2026, 1, 1))
        # the expiry release: CAR-X registered onto the successor after the
        # first pass's valid_to ends the first registration by expiry
        register_vehicle(cursor, tenant_id, TOKYO.id, successor.id, "CAR-X", date(2026, 8, 1))
        # end_registration's UPDATE: a second car, ended by the owner
        register_vehicle(cursor, tenant_id, DENVER.id, successor.id, "CAR-Y", date(2026, 8, 1))
        end_registration(cursor, tenant_id, TOKYO.id, successor.id, "CAR-Y", date(2026, 8, 15))
        # the revocation's UPDATE: the successor revoked at an instant that is
        # the same local day at Denver and at Tokyo
        change_state(cursor, tenant_id, DENVER.id, successor.id, State.REVOKED, by="owner",
                     at=at(date(2026, 9, 1), 2), reason="divorced")
    app.commit()
    first = shown(app, tenant_id, TOKYO.id, expiring.id)
    assert first["garages"] == ["Garage-tokyo", "garage-denver"], "the set, from create_pass"
    assert first["state"] == "active"
    assert [(r["vehicle_identity"], r["garage"], r["end_day"], r["ended_reason"])
            for r in first["registrations"]] == [
        ("CAR-X", "Garage-tokyo", date(2026, 7, 1), "pass valid_to passed"),
        ("CAR-X", "garage-denver", date(2026, 7, 1), "pass valid_to passed"),
    ]
    second = shown(app, tenant_id, DENVER.id, successor.id)
    assert second["state"] == "revoked"
    assert [(r["vehicle_identity"], r["garage"], r["effective_day"], r["end_day"],
             r["ended_reason"]) for r in second["registrations"]] == [
        ("CAR-X", "Garage-tokyo", date(2026, 8, 1), date(2026, 9, 1), "pass revoked"),
        ("CAR-X", "garage-denver", date(2026, 8, 1), date(2026, 9, 1), "pass revoked"),
        ("CAR-Y", "Garage-tokyo", date(2026, 8, 1), date(2026, 8, 15), "ended"),
        ("CAR-Y", "garage-denver", date(2026, 8, 1), date(2026, 8, 15), "ended"),
    ]
