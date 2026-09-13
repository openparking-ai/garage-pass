"""G19 -- one QR, one car, once. The enrolment is a one-time credential and a
redemption is one transaction.

**WHAT A REDEMPTION WRITES, AND THAT IT WRITES ALL OF IT OR NONE.** The
registration effective on the garage's local day; the pass to active where it
was draft or awaiting enrolment (recorded, with the enrolment as the actor);
the enrolment marked redeemed with the identity, the lane, the direction and
the instant; and the access answer read from those rows. A refusal anywhere --
by name, before a write; or after one, from a later step -- rolls back to the
savepoint and nothing stands. The test for the second shape injects a failure
AFTER the registration was written and requires no registration afterwards: a
QR that half-lands is a QR that can be used twice.

**THE DAY IS THE GARAGE'S LOCAL DAY.** A three-day QR from June 1st at a Denver
garage is good at 23:30 Denver on June 3rd -- 05:30 UTC on the 4th -- and
expired half an hour later. Nobody types ``expired``; typing it is refused by
its own code.

**REVOKED IS REVOKED, AND THE STATE CHECK IS LOAD-BEARING.** Revoking a pass
cancels every outstanding credential on it in the same transaction; and with
that cancellation put back by hand (a raw write as the owner, the shape the
brief calls "planting the cancellation away"), the redemption still refuses
the revoked pass by its own state check, naming the state.

Controls: the already-redeemed check planted away; the rollback to the
savepoint planted away; the absent days_valid defaulted to three; the derived
expiry planted to never expire; the revocation's cancellation planted away;
the registrable set planted to admit a revoked pass.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from enrolment_harness import (
    DAYS,
    ENROLMENT,
    GARAGES,
    HOLDER_LINK,
    NO_TRANSIENT,
    STARTS_ON,
    TRANSIENT_ENTRY,
    TRANSIENT_EXIT,
    credential,
    enrolment_row,
    issue,
    issue_link,
    link_row,
    pass_state,
    redeem,
    redeem_link,
    registrations,
    seeded,
    state_changes,
)
from fixtures import NOON_MONDAY, at, simple_terms
from garage_pass import findings as f
from garage_pass.access import Outcome
from garage_pass.enrolment import (
    CANCELLED_BY_REVOCATION,
    CredentialState,
    credential_state,
    digest,
    last_day,
    mint,
    parse_credential_state,
    payload_of,
    require_days_valid,
    token_of,
)
from garage_pass.passes import State
from garage_pass.store.postgres import tenant
from garage_pass.store.records import change_state
from garage_pass.terms import Direction
from store_harness import needs_postgres, query

pytestmark = needs_postgres


# ---------------------------------------------------------------------------
# pure
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G19")
def test_a_minted_token_is_random_urlsafe_and_known_only_by_its_digest():
    a, b = mint(), mint()
    assert a.token != b.token and len(a.token) >= 43
    assert a.sha256 == digest(a.token) and len(a.sha256) == 64
    assert a.payload == payload_of(a.token) and a.payload.endswith(a.token)
    assert token_of(a.payload) == a.token and token_of(a.token) == a.token
    assert token_of(f"  {a.payload} \n") == a.token


@pytest.mark.guarantee("G19")
def test_days_valid_is_stated_never_defaulted_and_positive():
    assert require_days_valid(3) == 3 and require_days_valid(1) == 1
    with pytest.raises(f.Refused) as refused:
        require_days_valid(None)
    assert refused.value.code == f.REFUSAL_DAYS_VALID_NOT_STATED
    assert refused.value.field == "days_valid"
    for bad in (0, -1, True, "3", 2.5):
        with pytest.raises(f.Refused) as refused:
            require_days_valid(bad)
        assert refused.value.code == f.REFUSAL_DAYS_VALID_NOT_POSITIVE, bad


@pytest.mark.guarantee("G19")
def test_expired_is_derived_in_the_local_day_and_cannot_be_typed():
    assert last_day(STARTS_ON, 3) == date(2026, 6, 3)
    assert last_day(STARTS_ON, 1) == STARTS_ON
    issued = CredentialState.ISSUED
    assert credential_state(STARTS_ON, 3, issued, date(2026, 6, 3)) == "issued"
    assert credential_state(STARTS_ON, 3, issued, date(2026, 6, 4)) == "expired"
    assert credential_state(STARTS_ON, 3, issued, date(2026, 5, 31)) == "issued", (
        "not-yet-started is a refusal at redemption, not a state"
    )
    # the terminal states outrank expiry
    assert credential_state(STARTS_ON, 3, CredentialState.REDEEMED, date(2027, 1, 1)) == "redeemed"
    cancelled = CredentialState.CANCELLED
    assert credential_state(STARTS_ON, 3, cancelled, date(2027, 1, 1)) == "cancelled"
    with pytest.raises(f.Refused) as refused:
        parse_credential_state("expired")
    assert refused.value.code == f.REFUSAL_ENROLMENT_EXPIRED_IS_DERIVED
    with pytest.raises(f.Refused) as refused:
        parse_credential_state("used")
    assert refused.value.code == f.REFUSAL_STATE_UNKNOWN
    assert parse_credential_state("redeemed") is CredentialState.REDEEMED


# ---------------------------------------------------------------------------
# the store: issue, redeem, and the four writes as one
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G19")
def test_issue_returns_the_token_once_and_the_row_holds_the_digest(app, tenant_id):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    out = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, vehicle_description="silver Toyota")
    assert out["enrolment"] == "qr-1" and out["pass"] == pass_.id
    assert out["payload"] == payload_of(out["token"])
    assert out["starts_on"] == STARTS_ON and out["days_valid"] == DAYS
    assert out["last_day"] == date(2026, 6, 3) and out["state"] == "issued"
    assert out["vehicle_description"] == "silver Toyota"
    assert query(app, tenant_id, "SELECT token_sha256, state, issued_by FROM enrolments") == [
        (digest(out["token"]), "issued", "owner")
    ]
    read = credential(app, tenant_id, "qr-1")
    assert read.id == "qr-1" and read.state is CredentialState.ISSUED
    assert read.vehicle_description == "silver Toyota" and read.last_day == date(2026, 6, 3)
    assert not any(v == out["token"] for v in vars(read).values()), "a read yielded the token"


@pytest.mark.guarantee("G19")
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
def test_a_redemption_writes_all_four_and_the_pass_moves_to_active_with_the_enrolment_as_actor(
    app, tenant_id, garage
):
    pass_ = seeded(app, tenant_id, garage, state=State.DRAFT)
    token = issue(app, tenant_id, garage, pass_)["token"]
    when = at(date(2026, 6, 2), 9)
    out = redeem(app, tenant_id, garage, token, "CAR-1", "L1", at=when)
    assert out.redeemed and out.refusal is None and out.enrolment == "qr-1"
    # 1. the registration, effective on the garage's local day
    assert out.registration["vehicle_identity"] == "CAR-1"
    assert out.registration["effective_day"] == date(2026, 6, 2)
    assert registrations(app, tenant_id) == [(pass_.id, "CAR-1", date(2026, 6, 2), None, None)]
    # 2. the pass to active, recorded, the enrolment as the actor
    assert pass_state(app, tenant_id, pass_) == "active"
    assert out.pass_state_change["from"] == "draft" and out.pass_state_change["to"] == "active"
    assert state_changes(app, tenant_id) == [
        (None, "draft", "seed", "created"),
        ("draft", "active", "qr-1", "redeemed at lane 'L1'"),
    ]
    # 3. the enrolment redeemed: identity, lane, direction, instant
    end = "entry" if garage is not TRANSIENT_EXIT else "exit"
    assert enrolment_row(app, tenant_id) == ("redeemed", "CAR-1", "L1", end, when, None, None, None)
    # 4. the answer for that same movement -- covered, now that the car is on it
    assert out.answer.outcome is Outcome.COVERED and out.answer.pass_id == pass_.id
    assert out.answer.direction.value == end


@pytest.mark.guarantee("G19")
def test_a_pass_already_active_takes_no_transition_the_second_car_on_a_pooled_pass(app, tenant_id):
    """Several outstanding enrolments on one pass are intended; each redeems to
    one car and dies. The first moves the pass to active; the second finds it
    there and records nothing about the state."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY, state=State.AWAITING_ENROLMENT)
    first = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-1")["token"]
    second = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-2")["token"]
    one = redeem(app, tenant_id, TRANSIENT_ENTRY, first, "CAR-1")
    two = redeem(app, tenant_id, TRANSIENT_ENTRY, second, "CAR-2", at=at(date(2026, 6, 2), 9))
    assert one.redeemed and two.redeemed
    assert one.pass_state_change["from"] == "awaiting_enrolment"
    assert two.pass_state_change is None, "active -> active is not a transition"
    assert [c[:3] for c in state_changes(app, tenant_id)] == [
        (None, "awaiting_enrolment", "seed"), ("awaiting_enrolment", "active", "qr-1"),
    ]
    assert [r[:2] for r in registrations(app, tenant_id)] == [(pass_.id, "CAR-1"),
                                                             (pass_.id, "CAR-2")]
    assert enrolment_row(app, tenant_id, "qr-1")[1] == "CAR-1"
    assert enrolment_row(app, tenant_id, "qr-2")[1] == "CAR-2"
    assert two.answer.outcome is Outcome.COVERED and two.answer.vehicle_identity == "CAR-2"


