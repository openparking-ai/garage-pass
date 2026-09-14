"""The terms of a pass, and the validator that refuses a contradiction at creation.

Six things, and every one of them is stated or absent -- there is no default
anywhere in this file:

1. **valid_from / valid_to** -- inclusive calendar days in the garage's local day.
2. **windows** -- recurring: days of the week plus minutes of the local day.
3. **max_stay** -- a duration, measured at exit from the recorded entry. It
   may be longer than any window: windows bind instants, not stays.
4. **visit_allowance** -- a count, over the pass's life or per window.
5. **directions** -- entry, exit, or both. Stated, because nothing is implicit.
6. **allowed_lanes** -- a named set, stated PER GARAGE: a lane name is a
   barrier at a garage, and ``A1`` at two garages is two barriers. Absent means
   every lane at every garage the pass names; stated, every garage the pass
   names has its own set (``Pass`` refuses one that has none), and the access
   call reads the set of the garage the car is at and no other.

**THE TERMS ARE ONE SET, ON THE PASS, EVALUATED AT WHICHEVER GARAGE THE CAR IS
AT.** A pass may name several garages; a 20-visit allowance is 20 on the pass,
not 20 per garage, and a Mon-Fri window is Mon-Fri everywhere. Only the lanes
are per garage, because only a lane means a different thing at each.

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
    REFUSAL_FIELD_BLANK,
    REFUSAL_LANE_NAME_BLANK,
    REFUSAL_LANES_GARAGE_REPEATED,
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
class GarageLanes:
    """The lanes a pass may use at ONE garage. A lane name is a barrier at a
    garage -- ``A1`` at two garages is two different barriers -- so a stated
    lane set is stated per garage, and the access call reads the set of the
    garage the car is at and no other."""

    garage_id: str
    lanes: frozenset[str]

    def describe(self) -> str:
        return f"{self.garage_id}:{','.join(sorted(self.lanes))}"


@dataclass(frozen=True)
class Terms:
    valid_from: date | None = None
    valid_to: date | None = None
    windows: tuple[Window, ...] = ()
    max_stay: timedelta | None = None
    visit_allowance: VisitAllowance | None = None
    directions: frozenset[Direction] = field(default_factory=frozenset)
    #: None means every lane at every garage the pass names. Stated, it is one
    #: entry per garage; an empty tuple, an entry with no lane, a blank lane
    #: or a garage named twice is refused. Whether every garage the pass names
    #: has an entry is the pass's to check (``passes.refuse_lanes_off_the_pass``):
    #: the terms alone do not know the pass's garages.
    allowed_lanes: tuple[GarageLanes, ...] | None = None

    def __post_init__(self) -> None:
        check_terms(self)

    def lanes_at(self, garage_id: str) -> frozenset[str] | None:
        """The stated lanes at one garage: ``None`` when lanes are not stated
        at all (every lane); the garage's own set when they are -- and the
        EMPTY set for a garage with no entry, which is no lane at all, never
        every lane. A pass whose lanes are stated names no garage without an
        entry (refused where the pass is built), so the empty set is reached
        only by asking about a garage the pass does not name."""
        if self.allowed_lanes is None:
            return None
        for entry in self.allowed_lanes:
            if entry.garage_id == garage_id:
                return entry.lanes
        return frozenset()

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
            parts.append("lanes " + "; ".join(
                entry.describe() for entry in sorted(self.allowed_lanes, key=lambda e: e.garage_id)
            ))
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
        seen: set[str] = set()
        for index, entry in enumerate(terms.allowed_lanes):
            where = f"allowed_lanes[{index}]"
            if not isinstance(entry, GarageLanes):
                raise TypeError(f"{where} must be a GarageLanes, not {entry!r}")
            if not isinstance(entry.garage_id, str) or not entry.garage_id.strip():
                raise Refused(
                    REFUSAL_FIELD_BLANK, f"{where}.garage_id",
                    f"{where}.garage_id must be non-blank text, not {entry.garage_id!r}.",
                )
            if entry.garage_id in seen:
                raise Refused(
                    REFUSAL_LANES_GARAGE_REPEATED, f"{where}.garage_id",
                    f"{where} names garage {entry.garage_id!r} again.",
                )
            seen.add(entry.garage_id)
            if not entry.lanes:
                raise Refused(
                    REFUSAL_LANES_STATED_BUT_EMPTY, f"{where}.lanes",
                    f"{where} states no lane at garage {entry.garage_id!r}.",
                )
            for lane in entry.lanes:
                if not isinstance(lane, str) or not lane.strip():
                    raise Refused(
                        REFUSAL_LANE_NAME_BLANK, f"{where}.lanes",
                        f"a lane at garage {entry.garage_id!r} is {lane!r}.",
                    )
