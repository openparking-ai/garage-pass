"""G21 -- a redemption refusal is never an exit refusal, and every redemption
is answered.

**THE CENSUS.** Every refusal a redemption can produce is built for real, at
every garage shape R1 produces, and presented at BOTH ends -- the end the
garage enrols at (the named refusal) and the other (the wrong end). Each call
must return an access answer for the movement: at an exit lane, covered or
not-covered with the exit note and never refused-to-answer (G4 holds through
the enrolment path); at an entry, whatever the access call says. The census is
reported N/N, with the number of exits answered, which is this module's own
measure. An exception anywhere is the failure, asserted as one.

Controls: the answer withheld when the redemption is refused (the call raises
instead); a refused redemption at an exit turned into a refused answer.
"""

from __future__ import annotations

from datetime import date

import pytest

from enrolment_harness import (
    GARAGES,
    NO_TRANSIENT,
    TRANSIENT_EXIT,
    issue,
    other_end,
    redeem,
    registrations,
    seeded,
)
from fixtures import NOON_MONDAY, at, simple_terms
from garage_pass import findings as f
from garage_pass.access import Answer, Outcome
from garage_pass.enrolment import where_enrolment_happens
from garage_pass.passes import State
from garage_pass.store.enrolments import Redemption, redeem_enrolment
from garage_pass.store.postgres import tenant
from garage_pass.store.records import change_state, register_vehicle
from garage_pass.terms import Direction
from store_harness import needs_postgres, query

pytestmark = needs_postgres


def assert_exit_is_not_refused(answer: Answer) -> None:
    """The same sentence G4's tests assert, on the answer a redemption carries."""
    assert answer.direction is Direction.EXIT
    assert answer.exit_note == f.EXIT_IS_NEVER_REFUSED
    assert answer.outcome in (Outcome.COVERED, Outcome.NOT_COVERED), (
        f"an exit produced no covered/not-covered answer: {answer}"
    )
    assert answer.missing is None, "an exit was refused an answer"
    if answer.outcome is Outcome.NOT_COVERED:
        assert answer.means == f.MEANS_EXIT_OUT_OF_TERMS


# Every refusal kind: builds the situation and returns what to present, and the
# code expected at the end the garage enrols at. Each is a real row, real state.
def unknown_token(app, owner, tenant_id, garage):
    seeded(app, tenant_id, garage)
    return "no-such-token", "CAR-1", "L1", NOON_MONDAY, f.REFUSAL_CREDENTIAL_UNKNOWN


def already_used(app, owner, tenant_id, garage):
    pass_ = seeded(app, tenant_id, garage)
    token = issue(app, tenant_id, garage, pass_)["token"]
    assert redeem(app, tenant_id, garage, token, "CAR-9").redeemed
    return token, "CAR-1", "L1", at(date(2026, 6, 2), 9), f.REFUSAL_CREDENTIAL_ALREADY_USED


def cancelled(app, owner, tenant_id, garage):
    pass_ = seeded(app, tenant_id, garage)
    token = issue(app, tenant_id, garage, pass_)["token"]
    with tenant(app, tenant_id) as cursor:
        change_state(cursor, tenant_id, garage.id, pass_.id, State.REVOKED, by="o",
                     at=NOON_MONDAY, reason="divorced")
    app.commit()
    return token, "CAR-1", "L1", at(date(2026, 6, 2), 9), f.REFUSAL_CREDENTIAL_CANCELLED


def expired(app, owner, tenant_id, garage):
    pass_ = seeded(app, tenant_id, garage)
    token = issue(app, tenant_id, garage, pass_)["token"]
    return token, "CAR-1", "L1", at(date(2026, 6, 4), 9), f.REFUSAL_CREDENTIAL_EXPIRED


def not_started(app, owner, tenant_id, garage):
    pass_ = seeded(app, tenant_id, garage)
    token = issue(app, tenant_id, garage, pass_)["token"]
    return token, "CAR-1", "L1", at(date(2026, 5, 31), 9), f.REFUSAL_CREDENTIAL_NOT_STARTED


