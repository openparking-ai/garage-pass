"""The terms of a pass, and the validator that refuses a contradiction at creation.

Six things, and every one of them is stated or absent -- there is no default
anywhere in this file:

1. **valid_from / valid_to** -- inclusive calendar days in the garage's local day.
2. **windows** -- recurring: days of the week plus minutes of the local day.
3. **max_stay** -- a duration, measured at exit from the recorded entry. It
   may be longer than any window: windows bind instants, not stays.
4. **visit_allowance** -- a count, over the pass's life or per window.
5. **directions** -- entry, exit, or both. Stated, because nothing is implicit.
6. **allowed_lanes** -- a named set; absent means every lane of the garage.

**THE VALIDATOR REFUSES CONTRADICTIONS AT CREATION, NAMING THE FIELD.** The gate
is never where a contradiction is discovered: a ``Terms`` value that fails
``check_terms`` cannot be constructed, so the access call never meets one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

from garage_pass.findings import (
    REFUSAL_ALLOWANCE_PER_WINDOW_WITHOUT_WINDOWS,
    REFUSAL_LANE_NAME_BLANK,
    REFUSAL_LANES_STATED_BUT_EMPTY,
    REFUSAL_MAX_STAY_NOT_POSITIVE,
    REFUSAL_NO_DIRECTIONS,
    REFUSAL_VALID_TO_BEFORE_VALID_FROM,
    REFUSAL_VISIT_ALLOWANCE_NOT_POSITIVE,
    REFUSAL_WINDOW_DAY_UNKNOWN,
    REFUSAL_WINDOW_ENDS_BEFORE_IT_STARTS,
    REFUSAL_WINDOW_HAS_NO_DAYS,
    REFUSAL_WINDOW_MINUTE_OUT_OF_RANGE,
    REFUSAL_WINDOW_NEVER_OCCURS,
    Refused,
)

#: The end of a local day, in minutes from its midnight. A window ending here
#: runs to the last minute of the day.
END_OF_DAY = 1440

DAY_NAMES = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}


class Direction(Enum):
    ENTRY = "entry"
    EXIT = "exit"


class AllowancePeriod(Enum):
    LIFE = "life"
    WINDOW = "window"


@dataclass(frozen=True)
class Window:
    """Days of the week (ISO: 1 = Monday .. 7 = Sunday) and minutes of the local day.

    ``[start_minute, end_minute)`` -- half-open, so 0..1440 is the whole day and
    two windows 0..360 and 360..1440 do not overlap on the minute they share.
    """

    days: frozenset[int]
    start_minute: int
    end_minute: int

    def describe(self) -> str:
        days = ",".join(DAY_NAMES[d] for d in sorted(self.days))
        return f"{days} {_hhmm(self.start_minute)}-{_hhmm(self.end_minute)}"

    @property
    def length(self) -> timedelta:
        return timedelta(minutes=self.end_minute - self.start_minute)


@dataclass(frozen=True)
class VisitAllowance:
    count: int
    per: AllowancePeriod


@dataclass(frozen=True)
class Terms:
    valid_from: date | None = None
    valid_to: date | None = None
    windows: tuple[Window, ...] = ()
    max_stay: timedelta | None = None
    visit_allowance: VisitAllowance | None = None
    directions: frozenset[Direction] = field(default_factory=frozenset)
    #: None means every lane of the garage. An empty set is refused.
    allowed_lanes: frozenset[str] | None = None

    def __post_init__(self) -> None:
        check_terms(self)

    def describe(self) -> str:
        """The terms in one line, for an answer and for the command line."""
        parts = []
        if self.valid_from or self.valid_to:
            parts.append(f"valid {self.valid_from or '...'}..{self.valid_to or '...'}")
        if self.windows:
            parts.append("windows " + "; ".join(w.describe() for w in self.windows))
        if self.max_stay is not None:
            parts.append(f"max stay {self.max_stay}")
        if self.visit_allowance is not None:
            parts.append(
                f"{self.visit_allowance.count} visit(s) per {self.visit_allowance.per.value}"
            )
        parts.append("directions " + "+".join(sorted(d.value for d in self.directions)))
        if self.allowed_lanes is not None:
            parts.append("lanes " + ",".join(sorted(self.allowed_lanes)))
        return "; ".join(parts)


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def days_that_occur(valid_from: date, valid_to: date) -> frozenset[int]:
    """Which ISO weekdays fall inside an inclusive day range. Seven days or more
    is every weekday; fewer is walked."""
    if (valid_to - valid_from).days >= 6:
        return frozenset(range(1, 8))
    out = set()
    day = valid_from
    while day <= valid_to:
        out.add(day.isoweekday())
        day += timedelta(days=1)
    return frozenset(out)


def check_terms(terms: Terms) -> None:
    """Refuse a contradiction, naming the field. Called by ``Terms`` itself, so
    a contradictory ``Terms`` value cannot exist."""
    if terms.valid_from is not None and terms.valid_to is not None:
        if terms.valid_to < terms.valid_from:
            raise Refused(
                REFUSAL_VALID_TO_BEFORE_VALID_FROM,
                "valid_to",
                f"valid_to {terms.valid_to} is before valid_from {terms.valid_from}.",
            )

    for index, window in enumerate(terms.windows):
        where = f"windows[{index}]"
        if not window.days:
            raise Refused(REFUSAL_WINDOW_HAS_NO_DAYS, f"{where}.days", f"{where} names no day.")
        unknown = sorted(d for d in window.days if not isinstance(d, int) or not 1 <= d <= 7)
        if unknown:
            raise Refused(
                REFUSAL_WINDOW_DAY_UNKNOWN, f"{where}.days", f"{where} names day(s) {unknown}."
            )
        for edge in ("start_minute", "end_minute"):
            value = getattr(window, edge)
            if not isinstance(value, int) or not 0 <= value <= END_OF_DAY:
                raise Refused(
                    REFUSAL_WINDOW_MINUTE_OUT_OF_RANGE,
                    f"{where}.{edge}",
                    f"{where}.{edge} is {value!r}; 0..{END_OF_DAY} from local midnight.",
                )
        if window.end_minute <= window.start_minute:
            raise Refused(
                REFUSAL_WINDOW_ENDS_BEFORE_IT_STARTS,
                f"{where}.end_minute",
                f"{where} runs {_hhmm(window.start_minute)}-{_hhmm(window.end_minute)}, "
                "which is empty.",
            )
        if terms.valid_from is not None and terms.valid_to is not None:
            occurring = days_that_occur(terms.valid_from, terms.valid_to)
            if not window.days & occurring:
                raise Refused(
                    REFUSAL_WINDOW_NEVER_OCCURS,
                    f"{where}.days",
                    f"{where} names {window.describe()!s} but "
                    f"{terms.valid_from}..{terms.valid_to} contains only "
                    f"{','.join(DAY_NAMES[d] for d in sorted(occurring))}.",
                )

    if terms.max_stay is not None:
        if terms.max_stay <= timedelta(0):
            raise Refused(
                REFUSAL_MAX_STAY_NOT_POSITIVE, "max_stay", f"max_stay is {terms.max_stay}."
            )
        # A maximum LONGER than a window is not a contradiction. Windows bind
        # the two instants -- the entry and the exit -- never the stay between
        # them: a stay may leave the window it began in (answered out-of-terms
        # at exit, never refused) or end inside a later occurrence (covered). So
        # a 6-hour maximum beside two 4-hour windows is reachable and binding,
        # measured: exit at 14:59 covered, 15:01 over the maximum. The first
        # cut refused it, and refused a legitimate pass; the L3 settled it by
        # execution and a test now creates exactly that pass.

    if terms.visit_allowance is not None:
        if terms.visit_allowance.count <= 0:
            raise Refused(
                REFUSAL_VISIT_ALLOWANCE_NOT_POSITIVE,
                "visit_allowance.count",
                f"visit_allowance.count is {terms.visit_allowance.count}.",
            )
        if terms.visit_allowance.per is AllowancePeriod.WINDOW and not terms.windows:
            raise Refused(
                REFUSAL_ALLOWANCE_PER_WINDOW_WITHOUT_WINDOWS,
                "visit_allowance.per",
                "visit_allowance is per window and the pass has no windows.",
            )

    if not terms.directions:
        raise Refused(REFUSAL_NO_DIRECTIONS, "directions", "directions is empty.")

    if terms.allowed_lanes is not None:
        if not terms.allowed_lanes:
            raise Refused(
                REFUSAL_LANES_STATED_BUT_EMPTY, "allowed_lanes", "allowed_lanes is an empty set."
            )
        for lane in terms.allowed_lanes:
            if not isinstance(lane, str) or not lane.strip():
                raise Refused(REFUSAL_LANE_NAME_BLANK, "allowed_lanes", f"a lane is {lane!r}.")
