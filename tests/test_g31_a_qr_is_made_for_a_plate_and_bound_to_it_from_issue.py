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
                                identity_read=read, decided_by="opa_id", lane="L1",
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
    assert [r[:5] for r in registrations(app, tenant_id)] == [
        (pass_.id, "KAY77", date(2026, 6, 1), date(2026, 6, 4), "the stay's last day")]
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
    assert first.redeemed and first.registration["vehicle_identity"] == "ANYCAR9"
    other = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "ANY-CAR-9", at=LATER)
    assert other.refusal.code == f.REFUSAL_CREDENTIAL_WRONG_CAR, "exact text, as it always was"


# ---------------------------------------------------------------------------
# The gate's fixes (F1, F2): the same car on the same pass is never "another
# pass", and the one normal form takes out every space and invisible character.
# ---------------------------------------------------------------------------

def _cancel(app, tenant_id, external_id, when=LATER):
    from garage_pass.store.enrolments import cancel_code

    with tenant(app, tenant_id) as cursor:
        cancel_code(cursor, tenant_id, TRANSIENT_ENTRY.id, external_id, by="desk", at=when,
                    reason="never received")
    app.commit()


def _replace(app, tenant_id, old, new, plate, starts_on, when):
    with tenant(app, tenant_id) as cursor:
        out = replace_car(cursor, tenant_id, TRANSIENT_ENTRY.id, old, new, starts_on, 3,
                          by="desk", at=when, reason="swap", plate=plate)
    app.commit()
    return out


def _minted(make) -> dict:
    """The call's result, or an assertion naming the refusal: a reissue for the
    same car that is refused is the subject of these checks, not an error."""
    try:
        return make()
    except f.Refused as refused:
        raise AssertionError(f"the same car on the same pass was refused: {refused}") from None


def _held(app, tenant_id, plate) -> list[tuple]:
    return [r for r in registrations(app, tenant_id) if r[1] == plate]


@pytest.mark.guarantee("G31")
@pytest.mark.parametrize("used", [False, True], ids=["unused", "used"])
def test_a_cancelled_qr_is_reissued_for_the_same_car_on_its_one_registration(
    app, tenant_id, used
):
    """GATE FIX CHECK 1, his rule: the desk reselects the guest and reissues the
    code. Issue -> cancel -> reissue, same plate, same pass: the reissue is
    minted, the pass still holds ONE registration for the plate, and the new
    QR is recognised on that plate."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    first = issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "ABC-123")["token"]
    if used:
        assert redeem(app, tenant_id, TRANSIENT_ENTRY, first, "ABC123", at=LATER).recognised
    held = _held(app, tenant_id, "ABC123")
    assert len(held) == 1
    _cancel(app, tenant_id, "qr-1")
    fresh = _minted(lambda: issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "abc 123",
                                        external_id="qr-2", starts_on=date(2026, 6, 2)))
    assert fresh["plate_key"] == "ABC123"
    assert _held(app, tenant_id, "ABC123") == held, "the car was registered a second time"
    shown = redeem(app, tenant_id, TRANSIENT_ENTRY, fresh["token"], "ABC 123",
                   at=at(date(2026, 6, 2), 10))
    assert shown.recognised and shown.refusal is None, shown.refusal
    assert shown.answer.outcome is Outcome.COVERED
    old = redeem(app, tenant_id, TRANSIENT_ENTRY, first, "ABC123", at=at(date(2026, 6, 2), 11))
    assert old.refusal is not None and old.refusal.code == f.REFUSAL_CREDENTIAL_CANCELLED


@pytest.mark.guarantee("G31")
def test_a_replaced_car_coming_back_gets_a_new_qr_on_its_registration(app, tenant_id):
    """GATE FIX CHECK 2. replace-car OLD -> NEW, then NEW -> OLD on the same
    pass: minted, OLD's new QR is recognised and enters, and NEW is the car
    that is exit only now."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "OLD-1")
    to_new = _replace(app, tenant_id, "qr-1", "qr-2", "NEW-2", date(2026, 6, 2), LATER)
    back = _minted(lambda: _replace(app, tenant_id, "qr-2", "qr-3", "old 1", date(2026, 6, 3),
                                    at(date(2026, 6, 3), 9)))
    assert back["new"]["plate_key"] == "OLD1" and len(_held(app, tenant_id, "OLD1")) == 1
    when = at(date(2026, 6, 3), 10)
    entry = redeem(app, tenant_id, TRANSIENT_ENTRY, back["new"]["token"], "OLD1",
                   direction=Direction.ENTRY, at=when)
    assert entry.recognised and entry.refusal is None, entry.refusal
    assert entry.answer.outcome is Outcome.COVERED
    by_plate = access_from_store(app, tenant_id, TRANSIENT_ENTRY.id, "OLD1", "L1",
                                 Direction.ENTRY, when)
    assert by_plate.outcome is Outcome.COVERED, "OLD came back and still reads exit only"
    new_in = redeem(app, tenant_id, TRANSIENT_ENTRY, to_new["new"]["token"], "NEW2",
                    direction=Direction.ENTRY, at=when)
    assert new_in.refusal is not None and new_in.refusal.code == f.REFUSAL_CREDENTIAL_EXIT_ONLY


#: The same plate as the desk or a lane might hand it in: an ASCII space, a
#: non-breaking space, a zero-width space and a leading byte-order mark.
UNICODE_PLATES = ("ABC 123", "ABC 123", "ABC​123", "﻿ABC123",
                  "abc -　123", "A‌B‍C123")


