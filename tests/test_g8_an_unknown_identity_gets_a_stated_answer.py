"""G8 -- an unknown identity produces a STATED answer, never an accidental
refusal and never a silent pass; a blank one is refused an answer by name.

Controls: the not-covered NO_PASS branch planted to refuse an answer instead;
the blank-identity check planted away (a blank identity is then looked up as
if it were a vehicle and comes back NO_PASS -- a stated answer to a question
that was never asked).
"""

from __future__ import annotations

from datetime import date

import pytest

from fixtures import NOON_MONDAY, a_pass, registered, transient_garage
from garage_pass import findings as f
from garage_pass.access import Outcome, access
from garage_pass.passes import State
from garage_pass.terms import Direction

GARAGE = transient_garage()


def ask(identity, registrations=(), passes=(), direction=Direction.ENTRY, lane="L1"):
    return access(
        garage=GARAGE, passes=list(passes), registrations=list(registrations), visits=[],
        vehicle_identity=identity, lane=lane, direction=direction, at=NOON_MONDAY,
    )


@pytest.mark.guarantee("G8")
@pytest.mark.parametrize("direction", list(Direction), ids=[d.value for d in Direction])
def test_an_identity_nobody_registered_is_not_covered_no_pass(direction):
    pass_ = a_pass()
    answer = ask("UNKNOWN-1", [registered(pass_, "CAR-1")], [pass_], direction)
    assert answer.outcome is Outcome.NOT_COVERED
    assert answer.reason == f.NO_PASS
    assert answer.pass_id is None
    assert "'UNKNOWN-1'" in answer.detail


@pytest.mark.guarantee("G8")
def test_an_ended_registration_is_named_in_the_detail():
    pass_ = a_pass()
    ended = registered(pass_, "CAR-1", effective=date(2026, 1, 1), end=date(2026, 5, 1))
    answer = ask("CAR-1", [ended], [pass_])
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.NO_PASS
    assert "ended on 2026-05-01" in answer.detail and "'pass-1'" in answer.detail


@pytest.mark.guarantee("G8")
def test_a_future_registration_is_named_in_the_detail():
    pass_ = a_pass()
    future = registered(pass_, "CAR-1", effective=date(2026, 7, 1))
    answer = ask("CAR-1", [future], [pass_])
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.NO_PASS
    assert "takes effect on 2026-07-01" in answer.detail


@pytest.mark.guarantee("G8")
def test_a_registration_ended_by_revocation_reads_as_revoked_not_no_pass():
    """The store ends registrations on revocation (G5); the reason the lane
    is given is still the real one."""
    pass_ = a_pass(state=State.REVOKED)
    ended = registered(pass_, "CAR-1", effective=date(2026, 1, 1), end=date(2026, 5, 1))
    answer = ask("CAR-1", [ended], [pass_])
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.REVOKED


@pytest.mark.guarantee("G8")
@pytest.mark.parametrize("blank", ["", "   ", None, 12], ids=["empty", "spaces", "None", "int"])
def test_a_blank_identity_is_refused_an_answer_naming_the_field(blank):
    answer = ask(blank)
    assert answer.outcome is Outcome.REFUSED_TO_ANSWER
    assert answer.missing == f.MISSING_VEHICLE_IDENTITY
    assert answer.reason is None


@pytest.mark.guarantee("G8")
def test_a_blank_lane_is_refused_an_answer_naming_the_field():
    answer = ask("CAR-1", lane=" ")
    assert answer.outcome is Outcome.REFUSED_TO_ANSWER and answer.missing == f.MISSING_LANE


@pytest.mark.guarantee("G8")
def test_two_passes_holding_one_identity_is_refused_an_answer_not_picked():
    """The state G1 prevents in the store; a library caller can still hand it
    in. Refused by name in either order, never decided by list position."""
    a, z = a_pass(id="pass-a"), a_pass(id="pass-z")
    for order in ((a, z), (z, a)):
        answer = ask("CAR-1", [registered(a, "CAR-1"), registered(z, "CAR-1")], order)
        assert answer.outcome is Outcome.REFUSED_TO_ANSWER
        assert answer.missing == f.MISSING_ONE_PASS
        assert "'pass-a'" in answer.detail and "'pass-z'" in answer.detail


@pytest.mark.guarantee("G8")
def test_a_registration_naming_a_pass_nobody_handed_in_is_a_refused_request():
    with pytest.raises(f.Refused) as refused:
        ask("CAR-1", [registered(a_pass(id="ghost"), "CAR-1")], [a_pass()])
    assert refused.value.code == f.REFUSAL_PASS_NOT_FOUND


@pytest.mark.guarantee("G8")
def test_a_registration_at_another_garage_is_not_this_garages_business():
    elsewhere = a_pass(id="pass-elsewhere", garage_id="garage-other")
    answer = ask("CAR-1", [registered(elsewhere, "CAR-1")], [elsewhere])
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.NO_PASS
