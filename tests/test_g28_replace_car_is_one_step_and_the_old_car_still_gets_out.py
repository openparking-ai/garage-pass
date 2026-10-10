"""G28 -- replace car is one step, and the old car still gets out.

**THE BRIEF'S CHECK 3.** A rental car is swapped: the desk replaces the car on
the pass from the old car's QR. The old QR stops opening the entry and keeps
opening the exit -- so a car that broke down inside can leave, COVERED, not as
a paying car -- and a new QR for the new car is issued on the same pass. The
old car read by its identity alone (no QR) is answered the same way by the
access call, because the fact is derived from its QR and never stored twice.

**ALL OR NONE.** The exit-only mark and the new QR are one transaction under a
savepoint: a refusal from the new QR's issue (an id already taken) leaves the
old QR exactly as it was, even in a caller that commits.

Controls: the old QR still enters (the redemption's exit-only check planted
away); the old QR refused at the exit too; the engine's exit-only check planted
away; the savepoint planted away.
"""

from __future__ import annotations

from datetime import date

import pytest

from enrolment_harness import (
    GARAGES,
    TRANSIENT_ENTRY,
    enrolment_row,
    issue,
    other_end,
    redeem,
    registrations,
    seeded,
)
from fixtures import NOON_MONDAY, at
from garage_pass import findings as f
from garage_pass.access import Outcome
from garage_pass.enrolment import where_enrolment_happens
from garage_pass.store.access import access_from_store
from garage_pass.store.enrolments import replace_car
from garage_pass.store.postgres import tenant
from garage_pass.terms import Direction
from store_harness import needs_postgres, query

pytestmark = needs_postgres

SWAPPED = at(date(2026, 6, 2), 9)


def replaced(app, tenant_id, garage, old="qr-1", new="qr-2", *, at_=SWAPPED,
             plate="car-new") -> dict:
    with tenant(app, tenant_id) as cursor:
        out = replace_car(cursor, tenant_id, garage.id, old, new, date(2026, 6, 2), 3,
                          by="desk", at=at_, reason="rental swapped", plate=plate)
    app.commit()
    return out


def exit_only_columns(app, tenant_id, external_id="qr-1") -> tuple:
    return query(app, tenant_id, "SELECT state, exit_only_at, exit_only_by, exit_only_reason "
                                 "FROM enrolments WHERE external_id = %s", (external_id,))[0]


@pytest.mark.guarantee("G28")
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
def test_the_old_qr_stops_entering_keeps_leaving_covered_and_the_new_qr_binds_the_new_car(
    app, tenant_id, garage
):
    pass_ = seeded(app, tenant_id, garage)
    token = issue(app, tenant_id, garage, pass_)["token"]
    end = Direction(where_enrolment_happens(garage))
    assert redeem(app, tenant_id, garage, token, "CAR-OLD", direction=end).redeemed
    out = replaced(app, tenant_id, garage)
    assert out["pass"] == pass_.id and out["replaced"]["now"] == "exit_only"
    assert out["replaced"]["vehicle_identity"] == "CAR-OLD"
    assert out["new"]["enrolment"] == "qr-2" and out["new"]["pass"] == pass_.id
    state, when, by, why = exit_only_columns(app, tenant_id)
    assert state == "redeemed" and when == SWAPPED and by == "desk"
    assert "'qr-2'" in why and "rental swapped" in why
    later = at(date(2026, 6, 3), 9)
    # the old QR at an entry: refused EXIT ONLY, and the answer agrees
    entering = redeem(app, tenant_id, garage, token, "CAR-OLD", direction=Direction.ENTRY,
                      at=later)
    assert not entering.recognised and entering.refusal is not None
    assert entering.refusal.code == f.REFUSAL_CREDENTIAL_EXIT_ONLY, entering.refusal
    assert entering.answer.outcome is not Outcome.COVERED
    # the old QR at an exit: recognised, the car COVERED -- it leaves on the pass
    leaving = redeem(app, tenant_id, garage, token, "CAR-OLD", direction=Direction.EXIT, at=later)
    assert leaving.recognised and leaving.refusal is None, leaving.refusal
    assert leaving.answer.outcome is Outcome.COVERED, leaving.answer
    # the old car by its identity alone: the same, from the access call
    by_plate_in = access_from_store(app, tenant_id, garage.id, "CAR-OLD", "L1", Direction.ENTRY,
                                    later)
    assert by_plate_in.outcome is Outcome.NOT_COVERED and by_plate_in.reason == f.EXIT_ONLY
    by_plate_out = access_from_store(app, tenant_id, garage.id, "CAR-OLD", "L1", Direction.EXIT,
                                     later)
    assert by_plate_out.outcome is Outcome.COVERED, by_plate_out
    # the new QR is bound to the new car's plate from issue, on the same pass:
    # registered already, and recognised at its first use
    assert out["new"]["plate"] == "car-new" and out["new"]["plate_key"] == "CARNEW"
    new_token = out["new"]["token"]
    bound = redeem(app, tenant_id, garage, new_token, "CAR-NEW", direction=end, at=later)
    assert bound.recognised and bound.answer.outcome is Outcome.COVERED
    assert ("CARNEW" in [r[1] for r in registrations(app, tenant_id) if r[0] == pass_.id])
    again = redeem(app, tenant_id, garage, new_token, "CAR-NEW", direction=other_end(end),
                   at=later)
    assert again.recognised and again.answer.outcome is Outcome.COVERED


