"""G30 -- a car whose identity was not read is never let in blind on a bound QR.

**THE FIX BRIEF'S CHECK 1.** A bound QR shown where the lane read no identity
answers MATCH REQUIRED -- the QR's id and the car it is bound to, for the lane's
picture match -- writes nothing, and its answer opens nothing: an entry is
refused an answer, an exit is not covered (and never refused).

**CHECK 2.** The lane's answer after its match (``confirm_match``): matched is a
recognised use answered for the bound car; not matched is WRONG CAR and opens
nothing. Every answer is kept on the QR's own row, in order, with its instant.

Controls: an unread identity recognised blind; a 'no' recorded as recognised;
the answer not kept.
"""

from __future__ import annotations

from datetime import date

import pytest

from enrolment_harness import GARAGES, TRANSIENT_ENTRY, issue, redeem, registrations, seeded
from fixtures import at
from garage_pass import findings as f
from garage_pass.access import Outcome
from garage_pass.enrolment import where_enrolment_happens
from garage_pass.store.enrolments import cancel_code, confirm_match, replace_car
from garage_pass.store.postgres import tenant
from garage_pass.terms import Direction
from store_harness import needs_postgres, query

pytestmark = needs_postgres

LATER = at(date(2026, 6, 2), 9)


def bound(app, tenant_id, garage=TRANSIENT_ENTRY) -> str:
    pass_ = seeded(app, tenant_id, garage)
    token = issue(app, tenant_id, garage, pass_)["token"]
    end = Direction(where_enrolment_happens(garage))
    assert redeem(app, tenant_id, garage, token, "CAR-1", direction=end).redeemed
    return token


def confirm(app, tenant_id, matched, *, read=None, by="fingerprint",
            direction=Direction.ENTRY, garage=TRANSIENT_ENTRY, external_id="qr-1"):
    with tenant(app, tenant_id) as cursor:
        out = confirm_match(cursor, tenant_id, garage.id, external_id, matched=matched,
                            identity_read=read, decided_by=by, lane="L1", direction=direction,
                            at=LATER)
    app.commit()
    return out


def matches(app, tenant_id, external_id="qr-1") -> list:
    return query(app, tenant_id, "SELECT matches FROM enrolments WHERE external_id = %s",
                 (external_id,))[0][0]


def written(app, tenant_id) -> tuple:
    return (query(app, tenant_id, "SELECT external_id, state, redeemed_vehicle_identity, "
                                  "matches FROM enrolments ORDER BY external_id"),
            registrations(app, tenant_id))


@pytest.mark.guarantee("G30")
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
@pytest.mark.parametrize("unread", ["", "   "], ids=["empty", "blank"])
def test_a_bound_qr_with_no_identity_read_requires_a_match_and_opens_nothing(
    app, tenant_id, garage, unread
):
    token = bound(app, tenant_id, garage)
    before = written(app, tenant_id)
    for direction in (Direction.ENTRY, Direction.EXIT):
        out = redeem(app, tenant_id, garage, token, unread, direction=direction, at=LATER)
        assert out.match_required and not out.recognised and not out.redeemed
        assert out.refusal is None and out.enrolment == "qr-1" and out.match_for == "CAR-1"
        assert out.answer.outcome is not Outcome.COVERED, out.answer
        if direction is Direction.ENTRY:
            assert out.answer.outcome is Outcome.REFUSED_TO_ANSWER
        else:
            assert out.answer.outcome is Outcome.NOT_COVERED
            assert out.answer.exit_note == f.EXIT_IS_NEVER_REFUSED
    assert written(app, tenant_id) == before, "a match request wrote something"
    # the control: the same QR with the identity READ is recognised -- the
    # match is asked for only because nothing was read
    read = redeem(app, tenant_id, garage, token, "CAR-1", direction=Direction.ENTRY, at=LATER)
    assert read.recognised and not read.match_required


@pytest.mark.guarantee("G30")
def test_cancelled_and_exit_only_are_refused_before_a_match_is_asked(app, tenant_id):
    token = bound(app, tenant_id)
    with tenant(app, tenant_id) as cursor:
        replace_car(cursor, tenant_id, TRANSIENT_ENTRY.id, "qr-1", "qr-2", date(2026, 6, 2), 3,
                    by="desk", at=LATER, reason="rental swapped", plate="CAR-NEW")
    app.commit()
    entering = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "", direction=Direction.ENTRY,
                      at=LATER)
    assert entering.refusal.code == f.REFUSAL_CREDENTIAL_EXIT_ONLY and not entering.match_required
    leaving = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "", direction=Direction.EXIT,
                     at=LATER)
    assert leaving.match_required, "at the exit an unread replaced car still needs its match"
    with tenant(app, tenant_id) as cursor:
        cancel_code(cursor, tenant_id, TRANSIENT_ENTRY.id, "qr-1", by="desk", at=LATER,
                    reason="lost")
    app.commit()
    gone = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "", direction=Direction.EXIT, at=LATER)
    assert gone.refusal.code == f.REFUSAL_CREDENTIAL_CANCELLED and not gone.match_required