@pytest.mark.guarantee("G19")
def test_a_redeemed_enrolment_can_never_be_redeemed_again(app, tenant_id):
    """The same car scanning again, and a different car with the used QR: both
    refused by name, nothing written. The same car is still COVERED -- it is
    on the pass -- and the other car is not: the answer is the access call's."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    first = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1")
    assert first.redeemed
    again = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1", at=at(date(2026, 6, 2), 9))
    assert not again.redeemed and again.refusal.code == f.REFUSAL_CREDENTIAL_ALREADY_USED
    assert again.enrolment == "qr-1" and "'qr-1'" in again.refusal.detail
    assert again.registration is None and again.pass_state_change is None
    assert again.answer.outcome is Outcome.COVERED, "CAR-1 is on the pass: the answer says so"
    other = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-2", at=at(date(2026, 6, 2), 9))
    assert not other.redeemed and other.refusal.code == f.REFUSAL_CREDENTIAL_ALREADY_USED
    assert other.answer.outcome is Outcome.NOT_COVERED and other.answer.reason == f.NO_PASS
    assert len(registrations(app, tenant_id)) == 1
    assert enrolment_row(app, tenant_id)[1] == "CAR-1", "the first redemption stands"


@pytest.mark.guarantee("G19")
def test_a_qr_redeemed_one_day_late_is_expired_in_the_garages_local_day(app, tenant_id):
    """23:30 Denver on the last day is 05:30 UTC the next day and still good;
    local midnight is expired."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    late = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1", at=at(date(2026, 6, 4), 12))
    assert not late.redeemed and late.refusal.code == f.REFUSAL_CREDENTIAL_EXPIRED
    assert "2026-06-03" in late.refusal.detail and "2026-06-04" in late.refusal.detail
    assert registrations(app, tenant_id) == [] and enrolment_row(app, tenant_id)[0] == "issued"
    midnight = datetime(2026, 6, 4, 6, 0, tzinfo=UTC)  # 00:00 Denver on the 4th
    assert not redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1", at=midnight).redeemed
    still_good = datetime(2026, 6, 4, 5, 30, tzinfo=UTC)  # 23:30 Denver on the 3rd
    good = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1", at=still_good)
    assert good.redeemed, good.refusal
    assert registrations(app, tenant_id)[0][2] == date(2026, 6, 3), "effective on the LOCAL day"


