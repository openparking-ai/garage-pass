"""The access answer from the store: read, then call the same engine.

There is ONE implementation of the answer, ``garage_pass.access.access``. This
function loads what the engine needs -- the garage, every pass at it that the
identity has a registration on, those registrations, and the visits recorded
on those passes -- and hands them over. Nothing is decided here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from garage_pass.access import Answer, access
from garage_pass.store.postgres import tenant
from garage_pass.store.records import (
    as_uuid,
    load_garage,
    load_pass,
    registrations_of,
    visits_on,
)
from garage_pass.terms import Direction


def access_from_store(
    connection: Any, tenant_id: Any, garage_external_id: str, vehicle_identity: str,
    lane: str, direction: Direction, at: datetime,
) -> Answer:
    tenant_uuid = as_uuid(tenant_id)
    identity = vehicle_identity.strip() if isinstance(vehicle_identity, str) else ""
    with tenant(connection, tenant_uuid) as cursor:
        garage_uuid, garage = load_garage(cursor, tenant_uuid, garage_external_id)
        registrations = (
            registrations_of(cursor, tenant_uuid, garage_uuid, identity) if identity else []
        )
        passes = {}
        visits = []
        for pass_uuid, registration in registrations:
            if registration.pass_id in passes:
                continue
            _uuid, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, registration.pass_id)
            passes[registration.pass_id] = pass_
            visits += visits_on(cursor, tenant_uuid, pass_uuid, registration.pass_id)
    connection.rollback()  # a read; leave the connection idle and unlocked
    return access(
        garage=garage,
        passes=list(passes.values()),
        registrations=[r for _u, r in registrations],
        visits=visits,
        vehicle_identity=identity,
        lane=lane,
        direction=direction,
        at=at,
    )
