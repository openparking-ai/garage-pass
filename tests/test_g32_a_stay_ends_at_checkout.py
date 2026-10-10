"""G32 -- a stay ends at checkout, and the same car with its next guest is a new stay.

**THE BRIEF'S CHECKS 1-4** (registry R1, stay ends at checkout). A rental car
comes back with a new guest; after the checkout day it is not the same guest.
A QR made for a plate registers that plate until the QR's LAST DAY -- the
checkout day -- never open. The car's next stay, on another pass, may start on
that day: the earlier registration ends that day by name, the earlier QR lets
the car OUT that day and opens nothing after. Before that day the plate on
another pass is refused by name, naming the earlier stay and its last day. A
stay ended early (end-stay, a checkout) frees the car from that day the same
way. Nothing carries over: a plate read, a match and a QR's answer for the
next stay name the next stay's pass, never the earlier one.

Controls: the next stay refused on the checkout day; the earlier QR entering on
the checkout day; the earlier QR leaving after it; the next stay allowed before
the checkout day; end-stay writing nothing; an earlier QR answered on its own
pass after its stay ended.
"""

from __future__ import annotations

from datetime import date

import pytest

from enrolment_harness import TRANSIENT_ENTRY, issue_plate, redeem, registrations, seeded
from fixtures import a_pass, at
from garage_pass import findings as f
from garage_pass.access import Outcome
from garage_pass.store.access import access_from_store
from garage_pass.store.enrolments import confirm_match
from garage_pass.store.postgres import tenant
from garage_pass.store.records import create_pass, end_stay
from garage_pass.terms import Direction
from store_harness import needs_postgres

pytestmark = needs_postgres

OCT = {d: date(2026, 10, d) for d in range(8, 16)}
DESK = at(OCT[8], 8)


def stay_b(app, tenant_id):
    other = a_pass(id="stay-b", garage_ids={TRANSIENT_ENTRY.id})
    with tenant(app, tenant_id) as cursor:
        create_pass(cursor, tenant_id, TRANSIENT_ENTRY.id, other, by="desk", at=DESK)
    app.commit()
    return other


def minted(make) -> dict:
    """The issue's result, or an assertion naming the refusal: a next stay
    refused is the subject here, not an error."""
    try:
        return make()
    except f.Refused as refused:
        raise AssertionError(f"the next stay was refused: {refused}") from None


def shown(app, tenant_id, token, day, direction, identity="ABC123"):
    return redeem(app, tenant_id, TRANSIENT_ENTRY, token, identity, direction=direction,
                  at=at(OCT[day], 10 if direction is Direction.ENTRY else 11))


def plate_read(app, tenant_id, day, direction=Direction.ENTRY, identity="ABC123"):
    return access_from_store(app, tenant_id, TRANSIENT_ENTRY.id, identity, "L1", direction,
                             at(OCT[day], 12))