@pytest.mark.guarantee("G19")
def test_a_qr_presented_before_it_starts_is_refused_and_writes_nothing(app, tenant_id):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    early = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1", at=at(date(2026, 5, 31), 23))
    assert not early.redeemed and early.refusal.code == f.REFUSAL_CREDENTIAL_NOT_STARTED
    assert registrations(app, tenant_id) == [] and pass_state(app, tenant_id, pass_) == "draft"


@pytest.mark.guarantee("G19")
def test_an_unknown_token_is_refused_naming_neither_the_token_nor_any_credential(app, tenant_id):
    seeded(app, tenant_id, TRANSIENT_ENTRY)
    out = redeem(app, tenant_id, TRANSIENT_ENTRY, "not-a-token-anyone-issued", "CAR-1")
    assert not out.redeemed and out.refusal.code == f.REFUSAL_CREDENTIAL_UNKNOWN
    assert out.enrolment is None and "not-a-token" not in out.refusal.detail
    assert out.answer.outcome is Outcome.NOT_COVERED and out.answer.reason == f.NO_PASS


@pytest.mark.guarantee("G19")
def test_days_valid_absent_at_issue_is_refused_by_name_and_nothing_is_minted(app, tenant_id):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    with pytest.raises(f.Refused) as refused:
        issue(app, tenant_id, TRANSIENT_ENTRY, pass_, days_valid=None)
    app.rollback()
    assert refused.value.code == f.REFUSAL_DAYS_VALID_NOT_STATED
    with pytest.raises(f.Refused) as refused:
        issue_link(app, tenant_id, TRANSIENT_ENTRY, pass_, days_valid=0)
    app.rollback()
    assert refused.value.code == f.REFUSAL_DAYS_VALID_NOT_POSITIVE
    assert query(app, tenant_id, "SELECT count(*) FROM enrolments") == [(0,)]
    assert query(app, tenant_id, "SELECT count(*) FROM holder_links") == [(0,)]