@pytest.mark.guarantee("G31")
@pytest.mark.parametrize("typed", UNICODE_PLATES, ids=ascii)
def test_every_space_and_invisible_character_is_out_of_the_one_normal_form(
    app, tenant_id, typed
):
    """GATE FIX CHECK 4. Typed at issue and read at the lane, each is ABC123."""
    assert plate_key(typed) == "ABC123"
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    issued = issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, typed)
    assert issued["plate_key"] == "ABC123" and issued["plate"] == typed.strip()
    for read in UNICODE_PLATES:
        out = redeem(app, tenant_id, TRANSIENT_ENTRY, issued["token"], read, at=LATER)
        assert out.recognised and not out.match_required, (ascii(typed), ascii(read))


@pytest.mark.guarantee("G31")
def test_a_plate_of_only_spaces_and_invisibles_is_refused_by_name_never_by_the_database(
    app, tenant_id
):
    """GATE FIX CHECK 4. Every character str.isspace() calls a space, and the
    four invisibles, alone: refused by name -- never a raw constraint error."""
    import sys

    spaces = [chr(c) for c in range(sys.maxunicode + 1) if chr(c).isspace()]
    invisibles = ["​", "‌", "‍", "﻿"]
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    before = written(app, tenant_id)
    for plate in [*spaces, *invisibles, "".join(spaces + invisibles)]:
        with pytest.raises(f.Refused) as refused:
            issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, plate)
        app.rollback()
        assert refused.value.code == f.REFUSAL_PLATE_NOT_STATED, ascii(plate)
    assert written(app, tenant_id) == before
    # and inside a plate, each is taken out -- none reaches the plate CHECK
    for i, ch in enumerate(spaces + invisibles):
        if ch in "\t\n\v\f\r\x1c\x1d\x1e\x1f\x85":
            continue  # control characters: refused by name (require_text), below
        issued = issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, f"Q{ch}{i}",
                             external_id=f"qr-sp-{i}")
        assert issued["plate_key"] == f"Q{i}", ascii(ch)
    with pytest.raises(f.Refused) as refused:
        issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "Q\t1", external_id="qr-tab")
    app.rollback()
    assert refused.value.code == f.REFUSAL_TEXT_HAS_CONTROL_CHARACTERS


@pytest.mark.guarantee("G31")
def test_another_plate_read_is_answered_on_its_own_pass_never_on_the_qr(app, tenant_id):
    """GATE FIX F3, the words measured: a picture match is pending and nothing
    opens on the QR, but the answer beside it is for what was read -- a car
    with its own valid pass is covered on THAT pass."""
    from garage_pass.passes import State
    from garage_pass.store.records import register_vehicle

    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY, state=State.ACTIVE)
    token = issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "ABC123")["token"]
    other = a_pass(id="pass-other", garage_ids={TRANSIENT_ENTRY.id}, state=State.ACTIVE)
    with tenant(app, tenant_id) as cursor:
        create_pass(cursor, tenant_id, TRANSIENT_ENTRY.id, other, by="seed", at=LATER)
        register_vehicle(cursor, tenant_id, TRANSIENT_ENTRY.id, "pass-other", "XYZ789",
                         date(2026, 6, 1))
    app.commit()
    # the read as round 4's lane sends it, in the one normal form (the access
    # answer is for the read as sent; this round changes words, not behaviour)
    out = redeem(app, tenant_id, TRANSIENT_ENTRY, token, plate_key("XYZ 789"),
                 direction=Direction.ENTRY, at=LATER)
    assert out.match_required and not out.recognised and out.refusal is None
    assert out.answer.outcome is Outcome.COVERED and out.answer.pass_id == "pass-other"
    unread = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "", direction=Direction.ENTRY,
                    at=LATER)
    assert unread.match_required and unread.answer.outcome is not Outcome.COVERED


@pytest.mark.guarantee("G31")
@pytest.mark.parametrize("read", ["XYZ 789", "xyz 789", "x-y.z–7​89", "XYZ789"],
                         ids=ascii)
def test_a_plate_read_with_no_qr_meets_the_registration_in_the_one_normal_form(
    app, tenant_id, read
):
    """STAY-ENDS AMENDMENT, ITEM 6. A plate read checked with no QR -- the
    lane asking about a car by its plate alone -- finds the registration in
    the one normal form: "XYZ 789" and "xyz 789" are XYZ789."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "XYZ789")["token"]
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, token, "XYZ789", at=LATER).recognised
    for direction in (Direction.ENTRY, Direction.EXIT):
        answer = access_from_store(app, tenant_id, TRANSIENT_ENTRY.id, read, "L1", direction,
                                   LATER)
        assert answer.outcome is Outcome.COVERED and answer.pass_id == pass_.id, (
            ascii(read), answer.detail)


@pytest.mark.guarantee("G31")
@pytest.mark.parametrize("typed", ["ABC–123", "ABC—123", "ABC−123",
                                   "ABC‐123", "ABC‑123"], ids=ascii)
def test_every_dash_is_out_of_the_one_normal_form(app, tenant_id, typed):
    """STAY-ENDS AMENDMENT, ITEM 7. En dash, em dash, minus sign, hyphen and
    non-breaking hyphen: each typed at issue and read at the lane is ABC123."""
    assert plate_key(typed) == "ABC123"
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    issued = issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, typed)
    assert issued["plate_key"] == "ABC123"
    out = redeem(app, tenant_id, TRANSIENT_ENTRY, issued["token"], typed, at=LATER)
    assert out.recognised and not out.match_required, ascii(typed)
