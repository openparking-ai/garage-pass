"""A garage: its identity, its clock, whether it sells transient parking, and
where it enrols.

``transient_available`` is a three-state field on purpose: ``True``, ``False``,
or **unstated** (``None``). There is no default and no inference. A garage that
has not stated it makes the access call REFUSE TO ANSWER at entry, naming the
field -- see ``findings.MISSING_TRANSIENT_MODE`` for why a guessed default is
the one mistake this module may never make.

``enrols_at`` -- ``'entry'``, ``'exit'`` or unstated (``None``) -- is where a
QR is redeemed. It has the same three-state shape and no default. R1 makes it
DERIVED for a garage that sells no transient parking: an unregistered vehicle
is not admitted there, so the registration must happen at the entry, and such
a garage need not state the field (``enrolment.where_enrolment_happens``). A
transient garage has a choice and states it. **No transient AND enrols at exit
is a contradiction**, refused here by name and, for a raw write, by the CHECK
on the table.
"""

from __future__ import annotations

from dataclasses import dataclass

from garage_pass.findings import (
    REFUSAL_ENROLS_AT_CONTRADICTS_TRANSIENT,
    REFUSAL_FIELD_BLANK,
    Refused,
    Unreadable,
)
from garage_pass.localday import UnknownTimezone, zone

#: The two ends a garage can enrol at. Read by the contract and the CHECK.
ENROLS_AT_ENTRY = "entry"
ENROLS_AT_EXIT = "exit"
ENROLS_AT = (ENROLS_AT_ENTRY, ENROLS_AT_EXIT)


def require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Refused(REFUSAL_FIELD_BLANK, field, f"{field} must be non-blank text, not {value!r}.")
    return value.strip()


def require_enrols_at(value: object) -> str | None:
    """``'entry'``, ``'exit'`` or ``None`` (unstated), or a refusal naming the
    field. The same discipline as ``transient_available``: absent is UNSTATED,
    never a default."""
    if value is None or value in ENROLS_AT:
        return value
    raise Refused(
        REFUSAL_FIELD_BLANK, "garage.enrols_at",
        f"enrols_at is 'entry', 'exit' or unstated, not {value!r}.",
    )


def refuse_enrols_at_contradiction(transient_available: bool | None, enrols_at: str | None) -> None:
    """R1: a garage with no transient parking cannot enrol at its exit. ONE
    check, called where a garage is built and where the field is repaired."""
    if transient_available is False and enrols_at == ENROLS_AT_EXIT:
        raise Refused(
            REFUSAL_ENROLS_AT_CONTRADICTS_TRANSIENT, "garage.enrols_at",
            "transient_available is false and enrols_at is 'exit': with no transient an "
            "unregistered vehicle is not admitted, so enrolment can only happen at entry.",
        )


@dataclass(frozen=True)
class Garage:
    id: str
    timezone: str
    #: True, False, or None for "not stated". None is not a default of False:
    #: absent is UNSTATED, and an unstated garage refuses every entry an answer.
    transient_available: bool | None = None
    #: 'entry', 'exit', or None for "not stated". Derived as 'entry' for a
    #: garage with no transient (R1); a transient garage states it or a
    #: redemption refuses to answer, naming the field.
    enrols_at: str | None = None
    #: Set by the store's LOAD path only, for a stored row this module refuses
    #: to read (a timezone the system does not carry). A garage is never
    #: WRITTEN unreadable -- ``zone`` refuses the value where it is written --
    #: but a row can go stale under a system whose tzdata lost the name, and an
    #: access call about it must still answer.
    unreadable: Unreadable | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_text(self.id, "garage.id"))
        if self.unreadable is None:
            zone(self.timezone)  # refuses an unknown zone by name
        if self.transient_available is not None and not isinstance(
            self.transient_available, bool
        ):
            raise Refused(
                REFUSAL_FIELD_BLANK,
                "garage.transient_available",
                f"transient_available is true, false or unstated, not "
                f"{self.transient_available!r}.",
            )
        require_enrols_at(self.enrols_at)
        refuse_enrols_at_contradiction(self.transient_available, self.enrols_at)


def garage_from_stored(
    id: str, timezone: str, transient_available: bool | None, enrols_at: str | None = None
) -> Garage:
    """The store's constructor: a row whose timezone the system does not carry
    becomes an UNREADABLE garage rather than an exception, so the access call
    answers -- refused-to-answer at entry, not-covered at exit, naming the field."""
    try:
        return Garage(id=id, timezone=timezone, transient_available=transient_available,
                      enrols_at=enrols_at)
    except UnknownTimezone as exc:
        return Garage(
            id=id, timezone=timezone, transient_available=transient_available,
            enrols_at=enrols_at, unreadable=exc.as_unreadable(),
        )
