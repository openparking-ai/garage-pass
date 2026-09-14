"""The access answer. The whole point of the module.

Given a garage, a vehicle identity, a lane, a direction and an instant -- and
the passes, registrations and recorded visits the caller holds -- one of:

* **covered** -- with the pass, its label and the term that covers it;
* **not covered** -- with a plain reason from ``findings.NOT_COVERED_REASONS``;
* **refused to answer** -- the call cannot answer without guessing, and names
  the field that would let it (``findings.REFUSED_TO_ANSWER``). **An ENTRY
  outcome only: an exit is never refused an answer.**

**NO FEE, NO AMOUNT, NO BALANCE, EVER CROSSES THIS CALL.** It is an access fact.
There is no field on ``Answer`` that could carry money, and a control plants
one and requires red.

**THIS MODULE NEVER OPENS OR CLOSES A GATE**, never counts who is inside and
never holds session state. It answers; the lane acts. What it does hold is a
LEDGER of the visits the lane told it about -- ``record_entry`` and
``record_exit`` in the store -- because a visit allowance and a maximum stay
are computed from the module's own recorded visits and from nothing else. A
ledger is not a count of who is inside: nothing here answers that question.

**AN EXIT IS NEVER REFUSED, AND EVERY EXIT IS ANSWERED.** A pass's terms govern
entry and which lanes may be used. At exit the same terms are EVALUATED -- an
exit outside them is answered not-covered, reason named, so that a transient
garage can charge the stay -- but the answer's meaning at the barrier is always
``findings.MEANS_EXIT_OUT_OF_TERMS``, every exit answer carries
``findings.EXIT_IS_NEVER_REFUSED``, and **an exit's outcome is always covered or
not covered**. Whatever cannot be evaluated at an exit is NAMED, never guessed
and never a refusal: a blank identity or lane is not-covered naming the blank
field; a maximum stay with no open recorded entry to measure from is answered
on the terms that can be evaluated with the stay marked UNMEASURED in
``Answer.unmeasured``; a stored pass or garage this module cannot read is
not-covered naming the pass and the field; two passes that both hold the
vehicle -- a state this module refuses to create -- are each evaluated and the
vehicle is covered if any of them covers it, the inconsistency named; a
registration naming a pass that was not handed in -- inconsistent data, which
an integrator assembling registrations from their own store can produce -- is
answered not-covered naming that pass, never raised. A garage whose transient
mode is unstated is refused an answer at ENTRY only; the exit half of the call
does not read that field at all, because nothing about an exit may depend on
configuration.

**WHAT "NEVER AN EXCEPTION" DOES NOT COVER, SAID PLAINLY -- AND IT IS A CLASS,
NOT A LIST.** A value of a type the signature does not accept -- for any
parameter, or any element of ``passes``, ``registrations`` or ``visits``; a
naive ``at`` is one (an instant with no timezone is not an instant) -- raises
on the first touch (``_require_inputs``), before there is an instant, a pass or
an answer to give, and NEVER answers: measured before this, ``vehicle_identity
=None`` was answered as a blank identity, which read a caller's bug as a car
with no plate. G4's test enumerates the signature and proves each parameter
raises; the class is closed by execution, which is what lets the sentence name
it rather than count instances. One environment error is raised by its own
name: a machine with no timezone database at all
(``TimezoneDatabaseUnavailable``), on which nothing can be read. A garage
carrying a zone this system does not carry cannot be constructed
(``Garage.__post_init__`` refuses it), and neither can a registration or a
visit with a wrong-typed field (``typed.require_typed``) -- through the pure
API. THE MODULE ANSWERS WHEN IT HOLDS A RECORD WHOSE CONTENT IT CANNOT READ,
and refuses only when it holds no record at all, or no instant: a STORED row it
cannot read loads unreadable and answers, above; a DOCUMENT it cannot read is
answered at an exit the same way (``documents.load_or_degrade`` builds the
same carrier a stored row becomes, or ``exit_on_unreadable_records`` below
states the not-covered answer for a registration, a visit, or a carrier that
cannot be built) and refused by name at an entry. A pass handed in twice under
one id is inconsistent data like the dangling registration: never resolved by
order, every copy evaluated, the duplication named.

**A PASS ANSWERS ONLY AT THE GARAGES IT NAMES.** A pass carries a set of
garages (``Pass.garage_ids``); which passes this call SELECTS is decided by
membership -- ``garage.id in p.garage_ids`` -- at both places a pass is read
for its garage (the duplicated-id grouping and ``by_id``), and a pass that
does not name this garage is not this garage's business: a registration on it
is skipped, never dangling. The terms are one set, evaluated here at whichever
garage the car is at; only the lanes are read per garage
(``Terms.lanes_at``). Membership changes WHICH passes are selected, never WHEN
anything is checked.

**EACH RECORDED ENTRY IS READ ON THE CLOCK OF THE GARAGE IT WAS RECORDED AT.**
The allowance is one count over every garage of the pass (C5), but whether
an entry fell "in this window, today" is a question about a wall clock, and
the wall clock is the one on the door the car drove through -- not the one at
the garage asking now. So the pass's garages reach this call (``garages``):
a per-window count resolves each entry's garage by id, reads that entry's day
and minute in THAT garage's zone, and compares the day to the asking garage's
``today``. Measured before this (the G3a merge gate): a pass over Denver and
Tokyo, one visit per window; a visit at Tokyo at 09:00 Monday read on
Denver's clock as 18:00 Sunday, counted nothing, and the allowance was spent
twice. Zero effect while every garage of a pass shares one zone. The
``LIFE`` allowance reads no clock and gains none. An entry recorded at a
garage that was not handed in -- inconsistent data, the dangling-registration
shape -- is REFUSED at the entry naming the garage, never read on the wrong
clock and never raised; a handed-in garage this module cannot read refuses
naming its field, the same path the asking garage takes; one handed in twice
under one id refuses naming the duplication, never resolved by order. The
asking garage is the ``garage`` parameter, whatever ``garages`` also carries
under its id: the caller said which garage the question is about. Only an
ENTRY counts an allowance, so no exit reaches any of those refusals.

**THE ORDER OF THE CHECKS IS PART OF THE CONTRACT.** An unreadable garage
answers first (without a clock nothing else can be read). Then the blank
identity and lane. Then, at entry, the transient mode. Then which pass. Per
pass: revoked outranks everything (revoked is revoked); then an unreadable
pass (its expiry cannot be derived); then expiry, which is derived; then the
typed state; then the terms: direction, lane, window, and -- at entry -- the
visit allowance; at exit, the maximum stay. The first thing that fails is the
reason; nothing after it is evaluated or reported.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum
from zoneinfo import ZoneInfo

from garage_pass.findings import (
    BLANK_IDENTITY,
    BLANK_LANE,
    DIRECTION_NOT_ALLOWED,
    DUPLICATED_GARAGE_ID,
    DUPLICATED_PASS_ID,
    EXIT_IS_NEVER_REFUSED,
    EXPIRED,
    GARAGE_UNREADABLE,
    MEANS_COVERED,
    MEANS_EXIT_OUT_OF_TERMS,
    MEANS_NOTHING_TO_ADMIT_AS,
    MEANS_TRANSIENT_STAY,
    MISSING_GARAGE_HANDED_IN,
    MISSING_LANE,
    MISSING_ONE_PASS,
    MISSING_PASS_HANDED_IN,
    MISSING_TIMEZONE,
    MISSING_TRANSIENT_MODE,
    MISSING_VEHICLE_IDENTITY,
    NO_PASS,
    NOT_ACTIVE,
    NOT_STARTED,
    OUT_OF_VISITS,
    OUTSIDE_WINDOW,
    OVER_MAX_STAY,
    PASS_DUPLICATED,
    PASS_NOT_HANDED_IN,
    PASS_UNREADABLE,
    RECORD_UNREADABLE,
    REFUSED_TO_ANSWER,
    REVOKED,
    SUSPENDED,
    UNREADABLE_TERMS,
    WRONG_LANE,
    Unreadable,
)
from garage_pass.garage import Garage
from garage_pass.localday import (
    day_of,
    elapsed,
    iso_weekday_of,
    local,
    minute_of_day,
    require_aware,
    zone,
)
from garage_pass.passes import EXPIRED as EXPIRED_STATE
from garage_pass.passes import Pass, Registration, State, Visit
from garage_pass.states import effective_state
from garage_pass.terms import AllowancePeriod, Direction, Window


class Outcome(Enum):
    COVERED = "covered"
    NOT_COVERED = "not_covered"
    REFUSED_TO_ANSWER = "refused_to_answer"


@dataclass(frozen=True)
class Answer:
    """What the lane is told. No money, no barrier command, no session state."""

    outcome: Outcome
    direction: Direction
    vehicle_identity: str
    lane: str
    #: The pass the answer is about, when there is one.
    pass_id: str | None
    pass_label: str | None
    #: For a covered answer: the terms, and which of them covered this movement.
    covering_term: str | None
    #: For a not-covered answer: a key of ``findings.NOT_COVERED_REASONS``.
    reason: str | None
    #: For a refused answer: a key of ``findings.REFUSED_TO_ANSWER``. Entry only.
    missing: str | None
    #: A key of ``findings.BARRIER_MEANINGS``, or None when nothing was answered.
    means: str | None
    detail: str
    #: ``findings.EXIT_IS_NEVER_REFUSED`` on every exit answer; None on entry.
    exit_note: str | None
    #: A term that could not be measured and was NOT treated as satisfied
    #: silently: names the term and why. Only a maximum stay at an exit with no
    #: open recorded entry to measure from, today. None when everything the
    #: answer rests on was measured.
    unmeasured: str | None


def access(
    *,
    garage: Garage,
    passes: Sequence[Pass],
    registrations: Sequence[Registration],
    visits: Sequence[Visit],
    vehicle_identity: str,
    lane: str,
    direction: Direction,
    at: datetime,
    garages: Sequence[Garage] = (),
) -> Answer:
    """``garages``: the garages the passes name, so that a recorded entry at
    another garage of a pass is read on ITS clock (the module docstring). The
    store hands in every garage of every pass it selected; the command line
    hands in ``--garages``. Absent means not handed in -- an entry recorded at
    a garage that is not here is then refused by name at an entry with a
    per-window allowance, and nothing else reads the sequence."""
    _require_inputs(garage, passes, registrations, visits, vehicle_identity, lane, direction, at,
                    garages)
    identity = vehicle_identity.strip()
    lane_name = lane.strip()
    is_exit = direction is Direction.EXIT
    exit_note = EXIT_IS_NEVER_REFUSED if is_exit else None

    def refused(missing: str, detail: str, pass_: Pass | None = None) -> Answer:
        """ENTRY ONLY. No exit path reaches here -- G4's tests prove it, and
        deliberately not an ``assert``: an assertion that fired here would be an
        exception at an exit lane, the one thing this module may never produce."""
        return Answer(
            outcome=Outcome.REFUSED_TO_ANSWER,
            direction=direction,
            vehicle_identity=identity,
            lane=lane_name,
            pass_id=pass_.id if pass_ else None,
            pass_label=pass_.label if pass_ else None,
            covering_term=None,
            reason=None,
            missing=missing,
            means=None,
            detail=f"{REFUSED_TO_ANSWER[missing]} {detail}".strip(),
            exit_note=exit_note,
            unmeasured=None,
        )

    def not_covered(
        reason: str, detail: str, pass_: Pass | None = None, unmeasured: str | None = None
    ) -> Answer:
        if is_exit:
            means = MEANS_EXIT_OUT_OF_TERMS
        elif garage.transient_available:
            means = MEANS_TRANSIENT_STAY
        else:
            means = MEANS_NOTHING_TO_ADMIT_AS
        return Answer(
            outcome=Outcome.NOT_COVERED,
            direction=direction,
            vehicle_identity=identity,
            lane=lane_name,
            pass_id=pass_.id if pass_ else None,
            pass_label=pass_.label if pass_ else None,
            covering_term=None,
            reason=reason,
            missing=None,
            means=means,
            detail=detail,
            exit_note=exit_note,
            unmeasured=unmeasured,
        )

    def covered(pass_: Pass, term: str, unmeasured: str | None = None) -> Answer:
        return Answer(
            outcome=Outcome.COVERED,
            direction=direction,
            vehicle_identity=identity,
            lane=lane_name,
            pass_id=pass_.id,
            pass_label=pass_.label,
            covering_term=term,
            reason=None,
            missing=None,
            means=MEANS_COVERED,
            detail=f"covered by pass {pass_.id!r} ({pass_.label}).",
            exit_note=exit_note,
            unmeasured=unmeasured,
        )

    # --- what cannot be evaluated at all -------------------------------------
    # The garage first: without a clock no day, window or range can be read.
    if garage.unreadable is not None:
        what = f"garage {garage.id!r}: {garage.unreadable.describe()}"
        if is_exit:
            return not_covered(GARAGE_UNREADABLE, what)
        return refused(MISSING_TIMEZONE, what)
    tz = zone(garage.timezone)
    today = day_of(at, tz)

    def rendered(instant: datetime) -> str:
        """An instant as the garage's wall clock reads it -- every instant a
        detail shows is rendered in the garage's zone, whatever offset it
        arrived with. Measured before this: an OVER_MAX_STAY detail showed the
        recorded entry in the DATABASE SESSION's zone beside the exit in the
        caller's offset; the instants and the duration were right, the
        rendering was not."""
        return local(instant, tz).isoformat()

    handed_in_garages: dict[str, list[Garage]] = {}
    for g in garages:
        handed_in_garages.setdefault(g.id, []).append(g)

    def clock_at(garage_id: str) -> ZoneInfo | tuple[str, str]:
        """The zone a recorded entry's day and minute are read in: the zone of
        the garage it was recorded at. The asking garage's is ``tz`` (already
        known readable above). Any other garage is resolved from ``garages``
        by id, and what cannot be resolved is a (missing, detail) pair the
        caller turns into a refusal -- never a guess at ``tz``."""
        if garage_id == garage.id:
            return tz
        copies = handed_in_garages.get(garage_id, [])
        if not copies:
            named = ", ".join(sorted(repr(gid) for gid in handed_in_garages)) or "none"
            return (
                MISSING_GARAGE_HANDED_IN,
                f"garage {garage_id!r} was not handed in (handed in: {named}; asking: "
                f"{garage.id!r}).",
            )
        if len(copies) > 1:
            return (
                DUPLICATED_GARAGE_ID,
                f"garage {garage_id!r} was handed in {len(copies)} times, which one id, one "
                "garage forbids.",
            )
        other = copies[0]
        if other.unreadable is not None:
            return MISSING_TIMEZONE, f"garage {other.id!r}: {other.unreadable.describe()}"
        return zone(other.timezone)

    if not identity:
        if is_exit:
            return not_covered(BLANK_IDENTITY, f"vehicle_identity is {vehicle_identity!r}.")
        return refused(MISSING_VEHICLE_IDENTITY, f"got {vehicle_identity!r}.")
    if not lane_name:
        if is_exit:
            return not_covered(BLANK_LANE, f"lane is {lane!r}.")
        return refused(MISSING_LANE, f"got {lane!r}.")
    # The transient mode decides what an uncovered ENTRY means. It is read
    # here, before anything else, so that a garage that has not stated it is
    # discovered at the first car and not at the first uncovered one. An EXIT
    # never reads it: see the module docstring.
    if not is_exit and garage.transient_available is None:
        return refused(MISSING_TRANSIENT_MODE, f"garage {garage.id!r}.")

    # --- which pass, if any -------------------------------------------------
    # A pass handed in TWICE under one id is INCONSISTENT DATA and is never
    # resolved by order. Measured before this: ``by_id`` was a dict, so the
    # last copy won silently and ``[revoked p1, active p1]`` admitted at an
    # entry the car that ``[active p1, revoked p1]`` refused. Copies are grouped
    # by id; an id with more than one copy, any of them at this garage, is
    # duplicated, and whether the copies agree is not asked -- the caller who
    # sent one id twice does not know which they meant. At an entry the call
    # refuses to answer naming the id; at an exit every copy is evaluated in a
    # fixed order, the holder is covered if any copy covers, and the
    # duplication is named either way.
    copies: dict[str, list[Pass]] = {}
    for p in passes:
        copies.setdefault(p.id, []).append(p)
    duplicated = {
        pid: sorted(ps, key=_copy_order)
        for pid, ps in copies.items()
        if len(ps) > 1 and any(garage.id in p.garage_ids for p in ps)
    }
    by_id = {p.id: p for p in passes if garage.id in p.garage_ids and p.id not in duplicated}
    here = []
    # A registration naming a pass that was NOT handed in is INCONSISTENT DATA
    # -- the registrations and the passes disagree -- and it is answered, not
    # raised. Measured before this: it raised ``Refused(REFUSAL_PASS_NOT_FOUND)``
    # at an exit, which an outside review read against the published sentence
    # "never an exception" and was right to. The store cannot produce it (it
    # loads the passes its registrations name); an integrator assembling
    # registrations from their own store can. Only a dangling registration IN
    # FORCE today bears on this instant; one that has ended, or has not started,
    # bears on no answer and is not consulted, like any other such registration.
    dangling: list[Registration] = []
    for registration in registrations:
        if registration.vehicle_identity.strip() != identity:
            continue
        if registration.pass_id in duplicated:
            here.append(registration)
            continue
        if registration.pass_id not in by_id:
            if any(p.id == registration.pass_id for p in passes):
                continue  # a pass that does not name this garage; not this garage's business
            if registration.covers(today):
                dangling.append(registration)
            continue
        here.append(registration)
    effective = [r for r in here if r.covers(today)]
    handed_in = sorted(repr(pid) for pid in copies if pid in by_id or pid in duplicated)
    duplicated_named = sorted({r.pass_id for r in effective if r.pass_id in duplicated})
    if dangling and not is_exit:
        named = ", ".join(sorted(repr(r.pass_id) for r in dangling))
        return refused(
            MISSING_PASS_HANDED_IN,
            f"registration of {identity!r} names pass {named}, in force on {today}, and no "
            f"pass with that id was handed in (handed in: {', '.join(handed_in) or 'none'}).",
        )
    if duplicated_named and not is_exit:
        return refused(
            DUPLICATED_PASS_ID,
            "; ".join(_duplication(pid, duplicated[pid]) for pid in duplicated_named)
            + f" -- the registration of {identity!r} in force on {today} names it.",
        )
    if dangling and not effective:
        r = dangling[0]
        return not_covered(
            PASS_NOT_HANDED_IN,
            f"INCONSISTENT: registration of {identity!r} names pass {r.pass_id!r}, in force "
            f"on {today}, and no pass with that id was handed in (handed in: "
            f"{', '.join(handed_in) or 'none'}); the registrations and the passes disagree. "
            "Answered not-covered, never raised.",
        )
    if not effective:
        # A stated answer for an unknown identity -- never an accidental
        # refusal and never a silent pass. Where a registration exists but is
        # not in force today, the detail says which and when; a revoked pass
        # is named as revoked, because that is the reason and not "no pass".
        # (A pass handed in twice is not read for its state here: that would be
        # picking a copy.)
        revoked = [
            r for r in here if r.pass_id in by_id and by_id[r.pass_id].state is State.REVOKED
        ]
        if revoked:
            r = max(revoked, key=lambda r: (r.end_day or today, r.effective_day))
            return not_covered(
                REVOKED,
                f"registration of {identity!r} on pass {r.pass_id!r} "
                f"({by_id[r.pass_id].label}) ended on {r.end_day}: the pass was revoked.",
                by_id[r.pass_id],
            )
        if here:
            r = max(here, key=lambda r: (r.end_day or today, r.effective_day))
            when = (
                f"ended on {r.end_day}" if r.end_day and r.end_day <= today
                else f"takes effect on {r.effective_day}"
            )
            return not_covered(
                NO_PASS,
                f"no registration of {identity!r} at garage {garage.id!r} is in force on "
                f"{today}; the nearest, on pass {r.pass_id!r}, {when}.",
            )
        return not_covered(
            NO_PASS,
            f"no registration of {identity!r} at garage {garage.id!r} on {today}.",
        )

    def evaluate(pass_: Pass) -> Answer:
        """One pass, in the order that is the contract."""
        # --- the state ------------------------------------------------------
        if pass_.state is State.REVOKED:
            return not_covered(REVOKED, f"pass {pass_.id!r} is revoked.", pass_)
        if pass_.unreadable is not None:
            # Its expiry cannot be derived (valid_to lives in the terms), so
            # nothing below can be read. Stated, naming the pass and the field.
            # ONE sentence for BOTH doors -- a stored row (G17) and, at an exit,
            # a document (documents.load_or_degrade) -- so it says "carries",
            # never "is stored with": measured before this, 66 of 199 answered
            # exits in the gate's census told the operator a row was stored
            # that never existed, and sent them to a database to undo a charge
            # against it. The wording is the registry sentence's own.
            what = (
                f"pass {pass_.id!r} ({pass_.label}) carries a value this module "
                f"refuses to read -- {pass_.unreadable.describe()}"
            )
            if is_exit:
                return not_covered(PASS_UNREADABLE, what, pass_)
            return refused(UNREADABLE_TERMS, what, pass_)
        terms = pass_.terms
        assert terms is not None
        state = effective_state(pass_, today)
        if state == EXPIRED_STATE:
            return not_covered(
                EXPIRED, f"pass {pass_.id!r} valid_to {terms.valid_to} is before {today}.",
                pass_,
            )
        if state == State.SUSPENDED.value:
            return not_covered(SUSPENDED, f"pass {pass_.id!r} is suspended.", pass_)
        if state in (State.DRAFT.value, State.AWAITING_ENROLMENT.value):
            return not_covered(NOT_ACTIVE, f"pass {pass_.id!r} is {state}.", pass_)
        if terms.valid_from is not None and today < terms.valid_from:
            return not_covered(
                NOT_STARTED,
                f"pass {pass_.id!r} valid_from {terms.valid_from} is after {today}.",
                pass_,
            )

        # --- the terms ----------------------------------------------------------
        if direction not in terms.directions:
            return not_covered(
                DIRECTION_NOT_ALLOWED,
                f"pass {pass_.id!r} states {sorted(d.value for d in terms.directions)}, "
                f"not {direction.value!r}.",
                pass_,
            )
        lanes_here = terms.lanes_at(garage.id)
        if lanes_here is not None and lane_name not in lanes_here:
            return not_covered(
                WRONG_LANE,
                f"pass {pass_.id!r} allows lanes {sorted(lanes_here)} at garage {garage.id!r}, "
                f"not {lane_name!r}.",
                pass_,
            )

        window: Window | None = None
        if terms.windows:
            weekday = iso_weekday_of(at, tz)
            minute = minute_of_day(at, tz)
            for candidate in terms.windows:
                inside = candidate.start_minute <= minute < candidate.end_minute
                if weekday in candidate.days and inside:
                    window = candidate
                    break
            if window is None:
                return not_covered(
                    OUTSIDE_WINDOW,
                    f"{at.isoformat()} is {today} ({_day_name(weekday)}) {minute // 60:02d}:"
                    f"{minute % 60:02d} in {garage.timezone}, inside none of: "
                    + "; ".join(w.describe() for w in terms.windows) + ".",
                    pass_,
                )

        covering = [terms.describe()]
        if window is not None:
            covering.append(f"in window {window.describe()} on {today}")

        if not is_exit and terms.visit_allowance is not None:
            counted = _visits_used(visits, pass_, window, today, clock_at)
            if isinstance(counted, NoClock):
                # an entry on this pass at a garage whose clock is not here:
                # refused by name, never read on this garage's clock instead
                return refused(counted.missing, counted.detail, pass_)
            used, denominator = counted
            allowed = terms.visit_allowance.count
            if used >= allowed:
                return not_covered(
                    OUT_OF_VISITS, f"{used} of {allowed} visit(s) used; {denominator}.", pass_
                )
            covering.append(f"visit {used + 1} of {allowed}; {denominator}")

        unmeasured: str | None = None
        if is_exit and terms.max_stay is not None:
            open_visit = _open_visit(visits, garage, pass_, identity)
            if open_visit is None or at < open_visit.entered_at:
                # UNMEASURED, and said so by name -- never treated as satisfied
                # silently, never a refusal: the exit is answered on the terms
                # that can be evaluated and the lane is told what was not.
                unmeasured = (
                    f"max_stay {terms.max_stay} of pass {pass_.id!r} could not be measured for "
                    f"vehicle {identity!r} at {rendered(at)}: "
                    + (
                        f"the open recorded entry is at {rendered(open_visit.entered_at)}, "
                        "later than this exit."
                        if open_visit else
                        "no open recorded entry of this vehicle on this pass at this garage."
                    )
                )
                covering.append("max stay UNMEASURED (see unmeasured)")
            else:
                stayed = elapsed(open_visit.entered_at, at)
                if stayed > terms.max_stay:
                    return not_covered(
                        OVER_MAX_STAY,
                        f"entered {rendered(open_visit.entered_at)}, exiting {rendered(at)} "
                        f"({garage.timezone}): {stayed} elapsed, more than {terms.max_stay}.",
                        pass_,
                    )
                covering.append(f"stayed {stayed} of at most {terms.max_stay}")

        return covered(pass_, "; ".join(covering), unmeasured)

    if len(effective) == 1 and not dangling and not duplicated_named:
        return evaluate(by_id[effective[0].pass_id])

    # More than one pass holds the vehicle today -- a state this module refuses
    # to create (one car, one pass per garage) and the database's EXCLUDE
    # backstops; it was handed in or written raw. At an ENTRY the call will
    # not pick one. At an EXIT every one is evaluated: the vehicle is covered
    # if any of them covers it, and the inconsistency is named either way,
    # because the holder who does have a covering pass gets out on it and the
    # operator has to be able to see the corruption. A dangling registration
    # beside an effective one is the same shape at an EXIT (the entry was
    # refused above): the passes that were handed in are evaluated, the one
    # that was not is named. A pass handed in twice is the same shape again:
    # every copy is evaluated, in a fixed order, so the answer does not depend
    # on the order the copies arrived in.
    named = ", ".join(sorted(repr(r.pass_id) for r in effective + dangling))
    if not is_exit:
        return refused(MISSING_ONE_PASS, f"passes {named}.")
    candidates: list[Pass] = []
    for r in sorted(effective, key=lambda r: r.pass_id):
        candidates.extend(duplicated.get(r.pass_id) or [by_id[r.pass_id]])
    answers = [evaluate(p) for p in candidates]
    parts = []
    if len(effective) + len(dangling) > 1:
        parts.append(
            f"{identity!r} is registered on {len(effective) + len(dangling)} passes at once "
            f"({named}), which one car, one pass forbids; every one that was handed in was "
            "evaluated"
            + (
                f"; {', '.join(sorted(repr(r.pass_id) for r in dangling))} was not handed in "
                "and could not be"
                if dangling else ""
            )
        )
    parts.extend(_duplication(pid, duplicated[pid]) for pid in duplicated_named)
    inconsistency = " INCONSISTENT: " + "; ".join(parts) + "."
    for answer in answers:
        if answer.outcome is Outcome.COVERED:
            return replace(answer, detail=answer.detail + inconsistency)
    if duplicated_named and len(effective) == 1 and not dangling:
        # The only inconsistency is the duplication, and no copy covers.
        return not_covered(
            PASS_DUPLICATED,
            f"INCONSISTENT: {_duplication(duplicated_named[0], candidates)}; no copy covers "
            "this exit -- "
            + "; ".join(f"copy {i + 1}: {a.reason}, {a.detail}" for i, a in enumerate(answers))
            + " Answered not-covered, never raised, whatever the order the copies arrived in.",
        )
    first = answers[0]
    return replace(first, detail=first.detail + inconsistency)


def _copy_order(pass_: Pass) -> tuple:
    """A fixed order for the copies of one id, so that which copy is
    evaluated first -- and so the answer -- does not depend on the order the
    caller's list happened to have. The label is the last tie-break only."""
    return (
        pass_.state.value,
        pass_.unreadable is not None,
        pass_.terms.describe() if pass_.terms is not None else "",
        pass_.label,
    )