@pytest.mark.guarantee("G30")
@pytest.mark.parametrize("by", ["fingerprint", "api"])
def test_a_yes_is_a_recognised_use_a_no_is_wrong_car_and_every_answer_is_kept(
    app, tenant_id, by
):
    bound(app, tenant_id)
    yes = confirm(app, tenant_id, True, by=by)
    assert yes.recognised and yes.refusal is None and not yes.redeemed
    assert yes.answer.outcome is Outcome.COVERED and yes.answer.vehicle_identity == "CAR-1"
    no = confirm(app, tenant_id, False, by=by, direction=Direction.EXIT)
    assert not no.recognised and no.refusal.code == f.REFUSAL_CREDENTIAL_WRONG_CAR
    assert no.answer.outcome is not Outcome.COVERED
    other = confirm(app, tenant_id, True, read="CAR-9", by=by)
    assert not other.recognised and other.refusal.code == f.REFUSAL_CREDENTIAL_WRONG_CAR
    assert other.answer.vehicle_identity == "CAR-9"
    assert other.answer.outcome is not Outcome.COVERED
    kept = matches(app, tenant_id)
    assert [(m["matched"], m["identity_read"], m["decided_by"], m["direction"], m["outcome"])
            for m in kept] == [
        (True, None, by, "entry", "recognised"),
        (False, None, by, "exit", f.REFUSAL_CREDENTIAL_WRONG_CAR),
        (True, "CAR-9", by, "entry", f.REFUSAL_CREDENTIAL_WRONG_CAR),
    ]
    assert all(m["at"] == LATER.isoformat() and m["lane"] == "L1" for m in kept)
    assert [r[1] for r in registrations(app, tenant_id)] == ["CAR-1"], "no car was added"


@pytest.mark.guarantee("G30")
def test_a_yes_on_a_replaced_car_at_an_entry_is_still_exit_only(app, tenant_id):
    bound(app, tenant_id)
    with tenant(app, tenant_id) as cursor:
        replace_car(cursor, tenant_id, TRANSIENT_ENTRY.id, "qr-1", "qr-2", date(2026, 6, 2), 3,
                    by="desk", at=LATER, reason="rental swapped", plate="CAR-NEW")
    app.commit()
    entering = confirm(app, tenant_id, True)
    assert entering.refusal.code == f.REFUSAL_CREDENTIAL_EXIT_ONLY and not entering.recognised
    leaving = confirm(app, tenant_id, True, direction=Direction.EXIT)
    assert leaving.recognised and leaving.answer.outcome is Outcome.COVERED
    assert [m["outcome"] for m in matches(app, tenant_id)] == [
        f.REFUSAL_CREDENTIAL_EXIT_ONLY, "recognised"]


@pytest.mark.guarantee("G30")
def test_an_unbound_cancelled_or_unknown_qr_and_an_unknown_decider_are_refused_and_keep_nothing(
    app, tenant_id
):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-unbound")
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-1")["token"]
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1").redeemed
    for kwargs, code in (
        ({"external_id": "qr-unbound"}, f.REFUSAL_CREDENTIAL_NOT_BOUND),
        ({"external_id": "qr-none"}, f.REFUSAL_CREDENTIAL_UNKNOWN),
        ({"by": "a guess"}, f.REFUSAL_MATCH_DECIDED_BY_UNKNOWN),
    ):
        with pytest.raises(f.Refused) as refused:
            confirm(app, tenant_id, True, **kwargs)
        app.rollback()
        assert refused.value.code == code, refused.value
    with tenant(app, tenant_id) as cursor:
        cancel_code(cursor, tenant_id, TRANSIENT_ENTRY.id, "qr-1", by="desk", at=LATER,
                    reason="lost")
    app.commit()
    with pytest.raises(f.Refused) as refused:
        confirm(app, tenant_id, True)
    app.rollback()
    assert refused.value.code == f.REFUSAL_CREDENTIAL_CANCELLED
    assert matches(app, tenant_id) == [] and matches(app, tenant_id, "qr-unbound") == []


@pytest.mark.guarantee("G30")
def test_the_match_and_its_refusals_are_rendered_through_the_command_line(
    app, tenant_id, capsys, monkeypatch
):
    import json

    import sweep_route_sentences as sweep

    from _rendered_sentences import rendered_so_far
    from enrolment_harness import app_dsn_into_the_environment
    from garage_pass.cli import main

    app_dsn_into_the_environment(monkeypatch)
    started = len(rendered_so_far())
    token = bound(app, tenant_id)
    T = ["--tenant", str(tenant_id), "--garage", TRANSIENT_ENTRY.id]
    MOVE = ["--lane", "L1", "--direction", "entry", "--at", LATER.isoformat()]
    status = main(["redeem-enrolment", *T, "--token", token, "--vehicle", "", *MOVE])
    out = json.loads(capsys.readouterr().out)
    assert out["enrolment"]["match_required"] is True and out["enrolment"]["match_for"] == "CAR-1"
    assert status == 2, "an entry with no identity is refused an answer"
    status = main(["confirm-match", *T, "--enrolment-id", "qr-1", "--matched", "yes",
                   "--decided-by", "api", *MOVE])
    out = json.loads(capsys.readouterr().out)
    assert status == 0 and out["enrolment"]["recognised"] is True
    status = main(["confirm-match", *T, "--enrolment-id", "qr-1", "--matched", "no",
                   "--decided-by", "fingerprint", *MOVE])
    out = json.loads(capsys.readouterr().out)
    assert out["enrolment"]["refused"] == f.REFUSAL_CREDENTIAL_WRONG_CAR
    wrong = out["enrolment"]["detail"]
    status = main(["confirm-match", *T, "--enrolment-id", "qr-1", "--matched", "yes",
                   "--decided-by", "nobody", *MOVE])
    out = json.loads(capsys.readouterr().out)
    assert status == 3 and out["refused"] == f.REFUSAL_MATCH_DECIDED_BY_UNKNOWN
    rendered = rendered_so_far()[started:]
    for detail in (wrong, out["detail"]):
        assert any(detail == d for d, _stack in rendered), detail
    status, result = sweep.judge_rendered(list(rendered))
    assert result["unjudged"] == [] and result["false"] == [], sweep.report_rendered(result)
    assert len(matches(app, tenant_id)) == 2, "the refused call kept nothing"
