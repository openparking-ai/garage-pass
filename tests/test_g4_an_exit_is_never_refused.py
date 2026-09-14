"""G4 -- no term, no state and no revocation refuses an exit to a vehicle inside,
and EVERY exit produces a stated covered/not-covered answer.

The billing module guarantees no configuration can trap a car in a garage. R6
lets an owner write terms about exits. Left alone, those two produce a car that
cannot leave. The resolution, binding on this module: terms are EVALUATED at
exit -- so a transient garage can charge an out-of-terms stay -- but the
answer's meaning at the barrier is always OUT-OF-TERMS, never a refusal, and
every exit answer carries the sentence saying so.

**REFUSED-TO-ANSWER IS NOT AN OUTCOME AN EXIT CAN HAVE** (chat's ruling after
the L3): a lane at a transient garage must be told something it can act on.
Whatever cannot be evaluated is named -- a blank identity or lane, an
unmeasurable maximum stay, an unreadable pass or garage, two passes holding one
car -- and the answer is still covered or not-covered. The absence of an
answer, a refusal, and an exception are each a failure of this guarantee.

Controls: the barrier meaning for exits planted to the no-transient entry
meaning; the exit note planted onto entries only; the transient-mode refusal
planted to fire on exits too; the revoked branch planted to refuse an answer;
the blank-identity refusal planted onto exits.
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
    terms_at,
    transient_garage,
    unstated_garage,
)
from garage_pass import findings as f
from garage_pass.access import Answer, Outcome, access
from garage_pass.passes import Registration, State, Visit
from garage_pass.terms import Direction

GARAGES = (transient_garage(), no_transient_garage(), unstated_garage())
STATES = tuple(State)


def exit_answer(garage, pass_, *, at_=NOON_MONDAY, lane="L1", visits=None, identity="CAR-1"):
    """CAR-1 is registered on the pass and entered two hours before noon; the
    exit asked about is ``identity``'s, which is CAR-1 unless a test asks
    about somebody else."""
    if visits is None:
        visits = [Visit(pass_id=pass_.id, garage_id=garage.id, vehicle_identity="CAR-1",
                        entry_lane="L1", entered_at=TWO_HOURS_BEFORE)]
    return access(
        garage=garage, passes=[pass_], registrations=[registered(pass_, "CAR-1")],
        visits=visits, vehicle_identity=identity, lane=lane, direction=Direction.EXIT, at=at_,
    )


def assert_exit_is_not_refused(answer: Answer) -> None:
    assert answer.direction is Direction.EXIT
    assert answer.exit_note == f.EXIT_IS_NEVER_REFUSED
    assert answer.outcome in (Outcome.COVERED, Outcome.NOT_COVERED), (
        f"an exit produced no covered/not-covered answer: {answer}"
    )
    assert answer.missing is None, "an exit was refused an answer"
    if answer.outcome is Outcome.NOT_COVERED:
        assert answer.means == f.MEANS_EXIT_OUT_OF_TERMS


@pytest.mark.guarantee("G4")
@pytest.mark.parametrize("state", STATES, ids=[s.value for s in STATES])
@pytest.mark.parametrize("name", list(TERMS_CONFIGURATIONS))
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
def test_every_state_every_configuration_every_garage(garage, name, state):
    pass_ = a_pass(garage_ids={garage.id}, terms=terms_at(garage.id, TERMS_CONFIGURATIONS[name]),
                   state=state)
    answer = exit_answer(garage, pass_)
    assert_exit_is_not_refused(answer)
    if state is State.REVOKED:
        assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.REVOKED


@pytest.mark.guarantee("G4")
def test_an_expired_pass_at_exit_is_out_of_terms_not_refused():
    garage = no_transient_garage()
    pass_ = a_pass(garage_ids={garage.id},
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
    pass_ = a_pass(garage_ids={garage.id}, terms=terms_at(garage.id, terms))
    answer = exit_answer(garage, pass_, **kwargs)
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == reason, answer
    assert_exit_is_not_refused(answer)


@pytest.mark.guarantee("G4")
def test_an_exit_at_a_garage_with_no_transient_mode_is_still_answered():
    """The entry half refuses to answer here (G6). The exit half never reads
    the field: a car inside a misconfigured garage still gets its answer."""
    garage = unstated_garage()
    pass_ = a_pass(garage_ids={garage.id})
    answer = exit_answer(garage, pass_)
    assert answer.outcome is Outcome.COVERED
    assert_exit_is_not_refused(answer)
    nobody = exit_answer(garage, pass_, identity="NOBODY")
    assert nobody.outcome is Outcome.NOT_COVERED and nobody.reason == f.NO_PASS
    assert_exit_is_not_refused(nobody)


@pytest.mark.guarantee("G4")
@pytest.mark.parametrize(
    "name,kwargs,reason",
    [
        ("blank identity", dict(vehicle_identity="  "), f.BLANK_IDENTITY),
        ("blank lane", dict(lane=""), f.BLANK_LANE),
    ],
)
def test_a_blank_identity_or_lane_at_exit_is_answered_not_covered_naming_the_field(
    name, kwargs, reason
):
    """Nothing can be looked up or evaluated, and the exit is STILL ANSWERED:
    not-covered, naming the blank field. The same inputs at an entry are
    refused an answer (G8); an exit never is. BLANK means blank TEXT: ``None``
    is not a blank identity but a wrong-typed one, and it raises (the
    signature enumeration below) -- measured before this it was answered as
    blank, which read a caller's bug as a car with no plate."""
    garage = transient_garage()
    pass_ = a_pass(garage_ids={garage.id})
    call = dict(garage=garage, passes=[pass_], registrations=[registered(pass_)], visits=[],
                vehicle_identity="CAR-1", lane="L1", at=NOON_MONDAY)
    call.update(kwargs)
    answer = access(direction=Direction.EXIT, **call)
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == reason, (name, answer)
    assert_exit_is_not_refused(answer)
    entry = access(direction=Direction.ENTRY, **call)
    assert entry.outcome is Outcome.REFUSED_TO_ANSWER, (name, entry)