@pytest.mark.guarantee("G28")
def test_a_qr_that_never_bound_is_cancelled_instead_and_the_new_qr_is_issued(app, tenant_id):
    """The guest arrived in a different car before the first entry: no car is
    inside, so the old QR is cancelled, not marked exit only."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    out = replaced(app, tenant_id, TRANSIENT_ENTRY)
    assert out["replaced"] == {"enrolment": "qr-1", "vehicle_identity": None,
                               "now": "cancelled", "at": SWAPPED}
    row = enrolment_row(app, tenant_id)
    assert row[0] == "cancelled" and "'qr-2'" in row[7], row
    shown = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1", at=at(date(2026, 6, 2), 10))
    assert shown.refusal.code == f.REFUSAL_CREDENTIAL_CANCELLED
    assert exit_only_columns(app, tenant_id)[1] is None, "exit only needs a bind"


@pytest.mark.guarantee("G28")
def test_a_cancelled_or_already_replaced_qr_is_refused_by_name_and_nothing_is_written(
    app, tenant_id
):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1").redeemed
    replaced(app, tenant_id, TRANSIENT_ENTRY)
    before = query(app, tenant_id, "SELECT * FROM enrolments ORDER BY external_id")
    with pytest.raises(f.Refused) as twice:
        replaced(app, tenant_id, TRANSIENT_ENTRY, new="qr-3")
    app.rollback()
    assert twice.value.code == f.REFUSAL_CREDENTIAL_ALREADY_REPLACED
    with pytest.raises(f.Refused) as unknown:
        replaced(app, tenant_id, TRANSIENT_ENTRY, old="qr-none", new="qr-3")
    app.rollback()
    assert unknown.value.code == f.REFUSAL_CREDENTIAL_UNKNOWN
    assert query(app, tenant_id, "SELECT * FROM enrolments ORDER BY external_id") == before


@pytest.mark.guarantee("G28")
def test_a_refusal_from_the_new_qr_takes_the_exit_only_mark_back_even_if_the_caller_commits(
    app, tenant_id
):
    """ALL OR NONE: the new QR's id is taken, so its issue refuses AFTER the old
    QR was marked exit only. The savepoint takes the mark back, and a caller
    that commits regardless commits nothing."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-taken")
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1").redeemed
    with tenant(app, tenant_id) as cursor:
        with pytest.raises(f.Refused) as refused:
            replace_car(cursor, tenant_id, TRANSIENT_ENTRY.id, "qr-1", "qr-taken",
                        date(2026, 6, 2), 3, by="desk", at=SWAPPED, reason="rental swapped",
                        plate="CAR-NEW")
    app.commit()  # the caller commits anyway
    assert refused.value.code == f.REFUSAL_CREDENTIAL_ALREADY_EXISTS
    assert exit_only_columns(app, tenant_id)[1:] == (None, None, None), "half a replacement"
    shown = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1", at=NOON_MONDAY)
    assert shown.recognised and shown.answer.outcome is Outcome.COVERED