def pass_suspended(app, owner, tenant_id, garage):
    pass_ = seeded(app, tenant_id, garage, state=State.ACTIVE)
    token = issue(app, tenant_id, garage, pass_)["token"]
    with tenant(app, tenant_id) as cursor:
        change_state(cursor, tenant_id, garage.id, pass_.id, State.SUSPENDED, by="o",
                     at=NOON_MONDAY, reason="hold")
    app.commit()
    return token, "CAR-1", "L1", at(date(2026, 6, 2), 9), f.REFUSAL_PASS_NOT_REGISTRABLE


def pass_revoked_with_the_cancellation_put_back(app, owner, tenant_id, garage):
    """The brief's control: the cancellation planted away by a raw write, so the
    pass's own state is what refuses."""
    pass_ = seeded(app, tenant_id, garage)
    token = issue(app, tenant_id, garage, pass_)["token"]
    with tenant(app, tenant_id) as cursor:
        change_state(cursor, tenant_id, garage.id, pass_.id, State.REVOKED, by="o",
                     at=NOON_MONDAY, reason="divorced")
    app.commit()
    with owner.cursor() as cursor:
        cursor.execute(
            "UPDATE enrolments SET state = 'issued', cancelled_by = NULL, cancelled_at = NULL, "
            "cancelled_reason = NULL WHERE tenant_id = %s", (tenant_id,),
        )
    return token, "CAR-1", "L1", at(date(2026, 6, 2), 9), f.REFUSAL_PASS_NOT_REGISTRABLE


def pass_expired(app, owner, tenant_id, garage):
    pass_ = seeded(app, tenant_id, garage,
                   terms=simple_terms(valid_from=date(2026, 1, 1), valid_to=date(2026, 6, 1)))
    token = issue(app, tenant_id, garage, pass_)["token"]  # starts on the pass's last day
    return token, "CAR-1", "L1", at(date(2026, 6, 2), 9), f.REFUSAL_PASS_NOT_REGISTRABLE


def lane_outside_the_terms(app, owner, tenant_id, garage):
    pass_ = seeded(app, tenant_id, garage, terms=simple_terms(allowed_lanes=frozenset({"L1"})))
    token = issue(app, tenant_id, garage, pass_)["token"]
    return token, "CAR-1", "L9", NOON_MONDAY, f.REFUSAL_LANE_OUTSIDE_THE_PASS_TERMS


