"""G29 -- one QR can be cancelled, and nothing else moves.

**THE BRIEF'S CHECK 4.** The guest never received the QR: the desk cancels that
one QR and issues a fresh one. The pass keeps its state, its other QRs keep
working, and every registration stays as it was -- cancelling a QR is not
revoking the pass. Bound or not: a bound QR, cancelled, answers for no car,
while the car it bound stays on the pass (ending the car is end-registration's).

Controls: the cancellation revokes the pass; the cancellation reaches every QR
of the pass.
"""

from __future__ import annotations

from datetime import date

import pytest

from enrolment_harness import (
    TRANSIENT_ENTRY,
    enrolment_row,
    issue,
    pass_state,
    redeem,
    registrations,
    seeded,
    state_changes,
)
from fixtures import at
from garage_pass import findings as f
from garage_pass.access import Outcome
from garage_pass.store.access import access_from_store
from garage_pass.store.enrolments import cancel_code
from garage_pass.store.postgres import tenant
from garage_pass.terms import Direction
from store_harness import needs_postgres, query

pytestmark = needs_postgres

WHEN = at(date(2026, 6, 2), 9)


def cancelled(app, tenant_id, external_id) -> dict:
    with tenant(app, tenant_id) as cursor:
        out = cancel_code(cursor, tenant_id, TRANSIENT_ENTRY.id, external_id, by="desk",
                          at=WHEN, reason="never received")
    app.commit()
    return out


@pytest.mark.guarantee("G29")
@pytest.mark.parametrize("bound", [False, True], ids=["unbound", "bound"])
def test_cancelling_one_qr_leaves_the_pass_its_other_qrs_and_its_registrations(
    app, tenant_id, bound
):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-1")["token"]
    other = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-other")["token"]
    sibling = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-sibling")["token"]
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, other, "CAR-OTHER").redeemed
    if bound:
        assert redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1").redeemed
    state_before = pass_state(app, tenant_id, pass_)
    history_before = state_changes(app, tenant_id)
    registrations_before = registrations(app, tenant_id)
    out = cancelled(app, tenant_id, "qr-1")
    assert out["state"] == "cancelled" and out["was"] == ("redeemed" if bound else "issued")
    assert out["vehicle_identity"] == ("CAR-1" if bound else None)
    row = enrolment_row(app, tenant_id, "qr-1")
    assert row[0] == "cancelled" and row[5:] == ("desk", WHEN, "never received"), row
    # the QR itself: refused CANCELLED
    shown = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1", at=at(date(2026, 6, 2), 10))
    assert shown.refusal is not None and shown.refusal.code == f.REFUSAL_CREDENTIAL_CANCELLED
    assert not shown.recognised and not shown.redeemed
    # nothing else moved: the pass, its history, its registrations
    assert pass_state(app, tenant_id, pass_) == state_before == "active"
    assert state_changes(app, tenant_id) == history_before
    assert registrations(app, tenant_id) == registrations_before
    # the pass's other QRs still work: the bound one is recognised, the
    # outstanding one binds a car
    still = redeem(app, tenant_id, TRANSIENT_ENTRY, other, "CAR-OTHER", at=at(date(2026, 6, 2), 11))
    assert still.recognised and still.answer.outcome is Outcome.COVERED
    fresh = redeem(app, tenant_id, TRANSIENT_ENTRY, sibling, "CAR-NEW", at=at(date(2026, 6, 2), 12))
    assert fresh.redeemed and fresh.answer.outcome is Outcome.COVERED
    if bound:  # the car the QR bound is still on the pass
        car = access_from_store(app, tenant_id, TRANSIENT_ENTRY.id, "CAR-1", "L1",
                                Direction.ENTRY, at(date(2026, 6, 2), 13))
        assert car.outcome is Outcome.COVERED


@pytest.mark.guarantee("G29")
def test_a_fresh_qr_reissued_after_the_cancel_binds_the_car(app, tenant_id):
    """His words: the desk reselects the guest and reissues the code."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-1")
    cancelled(app, tenant_id, "qr-1")
    fresh = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-2",
                  starts_on=date(2026, 6, 2))["token"]
    bound = redeem(app, tenant_id, TRANSIENT_ENTRY, fresh, "CAR-1", at=at(date(2026, 6, 2), 10))
    assert bound.redeemed and bound.answer.outcome is Outcome.COVERED


@pytest.mark.guarantee("G29")
def test_cancelling_twice_or_a_qr_that_does_not_exist_is_refused_and_writes_nothing(
    app, tenant_id
):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-1")
    cancelled(app, tenant_id, "qr-1")
    before = query(app, tenant_id, "SELECT * FROM enrolments ORDER BY external_id")
    for external_id, code in (("qr-1", f.REFUSAL_CREDENTIAL_CANCELLED),
                              ("qr-none", f.REFUSAL_CREDENTIAL_UNKNOWN)):
        with pytest.raises(f.Refused) as refused:
            cancelled(app, tenant_id, external_id)
        app.rollback()
        assert refused.value.code == code
    assert query(app, tenant_id, "SELECT * FROM enrolments ORDER BY external_id") == before