@pytest.mark.guarantee("G4")
def test_an_unmeasurable_maximum_stay_at_exit_is_answered_and_named_not_refused():
    """No open recorded entry to measure from: the exit is answered on the
    terms that can be evaluated, and the stay is named UNMEASURED -- never
    silently satisfied, never a refusal. G9 asserts the naming in detail."""
    garage = transient_garage()
    pass_ = a_pass(garage_ids={garage.id}, terms=TERMS_CONFIGURATIONS["max stay"])
    answer = exit_answer(garage, pass_, visits=[])
    assert answer.outcome is Outcome.COVERED, answer
    assert answer.unmeasured and "max_stay" in answer.unmeasured
    assert_exit_is_not_refused(answer)


@pytest.mark.guarantee("G4")
def test_two_passes_holding_one_car_at_exit_are_each_evaluated_and_the_holder_gets_out():
    """A state the module refuses to create (one car, one pass) and the
    EXCLUDE backstops -- handed in or written raw. At an exit every pass is
    evaluated: covered if any covers, the inconsistency named either way. At
    an entry the call refuses to pick one."""
    garage = transient_garage()
    good = a_pass(id="pass-good", garage_ids={garage.id})
    bad = a_pass(id="pass-bad", garage_ids={garage.id}, state=State.SUSPENDED)
    both = [registered(good, "CAR-1"), registered(bad, "CAR-1")]
    call = dict(garage=garage, passes=[bad, good], registrations=both, visits=[],
                vehicle_identity="CAR-1", lane="L1", at=NOON_MONDAY)
    answer = access(direction=Direction.EXIT, **call)
    assert answer.outcome is Outcome.COVERED and answer.pass_id == "pass-good", answer
    assert "INCONSISTENT" in answer.detail and "'pass-bad'" in answer.detail
    assert_exit_is_not_refused(answer)
    neither = access(direction=Direction.EXIT, **{**call, "passes": [bad, replace_state(good)]})
    assert neither.outcome is Outcome.NOT_COVERED and "INCONSISTENT" in neither.detail
    assert_exit_is_not_refused(neither)
    entry = access(direction=Direction.ENTRY, **call)
    assert entry.outcome is Outcome.REFUSED_TO_ANSWER and entry.missing == f.MISSING_ONE_PASS