@pytest.mark.guarantee("G28")
def test_the_schema_refuses_exit_only_without_a_bind_and_a_partial_mark(app, owner, tenant_id):
    """The backstop for a raw write: exit only needs a bind, and its three
    columns are all or none. The control: the same write on a bound row with
    all three is accepted."""
    import psycopg

    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-unbound")
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1").redeemed
    full = "exit_only_at = now(), exit_only_by = 'raw', exit_only_reason = 'raw'"
    for where, assignments, constraint in (
        ("qr-unbound", full, "enrolments_exit_only_needs_a_bind"),
        ("qr-1", "exit_only_at = now()", "enrolments_exit_only_is_all_or_nothing"),
    ):
        with owner.cursor() as cursor, pytest.raises(psycopg.errors.CheckViolation) as raised:
            cursor.execute(f"UPDATE enrolments SET {assignments} WHERE external_id = %s "
                           "AND tenant_id = %s", (where, tenant_id))
        owner.rollback()
        assert raised.value.diag.constraint_name == constraint
    with owner.cursor() as cursor:
        cursor.execute(f"UPDATE enrolments SET {full} WHERE external_id = 'qr-1' "
                       "AND tenant_id = %s", (tenant_id,))
        assert cursor.rowcount == 1
    owner.rollback()


@pytest.mark.guarantee("G28")
def test_every_refusal_of_the_two_writes_is_rendered_through_the_command_line(
    app, owner, tenant_id, capsys, monkeypatch
):
    """The exit-only, already-replaced and cancelled details reach an operator
    through the one seam, so the rendered-sentence collector reads each."""
    import json

    import sweep_route_sentences as sweep

    from _rendered_sentences import rendered_so_far
    from enrolment_harness import app_dsn_into_the_environment
    from garage_pass.cli import main

    app_dsn_into_the_environment(monkeypatch)
    started = len(rendered_so_far())
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1").redeemed
    replaced(app, tenant_id, TRANSIENT_ENTRY)
    T = ["--tenant", str(tenant_id), "--garage", TRANSIENT_ENTRY.id]
    seen = {}
    for argv, code in (
        (["redeem-enrolment", *T, "--token", token, "--vehicle", "CAR-1", "--lane", "L1",
          "--direction", "entry", "--at", "2026-06-03T09:00:00-06:00"],
         f.REFUSAL_CREDENTIAL_EXIT_ONLY),
        (["replace-car", *T, "--enrolment-id", "qr-1", "--new-enrolment-id", "qr-3",
          "--starts-on", "2026-06-03", "--days-valid", "3", "--plate", "CAR-3", "--by", "desk",
          "--reason", "again",
          "--at", "2026-06-03T09:00:00-06:00"], f.REFUSAL_CREDENTIAL_ALREADY_REPLACED),
    ):
        main(argv)
        out = json.loads(capsys.readouterr().out)
        refusal = out["enrolment"] if "enrolment" in out and "answer" in out else out
        assert refusal["refused"] == code, out
        seen[code] = refusal["detail"]
    rendered = rendered_so_far()[started:]
    for code, detail in seen.items():
        assert any(detail == d for d, _stack in rendered), f"{code}'s detail was not collected"
    status, result = sweep.judge_rendered(list(rendered))
    assert result["unjudged"] == [] and result["false"] == [], sweep.report_rendered(result)
    assert status == 0
