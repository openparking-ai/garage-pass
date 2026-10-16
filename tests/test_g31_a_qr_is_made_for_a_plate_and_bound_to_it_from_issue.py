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


def _replace(app, tenant_id, old, new, plate, starts_on, when, days=3):
    with tenant(app, tenant_id) as cursor:
        out = replace_car(cursor, tenant_id, TRANSIENT_ENTRY.id, old, new, starts_on, days,
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
    again = _held(app, tenant_id, "ABC123")
    assert [r[:3] for r in again] == [r[:3] for r in held], "the car was registered a second time"
    # the one registration runs on to the reissued QR's last day, June 4
    assert again[0][3:] == (date(2026, 6, 5), "the stay's last day"), again
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
    assert back["new"]["plate_key"] == "0LD1" and len(_held(app, tenant_id, "0LD1")) == 1
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


# ---------------------------------------------------------------------------
# A QR for a car the pass already holds works to its OWN last day; and the one
# normal form reads O as 0 and I as 1 (migration 0007).
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G31")
@pytest.mark.parametrize("how", ["reissued", "came back"])
def test_a_qr_for_a_car_the_pass_already_holds_works_to_its_own_last_day(app, tenant_id, how):
    """The car's QR, June 1 to 3, is cancelled and reissued -- or the car is
    replaced and comes back -- with a new QR from June 2 for five days, last
    day June 6. The pass keeps the ONE registration it has, and it runs on to
    June 6: the new QR is recognised and the plate covered on its last day,
    and the day after it the QR's stay is over. Measured before this: the
    registration was reused as it stood, ending June 3, so from June 4 the
    new QR was refused STAY_ENDED and the plate read as no pass."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "ABC-123")  # June 1 to 3
    if how == "reissued":
        _cancel(app, tenant_id, "qr-1")
        token = _minted(lambda: issue_plate(
            app, tenant_id, TRANSIENT_ENTRY, pass_, "abc 123", external_id="qr-2",
            starts_on=date(2026, 6, 2), days_valid=5))["token"]
    else:
        _replace(app, tenant_id, "qr-1", "qr-2", "XYZ-789", date(2026, 6, 2), LATER)
        token = _minted(lambda: _replace(
            app, tenant_id, "qr-2", "qr-3", "abc 123", date(2026, 6, 2),
            at(date(2026, 6, 2), 10), days=5))["new"]["token"]
    assert [r[2:] for r in _held(app, tenant_id, "ABC123")] == [
        (date(2026, 6, 1), date(2026, 6, 7), "the stay's last day")], "one registration, run on"
    last_day = at(date(2026, 6, 6), 9)
    shown = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "ABC 123", direction=Direction.ENTRY,
                   at=last_day)
    assert shown.recognised and shown.refusal is None, shown.refusal
    assert shown.answer.outcome is Outcome.COVERED, shown.answer.detail
    by_plate = access_from_store(app, tenant_id, TRANSIENT_ENTRY.id, "ABC123", "L1",
                                 Direction.ENTRY, last_day)
    assert by_plate.outcome is Outcome.COVERED and by_plate.pass_id == pass_.id, by_plate.detail
    after = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "ABC123", direction=Direction.EXIT,
                   at=at(date(2026, 6, 7), 9))
    assert after.refusal is not None and after.refusal.code == f.REFUSAL_CREDENTIAL_STAY_ENDED


@pytest.mark.guarantee("G31")
def test_o_reads_as_0_and_i_as_1_on_every_side(app, tenant_id):
    """A plate reader's alphabet has no I and no O: it prints 1 and 0. GO4IT
    typed at the desk is read G041T at the lane, and the one normal form makes
    them one car -- on the QR, on a plate read with no QR, and in the engine
    alone. The control: a plate that differs in any other character is still
    another plate."""
    from fixtures import registered, transient_garage
    from garage_pass.access import access

    assert plate_key("GO4IT") == plate_key("G041T") == plate_key("go4-it") == "G041T"
    assert plate_key("oi-OI") == "0101" and plate_key("G04IX") != plate_key("G041T")
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    issued = issue_plate(app, tenant_id, TRANSIENT_ENTRY, pass_, "GO4IT")
    assert (issued["plate"], issued["plate_key"]) == ("GO4IT", "G041T")
    out = redeem(app, tenant_id, TRANSIENT_ENTRY, issued["token"], "G041T", at=LATER)
    assert out.recognised and not out.match_required, out
    for direction in (Direction.ENTRY, Direction.EXIT):
        answer = access_from_store(app, tenant_id, TRANSIENT_ENTRY.id, "G041T", "L1", direction,
                                   LATER)
        assert answer.outcome is Outcome.COVERED and answer.pass_id == pass_.id, answer.detail
    engine = a_pass(garage_ids={TRANSIENT_ENTRY.id})
    alone = access(garage=transient_garage(), passes=[engine],
                   registrations=[registered(engine, "GO4IT")], visits=[],
                   vehicle_identity="G041T", lane="L1", direction=Direction.EXIT, at=LATER)
    assert alone.outcome is Outcome.COVERED, alone.detail
    other = access_from_store(app, tenant_id, TRANSIENT_ENTRY.id, "G04IX", "L1",
                              Direction.ENTRY, LATER)
    assert other.outcome is Outcome.NOT_COVERED and other.reason == f.NO_PASS


def _rebuild_to_0006(owner) -> None:
    from store_harness import MIGRATIONS

    with owner.cursor() as cursor:
        cursor.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name < "0007":
                cursor.execute(path.read_text())


def _try_0007(owner) -> str | None:
    """Apply 0007; the error's primary message when it refuses, else None."""
    import psycopg

    from store_harness import MIGRATIONS

    (path,) = MIGRATIONS.glob("0007_*.sql")
    with owner.cursor() as cursor:
        try:
            cursor.execute(path.read_text())
        except psycopg.Error as failure:
            cursor.execute("ROLLBACK")
            return (failure.diag.message_primary or str(failure)).strip()
    return None


@pytest.fixture
def at_0006(owner):
    """The schema at 0006 as the OWNER, under the cluster lock (0001 ALTERs
    the cluster-global role); rebuilt to the full schema afterwards so the
    module's other tests read the shape that ships."""
    from store_harness import DSN, cluster_lock, migrate

    with cluster_lock(DSN):
        _rebuild_to_0006(owner)
        yield owner
    migrate(DSN).close()


def _rows_at_0006(owner, tenant_id, registrations: list, visits: list = (), plates: list = ()):
    """Raw rows as the module wrote them before 0007: identities in the old
    normal form, with O and I in them. A garage, two passes on it."""
    with owner.cursor() as cursor:
        cursor.execute(
            "INSERT INTO garages (tenant_id, external_id, timezone, transient_available) "
            "VALUES (%s, 'g-a', 'America/Denver', true) RETURNING id", (tenant_id,))
        (garage,) = cursor.fetchone()
        passes = {}
        for ext in ("p-1", "p-2"):
            cursor.execute(
                "INSERT INTO passes (tenant_id, external_id, label, holder_email, entry_allowed, "
                "exit_allowed, lanes_stated, state) VALUES (%s, %s, 'l', 'h@example.com', true, "
                "true, false, 'active') RETURNING id", (tenant_id, ext))
            (passes[ext],) = cursor.fetchone()
            cursor.execute("INSERT INTO pass_garages (tenant_id, pass_id, garage_id) VALUES "
                           "(%s, %s, %s)", (tenant_id, passes[ext], garage))
        for pass_ext, identity, effective, end in registrations:
            cursor.execute(
                "INSERT INTO vehicle_registrations (tenant_id, garage_id, pass_id, "
                "vehicle_identity, effective_day, end_day, ended_reason) VALUES "
                "(%s, %s, %s, %s, %s, %s, %s)",
                (tenant_id, garage, passes[pass_ext], identity, effective, end,
                 "ended" if end else None))
        for pass_ext, identity in visits:
            cursor.execute(
                "INSERT INTO visits (tenant_id, garage_id, pass_id, vehicle_identity, "
                "entry_lane, entered_at) VALUES (%s, %s, %s, %s, 'L1', %s)",
                (tenant_id, garage, passes[pass_ext], identity, LATER))
        for i, plate in enumerate(plates):
            cursor.execute(
                "INSERT INTO enrolments (tenant_id, pass_id, external_id, token_sha256, "
                "starts_on, days_valid, issued_by, issued_at, state, plate_typed, plate) VALUES "
                "(%s, %s, %s, %s, '2026-06-01', 3, 'desk', %s, 'issued', %s, %s)",
                (tenant_id, passes["p-1"], f"qr-{i}", f"{i:064x}", LATER, plate, plate))


def _identities(owner, tenant_id) -> dict:
    out = {}
    with owner.cursor() as cursor:
        for table, column in (("vehicle_registrations", "vehicle_identity"),
                              ("visits", "vehicle_identity"), ("enrolments", "plate"),
                              ("enrolments", "plate_typed")):
            cursor.execute(f"SELECT {column} FROM {table} WHERE tenant_id = %s ORDER BY 1",
                           (tenant_id,))
            out[f"{table}.{column}"] = [row[0] for row in cursor.fetchall()]
    return out


@pytest.mark.guarantee("G31")
def test_0007_rekeys_every_stored_identity_and_the_floor_refuses_an_o_or_an_i(
    at_0006, tenant_id
):
    """Rows the module wrote before 0007 carry O and I. 0007 re-keys the three
    columns that hold the normal form -- registrations, visits and a QR's plate
    -- and keeps the plate as typed; after it, the database refuses a raw
    write of an O or an I, as it refuses a dash (0006)."""
    import psycopg

    from store_harness import new_tenant

    owner = at_0006
    tenant_id = new_tenant(owner)
    _rows_at_0006(owner, tenant_id,
                  registrations=[("p-1", "GO4IT", date(2026, 6, 1), None),
                                 ("p-2", "ABC123", date(2026, 6, 1), None)],
                  visits=[("p-1", "GO4IT")], plates=["GO4IT"])
    assert _identities(owner, tenant_id)["vehicle_registrations.vehicle_identity"] == [
        "ABC123", "GO4IT"], "the premise: a row to re-key"
    failure = _try_0007(owner)
    if failure is not None:
        pytest.fail(f"0007 did not apply over rows written at 0006: {failure}")
    assert _identities(owner, tenant_id) == {
        "vehicle_registrations.vehicle_identity": ["ABC123", "G041T"],
        "visits.vehicle_identity": ["G041T"],
        "enrolments.plate": ["G041T"],
        "enrolments.plate_typed": ["GO4IT"],
    }
    for table, constraint in (("vehicle_registrations",
                               "vehicle_registrations_identity_in_normal_form"),
                              ("visits", "visits_identity_in_normal_form")):
        with owner.cursor() as cursor, pytest.raises(psycopg.errors.CheckViolation) as raised:
            cursor.execute(f"UPDATE {table} SET vehicle_identity = 'GO4IT' "
                           "WHERE tenant_id = %s", (tenant_id,))
        assert raised.value.diag.constraint_name == constraint


@pytest.mark.guarantee("G31")
@pytest.mark.parametrize("clash", ["registrations", "open visits"])
def test_0007_refuses_by_name_when_two_rows_become_one_car_and_moves_nothing(
    at_0006, tenant_id, clash
):
    """GO4IT and G041T, registered at one garage on overlapping days (two
    passes), or both open visits on one pass: once O reads as 0 and I as 1
    they are one car, which the database's own constraints forbid. 0007 names
    them and stops, and nothing moves -- it never picks one. The control: the
    same two identities on days that do not overlap are re-keyed."""
    from store_harness import new_tenant

    owner = at_0006
    tenant_id = new_tenant(owner)
    if clash == "registrations":
        _rows_at_0006(owner, tenant_id, registrations=[
            ("p-1", "GO4IT", date(2026, 6, 1), None), ("p-2", "G041T", date(2026, 6, 10), None)])
    else:
        _rows_at_0006(owner, tenant_id, registrations=[
            ("p-1", "GO4IT", date(2026, 1, 1), date(2026, 2, 1)),
            ("p-2", "G041T", date(2026, 6, 1), None)],
            visits=[("p-1", "GO4IT"), ("p-1", "G041T")])
    before = _identities(owner, tenant_id)
    failure = _try_0007(owner)
    assert failure is not None, "0007 applied over two rows that become one car"
    assert "migration 0007 refuses to run" in failure and "G041T and GO4IT" in failure, failure
    assert "g-a" in failure and "Nothing was chosen for you" in failure, failure
    assert _identities(owner, tenant_id) == before, "a refused migration moved a row"
    if clash == "registrations":
        with owner.cursor() as cursor:
            cursor.execute("UPDATE vehicle_registrations SET end_day = '2026-06-10', "
                           "ended_reason = 'ended' WHERE tenant_id = %s AND vehicle_identity = "
                           "'GO4IT'", (tenant_id,))
        assert _try_0007(owner) is None, "the same two on days that do not overlap"
        assert _identities(owner, tenant_id)["vehicle_registrations.vehicle_identity"] == [
            "G041T", "G041T"]
