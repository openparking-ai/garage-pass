"""G31 -- a QR is made for a plate, and bound to it from issue.

**THE BRIEF'S CHECKS 1-5.** The plate is required to make a QR (issue,
replace-car, the holder's own link): without it, refused by name and nothing
minted. Plates are compared in ONE normal form on both sides -- capitals, no
space, dash or dot -- so "abc-123" typed and "ABC 123" read are one car. Against
the plate -- which SUPPORTS the picture match and never refuses on its own: the
same plate is RECOGNISED; anything else -- nothing read, part of it, a misread,
another plate -- is a PICTURE MATCH carrying the registered plate and what was
read, and only the match's own "no" is WRONG CAR. A new QR is bound from issue --
its plate is
registered on the pass when it is made, its first use binds nothing new, and the
register shows the plate before any use. A QR stored before plates were required
keeps its first-use behaviour, unchanged (G19 proves it whole).

Controls: a QR minted without a plate; plates compared as raw text; a different
read answered wrong car; an exact read answered with a match; a 'no' match
recorded as recognised; the register showing no identity until first use.
"""

from __future__ import annotations

from datetime import date

import pytest

from enrolment_harness import (
    GARAGES,
    TRANSIENT_ENTRY,
    issue,
    issue_plate,
    other_end,
    redeem,
    registrations,
    seeded,
    state_changes,
)
from fixtures import a_pass, at
from garage_pass import findings as f
from garage_pass.access import Outcome
from garage_pass.enrolment import plate_key, where_enrolment_happens
from garage_pass.store.access import access_from_store
from garage_pass.store.enrolments import redeem_holder_link, replace_car
from garage_pass.store.postgres import tenant
from garage_pass.store.records import create_pass, show_garage_register
from garage_pass.terms import Direction
from store_harness import needs_postgres, query

pytestmark = needs_postgres

LATER = at(date(2026, 6, 2), 9)


def written(app, tenant_id) -> tuple:
    return (query(app, tenant_id, "SELECT count(*) FROM enrolments"),
            registrations(app, tenant_id), state_changes(app, tenant_id))


@pytest.mark.guarantee("G31")
def test_the_normal_form_is_one_function():
    assert plate_key("abc-123") == plate_key("ABC 123") == plate_key("a.b.c 1-2-3") == "ABC123"
    assert plate_key(" - . ") == ""


