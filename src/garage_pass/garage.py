"""A garage: its identity, its clock, and whether it sells transient parking.

``transient_available`` is a three-state field on purpose: ``True``, ``False``,
or **unstated** (``None``). There is no default and no inference. A garage that
has not stated it makes the access call REFUSE TO ANSWER at entry, naming the
field -- see ``findings.MISSING_TRANSIENT_MODE`` for why a guessed default is
the one mistake this module may never make.
"""

from __future__ import annotations

from dataclasses import dataclass

from garage_pass.findings import REFUSAL_FIELD_BLANK, Refused
from garage_pass.localday import zone


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_text(self.id, "garage.id"))
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