def replace_state(pass_):
    from dataclasses import replace

    return replace(pass_, state=State.DRAFT)


@pytest.mark.guarantee("G4")
def test_no_exit_path_in_the_source_can_refuse_an_answer():
    """Every refused-to-answer input the entry half knows, asked as an exit,
    is answered covered or not-covered. (The engine does not police this with
    an ``assert`` of its own: an assertion firing at an exit lane would be the
    exception this guarantee forbids. The tests are the proof.)"""
    garage = unstated_garage()
    pass_ = a_pass(garage_ids={garage.id},
                   terms=terms_at(garage.id, TERMS_CONFIGURATIONS["max stay"]))
    two = a_pass(id="pass-2", garage_ids={garage.id})
    inputs = [
        dict(vehicle_identity=" "),
        dict(lane=" "),
        dict(visits=[]),
        dict(passes=[pass_, two], registrations=[registered(pass_), registered(two)]),
    ]
    for override in inputs:
        call = dict(garage=garage, passes=[pass_], registrations=[registered(pass_)],
                    visits=[], vehicle_identity="CAR-1", lane="L1", direction=Direction.EXIT,
                    at=NOON_MONDAY)
        call.update(override)
        assert_exit_is_not_refused(access(**call))


@pytest.mark.guarantee("G4")
def test_the_control_on_the_assertion_itself():
    """``assert_exit_is_not_refused`` must be able to say no: an entry answer
    at a no-transient garage, relabelled as an exit, fails it."""
    garage = no_transient_garage()
    pass_ = a_pass(garage_ids={garage.id}, state=State.SUSPENDED)
    entry = access(
        garage=garage, passes=[pass_], registrations=[registered(pass_)], visits=[],
        vehicle_identity="CAR-1", lane="L1", direction=Direction.ENTRY, at=NOON_MONDAY,
    )
    assert entry.means == f.MEANS_NOTHING_TO_ADMIT_AS
    from dataclasses import replace

    with pytest.raises(AssertionError):
        assert_exit_is_not_refused(replace(entry, direction=Direction.EXIT))


# ---------------------------------------------------------------------------
# Inconsistent DATA is answered; the outside reviews' cases, closed by tests.
# ---------------------------------------------------------------------------


def _dangling(identity="CAR-1", pass_id="missing"):
    from datetime import date as _date

    from garage_pass.passes import Registration

    return Registration(pass_id=pass_id, vehicle_identity=identity,
                        effective_day=_date(2026, 1, 1))


@pytest.mark.guarantee("G4")
def test_a_registration_naming_a_pass_not_handed_in_is_answered_at_exit_naming_the_pass():
    """THE OUTSIDE REVIEW'S COUNTEREXAMPLE, exactly: a registration whose
    ``pass_id`` is in none of the passes handed in, ``Direction.EXIT``, an
    aware instant. Measured before this it raised
    ``Refused(REFUSAL_PASS_NOT_FOUND)`` -- an exception at an exit lane. Now
    a stated not-covered answer naming the inconsistency and the pass; the
    well-formed exit in the same run is the positive control."""
    garage = transient_garage()
    pass_ = a_pass(garage_ids={garage.id})
    call = dict(garage=garage, passes=[pass_], visits=[], vehicle_identity="CAR-1", lane="L1",
                at=NOON_MONDAY)
    control = access(direction=Direction.EXIT, registrations=[registered(pass_, "CAR-1")], **call)
    assert control.outcome is Outcome.COVERED, "the positive control: a well-formed exit"
    try:
        answer = access(direction=Direction.EXIT, registrations=[_dangling()], **call)
    except Exception as exc:  # noqa: BLE001 -- the exception IS the defect
        pytest.fail(f"an exit raised on inconsistent data instead of answering: {exc!r}")
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.PASS_NOT_HANDED_IN
    assert_exit_is_not_refused(answer)
    assert "INCONSISTENT" in answer.detail and "'missing'" in answer.detail, answer.detail
    assert "'pass-1'" in answer.detail, "the passes that WERE handed in are named too"
    # at an ENTRY the call refuses to answer, naming the field -- never raises
    entry = access(direction=Direction.ENTRY, registrations=[_dangling()], **call)
    assert entry.outcome is Outcome.REFUSED_TO_ANSWER and entry.missing == f.MISSING_PASS_HANDED_IN
    assert "'missing'" in entry.detail


