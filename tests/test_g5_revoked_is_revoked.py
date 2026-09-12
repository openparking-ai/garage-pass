"""G5 -- a revoked pass is refused at entry in every configuration, and
revocation is terminal. His words: "revoked pass is a revoked pass. They got
divorced."

The store half -- revocation ends the pass's registrations on the revocation
day -- is in test_g12_state_changes_are_append_only.py beside the other store
state tests, and is marked G5 there.

Controls: the revoked branch of the access call planted away (a revoked pass
falls through to its terms); the terminal check planted away (revoked ->
active is accepted).
"""

from __future__ import annotations

import pytest

from fixtures import (
    NOON_MONDAY,
    TERMS_CONFIGURATIONS,
    TWO_HOURS_BEFORE,
    a_pass,
    no_transient_garage,
    registered,
    transient_garage,
)
from garage_pass import findings as f
from garage_pass.access import Outcome, access
from garage_pass.passes import State, Visit
from garage_pass.states import ALLOWED_TRANSITIONS, transition
from garage_pass.terms import Direction

GARAGES = (transient_garage(), no_transient_garage())


@pytest.mark.guarantee("G5")
@pytest.mark.parametrize("name", list(TERMS_CONFIGURATIONS))
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
def test_a_revoked_pass_is_not_covered_at_entry_in_every_configuration(garage, name):
    pass_ = a_pass(garage_id=garage.id, terms=TERMS_CONFIGURATIONS[name], state=State.REVOKED)
    answer = access(
        garage=garage, passes=[pass_], registrations=[registered(pass_)], visits=[],
        vehicle_identity="CAR-1", lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY,
    )
    assert answer.outcome is Outcome.NOT_COVERED
    assert answer.reason == f.REVOKED
    assert answer.pass_id == pass_.id
    expected = f.MEANS_TRANSIENT_STAY if garage.transient_available else f.MEANS_NOTHING_TO_ADMIT_AS
    assert answer.means == expected


ENTERABLE = [n for n, t in TERMS_CONFIGURATIONS.items() if Direction.ENTRY in t.directions]


@pytest.mark.guarantee("G5")
@pytest.mark.parametrize("name", ENTERABLE)
def test_the_same_pass_active_is_covered_so_the_red_above_is_about_revocation(name):
    """The control: every configuration in the matrix that states entry is
    satisfiable at entry at noon on a Monday, so a not-covered above can only
    be the state. The exit-only configuration is not in this list because its
    terms, not its state, refuse an entry -- a selection, not a skip."""
    garage = transient_garage()
    pass_ = a_pass(garage_id=garage.id, terms=TERMS_CONFIGURATIONS[name], state=State.ACTIVE)
    answer = access(
        garage=garage, passes=[pass_], registrations=[registered(pass_)],
        visits=[Visit(pass_id=pass_.id, vehicle_identity="CAR-1", entry_lane="L1",
                      entered_at=TWO_HOURS_BEFORE, exited_at=NOON_MONDAY, exit_lane="L1")],
        vehicle_identity="CAR-1", lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY,
    )
    assert answer.outcome is Outcome.COVERED, answer


@pytest.mark.guarantee("G5")
@pytest.mark.parametrize("to", list(State), ids=[s.value for s in State])
def test_no_transition_leaves_revoked(to):
    pass_ = a_pass(state=State.REVOKED)
    with pytest.raises(f.Refused) as refused:
        transition(pass_, to, by="owner", at=NOON_MONDAY, reason="trying")
    assert refused.value.code == f.REFUSAL_REVOKED_IS_TERMINAL
    assert ALLOWED_TRANSITIONS[State.REVOKED] == frozenset()


@pytest.mark.guarantee("G5")
def test_revoked_outranks_expiry_in_the_reason_the_lane_is_given():
    from datetime import date

    from fixtures import simple_terms

    garage = transient_garage()
    pass_ = a_pass(
        garage_id=garage.id, state=State.REVOKED,
        terms=simple_terms(valid_from=date(2025, 1, 1), valid_to=date(2025, 6, 30)),
    )
    answer = access(
        garage=garage, passes=[pass_], registrations=[registered(pass_)], visits=[],
        vehicle_identity="CAR-1", lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY,
    )
    assert answer.reason == f.REVOKED, "an expired-and-revoked pass reads as revoked"
