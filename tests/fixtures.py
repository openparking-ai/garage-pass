"""Fixtures, and the control that each one has the property it claims.

**A FIXTURE IS PART OF THE MEASUREMENT.** A garage fixture whose timezone never
observes daylight saving cannot exercise the local-day arithmetic, and a number
taken against it reads as evidence while measuring nothing. So every fixture here
carries an assertion that it holds the property it exists to represent, and
``test_fixture_axes.py`` runs those assertions as a test in their own right.

**AND A FIXTURE MUST VARY EVERY AXIS THE DECISION BRANCHES ON.** The axes the
access answer actually turns on, read from ``access.py`` rather than imagined:

* the typed state -- all five -- and the derived one, expired
* the direction -- entry and exit
* the transient mode -- true, false, unstated
* each term present and absent: valid range, windows, max stay, allowance, lanes
* the timezone -- one that shifts and one that does not
* the instant -- inside a window, outside it, on each transition day
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta

from garage_pass.garage import Garage
from garage_pass.localday import day_start, elapsed, zone
from garage_pass.passes import Holder, Pass, Registration, State
from garage_pass.terms import (
    AllowancePeriod,
    Direction,
    GarageLanes,
    Terms,
    VisitAllowance,
    Window,
)

#: A zone that observes daylight saving, and one that does not. The second is
#: not decoration: it is the control proving the first one's DST assertions are
#: about the zone rather than about the arithmetic being wrong everywhere.
SHIFTING_ZONE = "America/Denver"
FIXED_ZONE = "America/Phoenix"

#: 2026 US transitions. Named so a test asserts against a date rather than a
#: comment, and so the fixture control can prove they really are transitions.
SPRING_FORWARD_2026 = date(2026, 3, 8)
FALL_BACK_2026 = date(2026, 11, 1)

BOTH = frozenset({Direction.ENTRY, Direction.EXIT})
WEEKDAYS = frozenset({1, 2, 3, 4, 5})
SIX_TO_EIGHT = Window(days=WEEKDAYS, start_minute=6 * 60, end_minute=20 * 60)

HOLDER = Holder(email="holder@example.com", name="A Holder", phone="+1 555 0100")


def transient_garage(timezone: str = SHIFTING_ZONE) -> Garage:
    return Garage(id="garage-downtown", timezone=timezone, transient_available=True)


def no_transient_garage(timezone: str = SHIFTING_ZONE) -> Garage:
    return Garage(id="garage-staff-only", timezone=timezone, transient_available=False)


def unstated_garage(timezone: str = SHIFTING_ZONE) -> Garage:
    return Garage(id="garage-unstated", timezone=timezone, transient_available=None)


def simple_terms(**overrides: object) -> Terms:
    """Both directions, every lane, no other term. Override to add one."""
    fields: dict = {"directions": BOTH}
    fields.update(overrides)
    return Terms(**fields)


def everything_terms(garage_id: str = "garage-downtown") -> Terms:
    """Every term present at once, the lanes stated at ``garage_id``."""
    return Terms(
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        windows=(SIX_TO_EIGHT,),
        max_stay=timedelta(hours=10),
        visit_allowance=VisitAllowance(count=3, per=AllowancePeriod.WINDOW),
        directions=BOTH,
        allowed_lanes=lanes_at(garage_id, "L1", "L2"),
    )


def terms_at(garage_id: str, terms: Terms) -> Terms:
    """The same terms on a pass that names ONE garage, ``garage_id``: stated
    lanes are re-stated there (every lane the configuration names), so a
    configuration written for garage-downtown pairs with any garage. Lanes
    not stated stay not stated. Nothing else moves -- the terms are one set
    wherever the pass is, and this fixture proves it by construction."""
    import dataclasses

    if terms.allowed_lanes is None:
        return terms
    every_lane = frozenset(lane for entry in terms.allowed_lanes for lane in entry.lanes)
    return dataclasses.replace(terms, allowed_lanes=lanes_at(garage_id, *every_lane))


def a_pass(
    id: str = "pass-1",
    garage_ids: Iterable[str] = ("garage-downtown",),
    label: str = "Employee",
    terms: Terms | None = None,
    state: State = State.ACTIVE,
) -> Pass:
    """A pass naming ``garage_ids`` -- one garage by default, the shape every
    test before G3a had; a set of several for the multi-garage paths."""
    return Pass(id=id, garage_ids=frozenset(garage_ids), label=label, holder=HOLDER,
                terms=terms or simple_terms(), state=state)


def lanes_at(garage_id: str, *lanes: str) -> tuple[GarageLanes, ...]:
    """A stated lane set at ONE garage; add tuples for a pass over several."""
    return (GarageLanes(garage_id=garage_id, lanes=frozenset(lanes)),)


def registered(pass_: Pass, identity: str = "CAR-1", effective: date = date(2026, 1, 1),
               end: date | None = None) -> Registration:
    return Registration(pass_id=pass_.id, vehicle_identity=identity, effective_day=effective,
                        end_day=end)


def at(day: date, hour: int, minute: int = 0, timezone: str = SHIFTING_ZONE,
       fold: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone(timezone), fold=fold)


def pass_document(**overrides: object) -> dict:
    """The JSON shape the command line reads, valid as written."""
    document: dict = {
        "id": "pass-1",
        "garage_ids": ["garage-downtown"],
        "label": "Employee",
        "holder": {"email": "holder@example.com", "name": "A Holder", "phone": None},
        "terms": {
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "windows": [{"days": [1, 2, 3, 4, 5], "start_minute": 360, "end_minute": 1200}],
            "max_stay_minutes": 600,
            "visit_allowance": {"count": 3, "per": "window"},
            "directions": ["entry", "exit"],
            "allowed_lanes": [{"garage_id": "garage-downtown", "lanes": ["L1", "L2"]}],
        },
        "state": "active",
    }
    document.update(overrides)
    return document


# ---------------------------------------------------------------------------
# The controls on the fixtures themselves.
# ---------------------------------------------------------------------------


def assert_shifting_zone_really_shifts() -> None:
    tz = zone(SHIFTING_ZONE)
    for day, hours in ((SPRING_FORWARD_2026, 23), (FALL_BACK_2026, 25)):
        length = elapsed(day_start(day, tz), day_start(day + timedelta(days=1), tz))
        assert length == timedelta(hours=hours), (
            f"{SHIFTING_ZONE} was chosen because it observes daylight saving, and "
            f"{day} was named as a transition; it is {length} long, not {hours} hours."
        )


def assert_fixed_zone_really_does_not_shift() -> None:
    tz = zone(FIXED_ZONE)
    for day in (SPRING_FORWARD_2026, FALL_BACK_2026):
        length = elapsed(day_start(day, tz), day_start(day + timedelta(days=1), tz))
        assert length == timedelta(hours=24), f"{FIXED_ZONE} shifted on {day}: {length}"


def assert_the_everything_terms_carry_every_term() -> None:
    terms = everything_terms()
    assert terms.valid_from and terms.valid_to and terms.windows and terms.max_stay
    assert terms.visit_allowance and terms.allowed_lanes and terms.directions == BOTH


# ---------------------------------------------------------------------------
# The terms matrix: one configuration per axis the answer branches on, each
# satisfiable at NOON_MONDAY on lane L1 with a recorded entry two hours before.
# ---------------------------------------------------------------------------

#: Monday 2026-06-01, well away from any transition, noon local.
NOON_MONDAY = at(date(2026, 6, 1), 12)
TWO_HOURS_BEFORE = at(date(2026, 6, 1), 10)

TERMS_CONFIGURATIONS: dict[str, Terms] = {
    "nothing but directions": simple_terms(),
    "valid range": simple_terms(valid_from=date(2026, 1, 1), valid_to=date(2026, 12, 31)),
    "window": simple_terms(windows=(SIX_TO_EIGHT,)),
    "max stay": simple_terms(max_stay=timedelta(hours=8)),
    "allowance over life": simple_terms(
        visit_allowance=VisitAllowance(count=3, per=AllowancePeriod.LIFE)
    ),
    "allowance per window": simple_terms(
        windows=(SIX_TO_EIGHT,), visit_allowance=VisitAllowance(count=3, per=AllowancePeriod.WINDOW)
    ),
    "lanes": simple_terms(allowed_lanes=lanes_at("garage-downtown", "L1")),
    "entry only": simple_terms(directions=frozenset({Direction.ENTRY})),
    "exit only": simple_terms(directions=frozenset({Direction.EXIT})),
    "everything": everything_terms(),
}


def assert_the_matrix_holds_both_sides_of_every_axis() -> None:
    """Every term appears in at least one configuration and is absent from at
    least one, so a branch on its presence has a case on each side."""
    for attribute in ("valid_from", "valid_to", "windows", "max_stay",
                      "visit_allowance", "allowed_lanes"):
        present = [n for n, t in TERMS_CONFIGURATIONS.items() if getattr(t, attribute)]
        absent = [n for n, t in TERMS_CONFIGURATIONS.items() if not getattr(t, attribute)]
        assert present and absent, f"{attribute}: present in {present}, absent in {absent}"
    directions = {t.directions for t in TERMS_CONFIGURATIONS.values()}
    assert directions == {BOTH, frozenset({Direction.ENTRY}), frozenset({Direction.EXIT})}