def _duplication(pass_id: str, copies: Sequence[Pass]) -> str:
    states = ", ".join(
        f"{p.state.value}" + (" (unreadable)" if p.unreadable is not None else "")
        for p in copies
    )
    return (
        f"pass {pass_id!r} was handed in {len(copies)} times (copies: {states}), which one id, "
        "one pass forbids"
    )


def _require_inputs(
    garage: object, passes: object, registrations: object, visits: object,
    vehicle_identity: object, lane: object, direction: object, at: object, garages: object,
) -> None:
    """Every parameter of ``access()`` has the type its signature declares, or a
    ``TypeError`` naming the parameter -- raised on the first touch, before an
    instant, a pass or an answer exists. A wrong-typed value NEVER answers:
    measured before this, ``vehicle_identity=None`` was answered as a blank
    identity, which read a caller's bug as a car with no plate. G4's test
    enumerates the signature and hands each parameter a wrong-typed value."""
    require_aware(at, "at")
    if not isinstance(direction, Direction):
        raise TypeError(f"direction must be a Direction, not {direction!r}")
    if not isinstance(garage, Garage):
        raise TypeError(f"garage must be a Garage, not {garage!r}")
    for name, value, element in (
        ("passes", passes, Pass),
        ("registrations", registrations, Registration),
        ("visits", visits, Visit),
        ("garages", garages, Garage),
    ):
        if isinstance(value, str | bytes) or not isinstance(value, Sequence):
            raise TypeError(f"{name} must be a sequence of {element.__name__}, not {value!r}")
        for item in value:
            if not isinstance(item, element):
                raise TypeError(f"{name} must hold only {element.__name__}, not {item!r}")
    for name, value in (("vehicle_identity", vehicle_identity), ("lane", lane)):
        if not isinstance(value, str):
            raise TypeError(f"{name} must be text, not {value!r}")


