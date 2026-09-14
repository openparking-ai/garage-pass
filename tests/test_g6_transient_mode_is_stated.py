"""G6 -- a garage with no stated transient mode refuses to answer, naming the
field. It never defaults.

Control: the refusal planted away (``None`` falls through, and an uncovered
entry at an unstated garage is then answered as a transient stay -- the
guessed default the guarantee forbids).
"""

from __future__ import annotations

import pytest

from fixtures import (
    NOON_MONDAY,
    TERMS_CONFIGURATIONS,
    a_pass,
    no_transient_garage,
    registered,
    terms_at,
    transient_garage,
    unstated_garage,
)
from garage_pass import findings as f
from garage_pass.access import Outcome, access
from garage_pass.garage import Garage
from garage_pass.passes import State
from garage_pass.terms import Direction


def entry(garage, pass_, identity="CAR-1"):
    return access(
        garage=garage, passes=[pass_], registrations=[registered(pass_)], visits=[],
        vehicle_identity=identity, lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY,
    )


@pytest.mark.guarantee("G6")
@pytest.mark.parametrize("name", list(TERMS_CONFIGURATIONS))
@pytest.mark.parametrize("state", list(State), ids=[s.value for s in State])
def test_an_entry_at_an_unstated_garage_is_refused_an_answer(name, state):
    garage = unstated_garage()
    pass_ = a_pass(garage_ids={garage.id}, terms=terms_at(garage.id, TERMS_CONFIGURATIONS[name]),
                   state=state)
    answer = entry(garage, pass_)
    assert answer.outcome is Outcome.REFUSED_TO_ANSWER
    assert answer.missing == f.MISSING_TRANSIENT_MODE
    assert answer.means is None and answer.reason is None


@pytest.mark.guarantee("G6")
def test_a_vehicle_with_no_pass_at_an_unstated_garage_is_refused_an_answer_too():
    """The case the default would decide: nobody's car at the entry."""
    answer = entry(unstated_garage(), a_pass(garage_ids={"garage-unstated"}), identity="NOBODY")
    assert answer.outcome is Outcome.REFUSED_TO_ANSWER
    assert answer.missing == f.MISSING_TRANSIENT_MODE


@pytest.mark.guarantee("G6")
@pytest.mark.parametrize(
    "garage,means",
    [(transient_garage(), f.MEANS_TRANSIENT_STAY),
     (no_transient_garage(), f.MEANS_NOTHING_TO_ADMIT_AS)],
    ids=["transient", "no transient"],
)
def test_a_stated_garage_says_what_not_covered_means(garage, means):
    """The two stated values give two different meanings -- so the refusal on
    the unstated one is refusing to pick between things that differ."""
    answer = entry(garage, a_pass(garage_ids={garage.id}), identity="NOBODY")
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.NO_PASS
    assert answer.means == means


@pytest.mark.guarantee("G6")
def test_the_garage_value_keeps_unstated_distinct_from_false():
    assert Garage(id="g", timezone="UTC", transient_available=None).transient_available is None
    assert Garage(id="g", timezone="UTC", transient_available=False).transient_available is False
    with pytest.raises(f.Refused) as refused:
        Garage(id="g", timezone="UTC", transient_available="no")
    assert refused.value.field == "garage.transient_available"