@pytest.mark.guarantee("G32")
def test_the_next_stay_starts_on_the_checkout_day_and_the_earlier_qr_only_lets_the_car_out(
    app, tenant_id
):
    """CHECK 1. Stay A, ABC123, last day Oct 12. Stay B, another pass, a QR for
    ABC123 from Oct 12: minted; A's registration ends Oct 12 with its reason;
    B's QR is recognised on Oct 12. A's QR on Oct 12: refused at the entry
    (exit only), let out at the exit on A's own pass; on Oct 13 refused
    everywhere."""
    a = seeded(app, tenant_id, TRANSIENT_ENTRY)
    a_token = issue_plate(app, tenant_id, TRANSIENT_ENTRY, a, "ABC-123", "qr-a",
                          starts_on=OCT[10], days_valid=3, at=DESK)["token"]
    assert [r[1:] for r in registrations(app, tenant_id)] == [
        ("ABC123", OCT[10], OCT[13], "the stay's last day")], "a stay's registration is never open"
    assert shown(app, tenant_id, a_token, 11, Direction.ENTRY).recognised
    b = stay_b(app, tenant_id)
    b_token = minted(lambda: issue_plate(app, tenant_id, TRANSIENT_ENTRY, b, "abc 123", "qr-b",
                                         starts_on=OCT[12], days_valid=3, at=at(OCT[12], 7)))
    assert sorted(r[:5] for r in registrations(app, tenant_id)) == [
        (a.id, "ABC123", OCT[10], OCT[12], "the car's next stay began"),
        (b.id, "ABC123", OCT[12], OCT[15], "the stay's last day"),
    ]
    b_in = shown(app, tenant_id, b_token["token"], 12, Direction.ENTRY)
    assert b_in.recognised and b_in.answer.outcome is Outcome.COVERED
    assert b_in.answer.pass_id == b.id
    a_in = shown(app, tenant_id, a_token, 12, Direction.ENTRY)
    assert a_in.refusal is not None and a_in.refusal.code == f.REFUSAL_CREDENTIAL_EXIT_ONLY, (
        a_in.refusal)
    assert not a_in.recognised
    a_out = shown(app, tenant_id, a_token, 12, Direction.EXIT)
    assert a_out.recognised and a_out.refusal is None, a_out.refusal
    assert a_out.answer.outcome is Outcome.COVERED and a_out.answer.pass_id == a.id
    for direction in (Direction.ENTRY, Direction.EXIT):
        after = shown(app, tenant_id, a_token, 13, direction)
        assert after.refusal is not None, direction
        assert after.refusal.code == f.REFUSAL_CREDENTIAL_STAY_ENDED, after.refusal
        assert not after.recognised and not after.match_required


@pytest.mark.guarantee("G32")
def test_the_next_stay_before_the_checkout_day_is_refused_naming_the_stay_and_its_last_day(
    app, tenant_id
):
    """CHECK 2. Stay B from Oct 11 while A runs to Oct 12 and has not ended:
    refused by name, naming A and Oct 12; nothing is minted or moved."""
    a = seeded(app, tenant_id, TRANSIENT_ENTRY)
    issue_plate(app, tenant_id, TRANSIENT_ENTRY, a, "ABC123", "qr-a", starts_on=OCT[10],
                days_valid=3, at=DESK)
    b = stay_b(app, tenant_id)
    before = registrations(app, tenant_id)
    with pytest.raises(f.Refused) as refused:
        issue_plate(app, tenant_id, TRANSIENT_ENTRY, b, "ABC123", "qr-b", starts_on=OCT[11],
                    days_valid=3, at=DESK)
    app.rollback()
    assert refused.value.code == f.REFUSAL_VEHICLE_ON_ANOTHER_PASS
    assert f"'{a.id}'" in refused.value.detail and "its last day is 2026-10-12" in (
        refused.value.detail), refused.value.detail
    assert registrations(app, tenant_id) == before


@pytest.mark.guarantee("G32")
def test_a_stay_ended_early_frees_the_car_from_that_day_and_its_qr_only_lets_it_out(
    app, tenant_id
):
    """CHECK 3. A, Oct 8 to Oct 12, ends early on Oct 10 (end-stay, a checkout):
    B from Oct 10 is minted; A's QR is exit only on Oct 10 and opens nothing
    after."""
    a = seeded(app, tenant_id, TRANSIENT_ENTRY)
    a_token = issue_plate(app, tenant_id, TRANSIENT_ENTRY, a, "ABC123", "qr-a",
                          starts_on=OCT[8], days_valid=5, at=DESK)["token"]
    with tenant(app, tenant_id) as cursor:
        out = end_stay(cursor, tenant_id, TRANSIENT_ENTRY.id, a.id, OCT[10], by="desk",
                       reason="left early")
    app.commit()
    assert out["ended"] == [{"vehicle_identity": "ABC123", "garage": TRANSIENT_ENTRY.id}]
    assert [r[1:] for r in registrations(app, tenant_id)] == [
        ("ABC123", OCT[8], OCT[10], "checked out (desk): left early")]
    b = stay_b(app, tenant_id)
    b_token = minted(lambda: issue_plate(app, tenant_id, TRANSIENT_ENTRY, b, "ABC123", "qr-b",
                                         starts_on=OCT[10], days_valid=3, at=at(OCT[10], 7)))
    a_in = shown(app, tenant_id, a_token, 10, Direction.ENTRY)
    assert a_in.refusal is not None and a_in.refusal.code == f.REFUSAL_CREDENTIAL_EXIT_ONLY, (
        a_in.refusal)
    a_out = shown(app, tenant_id, a_token, 10, Direction.EXIT)
    assert a_out.recognised and a_out.answer.pass_id == a.id, a_out.refusal
    assert a_out.answer.outcome is Outcome.COVERED
    after = shown(app, tenant_id, a_token, 11, Direction.EXIT)
    assert after.refusal is not None and after.refusal.code == f.REFUSAL_CREDENTIAL_STAY_ENDED
    assert shown(app, tenant_id, b_token["token"], 10, Direction.ENTRY).recognised