@pytest.mark.guarantee("G4")
def test_a_dangling_registration_beside_a_covering_one_gets_the_holder_out_and_is_named():
    """The two-passes shape with one of them not handed in: the pass that was
    handed in is evaluated and covers; the one that was not is named."""
    garage = transient_garage()
    pass_ = a_pass(garage_ids={garage.id})
    call = dict(garage=garage, passes=[pass_], visits=[], vehicle_identity="CAR-1", lane="L1",
                at=NOON_MONDAY, registrations=[registered(pass_, "CAR-1"), _dangling()])
    answer = access(direction=Direction.EXIT, **call)
    assert answer.outcome is Outcome.COVERED and answer.pass_id == "pass-1", answer
    assert "INCONSISTENT" in answer.detail and "'missing' was not handed in" in answer.detail
    assert_exit_is_not_refused(answer)
    entry = access(direction=Direction.ENTRY, **call)
    assert entry.outcome is Outcome.REFUSED_TO_ANSWER and entry.missing == f.MISSING_PASS_HANDED_IN


@pytest.mark.guarantee("G4")
def test_a_dangling_registration_not_in_force_today_bears_on_no_answer():
    """Ended last year: like any registration not in force, it is not
    consulted. The vehicle on no pass today is NO_PASS, not inconsistent."""
    from datetime import date as _date

    from garage_pass.passes import Registration

    garage = transient_garage()
    pass_ = a_pass(garage_ids={garage.id})
    ended = Registration(pass_id="missing", vehicle_identity="CAR-1",
                         effective_day=_date(2025, 1, 1), end_day=_date(2025, 12, 31))
    answer = access(garage=garage, passes=[pass_], registrations=[ended], visits=[],
                    vehicle_identity="CAR-1", lane="L1", direction=Direction.EXIT, at=NOON_MONDAY)
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.NO_PASS
    assert_exit_is_not_refused(answer)


@pytest.mark.guarantee("G4")
def test_a_garage_with_a_timezone_the_system_does_not_carry_cannot_be_constructed():
    """THE OTHER OUTSIDE REVIEW'S COUNTEREXAMPLE, and why it cannot exist:
    ``Garage(timezone='America/Definitely_Not_A_Zone', unreadable=None)`` is
    refused at construction by name, so ``zone()`` inside ``access`` can never
    meet an unknown zone on a garage built by a caller; ``dataclasses.replace``
    goes through the same ``__post_init__``. The stored shape of the same row
    (``garage_from_stored``) is UNREADABLE and answers at the exit -- G17 --
    and the control is the same construction with a zone the system carries."""
    from dataclasses import replace

    from garage_pass.garage import Garage, garage_from_stored
    from garage_pass.localday import UnknownTimezone

    bad = "America/Definitely_Not_A_Zone"
    with pytest.raises(UnknownTimezone) as refused:
        Garage(id="g", timezone=bad, transient_available=True)
    assert refused.value.code == f.REFUSAL_TIMEZONE_UNKNOWN and bad in refused.value.detail
    good = Garage(id="g", timezone="America/Denver", transient_available=True)  # the control
    with pytest.raises(UnknownTimezone):
        replace(good, timezone=bad)
    stored = garage_from_stored("g", bad, True)
    assert stored.unreadable is not None
    pass_ = a_pass(garage_ids={"g"})
    answer = access(garage=stored, passes=[pass_], registrations=[registered(pass_, "CAR-1")],
                    visits=[], vehicle_identity="CAR-1", lane="L1", direction=Direction.EXIT,
                    at=NOON_MONDAY)
    assert answer.outcome is Outcome.NOT_COVERED and answer.reason == f.GARAGE_UNREADABLE
    assert_exit_is_not_refused(answer)


