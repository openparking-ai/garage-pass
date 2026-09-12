"""Writing and reading passes, registrations, state changes and visits.

Every function takes a cursor already inside a tenant's context (see
``postgres.tenant``) and never commits: the caller owns the transaction. A
refusal is raised BEFORE any row changes, so a caller that commits after a
refusal has committed nothing -- except where a constraint fires as the
backstop for two writers racing, which aborts the transaction and is reported
by its constraint name, and the caller rolls back.

**ONE CAR, ONE PASS PER GARAGE.** ``register_vehicle`` refuses by name, naming
the pass that holds the identity and the day that registration ends, before
the database's EXCLUDE has to. ``change_state`` to ``revoked`` ends the pass's
registrations on the revocation day, so the identity is free from that day
(``they got divorced``). A registration on a pass whose ``valid_to`` has passed
is released -- ended on the day after ``valid_to`` -- by the next registration
attempt that meets it, because expiry is derived and nobody writes it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from garage_pass.findings import (
    REFUSAL_CONSTRAINT,
    REFUSAL_EXIT_BEFORE_ENTRY,
    REFUSAL_FIELD_BLANK,
    REFUSAL_GARAGE_MISMATCH,
    REFUSAL_GARAGE_NOT_FOUND,
    REFUSAL_NO_OPEN_VISIT,
    REFUSAL_PASS_ALREADY_EXISTS,
    REFUSAL_PASS_NOT_FOUND,
    REFUSAL_REGISTRATION_ALREADY_ENDED,
    REFUSAL_REGISTRATION_ENDS_BEFORE_IT_STARTS,
    REFUSAL_REGISTRATION_NOT_FOUND,
    REFUSAL_REGISTRATION_OUTLIVES_THE_PASS,
    REFUSAL_VEHICLE_ON_ANOTHER_PASS,
    REFUSAL_VISIT_ALREADY_OPEN,
    Refused,
)
from garage_pass.garage import Garage, garage_from_stored, require_text
from garage_pass.localday import day_of, require_aware, zone
from garage_pass.passes import Holder, Pass, Registration, State, Visit
from garage_pass.states import transition
from garage_pass.terms import AllowancePeriod, Direction, Terms, VisitAllowance, Window

ONE_PASS_PER_GARAGE = "vehicle_registrations_one_pass_per_garage"
ONE_OPEN_VISIT = "visits_one_open_per_vehicle_per_pass"
ENDED_BY_REVOCATION = "pass revoked"
ENDED_BY_EXPIRY = "pass valid_to passed"
ENDED_BY_OWNER = "ended"


def as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


# ---------------------------------------------------------------------------
# garages
# ---------------------------------------------------------------------------


def store_garage(cursor: Any, tenant_id: Any, garage: Garage) -> UUID:
    cursor.execute(
        "INSERT INTO garages (tenant_id, external_id, timezone, transient_available) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (as_uuid(tenant_id), garage.id, garage.timezone, garage.transient_available),
    )
    return as_uuid(cursor.fetchone()[0])


def load_garage(cursor: Any, tenant_id: Any, external_id: str) -> tuple[UUID, Garage]:
    cursor.execute(
        "SELECT id, timezone, transient_available FROM garages "
        "WHERE tenant_id = %s AND external_id = %s",
        (as_uuid(tenant_id), external_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise Refused(REFUSAL_GARAGE_NOT_FOUND, "garage", f"no garage {external_id!r}.")
    # A stored timezone the running system does not carry is an UNREADABLE
    # garage, not an exception: the access call answers, naming the field.
    return as_uuid(row[0]), garage_from_stored(external_id, row[1], row[2])


# ---------------------------------------------------------------------------
# passes
# ---------------------------------------------------------------------------


def create_pass(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_: Pass, *, by: str, at: datetime
) -> UUID:
    """Store a pass. Its terms were validated when the ``Pass`` value was built,
    so a contradiction never reaches this function; the CHECKs in the schema
    are the backstop for a raw write."""
    tenant_uuid = as_uuid(tenant_id)
    require_aware(at, "at")
    if pass_.unreadable is not None or pass_.terms is None or pass_.holder is None:
        raise Refused(
            REFUSAL_FIELD_BLANK, "pass.terms",
            f"pass {pass_.id!r} carries no readable terms; only the load path builds such a value.",
        )
    garage_uuid, _garage = load_garage(cursor, tenant_uuid, garage_external_id)
    if pass_.garage_id != garage_external_id:
        raise Refused(
            REFUSAL_GARAGE_MISMATCH,
            "pass.garage_id",
            f"pass {pass_.id!r} names garage {pass_.garage_id!r}; asked to store it at "
            f"{garage_external_id!r}.",
        )
    cursor.execute(
        "SELECT 1 FROM passes WHERE tenant_id = %s AND garage_id = %s AND external_id = %s",
        (tenant_uuid, garage_uuid, pass_.id),
    )
    if cursor.fetchone():
        raise Refused(REFUSAL_PASS_ALREADY_EXISTS, "pass.id", f"pass {pass_.id!r}.")
    terms = pass_.terms
    cursor.execute(
        """
        INSERT INTO passes (tenant_id, garage_id, external_id, label, holder_email, holder_name,
                            holder_phone, valid_from, valid_to, max_stay_minutes,
                            allowance_count, allowance_per, entry_allowed, exit_allowed,
                            lanes_stated, state)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            tenant_uuid, garage_uuid, pass_.id, pass_.label, pass_.holder.email,
            pass_.holder.name, pass_.holder.phone, terms.valid_from, terms.valid_to,
            int(terms.max_stay.total_seconds() // 60) if terms.max_stay else None,
            terms.visit_allowance.count if terms.visit_allowance else None,
            terms.visit_allowance.per.value if terms.visit_allowance else None,
            Direction.ENTRY in terms.directions, Direction.EXIT in terms.directions,
            terms.allowed_lanes is not None, pass_.state.value,
        ),
    )
    pass_uuid = as_uuid(cursor.fetchone()[0])
    for position, window in enumerate(terms.windows):
        cursor.execute(
            "INSERT INTO pass_windows (tenant_id, pass_id, days, start_minute, end_minute, "
            "position) VALUES (%s, %s, %s, %s, %s, %s)",
            (tenant_uuid, pass_uuid, sorted(window.days), window.start_minute,
             window.end_minute, position),
        )
    for lane in sorted(terms.allowed_lanes or ()):
        cursor.execute(
            "INSERT INTO pass_lanes (tenant_id, pass_id, lane) VALUES (%s, %s, %s)",
            (tenant_uuid, pass_uuid, lane),
        )
    cursor.execute(
        "INSERT INTO pass_state_changes (tenant_id, pass_id, from_state, to_state, changed_by, "
        "changed_at, reason) VALUES (%s, %s, NULL, %s, %s, %s, 'created')",
        (tenant_uuid, pass_uuid, pass_.state.value, require_text(by, "by"), at),
    )
    return pass_uuid


