"""A calendar day is the garage's local day, and elapsed time is measured in UTC.

Every term on a pass is written in the garage's own clock: a window of
06:00-20:00 means the wall clock on the garage's door, a valid-from day means
the day that begins at the garage's local midnight, and "Monday" is Monday
where the garage stands. A garage in Denver and a garage in Phoenix read the
same instant as different times of day on two days a year, and as different
DAYS for an hour every night.

**WHY THIS FILE EXISTS SEPARATELY, AND WHAT THE DST GUARANTEE MEASURES.**

Two quantities here move on the night the clocks change, and a naive
implementation gets each of them wrong in a way that stays green in every test
written near noon:

* **Which local day and which local minute an instant falls in.** An instant
  converted to UTC and read as a wall clock is off by the garage's offset,
  which crosses a day boundary every night and crosses a window boundary at
  its edges. The guarantee is measured at those edges, on the two transition
  days, where local and UTC readings disagree.

* **How long a stay lasted.** Python subtracts two aware datetimes IN THE SAME
  ZONE by their wall clocks, ignoring ``fold`` (PEP 495 says so in as many
  words). A stay from 00:30 to 03:30 local on the fall-back night lasted FOUR
  hours and wall-clock arithmetic says three. So elapsed time is computed from
  the two instants' UTC readings, never from their local ones, and a control
  plants the wall-clock subtraction back and requires the assertion red.

**A local midnight can be SKIPPED or DOUBLED.** `zoneinfo` resolves both without
raising -- a skipped local time resolves forward, an ambiguous one to the FIRST
occurrence by default -- and never tells the caller that anything happened.
``day_start`` states its resolution with ``fold=0`` rather than depending on a
default that reads as an accident.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from garage_pass.findings import REFUSAL_TIMEZONE_UNKNOWN, Refused


class UnknownTimezone(Refused, ValueError):
    """A garage named a timezone the running system does not carry.

    A ``Refused`` -- registered as ``REFUSAL_TIMEZONE_UNKNOWN``, field
    ``garage.timezone`` -- so the command line renders it as the JSON refusal
    with the documented exit status. Measured before this: it was a bare
    ``ValueError``, the command line's handler did not see it, and an operator
    creating a garage with a mistyped zone read sixty lines of ``zoneinfo``
    stack. Still a ``ValueError`` too, for a caller that catches that.
    """

    def __init__(self, detail: str) -> None:
        Refused.__init__(self, REFUSAL_TIMEZONE_UNKNOWN, "garage.timezone", detail)


class TimezoneDatabaseUnavailable(RuntimeError):
    """The running machine carries NO timezone database at all.

    Not a refusal of the caller's value -- ``America/Denver`` is a perfectly
    good name, and blaming it would send an operator hunting for a typo that is
    not there. ``zoneinfo.available_timezones()`` returned an empty set: neither
    a system tz database on ``TZPATH`` nor the ``tzdata`` package is installed.
    This module cannot read a single local day without one, so it fails loudly
    and names what is missing rather than refusing every zone as unknown. The
    package does NOT add ``tzdata`` as a dependency to make this disappear: the
    install documentation says a tz database is required, and this error is the
    machine saying it has none.
    """

    def __init__(self) -> None:
        super().__init__(
            "this system carries no timezone database: zoneinfo.available_timezones() is "
            "empty, so no IANA name can be validated and no local day can be read. Install "
            "the system tz database (tzdata on Debian and Ubuntu, tzdata on Alpine and "
            "the RPM family) or the Python package `tzdata`; then run this again. This is "
            "the machine's configuration, not the value that was passed."
        )


@cache
def _tz_names() -> frozenset[str]:
    """Every IANA name the running system carries, as the tz DATABASE spells
    it -- read once per process. This is the set the check below asks, and
    deliberately not the filesystem: see ``zone``."""
    return frozenset(available_timezones())


def zone(name: str) -> ZoneInfo:
    """The garage's zone, or a refusal that names it.

    Refused rather than defaulted to UTC. A garage whose zone is unavailable
    would otherwise evaluate its windows on UTC clocks silently, which is wrong
    by hours at every window edge and invisible in every test written at noon.

    **THE NAME IS CHECKED AGAINST THE TZ DATABASE'S OWN NAME SET, CASE-EXACT,
    BEFORE A FILE IS OPENED.** Measured before this: the check was
    ``ZoneInfo(name)`` alone, whose lookup is a file open on ``TZPATH`` -- so on
    a case-insensitive filesystem (a Mac) ``america/denver`` was ACCEPTED and
    stored as typed, and the same stored row was refused on a case-sensitive
    one (a Linux server, CI): a garage created from a laptop, unreadable in
    production. ``available_timezones()`` is a listing of names, so membership
    in it gives the same answer on every filesystem.

    An EMPTY name set is a different condition from an unknown name and gets
    a different error: ``TimezoneDatabaseUnavailable``, never
    ``REFUSAL_TIMEZONE_UNKNOWN`` -- a validator that asked "is the name in the
    set" of a machine with no tz database would refuse EVERY zone, blaming each
    caller's good input for the machine's missing data.
    """
    if not isinstance(name, str) or not name:
        raise UnknownTimezone(
            f"a timezone must be an IANA name such as 'America/Denver', not {name!r}."
        )
    names = _tz_names()
    if not names:
        raise TimezoneDatabaseUnavailable()
    if name not in names:
        raise UnknownTimezone(
            f"{name!r} is not a timezone this system carries (the check is case-exact "
            "against the tz database's own names: 'America/Denver', not 'america/denver'). "
            "It is refused rather than defaulted to UTC: a pass evaluated on UTC clocks "
            "crosses its own window edges by hours, and nothing in the answer would say so."
        )
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        # A name the database lists but whose file cannot be opened: a broken
        # tz install. Still refused by name, never defaulted.
        raise UnknownTimezone(
            f"{name!r} is listed by this system's tz database but could not be loaded: {exc}"
        ) from exc


def require_aware(moment: datetime, what: str = "an instant") -> datetime:
    """Refuse a naive datetime.

    A naive value would be read as the running machine's local time by
    `astimezone`, which is right about half the time and silent about the rest
    -- and "about half the time" is how a 06:00 window opens at 05:00.
    """
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(
            f"{what} must carry a timezone. A naive datetime would be read as the "
            "running machine's local time, which is a property of the server and "
            "not of the garage."
        )
    return moment


def day_start(day: date, tz: ZoneInfo) -> datetime:
    """The instant a local calendar day begins. ``fold=0`` is stated, not defaulted."""
    return datetime.combine(day, time(0, 0), tzinfo=tz).replace(fold=0)


def local(moment: datetime, tz: ZoneInfo) -> datetime:
    """The instant as the garage's wall clock reads it."""
    return require_aware(moment).astimezone(tz)


def day_of(moment: datetime, tz: ZoneInfo) -> date:
    """Which local calendar day an instant falls on."""
    return local(moment, tz).date()


def minute_of_day(moment: datetime, tz: ZoneInfo) -> int:
    """Minutes since local midnight, as the wall clock reads them -- 0..1439."""
    wall = local(moment, tz)
    return wall.hour * 60 + wall.minute


def iso_weekday_of(moment: datetime, tz: ZoneInfo) -> int:
    """1 = Monday .. 7 = Sunday, in the garage's local day."""
    return day_of(moment, tz).isoweekday()


def elapsed(start: datetime, end: datetime) -> timedelta:
    """How long passed between two instants -- by their UTC readings.

    NOT ``end - start``. Two aware datetimes in the same zone subtract by wall
    clock under PEP 495, so a stay across the fall-back hour reads an hour
    short and a stay across spring-forward an hour long. Converting both to UTC
    first makes the subtraction a subtraction of instants.
    """
    return require_aware(end, "the end").astimezone(UTC) - require_aware(
        start, "the start"
    ).astimezone(UTC)
