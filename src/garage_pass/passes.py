"""The pass, its holder, the vehicles registered to it, and the visits recorded on it.

**THERE ARE NOT FIVE PASS TYPES.** "Monthly", "employee", "vendor" and the rest
are labels the owner types. ``label`` is free text and NO BEHAVIOUR KEYS OFF IT
-- a guarantee with a control, not a remark. The only structural difference
between passes is which module is connected to them, and in this round none is.

**A PASS NAMES A SET OF GARAGES, AND ANSWERS ONLY AT THOSE.** His decision,
2026-09-14: one account, many garages under it, and a monthly may be good at
more than one of them. ``garage_ids`` is a non-empty set stated by the owner --
never a nullable "everywhere" flag: a pass valid at every garage of the
account says so by listing them, because an implicit empty set is exactly the
shape this module keeps refusing at creation (``lanes_stated`` proved what the
alternative costs). Empty, or holding a blank member, is refused by name here,
naming ``pass.garage_ids``. The terms stay ON THE PASS -- one set, evaluated at
whichever garage the car is at -- except the lanes, which are stated PER
GARAGE because lane ``A1`` at two garages is two different barriers
(``terms.GarageLanes``); where lanes are stated, every garage the pass names
has at least one, refused here otherwise naming the garage that has none.

The holder is an email address plus an optional name and phone. The email is the
identity; there is no account, no password and no login here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from garage_pass.findings import (
    REFUSAL_HOLDER_EMAIL_MALFORMED,
    REFUSAL_LANES_AT_A_GARAGE_THE_PASS_DOES_NOT_NAME,
    REFUSAL_LANES_NOT_STATED_FOR_GARAGE,
    REFUSAL_PASS_NAMES_NO_GARAGE,
    Refused,
    Unreadable,
)
from garage_pass.garage import require_text
from garage_pass.localday import require_aware
from garage_pass.terms import Terms
from garage_pass.typed import require_typed


class State(Enum):
    """The states somebody TYPES. ``expired`` is not here: it is derived from
    the terms by ``states.effective_state`` and nobody may set it."""

    DRAFT = "draft"
    AWAITING_ENROLMENT = "awaiting_enrolment"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


#: The derived state's name, for answers and the contract. Not a ``State``.
EXPIRED = "expired"


@dataclass(frozen=True)
class Holder:
    email: str
    name: str | None = None
    phone: str | None = None

    def __post_init__(self) -> None:
        email = require_text(self.email, "holder.email")
        local, at, domain = email.partition("@")
        if not (at and local and domain):
            raise Refused(
                REFUSAL_HOLDER_EMAIL_MALFORMED, "holder.email",
                "needs an @ with text before it and text after it.",
            )
        object.__setattr__(self, "email", email)


def require_garage_ids(value: object, field: str = "pass.garage_ids") -> frozenset[str]:
    """A NON-EMPTY set of garage ids, every member non-blank text, or a
    refusal naming the field. A string is never read as a set of its
    characters. ONE validator, used where a pass is built and where the
    store reads the set back."""
    if isinstance(value, str | bytes) or not isinstance(value, frozenset | set | tuple | list):
        raise Refused(
            REFUSAL_PASS_NAMES_NO_GARAGE, field,
            f"{field} must be a list of garage ids, not {value!r}.",
        )
    if not value:
        raise Refused(
            REFUSAL_PASS_NAMES_NO_GARAGE, field,
            f"{field} is {list(value)!r}: a pass names at least one garage, and answers only "
            "there.",
        )
    return frozenset(require_text(member, field) for member in value)


def refuse_lanes_off_the_pass(garage_ids: frozenset[str], terms: Terms) -> None:
    """Lanes are stated PER GARAGE. Stated lanes name only garages the pass
    names (a lane at a garage the pass does not hold could never be used), and
    EVERY garage the pass names has at least one (a garage with no stated
    lane, on a pass whose lanes are stated, would be an implicit empty set --
    no lane at all -- and nothing here is implicit). Refused naming the
    garage; the database's own key backs the first rule for a raw write."""
    if terms.allowed_lanes is None:
        return
    stated = {entry.garage_id for entry in terms.allowed_lanes}
    for garage_id in sorted(stated - garage_ids):
        raise Refused(
            REFUSAL_LANES_AT_A_GARAGE_THE_PASS_DOES_NOT_NAME, "allowed_lanes",
            f"allowed_lanes names garage {garage_id!r}, and the pass names only "
            f"{sorted(garage_ids)}.",
        )
    for garage_id in sorted(garage_ids - stated):
        raise Refused(
            REFUSAL_LANES_NOT_STATED_FOR_GARAGE, "allowed_lanes",
            f"the pass states its lanes, and names garage {garage_id!r} with no lane stated "
            f"there (stated at {sorted(stated)}).",
        )