@pytest.mark.guarantee("G4")
def test_the_two_caller_contract_errors_stay_raises_and_are_named_as_such():
    """NOT data: a naive instant and a direction that is not a ``Direction``
    raise on the first call, before there is a movement to answer about. They
    are named in the guarantee as what its sentence does not cover, and this
    test pins that they were not quietly turned into answers -- an answer
    about a movement whose instant has no timezone would be a guess."""
    garage = transient_garage()
    pass_ = a_pass(garage_ids={garage.id})
    call = dict(garage=garage, passes=[pass_], registrations=[registered(pass_, "CAR-1")],
                visits=[], vehicle_identity="CAR-1", lane="L1")
    with pytest.raises(ValueError, match="must carry a timezone"):
        access(direction=Direction.EXIT, at=NOON_MONDAY.replace(tzinfo=None), **call)
    with pytest.raises(TypeError, match="must be a Direction"):
        access(direction="exit", at=NOON_MONDAY, **call)
    assert access(direction=Direction.EXIT, at=NOON_MONDAY, **call).outcome is Outcome.COVERED


# ---------------------------------------------------------------------------
# A pass handed in twice under one id: never resolved by order (W1).
# ---------------------------------------------------------------------------


def _both_orders(copies, direction, **call):
    """The answer with the copies in the given order and in the reverse one --
    they must be EQUAL, field for field, or the order decided something."""
    forward = access(passes=list(copies), direction=direction, **call)
    backward = access(passes=list(reversed(copies)), direction=direction, **call)
    assert forward == backward, (
        f"the order of the copies decided the answer:\n  {forward}\n  {backward}"
    )
    return forward


@pytest.mark.guarantee("G4")
def test_a_pass_handed_in_twice_is_never_resolved_by_order_whether_or_not_the_copies_agree():
    """THE ORDER-DEPENDENT ANSWER. Measured before this: ``[revoked p1, active
    p1]`` answered COVERED at an ENTRY and ``[active p1, revoked p1]`` answered
    REVOKED -- the last copy in the list won silently, and a revoked pass let a
    car in because a duplicate happened to come later. Two passes carrying one
    id is INCONSISTENT DATA, the family of the dangling registration, and gets
    the same treatment: at an ENTRY refused to answer, naming the id, whether
    or not the copies agree (the caller who sent one id twice does not know
    which they meant); at an EXIT answered, never refused, every copy
    evaluated, the holder covered if any copy covers, the duplication named --
    and the SAME answer in both orders. The single-pass controls read COVERED
    and NOT-COVERED in the same run."""
    garage = transient_garage()
    active = a_pass(garage_ids={garage.id}, state=State.ACTIVE)
    revoked = a_pass(garage_ids={garage.id}, state=State.REVOKED)
    suspended = a_pass(garage_ids={garage.id}, state=State.SUSPENDED)
    call = dict(garage=garage, registrations=[registered(active, "CAR-1")], visits=[],
                vehicle_identity="CAR-1", lane="L1", at=NOON_MONDAY)
    # the controls: one copy, either state
    assert access(passes=[active], direction=Direction.ENTRY, **call).outcome is Outcome.COVERED
    alone = access(passes=[revoked], direction=Direction.ENTRY, **call)
    assert alone.outcome is Outcome.NOT_COVERED and alone.reason == f.REVOKED
    # differing copies, ENTRY: refused naming the id, the same in both orders
    entry = _both_orders([revoked, active], Direction.ENTRY, **call)
    assert entry.outcome is Outcome.REFUSED_TO_ANSWER and entry.missing == f.DUPLICATED_PASS_ID
    assert "'pass-1' was handed in 2 times" in entry.detail and "revoked" in entry.detail
    # differing copies, EXIT: answered, the holder gets out on the copy that covers
    exit_ = _both_orders([revoked, active], Direction.EXIT, **call)
    assert exit_.outcome is Outcome.COVERED and exit_.pass_id == "pass-1"
    assert "INCONSISTENT" in exit_.detail and "'pass-1' was handed in 2 times" in exit_.detail
    assert_exit_is_not_refused(exit_)
    # EQUAL copies: the same treatment -- agreement is not asked
    entry = _both_orders([active, active], Direction.ENTRY, **call)
    assert entry.outcome is Outcome.REFUSED_TO_ANSWER and entry.missing == f.DUPLICATED_PASS_ID
    exit_ = _both_orders([active, active], Direction.EXIT, **call)
    assert exit_.outcome is Outcome.COVERED and "was handed in 2 times" in exit_.detail
    # no copy covers, EXIT: not-covered, the duplication IS the reason, each copy's own inside
    exit_ = _both_orders([revoked, suspended], Direction.EXIT, **call)
    assert exit_.outcome is Outcome.NOT_COVERED and exit_.reason == f.PASS_DUPLICATED
    assert f.REVOKED in exit_.detail and f.SUSPENDED in exit_.detail, exit_.detail
    assert_exit_is_not_refused(exit_)
    # three copies, one of them at another garage under the same id: still the duplication
    elsewhere = a_pass(garage_ids={"garage-elsewhere"}, state=State.ACTIVE)
    entry = _both_orders([active, elsewhere, revoked], Direction.ENTRY, **call)
    assert entry.outcome is Outcome.REFUSED_TO_ANSWER and "3 times" in entry.detail
    # a duplicated id the vehicle is NOT registered on bears on no answer
    other = a_pass(id="pass-9", garage_ids={garage.id})
    aside = access(passes=[active, other, other], direction=Direction.ENTRY, **call)
    assert aside.outcome is Outcome.COVERED, "a duplicate the registration does not name is aside"