@pytest.mark.guarantee("G19")
def test_a_credential_is_issued_onto_a_registrable_pass_only(app, tenant_id):
    """Revoked and suspended by their state; expired -- derived from valid_to
    against the credential's starts_on -- by name; and a second credential
    with the same id is refused by name."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY, state=State.ACTIVE)
    with tenant(app, tenant_id) as cursor:
        change_state(cursor, tenant_id, TRANSIENT_ENTRY.id, pass_.id, State.SUSPENDED, by="o",
                     at=NOON_MONDAY, reason="hold")
    app.commit()
    with pytest.raises(f.Refused) as refused:
        issue(app, tenant_id, TRANSIENT_ENTRY, pass_)
    app.rollback()
    assert refused.value.code == f.REFUSAL_PASS_NOT_REGISTRABLE and "suspended" in (
        refused.value.detail
    )
    over = seeded(app, tenant_id, NO_TRANSIENT, id="pass-over",
                  terms=simple_terms(valid_from=date(2025, 1, 1), valid_to=date(2025, 12, 31)))
    with pytest.raises(f.Refused) as refused:
        issue(app, tenant_id, NO_TRANSIENT, over)
    app.rollback()
    assert refused.value.code == f.REFUSAL_PASS_NOT_REGISTRABLE
    assert "expired" in refused.value.detail
    live = seeded(app, tenant_id, TRANSIENT_EXIT, id="pass-live")
    issue(app, tenant_id, TRANSIENT_EXIT, live, "qr-x")
    with pytest.raises(f.Refused) as refused:
        issue(app, tenant_id, TRANSIENT_EXIT, live, "qr-x")
    app.rollback()
    assert refused.value.code == f.REFUSAL_CREDENTIAL_ALREADY_EXISTS
    assert query(app, tenant_id, "SELECT count(*) FROM enrolments") == [(1,)]


@pytest.mark.guarantee("G19")
def test_a_refusal_after_the_registration_was_written_leaves_nothing_written(
    app, tenant_id, monkeypatch
):
    """ATOMICITY, with the failure injected AFTER a write: the registration
    lands, then the pass's move to active is refused. The savepoint takes the
    registration back; the enrolment is still issued; the answer is read from
    the rows as they stood -- no pass."""
    from garage_pass.store import enrolments

    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    real = enrolments.change_state

    def fails_after_the_registration(cursor, *args, **kwargs):
        # on the transaction's own cursor: the write is visible here and nowhere else yet
        cursor.execute("SELECT count(*) FROM vehicle_registrations")
        assert cursor.fetchone()[0] == 1, "the registration was written before this step"
        raise f.Refused(f.REFUSAL_STATE_TRANSITION_NOT_ALLOWED, "state", "injected after step 1")

    monkeypatch.setattr(enrolments, "change_state", fails_after_the_registration)
    out = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1")
    monkeypatch.setattr(enrolments, "change_state", real)
    assert not out.redeemed and out.refusal.code == f.REFUSAL_STATE_TRANSITION_NOT_ALLOWED
    assert registrations(app, tenant_id) == [], "the registration was taken back"
    assert pass_state(app, tenant_id, pass_) == "draft"
    assert enrolment_row(app, tenant_id)[0] == "issued"
    assert out.answer.outcome is Outcome.NOT_COVERED and out.answer.reason == f.NO_PASS
    # and the QR still works, once
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1").redeemed
    assert not redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1").redeemed


@pytest.mark.guarantee("G19")
def test_revocation_cancels_every_outstanding_credential_and_the_state_check_still_refuses(
    app, owner, tenant_id
):
    """R5: outstanding enrolments and links are cancelled with the revocation
    -- by the revoker, at the revocation instant, 'pass revoked' -- and
    redeemed ones are left as they are. Then the brief's control, in the
    test: the cancellation put back by a raw write, and the redemption must
    refuse the revoked pass by its own state check."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    used = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-used")["token"]
    outstanding = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-outstanding")["token"]
    issue_link(app, tenant_id, TRANSIENT_ENTRY, pass_, "link-1")
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, used, "CAR-1").redeemed
    when = at(date(2026, 6, 2), 9)
    with tenant(app, tenant_id) as cursor:
        out = change_state(cursor, tenant_id, TRANSIENT_ENTRY.id, pass_.id, State.REVOKED,
                           by="owner", at=when, reason="divorced")
    app.commit()
    assert out["enrolments_cancelled"] == 1 and out["holder_links_cancelled"] == 1
    assert out["registrations_ended"] == 1
    assert enrolment_row(app, tenant_id, "qr-outstanding") == (
        "cancelled", None, None, None, None, "owner", when, CANCELLED_BY_REVOCATION,
    )
    assert enrolment_row(app, tenant_id, "qr-used")[0] == "redeemed", "terminal stays terminal"
    assert link_row(app, tenant_id, "link-1") == ("cancelled", None, "owner", when,
                                                 CANCELLED_BY_REVOCATION)
    cancelled = redeem(app, tenant_id, TRANSIENT_ENTRY, outstanding, "CAR-2", at=when)
    assert not cancelled.redeemed and cancelled.refusal.code == f.REFUSAL_CREDENTIAL_CANCELLED
    assert CANCELLED_BY_REVOCATION in cancelled.refusal.detail
    with pytest.raises(f.Refused) as refused:
        redeem_link(app, tenant_id, TRANSIENT_ENTRY, "no-such", at=when)
    app.rollback()
    assert refused.value.code == f.REFUSAL_CREDENTIAL_UNKNOWN
    # THE CONTROL IN THE TEST: the cancellation planted away, by a raw write
    with owner.cursor() as cursor:
        cursor.execute(
            "UPDATE enrolments SET state = 'issued', cancelled_by = NULL, cancelled_at = NULL, "
            "cancelled_reason = NULL WHERE tenant_id = %s AND external_id = 'qr-outstanding'",
            (tenant_id,),
        )
    assert enrolment_row(app, tenant_id, "qr-outstanding")[0] == "issued"
    still = redeem(app, tenant_id, TRANSIENT_ENTRY, outstanding, "CAR-2", at=when)
    assert not still.redeemed, "a revoked pass took a car through an uncancelled QR"
    assert still.refusal.code == f.REFUSAL_PASS_NOT_REGISTRABLE
    assert "revoked" in still.refusal.detail
    assert [r[:2] for r in registrations(app, tenant_id)] == [(pass_.id, "CAR-1")]
    assert still.answer.outcome is Outcome.NOT_COVERED and still.answer.reason == f.NO_PASS


