"""G33 -- similar enough gets a pass (the owner's rule, 2026-10-30).

A VALID QR made for a plate opens for the car at the lane when what the lane
read is:

  (a) the plate once look-alike characters are one (O/0/Q/D, I/1/L, B/8, S/5,
      Z/2, G/6 -- ``enrolment.LOOK_ALIKE_GROUPS``, the one table, extending
      ``plate_key``'s O and I);
  (b) one character from it after that (a substitution, an insertion or a
      deletion), on a QR plate of five characters or more, folded
      (``ONE_DIFFERENCE_MIN_LENGTH``); a shorter plate is clearly different;
  (c) nothing usable (the lane hands in nothing for no plate, or a plate below
      its confidence).

Two differences or more is a CLEARLY DIFFERENT car: nothing opens on the QR
and it is a case for a person (``match_required``). Every pass by (b) or (c)
is kept on the QR's own row with what was read; the QR's plate is on the same
row and on every answer about a bound QR (``qr_plate``), so the lane can check
its owner's deny rule against the car it lets in. A QR still has to be valid:
cancelled, outside its stay and exit-only are refused first. The stored form
(``plate_key``) is unchanged, and a QR stored before plates were required keeps
its exact first-use binding.

Controls: the look-alikes not folded; one difference refused; one difference
passed on a short plate; two differences
passed; an insertion or deletion not one difference; nothing read kept shut;
a pass not kept; the QR's plate left off the answer; the stored form widened;
a QR with no plate widened too.
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
    seeded,
)
from fixtures import at
from garage_pass import findings as f
from garage_pass.access import Outcome
from garage_pass.cli import _redemption
from garage_pass.enrolment import (
    LOOK_ALIKE_GROUPS,
    ONE_DIFFERENCE_MIN_LENGTH,
    PASSED_LOOK_ALIKE,
    PASSED_NOTHING_READ,
    PASSED_ONE_DIFFERENCE,
    PASSED_SAME_PLATE,
    look_alike_key,
    plate_key,
    similar_enough,
    where_enrolment_happens,
    within_one_difference,
)
from garage_pass.store.enrolments import cancel_code, replace_car
from garage_pass.store.postgres import tenant
from garage_pass.terms import Direction
from store_harness import needs_postgres, query

LATER = at(date(2026, 6, 2), 9)

#: The plate every QR below is made for.
PLATE = "ABC-123"

#: (a): each look-alike group, alone and together.
LOOK_ALIKES = ["A8C123", "ABCL23", "ABC1Z3", "A8CL23", "a8c lz3", "A8CLZ3"]
#: (b): one character substituted, inserted or deleted -- after the look-alikes.
ONE_DIFFERENCE = ["ABC124", "XBC123", "ABC1234", "ABC12", "BC123", "A8C124", "ABCI2"]
#: Two differences or more: a clearly different car.
TWO_DIFFERENCES = ["ABC145", "XBC124", "ABC12345", "ABC1", "AB", "XYZ789", "A8C1Z456"]
#: (c): nothing usable read.
NOTHING = ["", "   "]


def matches(app, tenant_id, external_id="qr-1") -> list:
    return query(app, tenant_id, "SELECT matches FROM enrolments WHERE external_id = %s",
                 (external_id,))[0][0]


def made_for_a_plate(app, tenant_id, garage=TRANSIENT_ENTRY, plate=PLATE) -> str:
    pass_ = seeded(app, tenant_id, garage)
    return issue_plate(app, tenant_id, garage, pass_, plate)["token"]


# ---------------------------------------------------------------------------
# The one decision, as a function
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G33")
@pytest.mark.parametrize(("read", "passed"), [
    *[(r, PASSED_LOOK_ALIKE) for r in LOOK_ALIKES],
    *[(r, PASSED_ONE_DIFFERENCE) for r in ONE_DIFFERENCE],
    *[(r, None) for r in TWO_DIFFERENCES],
    *[(r, PASSED_NOTHING_READ) for r in NOTHING],
    (None, PASSED_NOTHING_READ),
    ("abc 123", PASSED_SAME_PLATE),
    ("ABCI23", PASSED_SAME_PLATE),
    ("ABCL23", PASSED_LOOK_ALIKE),
], ids=repr)
def test_the_one_decision_names_the_rule_that_passed_or_none(read, passed):
    assert similar_enough(read, PLATE) == passed


@pytest.mark.guarantee("G33")
@pytest.mark.parametrize(("plate", "read", "passed"), [
    ("AB12", "AB13", None), ("AB12", "AB1", None), ("AB12", "AB123", None),
    ("AB-12", "A8L2", PASSED_LOOK_ALIKE), ("AB12", "AB12", PASSED_SAME_PLATE),
    ("AB12", None, PASSED_NOTHING_READ),
    ("AB123", "AB124", PASSED_ONE_DIFFERENCE), ("AB123", "AB12", PASSED_ONE_DIFFERENCE),
    ("AB-123", "AB1234", PASSED_ONE_DIFFERENCE),
], ids=repr)
def test_one_difference_needs_a_plate_of_five_characters_or_more(plate, read, passed):
    assert ONE_DIFFERENCE_MIN_LENGTH == 5
    assert similar_enough(read, plate) == passed


@pytest.mark.guarantee("G33")
def test_every_look_alike_group_is_one_character_and_only_for_the_qr():
    for group in LOOK_ALIKE_GROUPS:
        assert len({look_alike_key(ch) for ch in group}) == 1, group
    assert look_alike_key("GOOD-5S") == look_alike_key("6QD0S5") == "600055"
    assert similar_enough("6QDO55", "GOOD5S") == PASSED_LOOK_ALIKE
    # THE STORED FORM IS NOT WIDENED: a registration still tells ABC5 from ABCS,
    # A8C from ABC -- only O and I are read as digits there, as before
    assert plate_key("ABC5") != plate_key("ABCS")
    assert plate_key("A8C") != plate_key("ABC")
    assert plate_key("GO4IT") == plate_key("G041T") == "G041T"


@pytest.mark.guarantee("G33")
@pytest.mark.parametrize(("a", "b", "within"), [
    ("ABC", "ABC", True), ("ABC", "ABD", True), ("ABC", "ABCD", True), ("ABC", "AC", True),
    ("ABC", "XBC", True), ("ABC", "BC", True), ("", "A", True), ("ABC", "ADE", False),
    ("ABC", "ABCDE", False), ("ABC", "CBA", False), ("ABCD", "ABDC", False), ("AB", "BA", False),
])
def test_one_difference_is_one_substitution_insertion_or_deletion(a, b, within):
    assert within_one_difference(a, b) is within
    assert within_one_difference(b, a) is within


# ---------------------------------------------------------------------------
# At the lane: (a), (b), (c) open; two differences do not
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G33")
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
def test_a_look_alike_read_is_the_qrs_car_at_either_end_and_keeps_nothing(
    app, tenant_id, garage
):
    token = made_for_a_plate(app, tenant_id, garage)
    end = Direction(where_enrolment_happens(garage))
    for read in LOOK_ALIKES:
        for direction in (end, other_end(end)):
            out = redeem(app, tenant_id, garage, token, read, direction=direction, at=LATER)
            assert out.recognised and not out.match_required and out.refusal is None, read
            assert out.passed_by == PASSED_LOOK_ALIKE and out.qr_plate == "ABC123"
            assert out.answer.outcome is Outcome.COVERED
            assert out.answer.vehicle_identity == "ABC123", "answered for the QR's car"
    assert matches(app, tenant_id) == [], "a look-alike is the plate: nothing to keep"


@pytest.mark.guarantee("G33")
@pytest.mark.parametrize("read", ONE_DIFFERENCE)
def test_one_difference_opens_and_is_kept_with_the_read(app, tenant_id, read):
    token = made_for_a_plate(app, tenant_id)
    out = redeem(app, tenant_id, TRANSIENT_ENTRY, token, read, direction=Direction.ENTRY,
                 at=LATER)
    assert out.recognised and not out.match_required and out.refusal is None
    assert out.passed_by == PASSED_ONE_DIFFERENCE and out.qr_plate == "ABC123"
    assert out.answer.outcome is Outcome.COVERED and out.answer.vehicle_identity == "ABC123"
    [kept] = matches(app, tenant_id)
    assert kept["identity_read"] == read and kept["passed_by"] == PASSED_ONE_DIFFERENCE
    assert (kept["matched"], kept["outcome"], kept["decided_by"]) == (
        True, "recognised", "similar_enough")
    assert (kept["lane"], kept["direction"], kept["at"]) == ("L1", "entry", LATER.isoformat())
    [(row_plate,)] = query(app, tenant_id, "SELECT plate FROM enrolments")
    assert row_plate == "ABC123", "the QR's plate is on the same row as the read"


@pytest.mark.guarantee("G33")
def test_a_four_character_plate_one_character_off_is_a_case_for_a_person(app, tenant_id):
    token = made_for_a_plate(app, tenant_id, plate="AB-12")
    out = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "AB13", direction=Direction.ENTRY,
                 at=LATER)
    assert out.match_required and not out.recognised and out.passed_by is None
    assert out.answer.outcome is not Outcome.COVERED and matches(app, tenant_id) == []
    same = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "A8-L2", direction=Direction.ENTRY,
                  at=LATER)
    assert same.recognised and same.passed_by == PASSED_LOOK_ALIKE, "the control: a look-alike"


@pytest.mark.guarantee("G33")
def test_a_five_character_plate_one_character_off_passes_and_names_the_qr(app, tenant_id):
    token = made_for_a_plate(app, tenant_id, plate="AB-123")
    out = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "AB124", direction=Direction.ENTRY,
                 at=LATER)
    assert out.recognised and out.passed_by == PASSED_ONE_DIFFERENCE
    assert out.answer.outcome is Outcome.COVERED
    # THE LANE IS TOLD WHICH QR, BESIDE HOW IT PASSED: the enrolment's id is on
    # the same half of the answer the platform relays, so a stay can be tied
    # to the QR (the platform's exit work)
    told = _redemption(out)["enrolment"]
    assert (told["enrolment"], told["passed_by"], told["qr_plate"]) == (
        "qr-1", PASSED_ONE_DIFFERENCE, "AB123")
    [kept] = matches(app, tenant_id)
    assert kept["identity_read"] == "AB124"


@pytest.mark.guarantee("G33")
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
@pytest.mark.parametrize("read", NOTHING, ids=["empty", "blank"])
def test_nothing_read_opens_at_either_end_and_is_kept(app, tenant_id, garage, read):
    token = made_for_a_plate(app, tenant_id, garage)
    end = Direction(where_enrolment_happens(garage))
    for direction in (end, other_end(end)):
        out = redeem(app, tenant_id, garage, token, read, direction=direction, at=LATER)
        assert out.recognised and not out.match_required and out.refusal is None
        assert out.passed_by == PASSED_NOTHING_READ and out.qr_plate == "ABC123"
        assert out.answer.outcome is Outcome.COVERED and out.answer.vehicle_identity == "ABC123"
    kept = matches(app, tenant_id)
    assert [(m["identity_read"], m["passed_by"], m["direction"]) for m in kept] == [
        (None, PASSED_NOTHING_READ, end.value),
        (None, PASSED_NOTHING_READ, other_end(end).value)], "one record per opening, in order"


@pytest.mark.guarantee("G33")
@pytest.mark.parametrize("read", TWO_DIFFERENCES)
def test_two_differences_open_nothing_on_the_qr_and_are_a_case_for_a_person(
    app, tenant_id, read
):
    token = made_for_a_plate(app, tenant_id)
    for direction in (Direction.ENTRY, Direction.EXIT):
        out = redeem(app, tenant_id, TRANSIENT_ENTRY, token, read, direction=direction,
                     at=LATER)
        assert out.match_required and not out.recognised and out.refusal is None
        assert out.passed_by is None and out.qr_plate == "ABC123"
        assert out.match_for == "ABC123" and out.match_read == read
        assert out.answer.outcome is not Outcome.COVERED, "nothing opens on the QR"
    assert matches(app, tenant_id) == [], "a case for a person writes nothing here"


@pytest.mark.guarantee("G33")
def test_the_exact_plate_is_the_same_plate_and_keeps_nothing(app, tenant_id):
    token = made_for_a_plate(app, tenant_id)
    out = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "abc.123", direction=Direction.ENTRY,
                 at=LATER)
    assert out.recognised and out.passed_by == PASSED_SAME_PLATE and out.qr_plate == "ABC123"
    assert matches(app, tenant_id) == []


# ---------------------------------------------------------------------------
# Only a VALID QR: the refusals come first
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G33")
def test_a_replaced_cars_qr_is_still_exit_only_and_a_cancelled_one_cancelled(app, tenant_id):
    token = made_for_a_plate(app, tenant_id)
    with tenant(app, tenant_id) as cursor:
        replace_car(cursor, tenant_id, TRANSIENT_ENTRY.id, "qr-1", "qr-2", date(2026, 6, 2), 3,
                    by="desk", at=LATER, reason="rental swapped", plate="NEW-77")
    app.commit()
    for read in ("", "ABC124"):
        entering = redeem(app, tenant_id, TRANSIENT_ENTRY, token, read,
                          direction=Direction.ENTRY, at=LATER)
        assert entering.refusal.code == f.REFUSAL_CREDENTIAL_EXIT_ONLY
        assert not entering.recognised and entering.passed_by is None
    leaving = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "", direction=Direction.EXIT,
                     at=LATER)
    assert leaving.recognised and leaving.passed_by == PASSED_NOTHING_READ
    with tenant(app, tenant_id) as cursor:
        cancel_code(cursor, tenant_id, TRANSIENT_ENTRY.id, "qr-1", by="desk", at=LATER,
                    reason="lost")
    app.commit()
    gone = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "", direction=Direction.EXIT, at=LATER)
    assert gone.refusal.code == f.REFUSAL_CREDENTIAL_CANCELLED and not gone.recognised


@pytest.mark.guarantee("G33")
def test_a_qr_after_its_stay_is_refused_whatever_was_read(app, tenant_id):
    token = made_for_a_plate(app, tenant_id)
    after = at(date(2026, 6, 9), 9)
    for read in ("", "ABC124", "A8C123"):
        out = redeem(app, tenant_id, TRANSIENT_ENTRY, token, read, direction=Direction.ENTRY,
                     at=after)
        assert out.refusal is not None and not out.recognised, read
        assert out.answer.outcome is not Outcome.COVERED
    assert matches(app, tenant_id) == []


# ---------------------------------------------------------------------------
# A QR stored before plates were required keeps its exact binding
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G33")
def test_a_qr_with_no_plate_keeps_its_exact_first_use_binding(app, tenant_id):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_)["token"]
    # long enough that one difference WOULD pass on a QR made for a plate
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CARX-10", at=LATER).redeemed
    same = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CARX-10", at=LATER)
    assert same.recognised and same.passed_by == PASSED_SAME_PLATE and same.qr_plate == "CARX10"
    assert similar_enough("CARX-11", "CARX-10") == PASSED_ONE_DIFFERENCE
    near = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CARX-11", at=LATER)
    assert near.refusal is not None and near.refusal.code == f.REFUSAL_CREDENTIAL_WRONG_CAR
    unread = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "", at=LATER)
    assert unread.match_required and not unread.recognised
    assert matches(app, tenant_id) == []


pytestmark = needs_postgres
