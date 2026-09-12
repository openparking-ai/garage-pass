"""The pass, its holder, the vehicles registered to it, and the visits recorded on it.

**THERE ARE NOT FIVE PASS TYPES.** "Monthly", "employee", "vendor" and the rest
are labels the owner types. ``label`` is free text and NO BEHAVIOUR KEYS OFF IT
-- a guarantee with a control, not a remark. The only structural difference
between passes is which module is connected to them, and in this round none is.

The holder is an email address plus an optional name and phone. The email is the
identity; there is no account, no password and no login here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from garage_pass.findings import REFUSAL_HOLDER_EMAIL_MALFORMED, Refused, Unreadable
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
                REFUSAL_HOLDER_EMAIL_MALFORMED, "holder.email", "needs one @ with text both sides."
            )
        object.__setattr__(self, "email", email)


@dataclass(frozen=True)
class Pass:
    id: str
    garage_id: str
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
        object.__setattr__(self, "garage_id", require_text(self.garage_id, "pass.garage_id"))
        object.__setattr__(self, "label", require_text(self.label, "pass.label"))
        if not isinstance(self.state, State):
            raise TypeError(f"state must be a State, not {self.state!r}")
        if self.unreadable is None:
            if not isinstance(self.holder, Holder):
                raise TypeError(f"holder must be a Holder, not {self.holder!r}")
            if not isinstance(self.terms, Terms):
                raise TypeError(f"terms must be a Terms, not {self.terms!r}")
        elif not isinstance(self.unreadable, Unreadable):
            raise TypeError(f"unreadable must be an Unreadable, not {self.unreadable!r}")


@dataclass(frozen=True)
class Registration:
    """A vehicle identity bound to a pass for a half-open range of local days:
    ``effective_day`` inclusive, ``end_day`` exclusive. The identity is free
    FROM ``end_day``; ``None`` means the registration has no end day of its own
    (the store bounds it by the pass's ``valid_to`` where one is stated)."""

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
    """One recorded entry on a pass, and its exit once recorded."""

    pass_id: str
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
