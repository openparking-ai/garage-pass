"""State transitions, and the one state nobody types.

    draft ──► awaiting_enrolment ──► active ◄──► suspended
      │              │                 │             │
      └──────────────┴────────► revoked ◄────────────┘   (terminal)

``expired`` is DERIVED: a pass whose ``valid_to`` is before today reads as
expired whatever its typed state, unless it is revoked -- revocation is
terminal and outranks everything.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from garage_pass.findings import (
    REFUSAL_EXPIRED_IS_DERIVED,
    REFUSAL_REVOKED_IS_TERMINAL,
    REFUSAL_STATE_CHANGE_NEEDS_WHO_AND_WHY,
    REFUSAL_STATE_TRANSITION_NOT_ALLOWED,
    REFUSAL_STATE_UNKNOWN,
    Refused,
)
from garage_pass.localday import require_aware
from garage_pass.passes import EXPIRED, Pass, State, StateChange

#: From each typed state, the typed states it may move to. Read by the contract.
ALLOWED_TRANSITIONS: dict[State, frozenset[State]] = {
    State.DRAFT: frozenset({State.AWAITING_ENROLMENT, State.ACTIVE, State.REVOKED}),
    State.AWAITING_ENROLMENT: frozenset({State.ACTIVE, State.REVOKED}),
    State.ACTIVE: frozenset({State.SUSPENDED, State.REVOKED}),
    State.SUSPENDED: frozenset({State.ACTIVE, State.REVOKED}),
    State.REVOKED: frozenset(),
}


def parse_state(name: object) -> State:
    """A typed state by name. ``expired`` is refused by its own code, because
    somebody typing it is the mistake the derivation exists to prevent."""
    if name == EXPIRED:
        raise Refused(REFUSAL_EXPIRED_IS_DERIVED, "state", "'expired' was typed.")
    try:
        return State(name)
    except ValueError:
        raise Refused(
            REFUSAL_STATE_UNKNOWN,
            "state",
            f"{name!r}; the typed states are {[s.value for s in State]}.",
        ) from None


def effective_state(pass_: Pass, today: date) -> str:
    """The state the access call reads: the typed one, or ``expired``.

    Revoked outranks expiry -- a revoked pass is revoked, not "expired", and
    the reason a lane is given says so. An UNREADABLE pass (store load path)
    has no terms to derive expiry from; the access call answers it before
    expiry is asked, so this returns its typed state.
    """
    if pass_.state is State.REVOKED:
        return State.REVOKED.value
    terms = pass_.terms
    if terms is not None and terms.valid_to is not None and today > terms.valid_to:
        return EXPIRED
    return pass_.state.value


def transition(
    pass_: Pass, to: State, *, by: str, at: datetime, reason: str
) -> tuple[Pass, StateChange]:
    """Move a pass to a typed state, or refuse by name. Returns the new pass
    value and the record of who, when and why."""
    require_aware(at, "changed_at")
    if not isinstance(to, State):
        raise Refused(REFUSAL_STATE_UNKNOWN, "state", f"{to!r} is not a State.")
    if not (isinstance(by, str) and by.strip()) or not (isinstance(reason, str) and reason.strip()):
        raise Refused(
            REFUSAL_STATE_CHANGE_NEEDS_WHO_AND_WHY,
            "changed_by" if not (isinstance(by, str) and by.strip()) else "reason",
            f"changed_by={by!r} reason={reason!r}.",
        )
    if pass_.state is State.REVOKED:
        raise Refused(
            REFUSAL_REVOKED_IS_TERMINAL,
            "state",
            f"pass {pass_.id!r} is revoked and was asked to become {to.value!r}.",
        )
    if to not in ALLOWED_TRANSITIONS[pass_.state]:
        raise Refused(
            REFUSAL_STATE_TRANSITION_NOT_ALLOWED,
            "state",
            f"pass {pass_.id!r} is {pass_.state.value!r}; {to.value!r} is not among "
            f"{sorted(s.value for s in ALLOWED_TRANSITIONS[pass_.state])}.",
        )
    change = StateChange(
        pass_id=pass_.id,
        from_state=pass_.state,
        to_state=to,
        changed_by=by.strip(),
        changed_at=at,
        reason=reason.strip(),
    )
    return replace(pass_, state=to), change