# ---------------------------------------------------------------------------
# What is outside the sentence, proven closed by execution (W4, A2.5).
# ---------------------------------------------------------------------------

#: A value of a type the signature does not accept, per parameter -- and for a
#: sequence parameter, a sequence holding one. Built by name so the test below
#: can prove it covers EVERY parameter the signature has, not the ones somebody
#: listed: a parameter added to ``access()`` with no entry here fails this test.
WRONG_TYPED: dict[str, tuple[object, ...]] = {
    "garage": ("garage-downtown", None, {"id": "g"}),
    "passes": ("pass-1", None, [{"id": "pass-1"}], [None]),
    "registrations": ("CAR-1", None, [("pass-1", "CAR-1")]),
    "visits": (None, [{"pass_id": "pass-1"}]),
    "vehicle_identity": (None, 1234, ["CAR-1"], b"CAR-1"),
    "lane": (None, 1, ["L1"]),
    "direction": ("exit", None, 1),
    "at": ("2026-06-01T12:00:00-06:00", None, NOON_MONDAY.date(), NOON_MONDAY.replace(tzinfo=None)),
    "garages": ("garage-far", None, [{"id": "garage-far"}], [None]),
}


@pytest.mark.guarantee("G4")
def test_every_parameter_of_the_signature_refuses_a_wrong_type_before_answering():
    """THE ENUMERATION THE SENTENCE IS DERIVED FROM. G4 names what is outside it
    as a CLASS -- a value of a type the signature does not accept -- and a class
    is a re-derivation rather than a retreat only if it is proven closed by
    execution. So: every parameter of ``access()``, read from the signature and
    not typed by hand, is handed wrong-typed values (a naive instant among
    them: an instant with no timezone is not an instant), and every one must
    RAISE on the first touch -- a ``TypeError``, or ``ValueError`` for the
    naive instant -- naming the parameter, and NEVER ANSWER. A wrong-typed value
    that produces an answer is the W3 family of defect, not an exclusion:
    measured before this, ``vehicle_identity=None`` was answered as a blank
    identity, which read a caller's bug as a car with no plate. The
    well-formed call in the same run is the control."""
    import inspect

    garage = transient_garage()
    pass_ = a_pass(garage_ids={garage.id})
    good = dict(garage=garage, passes=[pass_], registrations=[registered(pass_, "CAR-1")],
                visits=[], vehicle_identity="CAR-1", lane="L1", direction=Direction.EXIT,
                at=NOON_MONDAY)
    parameters = list(inspect.signature(access).parameters)
    assert sorted(parameters) == sorted(WRONG_TYPED), (
        "the signature and the enumeration disagree: every parameter needs wrong-typed values"
    )
    assert access(**good).outcome is Outcome.COVERED, "the control: the well-formed call answers"
    for name in parameters:
        for wrong in WRONG_TYPED[name]:
            call = {**good, name: wrong}
            try:
                answer = access(**call)
            except (TypeError, ValueError) as exc:
                assert name in str(exc) or name == "at" and "at" in str(exc), (
                    f"{name}={wrong!r} raised without naming the parameter: {exc!r}"
                )
                continue
            except Exception as exc:  # noqa: BLE001 -- judged here
                pytest.fail(f"{name}={wrong!r} raised {exc!r}, not the caller-contract error")
            pytest.fail(
                f"{name}={wrong!r} ANSWERED {answer.outcome.value} -- a wrong-typed value that "
                "answers is a defect, not an exclusion"
            )


