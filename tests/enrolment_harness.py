"""The enrolment tests' shared moves: the three garage shapes R1 produces,
issuing a credential, redeeming one, and reading what was written -- each a
committed round trip through the module, as an owner's screen or a lane
would make it.

Not a test module (no ``test_`` prefix) and not a conftest: imported by name
so a reader of any enrolment test can see where a row came from.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fixtures import NOON_MONDAY, SHIFTING_ZONE, a_pass
from garage_pass.enrolment import where_enrolment_happens
from garage_pass.garage import Garage
from garage_pass.passes import Pass, State
from garage_pass.store.enrolments import (
    ENROLMENT,
    HOLDER_LINK,
    Redemption,
    issue_enrolment,
    issue_holder_link,
    load_credential,
    redeem_enrolment,
    redeem_holder_link,
)
from garage_pass.store.postgres import tenant
from garage_pass.terms import Direction
from store_harness import query, seed

#: The three shapes R1 produces. A no-transient garage DERIVES entry and states
#: nothing; a transient garage states which end.
NO_TRANSIENT = Garage(id="garage-staff-only", timezone=SHIFTING_ZONE, transient_available=False)
TRANSIENT_ENTRY = Garage(id="garage-downtown", timezone=SHIFTING_ZONE, transient_available=True,
                         enrols_at="entry")
TRANSIENT_EXIT = Garage(id="garage-airport", timezone=SHIFTING_ZONE, transient_available=True,
                        enrols_at="exit")
TRANSIENT_UNSTATED = Garage(id="garage-downtown", timezone=SHIFTING_ZONE, transient_available=True)
GARAGES = (NO_TRANSIENT, TRANSIENT_ENTRY, TRANSIENT_EXIT)

def other_end(direction: Direction) -> Direction:
    return Direction.EXIT if direction is Direction.ENTRY else Direction.ENTRY


#: Monday 2026-06-01: the credential's starting day, three days from it.
STARTS_ON = date(2026, 6, 1)
DAYS = 3


def seeded(app: Any, tenant_id: Any, garage: Garage, state: State = State.DRAFT,
           **overrides) -> Pass:
    """A garage and one pass at it, committed. The pass is DRAFT by default:
    the first redemption moves it to active, which is the case worth watching."""
    pass_ = a_pass(garage_id=garage.id, state=state, **overrides)
    seed(app, tenant_id, garage, (pass_,))
    return pass_


def issue(app: Any, tenant_id: Any, garage: Garage, pass_: Pass, external_id: str = "qr-1",
          starts_on: date = STARTS_ON, days_valid: object = DAYS, by: str = "owner",
          at: datetime = NOON_MONDAY, vehicle_description: str | None = None) -> dict:
    with tenant(app, tenant_id) as cursor:
        out = issue_enrolment(cursor, tenant_id, garage.id, pass_.id, external_id, starts_on,
                              days_valid, by=by, at=at, vehicle_description=vehicle_description)
    app.commit()
    return out


def issue_link(app: Any, tenant_id: Any, garage: Garage, pass_: Pass, external_id: str = "link-1",
               starts_on: date = STARTS_ON, days_valid: object = DAYS, by: str = "owner",
               at: datetime = NOON_MONDAY) -> dict:
    with tenant(app, tenant_id) as cursor:
        out = issue_holder_link(cursor, tenant_id, garage.id, pass_.id, external_id, starts_on,
                                days_valid, by=by, at=at)
    app.commit()
    return out


def redeem(app: Any, tenant_id: Any, garage: Garage, token: str, identity: str = "CAR-1",
           lane: str = "L1", direction: Direction | None = None,
           at: datetime = NOON_MONDAY) -> Redemption:
    """Present the QR at a lane -- at the end the garage enrols at unless told
    otherwise -- and commit what the module wrote (nothing, when refused)."""
    direction = Direction(where_enrolment_happens(garage)) if direction is None else direction
    with tenant(app, tenant_id) as cursor:
        out = redeem_enrolment(cursor, tenant_id, garage.id, token, identity, lane, direction, at)
    app.commit()
    return out


def redeem_link(app: Any, tenant_id: Any, garage: Garage, token: str, *, name: str = "A Holder",
                phone: str = "+1 555 0100", enrolment_external_id: str = "qr-from-link",
                starts_on: date = STARTS_ON, days_valid: object = DAYS,
                at: datetime = NOON_MONDAY, vehicle_description: str | None = None) -> dict:
    with tenant(app, tenant_id) as cursor:
        out = redeem_holder_link(
            cursor, tenant_id, garage.id, token, name=name, phone=phone,
            enrolment_external_id=enrolment_external_id, starts_on=starts_on,
            days_valid=days_valid, at=at, vehicle_description=vehicle_description,
        )
    app.commit()
    return out


def enrolment_row(app: Any, tenant_id: Any, external_id: str = "qr-1") -> tuple:
    """state, redeemed identity, lane, direction, instant, cancelled by/at/reason."""
    rows = query(
        app, tenant_id,
        "SELECT state, redeemed_vehicle_identity, redeemed_lane, redeemed_direction, redeemed_at, "
        "cancelled_by, cancelled_at, cancelled_reason FROM enrolments WHERE external_id = %s",
        (external_id,),
    )
    assert len(rows) == 1, rows
    return rows[0]


def credential(app: Any, tenant_id: Any, external_id: str, kind: str = ENROLMENT):
    with tenant(app, tenant_id) as cursor:
        out = load_credential(cursor, tenant_id, kind, external_id)
    app.rollback()
    return out


def link_row(app: Any, tenant_id: Any, external_id: str = "link-1") -> tuple:
    rows = query(
        app, tenant_id,
        "SELECT state, redeemed_at, cancelled_by, cancelled_at, cancelled_reason FROM holder_links "
        "WHERE external_id = %s",
        (external_id,),
    )
    assert len(rows) == 1, rows
    return rows[0]


def registrations(app: Any, tenant_id: Any) -> list[tuple]:
    return query(
        app, tenant_id,
        "SELECT p.external_id, r.vehicle_identity, r.effective_day, r.end_day, r.ended_reason "
        "FROM vehicle_registrations r JOIN passes p ON p.id = r.pass_id ORDER BY r.created_at",
    )


def pass_state(app: Any, tenant_id: Any, pass_: Pass) -> str:
    return query(app, tenant_id, "SELECT state FROM passes WHERE external_id = %s",
                 (pass_.id,))[0][0]


def state_changes(app: Any, tenant_id: Any) -> list[tuple]:
    return query(
        app, tenant_id,
        "SELECT from_state, to_state, changed_by, reason FROM pass_state_changes "
        "ORDER BY changed_at, created_at",
    )


__all__ = [
    "DAYS", "ENROLMENT", "GARAGES", "HOLDER_LINK", "NO_TRANSIENT", "STARTS_ON",
    "TRANSIENT_ENTRY", "TRANSIENT_EXIT", "TRANSIENT_UNSTATED", "credential", "enrolment_row",
    "issue", "issue_link", "link_row", "other_end", "pass_state", "redeem", "redeem_link",
    "registrations", "seeded", "state_changes",
]
