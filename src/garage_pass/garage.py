"""A garage: its identity, its clock, and whether it sells transient parking.

``transient_available`` is a three-state field on purpose: ``True``, ``False``,
or **unstated** (``None``). There is no default and no inference. A garage that
has not stated it makes the access call REFUSE TO ANSWER at entry, naming the
field -- see ``findings.MISSING_TRANSIENT_MODE`` for why a guessed default is
the one mistake this module may never make.
"""

from __future__ import annotations

from dataclasses import dataclass

from garage_pass.findings import REFUSAL_FIELD_BLANK, Refused, Unreadable
from garage_pass.localday import UnknownTimezone, zone


def require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Refused(REFUSAL_FIELD_BLANK, field, f"{field} must be non-blank text, not {value!r}.")
    return value.strip()


@dataclass(frozen=True)
class Garage:
    id: str
    timezone: str
    #: True, False, or None for "not stated". None is not a default of False.
    transient_available: bool | None
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


def garage_from_stored(
    id: str, timezone: str, transient_available: bool | None
) -> Garage:
    """The store's constructor: a row whose timezone the system does not carry
    becomes an UNREADABLE garage rather than an exception, so the access call
    answers -- refused-to-answer at entry, not-covered at exit, naming the field."""
    try:
        return Garage(id=id, timezone=timezone, transient_available=transient_available)
    except UnknownTimezone as exc:
        return Garage(
            id=id, timezone=timezone, transient_available=transient_available,
            unreadable=Unreadable("UnknownTimezone", "garage.timezone", str(exc)),
        )