@pytest.mark.guarantee("G4")
def test_the_sentence_names_the_class_the_enumeration_closed():
    """The registry's G4 text names the CLASS ('a type the signature does not
    accept'), the ONE environment error, and no list of instances -- so the
    published row cannot drift back into counting."""
    from _guarantees import GUARANTEES

    sentence = GUARANTEES["G4"]
    assert "a type the signature does not accept" in sentence
    assert "raises on the first touch" in sentence and "never answers" in sentence
    assert "timezone database" in sentence
    assert "two CALLER-CONTRACT errors" not in sentence, "the list of instances is back"


@pytest.mark.guarantee("G4")
@pytest.mark.parametrize(
    "build,what",
    [
        (lambda: Registration(pass_id="p", vehicle_identity=None, effective_day=date(2026, 1, 1)),
         "Registration.vehicle_identity"),
        (lambda: Registration(pass_id="p", vehicle_identity=1234, effective_day=date(2026, 1, 1)),
         "Registration.vehicle_identity"),
        (lambda: Registration(pass_id={"id": "p"}, vehicle_identity="C",
                              effective_day=date(2026, 1, 1)), "Registration.pass_id"),
        (lambda: Registration(pass_id="p", vehicle_identity="C", effective_day="2026-01-01"),
         "Registration.effective_day"),
        (lambda: Registration(pass_id="p", vehicle_identity="C", effective_day=None),
         "Registration.effective_day"),
        (lambda: Registration(pass_id="p", vehicle_identity="C", effective_day=NOON_MONDAY),
         "Registration.effective_day"),
        (lambda: Registration(pass_id="p", vehicle_identity="C", effective_day=date(2026, 1, 1),
                              end_day="2027-01-01"), "Registration.end_day"),
        (lambda: Visit(pass_id="p", garage_id="g", vehicle_identity=None, entry_lane="L1",
                       entered_at=NOON_MONDAY), "Visit.vehicle_identity"),
        (lambda: Visit(pass_id="p", garage_id="g", vehicle_identity="C", entry_lane=1,
                       entered_at=NOON_MONDAY), "Visit.entry_lane"),
        (lambda: Visit(pass_id="p", garage_id=None, vehicle_identity="C", entry_lane="L1",
                       entered_at=NOON_MONDAY), "Visit.garage_id"),
        (lambda: Visit(pass_id="p", garage_id="g", vehicle_identity="C", entry_lane="L1",
                       entered_at=NOON_MONDAY, exit_lane=2), "Visit.exit_lane"),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_a_registration_or_visit_with_a_wrong_typed_field_cannot_be_constructed(build, what):
    """THE EIGHT PURE-API RAISES THE L3 FOUND, closed at the door. These shapes
    were CONSTRUCTED without complaint and raised at an exit lane: a string
    day (``'<=' not supported``), a None identity (``AttributeError``), a
    datetime where a day belongs (read as its midnight, silently, before
    ``covers`` raised). ``Registration`` validated nothing; ``Visit`` only its
    instants. Now every field is checked against its declared type -- derived
    from the annotation, the same source the document loader reads -- so a
    wrong-typed registration is not a path that exists, like a wrong-typed
    Pass. The control: the well-formed shapes construct."""
    with pytest.raises(TypeError, match=what):
        build()
    assert Registration(pass_id="p", vehicle_identity="C", effective_day=date(2026, 1, 1))
    assert Visit(pass_id="p", garage_id="g", vehicle_identity="C", entry_lane="L1",
                 entered_at=NOON_MONDAY)
