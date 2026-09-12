"""G4 -- no term, no state and no revocation refuses an exit to a vehicle inside.

The billing module guarantees no configuration can trap a car in a garage. R6
lets an owner write terms about exits. Left alone, those two produce a car that
cannot leave. The resolution, binding on this module: terms are EVALUATED at
exit -- so a transient garage can charge an out-of-terms stay -- but the
answer's meaning at the barrier is always OUT-OF-TERMS, never a refusal, and
every exit answer carries the sentence saying so, whatever its outcome.

Controls: the barrier meaning for exits planted to the no-transient entry
meaning; the exit note planted onto entries only; the transient-mode refusal
planted to fire on exits too; the revoked branch planted to refuse an answer.
"""

from __future__ import annotations

from datetime import date

import pytest

from fixtures import (
    NOON_MONDAY,
    TERMS_CONFIGURATIONS,
    TWO_HOURS_BEFORE,
    a_pass,
    at,
    no_transient_garage,
    registered,
    simple_terms,
    transient_garage,
    unstated_garage,
)
from garage_pass import findings as f
from garage_pass.access import Answer, Outcome, access
from garage_pass.passes import State, Visit
from garage_pass.terms import Direction

GARAGES = (transient_garage(), no_transient_garage(), unstated_garage())
STATES = tuple(State)


def exit_answer(garage, pass_, *, at_=NOON_MONDAY, lane="L1", visits=None, identity="CAR-1"):
    """CAR-1 is registered on the pass and entered two hours before noon; the
    exit asked about is ``identity``'s, which is CAR-1 unless a test asks
    about somebody else."""
    if visits is None:
        visits = [Visit(pass_id=pass_.id, vehicle_identity="CAR-1", entry_lane="L1",
                        entered_at=TWO_HOURS_BEFORE)]
    return access(
        garage=garage, passes=[pass_], registrations=[registered(pass_, "CAR-1")],
        visits=visits, vehicle_identity=identity, lane=lane, direction=Direction.EXIT, at=at_,
    )


def assert_exit_is_not_refused(answer: Answer) -> None:
    assert answer.direction is Direction.EXIT
    assert answer.exit_note == f.EXIT_IS_NEVER_REFUSED
    if answer.outcome is Outcome.NOT_COVERED:
        assert answer.means == f.MEANS_EXIT_OUT_OF_TERMS
    if answer.outcome is Outcome.REFUSED_TO_ANSWER:
        assert answer.missing != f.MISSING_TRANSIENT_MODE, "an exit read the transient mode"


@pytest.mark.guarantee("G4")
@pytest.mark.parametrize("state", STATES, ids=[s.value for s in STATES])
@pytest.mark.parametrize("name", list(TERMS_CONFIGURATIONS))
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
def test_every_state_every_configuration_every_garage(garage, name, state):
    pass_ = a_pass(garage_id=garage.id, terms=TERMS_CONFIGURATIONS[name], state=state)
    answer = exit_answer(garage, pass_)
    assert_exit_is_not_refused(answer)
    if state is State.REVOKED:
        assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.REVOKED


@pytest.mark.guarantee("G4")
def test_an_expired_pass_at_exit_is_out_of_terms_not_refused():
    garage = no_transient_garage()
    pass_ = a_pass(garage_id=garage.id,
                   terms=simple_terms(valid_from=date(2025, 1, 1), valid_to=date(2025, 12, 31)))
    answer = exit_answer(garage, pass_)
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.EXPIRED
    assert_exit_is_not_refused(answer)


@pytest.mark.guarantee("G4")
@pytest.mark.parametrize(
    "name,kwargs,reason",
    [
        ("wrong lane", dict(lane="L9"), f.WRONG_LANE),
        ("outside window", dict(at_=at(date(2026, 6, 1), 22)), f.OUTSIDE_WINDOW),
        ("over max stay", dict(at_=at(date(2026, 6, 1), 21)), f.OVER_MAX_STAY),
    ],
)
def test_an_out_of_terms_exit_is_answered_as_out_of_terms(name, kwargs, reason):
    """The three term violations an exit can have. The over-max-stay case uses
    a pass with no window, because with both present the published order
    reports outside-window first and this case is about the stay."""
    garage = no_transient_garage()
    terms = TERMS_CONFIGURATIONS["everything"] if name != "over max stay" else (
        TERMS_CONFIGURATIONS["max stay"]
    )
    pass_ = a_pass(garage_id=garage.id, terms=terms)
    answer = exit_answer(garage, pass_, **kwargs)
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == reason, answer
    assert_exit_is_not_refused(answer)


@pytest.mark.guarantee("G4")
def test_an_exit_at_a_garage_with_no_transient_mode_is_still_answered():
    """The entry half refuses to answer here (G6). The exit half never reads
    the field: a car inside a misconfigured garage still gets its answer."""
    garage = unstated_garage()
    pass_ = a_pass(garage_id=garage.id)
    answer = exit_answer(garage, pass_)
    assert answer.outcome is Outcome.COVERED
    assert_exit_is_not_refused(answer)
    nobody = exit_answer(garage, pass_, identity="NOBODY")
    assert nobody.outcome is Outcome.NOT_COVERED and nobody.reason == f.NO_PASS
    assert_exit_is_not_refused(nobody)


@pytest.mark.guarantee("G4")
def test_even_a_refused_answer_at_exit_carries_the_sentence():
    """A blank identity cannot be looked up; the answer is refused; the car
    still leaves, and the answer says so."""
    garage = transient_garage()
    pass_ = a_pass(garage_id=garage.id)
    answer = access(
        garage=garage, passes=[pass_], registrations=[registered(pass_)], visits=[],
        vehicle_identity="  ", lane="L1", direction=Direction.EXIT, at=NOON_MONDAY,
    )
    assert answer.outcome is Outcome.REFUSED_TO_ANSWER
    assert_exit_is_not_refused(answer)


@pytest.mark.guarantee("G4")
def test_the_control_on_the_assertion_itself():
    """``assert_exit_is_not_refused`` must be able to say no: an entry answer
    at a no-transient garage, relabelled as an exit, fails it."""
    garage = no_transient_garage()
    pass_ = a_pass(garage_id=garage.id, state=State.SUSPENDED)
    entry = access(
        garage=garage, passes=[pass_], registrations=[registered(pass_)], visits=[],
        vehicle_identity="CAR-1", lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY,
    )
    assert entry.means == f.MEANS_NOTHING_TO_ADMIT_AS
    from dataclasses import replace

    with pytest.raises(AssertionError):
        assert_exit_is_not_refused(replace(entry, direction=Direction.EXIT))