@pytest.mark.guarantee("G32")
def test_nothing_carries_over_to_the_next_stay(app, tenant_id):
    """CHECK 4. From B's start, an ABC123 read answers for B's pass only; A's
    QR, shown or confirmed by a picture match after A's stay, is refused and
    never answered on A's pass or as B's."""
    a = seeded(app, tenant_id, TRANSIENT_ENTRY)
    a_token = issue_plate(app, tenant_id, TRANSIENT_ENTRY, a, "ABC123", "qr-a",
                          starts_on=OCT[10], days_valid=3, at=DESK)["token"]
    b = stay_b(app, tenant_id)
    b_token = issue_plate(app, tenant_id, TRANSIENT_ENTRY, b, "ABC123", "qr-b",
                          starts_on=OCT[12], days_valid=3, at=at(OCT[12], 7))["token"]
    assert shown(app, tenant_id, b_token, 12, Direction.ENTRY).recognised  # B's pass active
    for day in (12, 13, 14):
        for direction in (Direction.ENTRY, Direction.EXIT):
            read = plate_read(app, tenant_id, day, direction)
            assert read.pass_id == b.id, (day, direction, read)
    for direction in (Direction.ENTRY, Direction.EXIT):
        old = shown(app, tenant_id, a_token, 13, direction)
        assert old.refusal is not None and old.refusal.code == f.REFUSAL_CREDENTIAL_STAY_ENDED
        assert old.answer.pass_id != a.id, "the earlier stay answered after it ended"
    with tenant(app, tenant_id) as cursor:
        matched = confirm_match(cursor, tenant_id, TRANSIENT_ENTRY.id, "qr-a", matched=True,
                                identity_read=None, decided_by="opa_id", lane="L1",
                                direction=Direction.EXIT, at=at(OCT[13], 15))
    app.commit()
    assert matched.refusal is not None
    assert matched.refusal.code == f.REFUSAL_CREDENTIAL_STAY_ENDED
    assert not matched.recognised and matched.answer.outcome is not Outcome.COVERED


@pytest.mark.guarantee("G32")
def test_end_stay_with_nothing_in_force_is_refused_and_writes_nothing(app, tenant_id):
    """end-stay on a pass that holds nothing on or after the day: refused by
    name; and a revoked or owner-ended registration is never a stay's last day
    (it frees the car FROM its end day, as G1 and G5 say)."""
    a = seeded(app, tenant_id, TRANSIENT_ENTRY)
    issue_plate(app, tenant_id, TRANSIENT_ENTRY, a, "ABC123", "qr-a", starts_on=OCT[8],
                days_valid=2, at=DESK)
    before = registrations(app, tenant_id)
    with tenant(app, tenant_id) as cursor, pytest.raises(f.Refused) as refused:
        end_stay(cursor, tenant_id, TRANSIENT_ENTRY.id, a.id, OCT[12], by="desk",
                 reason="late")
    app.rollback()
    assert refused.value.code == f.REFUSAL_REGISTRATION_NOT_FOUND
    assert registrations(app, tenant_id) == before