@dataclass(frozen=True)
class Pass:
    id: str
    #: The garages this pass answers at. Non-empty; stated, never inferred.
    garage_ids: frozenset[str]
    label: str
    #: None only on an unreadable pass whose holder is the unreadable part.
    holder: Holder | None
    #: None only on an unreadable pass whose terms are the unreadable part.
    terms: Terms | None
    state: State = State.DRAFT
    #: Set by the store's LOAD path only: a stored row whose terms or holder
    #: this module refuses to read. Never constructed by a caller building a
    #: pass -- ``Terms`` and ``Holder`` refuse at creation. Terms are re-validated
    #: on every load, so a validator tightened after a pass was stored strands
    #: it; a stranded pass degrades to a STATED answer, never an exception.
    unreadable: Unreadable | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_text(self.id, "pass.id"))
        object.__setattr__(self, "garage_ids", require_garage_ids(self.garage_ids))
        object.__setattr__(self, "label", require_text(self.label, "pass.label"))
        if not isinstance(self.state, State):
            raise TypeError(f"state must be a State, not {self.state!r}")
        if self.unreadable is None:
            if not isinstance(self.holder, Holder):
                raise TypeError(f"holder must be a Holder, not {self.holder!r}")
            if not isinstance(self.terms, Terms):
                raise TypeError(f"terms must be a Terms, not {self.terms!r}")
            refuse_lanes_off_the_pass(self.garage_ids, self.terms)
        elif not isinstance(self.unreadable, Unreadable):
            raise TypeError(f"unreadable must be an Unreadable, not {self.unreadable!r}")


@dataclass(frozen=True)
class Registration:
    """A vehicle identity bound to a pass for a half-open range of local days:
    ``effective_day`` inclusive, ``end_day`` exclusive. The identity is free
    FROM ``end_day``; ``None`` means the registration has no end day of its own
    (the store bounds it by the pass's ``valid_to`` where one is stated).

    A registration carries no garage of its own: in the pure API it is a car
    on a pass, and the pass names the garages it answers at. The store keys
    its rows per garage -- one row per garage of the pass, written together --
    and hands the engine the rows of the garage being asked about."""

    pass_id: str
    vehicle_identity: str
    effective_day: date
    end_day: date | None = None

    def __post_init__(self) -> None:
        # Every field against its declared type, derived from the annotation
        # (``typed.require_typed``). Measured before this: a registration whose
        # identity was None, or whose day was the JSON string, was constructed
        # without complaint and raised at an EXIT lane instead.
        require_typed(self)

    def covers(self, day: date) -> bool:
        return self.effective_day <= day and (self.end_day is None or day < self.end_day)


@dataclass(frozen=True)
class Visit:
    """One recorded entry on a pass AT A GARAGE, and its exit once recorded.

    A visit carries its garage, unlike a registration: the ledger is per
    garage (one open visit per vehicle per pass per garage), a pass names a
    set of garages, and a stay is measured at the garage the car is leaving
    -- from the entry recorded THERE, never from one at another garage of the
    set. Measured before this (the G3a fix round's receipt named it): with no
    garage on the visit, an exit at garage B measured the stay from an entry
    recorded at garage A and answered OVER_MAX_STAY quoting A's instant. The
    allowance is the other question and stays per pass: every garage's
    entries count (C5)."""

    pass_id: str
    garage_id: str
    vehicle_identity: str
    entry_lane: str
    entered_at: datetime
    exited_at: datetime | None = None
    exit_lane: str | None = None

    def __post_init__(self) -> None:
        require_typed(self)
        require_aware(self.entered_at, "entered_at")
        if self.exited_at is not None:
            require_aware(self.exited_at, "exited_at")

    @property
    def is_open(self) -> bool:
        return self.exited_at is None


@dataclass(frozen=True)
class StateChange:
    """Who, when and why. Append-only wherever it is stored."""

    pass_id: str
    from_state: State
    to_state: State
    changed_by: str
    changed_at: datetime
    reason: str
