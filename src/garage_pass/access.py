"""The access answer. The whole point of the module.

Given a garage, a vehicle identity, a lane, a direction and an instant -- and
the passes, registrations and recorded visits the caller holds -- one of:

* **covered** -- with the pass, its label and the term that covers it;
* **not covered** -- with a plain reason from ``findings.NOT_COVERED_REASONS``;
* **refused to answer** -- the call cannot answer without guessing, and names
  the field that would let it (``findings.REFUSED_TO_ANSWER``).

**NO FEE, NO AMOUNT, NO BALANCE, EVER CROSSES THIS CALL.** It is an access fact.
There is no field on ``Answer`` that could carry money, and a control plants
one and requires red.

**THIS MODULE NEVER OPENS OR CLOSES A GATE**, never counts who is inside and
never holds session state. It answers; the lane acts. What it does hold is a
LEDGER of the visits the lane told it about -- ``record_entry`` and
``record_exit`` in the store -- because a visit allowance and a maximum stay
are computed from the module's own recorded visits and from nothing else. A
ledger is not a count of who is inside: nothing here answers that question.

**AN EXIT IS NEVER REFUSED.** A pass's terms govern entry and which lanes may
be used. At exit the same terms are EVALUATED -- an exit outside them is
answered not-covered, reason named, so that a transient garage can charge the
stay -- but the answer's meaning at the barrier is always
``findings.MEANS_EXIT_OUT_OF_TERMS`` and every exit answer, whatever its
outcome, carries ``findings.EXIT_IS_NEVER_REFUSED``. A garage whose transient
mode is unstated is refused an answer at ENTRY only; the exit half of the call
does not read that field at all, because nothing about an exit may depend on
configuration.

**THE ORDER OF THE CHECKS IS PART OF THE CONTRACT.** Revoked outranks
everything (revoked is revoked). Then expiry, which is derived. Then the typed
state. Then the terms: direction, lane, window, and -- at entry -- the visit
allowance; at exit, the maximum stay. The first thing that fails is the
reason; nothing after it is evaluated or reported.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from garage_pass.findings import (
    DIRECTION_NOT_ALLOWED,
    EXIT_IS_NEVER_REFUSED,
    EXPIRED,
    MEANS_COVERED,
    MEANS_EXIT_OUT_OF_TERMS,
    MEANS_NOTHING_TO_ADMIT_AS,
    MEANS_TRANSIENT_STAY,
    MISSING_LANE,
    MISSING_ONE_PASS,
    MISSING_RECORDED_ENTRY,
    MISSING_TRANSIENT_MODE,
    MISSING_VEHICLE_IDENTITY,
    NO_PASS,
    NOT_ACTIVE,
    NOT_STARTED,
    OUT_OF_VISITS,
    OUTSIDE_WINDOW,
    OVER_MAX_STAY,
    REFUSAL_PASS_NOT_FOUND,
    REFUSED_TO_ANSWER,
    REVOKED,
    SUSPENDED,
    WRONG_LANE,
    Refused,
)
from garage_pass.garage import Garage
from garage_pass.localday import (
    day_of,
    elapsed,
    iso_weekday_of,
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
    #: For a refused answer: a key of ``findings.REFUSED_TO_ANSWER``.
    missing: str | None
    #: A key of ``findings.BARRIER_MEANINGS``, or None when nothing was answered.
    means: str | None
    detail: str
    #: ``findings.EXIT_IS_NEVER_REFUSED`` on every exit answer; None on entry.
    exit_note: str | None


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
) -> Answer:
    require_aware(at, "at")
    if not isinstance(direction, Direction):
        raise TypeError(f"direction must be a Direction, not {direction!r}")
    tz = zone(garage.timezone)
    today = day_of(at, tz)
    identity = vehicle_identity.strip() if isinstance(vehicle_identity, str) else ""
    lane_name = lane.strip() if isinstance(lane, str) else ""
    exit_note = EXIT_IS_NEVER_REFUSED if direction is Direction.EXIT else None

    def refused(missing: str, detail: str, pass_: Pass | None = None) -> Answer:
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
        )

    def not_covered(reason: str, detail: str, pass_: Pass | None = None) -> Answer:
        if direction is Direction.EXIT:
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
        )

    def covered(pass_: Pass, term: str) -> Answer:
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
        )

    # --- what cannot be answered at all -----------------------------------
    if not identity:
        return refused(MISSING_VEHICLE_IDENTITY, f"got {vehicle_identity!r}.")
    if not lane_name:
        return refused(MISSING_LANE, f"got {lane!r}.")
    # The transient mode decides what an uncovered ENTRY means. It is read
    # here, before anything else, so that a garage that has not stated it is
    # discovered at the first car and not at the first uncovered one. An EXIT
    # never reads it: see the module docstring.
    if direction is Direction.ENTRY and garage.transient_available is None:
        return refused(MISSING_TRANSIENT_MODE, f"garage {garage.id!r}.")

    # --- which pass, if any -------------------------------------------------
    by_id = {p.id: p for p in passes if p.garage_id == garage.id}
    here = []
    for registration in registrations:
        if registration.vehicle_identity.strip() != identity:
            continue
        if registration.pass_id not in by_id:
            if any(p.id == registration.pass_id for p in passes):
                continue  # a pass at another garage; not this garage's business
            raise Refused(
                REFUSAL_PASS_NOT_FOUND,
                "registration.pass_id",
                f"registration names pass {registration.pass_id!r}, which was not handed in.",
            )
        here.append(registration)
    effective = [r for r in here if r.covers(today)]
    if len(effective) > 1:
        return refused(
            MISSING_ONE_PASS,
            "passes " + ", ".join(sorted(repr(r.pass_id) for r in effective)) + ".",
        )
    if not effective:
        # A stated answer for an unknown identity -- never an accidental
        # refusal and never a silent pass. Where a registration exists but is
        # not in force today, the detail says which and when; a revoked pass
        # is named as revoked, because that is the reason and not "no pass".
        revoked = [r for r in here if by_id[r.pass_id].state is State.REVOKED]
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

    registration = effective[0]
    pass_ = by_id[registration.pass_id]
    terms = pass_.terms

    # --- the state, in the order that is the contract ------------------------
    state = effective_state(pass_, today)
    if state == State.REVOKED.value:
        return not_covered(REVOKED, f"pass {pass_.id!r} is revoked.", pass_)
    if state == EXPIRED_STATE:
        return not_covered(
            EXPIRED, f"pass {pass_.id!r} valid_to {terms.valid_to} is before {today}.", pass_
        )
    if state == State.SUSPENDED.value:
        return not_covered(SUSPENDED, f"pass {pass_.id!r} is suspended.", pass_)
    if state in (State.DRAFT.value, State.AWAITING_ENROLMENT.value):
        return not_covered(NOT_ACTIVE, f"pass {pass_.id!r} is {state}.", pass_)
    if terms.valid_from is not None and today < terms.valid_from:
        return not_covered(
            NOT_STARTED, f"pass {pass_.id!r} valid_from {terms.valid_from} is after {today}.",
            pass_,
        )

    # --- the terms --------------------------------------------------------------
    if direction not in terms.directions:
        return not_covered(
            DIRECTION_NOT_ALLOWED,
            f"pass {pass_.id!r} states {sorted(d.value for d in terms.directions)}, "
            f"not {direction.value!r}.",
            pass_,
        )
    if terms.allowed_lanes is not None and lane_name not in terms.allowed_lanes:
        return not_covered(
            WRONG_LANE,
            f"pass {pass_.id!r} allows lanes {sorted(terms.allowed_lanes)}, not {lane_name!r}.",
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

    if direction is Direction.ENTRY and terms.visit_allowance is not None:
        used, denominator = _visits_used(visits, pass_, window, at, tz)
        allowed = terms.visit_allowance.count
        if used >= allowed:
            return not_covered(
                OUT_OF_VISITS, f"{used} of {allowed} visit(s) used; {denominator}.", pass_
            )
        covering.append(f"visit {used + 1} of {allowed}; {denominator}")

    if direction is Direction.EXIT and terms.max_stay is not None:
        open_visit = _open_visit(visits, pass_, identity)
        if open_visit is None or at < open_visit.entered_at:
            return refused(
                MISSING_RECORDED_ENTRY,
                f"pass {pass_.id!r}, vehicle {identity!r}, at {at.isoformat()}"
                + (
                    f"; the open entry is at {open_visit.entered_at.isoformat()}, later."
                    if open_visit else "."
                ),
                pass_,
            )
        stayed = elapsed(open_visit.entered_at, at)
        if stayed > terms.max_stay:
            return not_covered(
                OVER_MAX_STAY,
                f"entered {open_visit.entered_at.isoformat()}, exiting {at.isoformat()}: "
                f"{stayed} elapsed, more than {terms.max_stay}.",
                pass_,
            )
        covering.append(f"stayed {stayed} of at most {terms.max_stay}")

    return covered(pass_, "; ".join(covering))


def _day_name(weekday: int) -> str:
    from garage_pass.terms import DAY_NAMES

    return DAY_NAMES[weekday]


def _visits_used(
    visits: Sequence[Visit], pass_: Pass, window: Window | None, at: datetime, tz
) -> tuple[int, str]:
    """How many recorded entries count against the allowance, and the sentence
    that names the denominator -- what was counted, on what, over what."""
    on_pass = [v for v in visits if v.pass_id == pass_.id]
    allowance = pass_.terms.visit_allowance
    assert allowance is not None
    if allowance.per is AllowancePeriod.LIFE:
        return len(on_pass), (
            f"counted {len(on_pass)} recorded entr{'y' if len(on_pass) == 1 else 'ies'} on "
            f"pass {pass_.id!r} over its life"
        )
    assert window is not None  # per-window allowance without windows is refused at creation
    today = day_of(at, tz)
    in_window = [
        v for v in on_pass
        if day_of(v.entered_at, tz) == today
        and window.start_minute <= minute_of_day(v.entered_at, tz) < window.end_minute
    ]
    return len(in_window), (
        f"counted {len(in_window)} recorded entr{'y' if len(in_window) == 1 else 'ies'} on "
        f"pass {pass_.id!r} in window {window.describe()} on {today}"
    )


def _open_visit(visits: Sequence[Visit], pass_: Pass, identity: str) -> Visit | None:
    """The latest still-open recorded entry of this vehicle on this pass."""
    candidates = [
        v for v in visits
        if v.pass_id == pass_.id and v.vehicle_identity.strip() == identity and v.is_open
    ]
    return max(candidates, key=lambda v: v.entered_at) if candidates else None