def exit_on_unreadable_records(
    unreadable: Sequence[Unreadable], *, vehicle_identity: str, lane: str
) -> Answer:
    """THE EXIT ANSWER WHEN A RECORD HANDED IN CANNOT BE READ. The module holds
    the record -- a registration or visit document, or a pass or garage document
    too malformed to carry its refusal the way a stored row does -- and cannot
    read its content, so the exit is ANSWERED: not-covered, RECORD_UNREADABLE,
    naming every document and field, with the exit note and the OUT-OF-TERMS
    meaning every exit answer carries. Never a refusal, never an exception.
    Exit only: at an entry the same document is refused by name (the command
    line does that; this is not called). Measured before this: six malformed
    documents at an exit were six refusals with no outcome."""
    if not isinstance(vehicle_identity, str) or not isinstance(lane, str):
        raise TypeError("vehicle_identity and lane must be text")
    if not unreadable or not all(isinstance(u, Unreadable) for u in unreadable):
        raise TypeError("unreadable must be one or more Unreadable markers")
    named = "; ".join(u.describe() for u in unreadable)
    return Answer(
        outcome=Outcome.NOT_COVERED,
        direction=Direction.EXIT,
        vehicle_identity=vehicle_identity.strip(),
        lane=lane.strip(),
        pass_id=None,
        pass_label=None,
        covering_term=None,
        reason=RECORD_UNREADABLE,
        missing=None,
        means=MEANS_EXIT_OUT_OF_TERMS,
        detail=(
            f"{len(unreadable)} record(s) handed in with this exit could not be read as what "
            f"they claim to be, so the vehicle cannot be matched to a pass: {named} "
            "Answered not-covered, never refused."
        ),
        exit_note=EXIT_IS_NEVER_REFUSED,
        unmeasured=None,
    )