@pytest.mark.guarantee("G19")
def test_a_holder_link_is_the_same_primitive_used_once(app, tenant_id):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    out = issue_link(app, tenant_id, TRANSIENT_ENTRY, pass_)
    assert out["holder_link"] == "link-1" and out["payload"] == payload_of(out["token"])
    assert query(app, tenant_id, "SELECT token_sha256 FROM holder_links") == [
        (digest(out["token"]),)
    ]
    read = credential(app, tenant_id, "link-1", HOLDER_LINK)
    assert read.kind == HOLDER_LINK and read.vehicle_description is None
    used = redeem_link(app, tenant_id, TRANSIENT_ENTRY, out["payload"])
    assert used["holder_link"] == "link-1" and used["enrolment"]["enrolment"] == "qr-from-link"
    assert link_row(app, tenant_id)[0] == "redeemed"
    with pytest.raises(f.Refused) as refused:
        redeem_link(app, tenant_id, TRANSIENT_ENTRY, out["token"], enrolment_external_id="qr-2")
    app.rollback()
    assert refused.value.code == f.REFUSAL_CREDENTIAL_ALREADY_USED
    assert query(app, tenant_id, "SELECT count(*) FROM enrolments") == [(1,)]
    late = at(date(2026, 6, 4), 12)
    fresh = issue_link(app, tenant_id, TRANSIENT_ENTRY, pass_, "link-2")["token"]
    with pytest.raises(f.Refused) as refused:
        redeem_link(app, tenant_id, TRANSIENT_ENTRY, fresh, enrolment_external_id="qr-3", at=late)
    app.rollback()
    assert refused.value.code == f.REFUSAL_CREDENTIAL_EXPIRED
    assert link_row(app, tenant_id, "link-2")[0] == "issued"