def load_pass(
    cursor: Any, tenant_id: Any, garage_uuid: UUID, external_id: str
) -> tuple[UUID, Pass]:
    tenant_uuid = as_uuid(tenant_id)
    cursor.execute(
        """
        SELECT p.id, g.external_id, p.label, p.holder_email, p.holder_name, p.holder_phone,
               p.valid_from, p.valid_to, p.max_stay_minutes, p.allowance_count,
               p.allowance_per, p.entry_allowed, p.exit_allowed, p.lanes_stated, p.state
        FROM passes p JOIN garages g ON g.tenant_id = p.tenant_id AND g.id = p.garage_id
        WHERE p.tenant_id = %s AND p.garage_id = %s AND p.external_id = %s
        """,
        (tenant_uuid, garage_uuid, external_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise Refused(REFUSAL_PASS_NOT_FOUND, "pass.id", f"no pass {external_id!r}.")
    return as_uuid(row[0]), _pass_from_row(cursor, tenant_uuid, external_id, row)


def _pass_from_row(cursor: Any, tenant_uuid: UUID, external_id: str, row: tuple) -> Pass:
    """The stored row as a ``Pass``.

    **TERMS ARE RE-VALIDATED ON EVERY LOAD** -- ``Terms`` and ``Holder`` run
    their validators when built -- so a row that passes every CHECK in the
    schema but fails the validator (a raw write; or a validator TIGHTENED after
    the row was stored, which strands every pass it no longer accepts) is met
    here, not at creation. It becomes an UNREADABLE pass carrying the refusal,
    never an exception: an access call about it -- an exit above all -- still
    produces a stated answer naming the pass and the field. Measured: before
    this, four such rows made every access call on the pass raise.
    """
    try:
        return _readable_pass_from_row(cursor, tenant_uuid, external_id, row)
    except Refused as refusal:
        (pass_uuid, garage_ext, label, *_rest, state) = row
        return Pass(
            id=external_id, garage_id=garage_ext, label=label, holder=None, terms=None,
            state=State(state), unreadable=refusal.as_unreadable(),
        )


def _readable_pass_from_row(
    cursor: Any, tenant_uuid: UUID, external_id: str, row: tuple
) -> Pass:
    (pass_uuid, garage_ext, label, email, name, phone, valid_from, valid_to, max_stay,
     count, per, entry, exit_, lanes_stated, state) = row
    cursor.execute(
        "SELECT days, start_minute, end_minute FROM pass_windows "
        "WHERE tenant_id = %s AND pass_id = %s ORDER BY position",
        (tenant_uuid, pass_uuid),
    )
    windows = tuple(
        Window(days=frozenset(d), start_minute=s, end_minute=e) for d, s, e in cursor.fetchall()
    )
    lanes = None
    if lanes_stated:
        cursor.execute(
            "SELECT lane FROM pass_lanes WHERE tenant_id = %s AND pass_id = %s",
            (tenant_uuid, pass_uuid),
        )
        lanes = frozenset(r[0] for r in cursor.fetchall())
    directions = set()
    if entry:
        directions.add(Direction.ENTRY)
    if exit_:
        directions.add(Direction.EXIT)
    return Pass(
        id=external_id,
        garage_id=garage_ext,
        label=label,
        holder=Holder(email=email, name=name, phone=phone),
        terms=Terms(
            valid_from=valid_from,
            valid_to=valid_to,
            windows=windows,
            max_stay=timedelta(minutes=max_stay) if max_stay is not None else None,
            visit_allowance=VisitAllowance(count, AllowancePeriod(per)) if count else None,
            directions=frozenset(directions),
            allowed_lanes=lanes,
        ),
        state=State(state),
    )


def change_state(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str, to: State,
    *, by: str, at: datetime, reason: str,
) -> dict:
    """Move a pass, record who/when/why, and -- on revocation -- end its
    registrations on the revocation day in the garage's local calendar."""
    tenant_uuid = as_uuid(tenant_id)
    garage_uuid, garage = load_garage(cursor, tenant_uuid, garage_external_id)
    pass_uuid, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    moved, change = transition(pass_, to, by=by, at=at, reason=reason)
    cursor.execute(
        "UPDATE passes SET state = %s WHERE tenant_id = %s AND id = %s",
        (moved.state.value, tenant_uuid, pass_uuid),
    )
    cursor.execute(
        "INSERT INTO pass_state_changes (tenant_id, pass_id, from_state, to_state, changed_by, "
        "changed_at, reason) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (tenant_uuid, pass_uuid, change.from_state.value, change.to_state.value,
         change.changed_by, change.changed_at, change.reason),
    )
    ended = 0
    if to is State.REVOKED:
        today = day_of(at, zone(garage.timezone))
        cursor.execute(
            "UPDATE vehicle_registrations SET end_day = GREATEST(%s, effective_day), "
            "ended_reason = %s WHERE tenant_id = %s AND pass_id = %s "
            "AND (end_day IS NULL OR end_day > GREATEST(%s, effective_day))",
            (today, ENDED_BY_REVOCATION, tenant_uuid, pass_uuid, today),
        )
        ended = cursor.rowcount
    return {
        "pass": pass_external_id, "from": change.from_state.value, "to": change.to_state.value,
        "changed_by": change.changed_by, "changed_at": change.changed_at,
        "reason": change.reason, "registrations_ended": ended,
    }


# ---------------------------------------------------------------------------
# registrations
# ---------------------------------------------------------------------------


def _holders(
    cursor: Any, tenant_uuid: UUID, garage_uuid: UUID, identity: str, effective: date,
    end: date | None,
) -> list[tuple]:
    """Every registration of ``identity`` at the garage overlapping the range,
    with its pass's external id, label, state and valid_to."""
    cursor.execute(
        """
        SELECT r.id, p.external_id, p.label, p.state, p.valid_to, r.effective_day, r.end_day
        FROM vehicle_registrations r
        JOIN passes p ON p.tenant_id = r.tenant_id AND p.id = r.pass_id
        WHERE r.tenant_id = %s AND r.garage_id = %s AND r.vehicle_identity = %s
          AND daterange(r.effective_day, r.end_day, '[)') && daterange(%s, %s, '[)')
        ORDER BY r.effective_day
        """,
        (tenant_uuid, garage_uuid, identity, effective, end),
    )
    return cursor.fetchall()


def register_vehicle(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str,
    vehicle_identity: str, effective_day: date, end_day: date | None = None,
) -> dict:
    """Bind a vehicle identity to a pass from ``effective_day``, refusing by
    name if another pass at the garage holds it on any of those days."""
    tenant_uuid = as_uuid(tenant_id)
    identity = require_text(vehicle_identity, "vehicle_identity")
    garage_uuid, _garage = load_garage(cursor, tenant_uuid, garage_external_id)
    pass_uuid, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    if pass_.unreadable is not None or pass_.terms is None:
        # Nothing can be registered against terms the module cannot read; the
        # refusal that made the pass unreadable is the refusal here, by name.
        u = pass_.unreadable
        raise Refused(
            u.code if u else REFUSAL_FIELD_BLANK, u.field if u else "pass.terms",
            f"pass {pass_external_id!r} is stored unreadable: {u.detail if u else 'no terms'}",
        )
    last_day = pass_.terms.valid_to
    if end_day is not None:
        if end_day <= effective_day:
            raise Refused(
                REFUSAL_REGISTRATION_ENDS_BEFORE_IT_STARTS, "end_day",
                f"end_day {end_day} is not after effective_day {effective_day}.",
            )
        if last_day is not None and end_day > last_day + timedelta(days=1):
            raise Refused(
                REFUSAL_REGISTRATION_OUTLIVES_THE_PASS, "end_day",
                f"end_day {end_day} is past pass {pass_external_id!r} valid_to {last_day}.",
            )

    # 1. Refuse by name before anything is written. A registration on a pass
    #    whose valid_to has passed before this one takes effect holds nothing --
    #    expiry is derived -- and is released in step 2, not named here.
    holders = _holders(cursor, tenant_uuid, garage_uuid, identity, effective_day, end_day)
    for _rid, other, label, state, other_valid_to, other_from, other_end in holders:
        if state == State.REVOKED.value:
            continue  # ended at revocation; cannot overlap, but stated for the reader
        if other_valid_to is not None and other_valid_to < effective_day and other_end is None:
            continue  # expired before this registration starts: released below
        ends = (
            f"ends on {other_end}" if other_end is not None
            else f"runs to the pass's valid_to {other_valid_to}, so ends on "
                 f"{other_valid_to + timedelta(days=1)}" if other_valid_to is not None
            else "has no end day"
        )
        raise Refused(
            REFUSAL_VEHICLE_ON_ANOTHER_PASS,
            "vehicle_identity",
            f"{identity!r} is registered to pass {other!r} ({label}, {state}) from "
            f"{other_from}, and that registration {ends}.",
        )

    # 2. Release what expiry has already freed.
    for rid, _other, _label, _state, other_valid_to, _from, other_end in holders:
        if other_end is None and other_valid_to is not None and other_valid_to < effective_day:
            cursor.execute(
                "UPDATE vehicle_registrations SET end_day = GREATEST(%s, effective_day), "
                "ended_reason = %s WHERE tenant_id = %s AND id = %s",
                (other_valid_to + timedelta(days=1), ENDED_BY_EXPIRY, tenant_uuid, rid),
            )

    # 3. Write, with the constraint as the backstop for a race.
    import psycopg

    try:
        cursor.execute(
            "INSERT INTO vehicle_registrations (tenant_id, garage_id, pass_id, vehicle_identity, "
            "effective_day, end_day, ended_reason) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "RETURNING id",
            (tenant_uuid, garage_uuid, pass_uuid, identity, effective_day, end_day,
             ENDED_BY_OWNER if end_day is not None else None),
        )
    except psycopg.errors.ExclusionViolation as violation:
        raise Refused(
            REFUSAL_CONSTRAINT, "vehicle_identity",
            f"constraint {violation.diag.constraint_name}: another registration of "
            f"{identity!r} landed first. Roll back and read again.",
        ) from violation
    return {
        "pass": pass_external_id, "vehicle_identity": identity,
        "effective_day": effective_day, "end_day": end_day,
        "bounded_by_valid_to": last_day if end_day is None else None,
    }


def end_registration(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str,
    vehicle_identity: str, end_day: date,
) -> dict:
    """End a registration on a day. The identity is free FROM that day."""
    tenant_uuid = as_uuid(tenant_id)
    identity = require_text(vehicle_identity, "vehicle_identity")
    garage_uuid, _garage = load_garage(cursor, tenant_uuid, garage_external_id)
    pass_uuid, _pass = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    cursor.execute(
        "SELECT id, effective_day, end_day FROM vehicle_registrations WHERE tenant_id = %s "
        "AND pass_id = %s AND vehicle_identity = %s ORDER BY effective_day DESC",
        (tenant_uuid, pass_uuid, identity),
    )
    rows = cursor.fetchall()
    if not rows:
        raise Refused(
            REFUSAL_REGISTRATION_NOT_FOUND, "vehicle_identity",
            f"{identity!r} on pass {pass_external_id!r}.",
        )
    rid, effective, current_end = rows[0]
    if current_end is not None:
        raise Refused(
            REFUSAL_REGISTRATION_ALREADY_ENDED, "end_day",
            f"{identity!r} on pass {pass_external_id!r} already ends on {current_end}.",
        )
    if end_day <= effective:
        raise Refused(
            REFUSAL_REGISTRATION_ENDS_BEFORE_IT_STARTS, "end_day",
            f"end_day {end_day} is not after effective_day {effective}.",
        )
    cursor.execute(
        "UPDATE vehicle_registrations SET end_day = %s, ended_reason = %s "
        "WHERE tenant_id = %s AND id = %s",
        (end_day, ENDED_BY_OWNER, tenant_uuid, rid),
    )
    return {"pass": pass_external_id, "vehicle_identity": identity, "end_day": end_day}


def registrations_of(
    cursor: Any, tenant_id: Any, garage_uuid: UUID, identity: str
) -> list[tuple[UUID, Registration]]:
    """Every registration of the identity at the garage, as (pass uuid, value)."""
    cursor.execute(
        """
        SELECT r.pass_id, p.external_id, r.effective_day, r.end_day
        FROM vehicle_registrations r
        JOIN passes p ON p.tenant_id = r.tenant_id AND p.id = r.pass_id
        WHERE r.tenant_id = %s AND r.garage_id = %s AND r.vehicle_identity = %s
        ORDER BY r.effective_day
        """,
        (as_uuid(tenant_id), garage_uuid, identity),
    )
    return [
        (as_uuid(pid), Registration(pass_id=ext, vehicle_identity=identity,
                                    effective_day=eff, end_day=end))
        for pid, ext, eff, end in cursor.fetchall()
    ]


# ---------------------------------------------------------------------------
# visits — the ledger
# ---------------------------------------------------------------------------


def _open_visit(cursor: Any, tenant_uuid: UUID, pass_uuid: UUID, identity: str) -> tuple | None:
    cursor.execute(
        "SELECT id, entered_at FROM visits WHERE tenant_id = %s AND pass_id = %s "
        "AND vehicle_identity = %s AND exited_at IS NULL",
        (tenant_uuid, pass_uuid, identity),
    )
    return cursor.fetchone()


def record_entry(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str,
    vehicle_identity: str, lane: str, at: datetime,
) -> dict:
    tenant_uuid = as_uuid(tenant_id)
    identity = require_text(vehicle_identity, "vehicle_identity")
    require_aware(at, "at")
    garage_uuid, _garage = load_garage(cursor, tenant_uuid, garage_external_id)
    pass_uuid, _pass = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    open_ = _open_visit(cursor, tenant_uuid, pass_uuid, identity)
    if open_ is not None:
        raise Refused(
            REFUSAL_VISIT_ALREADY_OPEN, "vehicle_identity",
            f"{identity!r} entered on pass {pass_external_id!r} at {open_[1].isoformat()} "
            "and has no recorded exit.",
        )
    import psycopg

    try:
        cursor.execute(
            "INSERT INTO visits (tenant_id, garage_id, pass_id, vehicle_identity, entry_lane, "
            "entered_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (tenant_uuid, garage_uuid, pass_uuid, identity, require_text(lane, "lane"), at),
        )
    except psycopg.errors.UniqueViolation as violation:
        raise Refused(
            REFUSAL_CONSTRAINT, "vehicle_identity",
            f"constraint {violation.diag.constraint_name}: an entry landed first.",
        ) from violation
    return {"pass": pass_external_id, "vehicle_identity": identity, "entered_at": at,
            "entry_lane": lane}


def record_exit(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str,
    vehicle_identity: str, lane: str, at: datetime,
) -> dict:
    tenant_uuid = as_uuid(tenant_id)
    identity = require_text(vehicle_identity, "vehicle_identity")
    require_aware(at, "at")
    garage_uuid, _garage = load_garage(cursor, tenant_uuid, garage_external_id)
    pass_uuid, _pass = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    open_ = _open_visit(cursor, tenant_uuid, pass_uuid, identity)
    if open_ is None:
        raise Refused(
            REFUSAL_NO_OPEN_VISIT, "vehicle_identity",
            f"{identity!r} on pass {pass_external_id!r}.",
        )
    visit_id, entered_at = open_
    if at < entered_at:
        raise Refused(
            REFUSAL_EXIT_BEFORE_ENTRY, "at",
            f"{at.isoformat()} is before the entry at {entered_at.isoformat()}.",
        )
    cursor.execute(
        "UPDATE visits SET exited_at = %s, exit_lane = %s WHERE tenant_id = %s AND id = %s",
        (at, require_text(lane, "lane"), tenant_uuid, visit_id),
    )
    return {"pass": pass_external_id, "vehicle_identity": identity, "entered_at": entered_at,
            "exited_at": at, "exit_lane": lane}


def visits_on(cursor: Any, tenant_id: Any, pass_uuid: UUID, pass_external_id: str) -> list[Visit]:
    cursor.execute(
        "SELECT vehicle_identity, entry_lane, entered_at, exited_at, exit_lane FROM visits "
        "WHERE tenant_id = %s AND pass_id = %s ORDER BY entered_at",
        (as_uuid(tenant_id), pass_uuid),
    )
    return [
        Visit(pass_id=pass_external_id, vehicle_identity=v, entry_lane=el, entered_at=ea,
              exited_at=xa, exit_lane=xl)
        for v, el, ea, xa, xl in cursor.fetchall()
    ]