def _day_name(weekday: int) -> str:
    from garage_pass.terms import DAY_NAMES

    return DAY_NAMES[weekday]


@dataclass(frozen=True)
class NoClock:
    """A recorded entry whose garage's clock the call does not hold: which
    refusal (a key of ``findings.REFUSED_TO_ANSWER``) and the sentence."""

    missing: str
    detail: str


def _visits_used(
    visits: Sequence[Visit], pass_: Pass, window: Window | None, today: date,
    clock_at: Callable[[str], ZoneInfo | tuple[str, str]],
) -> tuple[int, str] | NoClock:
    """How many recorded entries count against the allowance, and the sentence
    that names the denominator -- what was counted, on what, over what, and
    on whose clock. The count is over EVERY garage of the pass (C5); each
    entry's day and minute are read in the zone of the garage it was recorded
    at (``clock_at``), and compared to the asking garage's ``today``. An entry
    whose garage's clock is not here is a ``NoClock``, never counted on the
    wrong clock and never dropped."""
    on_pass = [v for v in visits if v.pass_id == pass_.id]
    assert pass_.terms is not None
    allowance = pass_.terms.visit_allowance
    assert allowance is not None
    if allowance.per is AllowancePeriod.LIFE:
        return len(on_pass), (
            f"counted {len(on_pass)} recorded entr{'y' if len(on_pass) == 1 else 'ies'} on "
            f"pass {pass_.id!r} over its life"
        )
    assert window is not None  # per-window allowance without windows is refused at creation
    in_window: list[Visit] = []
    for v in on_pass:
        clock = clock_at(v.garage_id)
        if not isinstance(clock, ZoneInfo):
            missing, detail = clock
            return NoClock(missing, (
                f"entry of {v.vehicle_identity!r} on pass {pass_.id!r} recorded at garage "
                f"{v.garage_id!r} at {v.entered_at.isoformat()} must be read on that garage's "
                f"clock to count it against the allowance, and {detail}"
            ))
        if (
            day_of(v.entered_at, clock) == today
            and window.start_minute <= minute_of_day(v.entered_at, clock) < window.end_minute
        ):
            in_window.append(v)
    per_garage: dict[str, int] = {}
    for v in in_window:
        per_garage[v.garage_id] = per_garage.get(v.garage_id, 0) + 1
    at_each = ", ".join(f"{gid}: {n}" for gid, n in sorted(per_garage.items())) or "none"
    return len(in_window), (
        f"counted {len(in_window)} recorded entr{'y' if len(in_window) == 1 else 'ies'} on "
        f"pass {pass_.id!r} in window {window.describe()} on {today}, each read in the local "
        f"day of the garage it was recorded at ({at_each})"
    )


def _open_visit(
    visits: Sequence[Visit], garage: Garage, pass_: Pass, identity: str
) -> Visit | None:
    """The latest still-open recorded entry of this vehicle on this pass AT
    THIS GARAGE. The garage is part of the key, deliberately: the visits handed
    in span every garage the pass names (the allowance counts them all), and a
    stay is measured from the entry recorded where the car is leaving. An
    entry open at another garage of the set is not this exit's entry -- the
    stay is then UNMEASURED and named, never measured from the wrong garage."""
    candidates = [
        v for v in visits
        if v.pass_id == pass_.id and v.garage_id == garage.id
        and v.vehicle_identity.strip() == identity and v.is_open
    ]
    return max(candidates, key=lambda v: v.entered_at) if candidates else None