@pytest.mark.guarantee("G19")
def test_a_qr_of_another_garages_pass_is_refused_naming_the_garage(app, tenant_id):
    """The garage is the pass's, read through the pass: a QR presented at a
    garage its pass is not at is refused by name, never redeemed there."""
    here = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, here)["token"]
    seeded(app, tenant_id, TRANSIENT_EXIT, id="pass-elsewhere")
    out = redeem(app, tenant_id, TRANSIENT_EXIT, token, "CAR-1", direction=Direction.EXIT)
    assert not out.redeemed and out.refusal.code == f.REFUSAL_GARAGE_MISMATCH
    assert TRANSIENT_EXIT.id in out.refusal.detail and out.enrolment == "qr-1"
    assert registrations(app, tenant_id) == []
    assert credential(app, tenant_id, "qr-1", ENROLMENT).state is CredentialState.ISSUED


@pytest.mark.guarantee("G19")
def test_the_swap_is_end_registration_then_a_new_qr_and_the_half_open_range_holds(app, tenant_id):
    """His words: deactivate the old car, create a new QR for the new car.
    Built from the shipped end-registration plus issue -- no compound verb.
    Ended on day D, the new car is bound FROM D; the old identity is free FROM
    D and covered up to and not including D."""
    from garage_pass.store.access import access_from_store
    from garage_pass.store.records import end_registration

    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    old = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-old")["token"]
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, old, "CAR-OLD").redeemed  # June 1st
    D = date(2026, 6, 3)
    with tenant(app, tenant_id) as cursor:
        end_registration(cursor, tenant_id, TRANSIENT_ENTRY.id, pass_.id, "CAR-OLD", D)
    app.commit()
    new = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, "qr-new", starts_on=D)["token"]
    swapped = redeem(app, tenant_id, TRANSIENT_ENTRY, new, "CAR-NEW", at=at(D, 8))
    assert swapped.redeemed and swapped.pass_state_change is None, "the pass stayed active"
    assert registrations(app, tenant_id) == [
        (pass_.id, "CAR-OLD", date(2026, 6, 1), D, "ended"),
        (pass_.id, "CAR-NEW", D, None, None),
    ]
    # the old car is covered up to and not including D, and free from D: another
    # pass's QR binds it effective D
    covered = access_from_store(app, tenant_id, TRANSIENT_ENTRY.id, "CAR-OLD", "L1",
                                Direction.ENTRY, at(date(2026, 6, 2), 8))
    assert covered.outcome is Outcome.COVERED
    gone = access_from_store(app, tenant_id, TRANSIENT_ENTRY.id, "CAR-OLD", "L1",
                             Direction.ENTRY, at(D, 8))
    assert gone.outcome is Outcome.NOT_COVERED and gone.reason == f.NO_PASS
    assert "ended on 2026-06-03" in gone.detail
    from fixtures import a_pass
    from garage_pass.store.records import create_pass

    other = a_pass(id="pass-other", garage_id=TRANSIENT_ENTRY.id)
    with tenant(app, tenant_id) as cursor:
        create_pass(cursor, tenant_id, TRANSIENT_ENTRY.id, other, by="seed", at=NOON_MONDAY)
    app.commit()
    elsewhere = issue(app, tenant_id, TRANSIENT_ENTRY, other, "qr-elsewhere", starts_on=D)["token"]
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, elsewhere, "CAR-OLD", at=at(D, 9)).redeemed
    # and a day EARLIER it would have been refused by name: the old pass held it on the 2nd
    before_d = issue(app, tenant_id, TRANSIENT_ENTRY, other, "qr-early")["token"]
    early = redeem(app, tenant_id, TRANSIENT_ENTRY, before_d, "CAR-OLD",
                   at=at(date(2026, 6, 2), 9))
    assert not early.redeemed and early.refusal.code == f.REFUSAL_VEHICLE_ON_ANOTHER_PASS