def identity_on_another_pass(app, owner, tenant_id, garage):
    from fixtures import a_pass
    from garage_pass.store.records import create_pass

    pass_ = seeded(app, tenant_id, garage)
    holder = a_pass(id="pass-other", garage_id=garage.id, state=State.ACTIVE)
    with tenant(app, tenant_id) as cursor:
        create_pass(cursor, tenant_id, garage.id, holder, by="seed", at=NOON_MONDAY)
        register_vehicle(cursor, tenant_id, garage.id, holder.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    token = issue(app, tenant_id, garage, pass_)["token"]
    return token, "CAR-1", "L1", NOON_MONDAY, f.REFUSAL_VEHICLE_ON_ANOTHER_PASS


def blank_identity(app, owner, tenant_id, garage):
    pass_ = seeded(app, tenant_id, garage)
    token = issue(app, tenant_id, garage, pass_)["token"]
    return token, "   ", "L1", NOON_MONDAY, f.REFUSAL_FIELD_BLANK


def unreadable_garage(app, owner, tenant_id, garage):
    pass_ = seeded(app, tenant_id, garage)
    token = issue(app, tenant_id, garage, pass_)["token"]
    with owner.cursor() as cursor:
        cursor.execute("UPDATE garages SET timezone = 'Mars/Olympus' WHERE tenant_id = %s",
                       (tenant_id,))
    return token, "CAR-1", "L1", NOON_MONDAY, f.REFUSAL_TIMEZONE_UNKNOWN


SITUATIONS = [unknown_token, already_used, cancelled, expired, not_started, pass_suspended,
              pass_revoked_with_the_cancellation_put_back, pass_expired, lane_outside_the_terms,
              identity_on_another_pass, blank_identity, unreadable_garage]


def answered(app, tenant_id, garage, token, identity, lane, direction, when) -> Redemption:
    """The subject is 'always answered': an exception here is the failure,
    asserted as one -- never a traceback the runner cannot read."""
    try:
        with tenant(app, tenant_id) as cursor:
            out = redeem_enrolment(cursor, tenant_id, garage.id, token, identity, lane, direction,
                                   when)
        app.commit()
        return out
    except Exception as exc:  # noqa: BLE001 -- any exception is the defect
        app.rollback()
        pytest.fail(f"a redemption raised instead of answering: {exc!r}")


CENSUS: list[tuple[str, str, str, str]] = []


@pytest.mark.guarantee("G21")
@pytest.mark.parametrize("situation", SITUATIONS, ids=[s.__name__ for s in SITUATIONS])
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
def test_every_refusal_at_every_end_is_answered_and_an_exit_is_never_refused(
    app, owner, tenant_id, garage, situation
):
    token, identity, lane, when, code = situation(app, owner, tenant_id, garage)
    end = Direction(where_enrolment_happens(garage))
    before = registrations(app, tenant_id)
    for direction in (end, other_end(end)):
        out = answered(app, tenant_id, garage, token, identity, lane, direction, when)
        assert not out.redeemed and out.refusal is not None
        expected = code if direction is end else f.REFUSAL_ENROLMENT_AT_WRONG_END
        if situation is unreadable_garage:
            expected = code  # answered before the end is asked: no clock
        assert out.refusal.code == expected, (direction, out.refusal)
        assert isinstance(out.answer, Answer) and out.answer.direction is direction
        if direction is Direction.EXIT:
            assert_exit_is_not_refused(out.answer)
        CENSUS.append((garage.id, situation.__name__, direction.value, out.refusal.code))
    assert registrations(app, tenant_id) == before, "a refused redemption wrote a registration"
    assert query(app, tenant_id, "SELECT count(*) FROM enrolments WHERE state = 'redeemed'") == [
        (1 if situation is already_used else 0,)
    ]


@pytest.mark.guarantee("G21")
def test_the_census_is_reported_and_no_exit_went_unanswered():
    """Runs after the matrix (pytest keeps file order): the denominator, in
    words, so a receipt quotes a measured number and not a remembered one."""
    exits = [row for row in CENSUS if row[2] == "exit"]
    print(f"\nCENSUS: {len(CENSUS)} redemptions refused and answered, {len(exits)} of them at "
          f"an exit lane, 0 unanswered exits; {len(SITUATIONS)} refusal kinds x "
          f"{len(GARAGES)} garage shapes x 2 ends")
    assert len(CENSUS) == len(SITUATIONS) * len(GARAGES) * 2
    assert len(exits) == len(SITUATIONS) * len(GARAGES)


@pytest.mark.guarantee("G21")
def test_a_wrong_end_refusal_at_an_exit_still_lets_the_car_out_covered(app, tenant_id):
    """The case the brief names: a garage that enrols at entry, a QR at an
    exit lane -- refused by name, and the movement still covered, because
    the car is on the pass already."""
    pass_ = seeded(app, tenant_id, NO_TRANSIENT, state=State.ACTIVE)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, NO_TRANSIENT.id, pass_.id, "CAR-1", date(2026, 1, 1))
    app.commit()
    token = issue(app, tenant_id, NO_TRANSIENT, pass_)["token"]
    out = redeem(app, tenant_id, NO_TRANSIENT, token, "CAR-1", "L1", direction=Direction.EXIT)
    assert not out.redeemed and out.refusal.code == f.REFUSAL_ENROLMENT_AT_WRONG_END
    assert out.answer.outcome is Outcome.COVERED and out.answer.exit_note == f.EXIT_IS_NEVER_REFUSED
    # and at an exit-enrolling garage, a redemption at the exit is the bind AND the answer
    exit_pass = seeded(app, tenant_id, TRANSIENT_EXIT, id="pass-exit")
    token = issue(app, tenant_id, TRANSIENT_EXIT, exit_pass, "qr-2")["token"]
    out = redeem(app, tenant_id, TRANSIENT_EXIT, token, "CAR-2", "L1")
    assert out.redeemed and out.answer.direction is Direction.EXIT
    assert out.answer.outcome is Outcome.COVERED and out.answer.exit_note == f.EXIT_IS_NEVER_REFUSED