@pytest.mark.guarantee("G31")
@pytest.mark.parametrize("plate", [None, "", "   ", " - . ", 7], ids=repr)
def test_issue_replace_and_the_holder_link_without_a_plate_are_refused_and_mint_nothing(
    app, tenant_id, plate
):
    """CHECK 1."""
    from enrolment_harness import issue_link

    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    before = written(app, tenant_id)
    with pytest.raises(f.Refused) as refused:
        issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, plate)
    app.rollback()
    assert refused.value.code == f.REFUSAL_PLATE_NOT_STATED and refused.value.field == "plate"
    assert written(app, tenant_id) == before, "a QR without a plate minted something"
    old = issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "OLD-1")
    after_old = written(app, tenant_id)
    with tenant(app, tenant_id) as cursor, pytest.raises(f.Refused) as refused:
        replace_car(cursor, tenant_id, TRANSIENT_ENTRY.id, old["enrolment"], "qr-2",
                    date(2026, 6, 2), 3, by="desk", at=LATER, reason="swap", plate=plate)
    app.rollback()
    assert refused.value.code == f.REFUSAL_PLATE_NOT_STATED
    assert written(app, tenant_id) == after_old
    link = issue_link(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    with tenant(app, tenant_id) as cursor, pytest.raises(f.Refused) as refused:
        redeem_holder_link(cursor, tenant_id, TRANSIENT_ENTRY.id, link, name="A", phone="1",
                           enrolment_external_id="qr-3", starts_on=date(2026, 6, 1),
                           days_valid=3, at=LATER, plate=plate)
    app.rollback()
    assert refused.value.code == f.REFUSAL_PLATE_NOT_STATED
    assert written(app, tenant_id) == after_old


@pytest.mark.guarantee("G31")
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
def test_typed_one_way_and_read_another_is_the_same_car_recognised_at_either_end(
    app, tenant_id, garage
):
    """The plate-at-issue brief's check 2, and this brief's CHECK 3: the exact
    plate, in the one normal form, is recognised -- never a match."""
    pass_ = seeded(app, tenant_id, garage)
    token = issue_plate(app, tenant_id, garage, pass_, "abc-123")["token"]
    end = Direction(where_enrolment_happens(garage))
    for direction, read in ((end, "ABC 123"), (other_end(end), "abc.123"), (end, "ABC123")):
        out = redeem(app, tenant_id, garage, token, read, direction=direction, at=LATER)
        assert out.recognised and out.refusal is None and not out.match_required, out.refusal
        assert out.answer.outcome is Outcome.COVERED and out.answer.vehicle_identity == "ABC123"


@pytest.mark.guarantee("G31")
@pytest.mark.parametrize("read", ["ABC1Z3", "A8C123", "XYZ789", "ABC12", "AB", "", "   "])
def test_any_read_but_the_plate_asks_for_a_match_and_never_refuses(app, tenant_id, read):
    """CHECK 1. A misread, part of the plate, another plate or nothing at all:
    each a picture match against the registered plate, carrying what was read,
    never wrong car; nothing opens and nothing is written."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "ABC123")["token"]
    before = written(app, tenant_id)
    for direction in (Direction.ENTRY, Direction.EXIT):
        out = redeem(app, tenant_id, TRANSIENT_ENTRY, token, read, direction=direction, at=LATER)
        assert out.match_required and out.refusal is None, out.refusal
        assert not out.recognised and not out.redeemed
        assert out.match_for == "ABC123" and out.match_read == (read.strip() or None)
        assert out.answer.outcome is not Outcome.COVERED
    assert written(app, tenant_id) == before


@pytest.mark.guarantee("G31")
@pytest.mark.parametrize("read", ["XYZ789", "ABC1Z3"])
def test_the_match_decides_no_is_wrong_car_and_yes_is_a_recognised_use(app, tenant_id, read):
    """CHECK 2. Only the picture match's own answer turns a different read into
    wrong car; a yes, whatever was read, is a recognised use, and both are kept."""
    from garage_pass.store.enrolments import confirm_match

    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "ABC123")["token"]
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, token, read, at=LATER).match_required

    def confirm(matched):
        with tenant(app, tenant_id) as cursor:
            out = confirm_match(cursor, tenant_id, TRANSIENT_ENTRY.id, "qr-1", matched=matched,
                                identity_read=read, decided_by="fingerprint", lane="L1",
                                direction=Direction.ENTRY, at=LATER)
        app.commit()
        return out

    no = confirm(False)
    assert no.refusal is not None and no.refusal.code == f.REFUSAL_CREDENTIAL_WRONG_CAR
    assert not no.recognised and no.answer.outcome is not Outcome.COVERED
    yes = confirm(True)
    assert yes.recognised and yes.refusal is None
    assert yes.answer.outcome is Outcome.COVERED and yes.answer.vehicle_identity == "ABC123"
    assert yes.pass_state_change["to"] == "active", "the match was the first use: draft to active"
    kept = query(app, tenant_id, "SELECT matches FROM enrolments")[0][0]
    assert [(m["matched"], m["identity_read"], m["outcome"]) for m in kept] == [
        (False, read, f.REFUSAL_CREDENTIAL_WRONG_CAR), (True, read, "recognised")]


@pytest.mark.guarantee("G31")
def test_a_new_qr_is_bound_from_issue_and_its_first_use_binds_nothing_new(app, tenant_id):
    """CHECK 5. Issued for its plate on a draft pass: the plate is registered at
    once (from starts_on, at every garage of the pass), the register shows it
    before any use, the car is covered by its plate alone once the pass is
    active, and the QR's first use is recognised, writes no registration and
    moves the draft pass to active."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    issued = issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "kay 77",
                         starts_on=date(2026, 6, 1))
    assert issued["plate"] == "kay 77" and issued["plate_key"] == "KAY77"
    assert [r[:4] for r in registrations(app, tenant_id)] == [
        (pass_.id, "KAY77", date(2026, 6, 1), None)]
    with tenant(app, tenant_id) as cursor:
        register = show_garage_register(cursor, tenant_id, TRANSIENT_ENTRY.id)
    app.rollback()
    [code] = register["codes"]
    assert code["bound_identity"] == "KAY77" and code["state"] == "issued"
    regs_before = registrations(app, tenant_id)
    first = redeem(app, tenant_id, TRANSIENT_ENTRY, issued["token"], "KAY-77", at=LATER)
    assert first.recognised and not first.redeemed and first.registration is None
    assert first.pass_state_change is not None and first.pass_state_change["to"] == "active"
    assert registrations(app, tenant_id) == regs_before, "the first use bound something new"
    again = redeem(app, tenant_id, TRANSIENT_ENTRY, issued["token"], "KAY77", at=LATER)
    assert again.recognised and again.pass_state_change is None
    by_plate = access_from_store(app, tenant_id, TRANSIENT_ENTRY.id, plate_key("Kay 77"), "L1",
                                 Direction.ENTRY, LATER)
    assert by_plate.outcome is Outcome.COVERED


@pytest.mark.guarantee("G31")
def test_a_plate_on_another_pass_is_refused_at_the_desk_and_nothing_is_minted(app, tenant_id):
    """One car, one pass, met when the QR is made -- not at the lane."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    other = a_pass(id="pass-other", garage_ids={TRANSIENT_ENTRY.id})
    with tenant(app, tenant_id) as cursor:
        create_pass(cursor, tenant_id, TRANSIENT_ENTRY.id, other, by="seed", at=LATER)
    app.commit()
    issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "ABC-123")
    before = written(app, tenant_id)
    with pytest.raises(f.Refused) as refused:
        issue_plate(app, tenant_id, TRANSIENT_ENTRY, other, "abc 123", external_id="qr-2")
    app.rollback()
    assert refused.value.code == f.REFUSAL_VEHICLE_ON_ANOTHER_PASS
    assert written(app, tenant_id) == before, "the refused issue left a QR or a registration"


@pytest.mark.guarantee("G31")
def test_a_qr_stored_without_a_plate_keeps_its_first_use_binding(app, tenant_id):
    """Point 5: the rows made before plates were required. The control beside
    the new rule: the same garage, a plate-less QR binds whatever car first
    uses it, as it always did."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    assert query(app, tenant_id, "SELECT plate, plate_typed FROM enrolments") == [(None, None)]
    assert registrations(app, tenant_id) == []
    first = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "any-car 9", at=LATER)
    assert first.redeemed and first.registration["vehicle_identity"] == "any-car 9"
    other = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "ANY-CAR-9", at=LATER)
    assert other.refusal.code == f.REFUSAL_CREDENTIAL_WRONG_CAR, "exact text, as it always was"
