"""The access answer from the store: read, then call the same engine.

There is ONE implementation of the answer, ``garage_pass.access.access``. This
module loads what the engine needs -- the garage, every pass at it that the
identity has a registration on, those registrations, the visits recorded on
those passes, and EVERY GARAGE THOSE PASSES NAME (so that an entry recorded at
another garage of a pass is read on that garage's clock, not this one's) -- and
hands them over. Nothing is decided here.

Two doors onto the one loader. ``access_from_store`` opens its own transaction
on a connection, reads, and leaves the connection idle -- the command line's
``access-in-store``. ``answer_in_transaction`` reads on a cursor a caller
already holds, INSIDE that caller's transaction, so a redemption that has just
written a registration gets the access answer for that same movement from the
rows it wrote and not from a second implementation of the question.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from garage_pass.access import Answer, access
from garage_pass.garage import Garage
from garage_pass.store.postgres import tenant
from garage_pass.store.records import (
    as_uuid,
    garages_of,
    load_garage,
    load_pass,
    registrations_of,
    visits_on,
)
from garage_pass.terms import Direction


def answer_in_transaction(
    cursor: Any, tenant_id: Any, garage_external_id: str, vehicle_identity: str,
    lane: str, direction: Direction, at: datetime,
) -> Answer:
    """The access answer for one movement, read through ``cursor`` in the
    caller's transaction and answered by the engine. The caller owns the
    transaction: nothing here commits or rolls back."""
    tenant_uuid = as_uuid(tenant_id)
    identity = vehicle_identity.strip() if isinstance(vehicle_identity, str) else ""
    garage_uuid, garage = load_garage(cursor, tenant_uuid, garage_external_id)
    registrations = (
        registrations_of(cursor, tenant_uuid, garage_uuid, identity) if identity else []
    )
    passes = {}
    visits = []
    # the garages of every selected pass, each loaded ONCE by its external id
    # (``load_garage``: a stored zone the system does not carry loads as an
    # UNREADABLE garage, and the engine refuses by name if it must read it)
    garages: dict[str, Garage] = {}
    for pass_uuid, registration in registrations:
        if registration.pass_id in passes:
            continue
        _uuid, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, registration.pass_id)
        passes[registration.pass_id] = pass_
        visits += visits_on(cursor, tenant_uuid, pass_uuid, registration.pass_id)
        for external_id, _garage_uuid in garages_of(cursor, tenant_uuid, pass_uuid):
            if external_id not in garages and external_id != garage_external_id:
                _u, garages[external_id] = load_garage(cursor, tenant_uuid, external_id)
    return access(
        garage=garage,
        passes=list(passes.values()),
        registrations=[r for _u, r in registrations],
        visits=visits,
        vehicle_identity=identity,
        lane=lane,
        direction=direction,
        at=at,
        garages=list(garages.values()),
    )


def access_from_store(
    connection: Any, tenant_id: Any, garage_external_id: str, vehicle_identity: str,
    lane: str, direction: Direction, at: datetime,
) -> Answer:
    with tenant(connection, tenant_id) as cursor:
        answer = answer_in_transaction(
            cursor, tenant_id, garage_external_id, vehicle_identity, lane, direction, at,
        )
    connection.rollback()  # a read; leave the connection idle and unlocked
    return answer
