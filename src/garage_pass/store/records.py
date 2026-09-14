"""Writing and reading passes, registrations, state changes and visits.

Every function takes a cursor already inside a tenant's context (see
``postgres.tenant``) and never commits: the caller owns the transaction. A
refusal is raised BEFORE any row changes, so a caller that commits after a
refusal has committed nothing -- except where a constraint fires as the
backstop for two writers racing, which aborts the transaction and is reported
by its constraint name, and the caller rolls back.

**A PASS NAMES A SET OF GARAGES, AND THE STORE READS THE SET AT EVERY DOOR.**
``create_pass`` writes the set (``pass_garages``) and the lanes per garage in
the same transaction as the pass, and refuses by name to store a pass at a
garage it does not name; ``load_pass`` loads by ``(tenant, external id)``,
returns the pass with its full set, and KEEPS ITS GARAGE ARGUMENT -- it refuses
when that garage is not in the set, so every caller's existing refusal still
fires. Everything below that takes a garage takes one the pass names.

**ONE CAR, ONE PASS PER GARAGE -- AT EVERY GARAGE THE PASS NAMES, TOGETHER OR
NOT AT ALL.** ``register_vehicle`` writes ONE ``vehicle_registrations`` row per
garage of the pass, in one transaction: the EXCLUDE keeps its exact per-garage
meaning and its backstop role, and a pass that spans three garages holds the
car at all three from one enrolment. The collision check runs at EVERY garage
of the set BEFORE the first row is written, so a car held by another pass at
any one of them refuses the whole registration by name -- naming that garage,
the pass that holds the identity and the day that registration ends -- and a
partial fan-out is never an outcome. The EXCLUDE is the backstop at each
garage. ``change_state`` to ``revoked`` ends the pass's
registrations on the revocation day, so the identity is free from that day
(``they got divorced``). A registration on a pass whose ``valid_to`` has passed
is released -- ended on the day after ``valid_to`` -- by the next registration
attempt that meets it, because expiry is derived and nobody writes it.

**THE TARGET PASS'S STATE IS READ, AND A PASS THAT IS NOT REGISTRABLE IS
REFUSED BY NAME, NAMING THE STATE.** Registrable: ``draft``,
``awaiting_enrolment`` and ``active`` (enrolment registers onto the first
two). Refused: ``suspended`` -- a hold, and a car added to a hold is a claim
the owner did not make; ``revoked`` -- they got divorced; ``expired`` -- over,
derived from ``valid_to`` against the registration's ``effective_day``.
Measured before this: a car was registered onto a REVOKED pass through the
command line, and the overlap check then SKIPPED holders on revoked passes on
the assumption that revocation had ended them, so the same car registered
onto a live pass met the EXCLUDE and was told to "roll back and read again" --
race advice where there was no race. Now every open registration is a holder
whatever its pass's state, so the by-name refusal fires with the survivor
named and the EXCLUDE is the backstop it was designed as: reached only by a
raw write, or by two registrations genuinely racing.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from garage_pass.enrolment import CANCELLED_BY_REVOCATION, CredentialState
from garage_pass.findings import (
    REFUSAL_CONSTRAINT,
    REFUSAL_EXIT_BEFORE_ENTRY,
    REFUSAL_FIELD_BLANK,
    REFUSAL_GARAGE_ALREADY_EXISTS,
    REFUSAL_GARAGE_MISMATCH,
    REFUSAL_GARAGE_NOT_FOUND,
    REFUSAL_NO_OPEN_VISIT,
    REFUSAL_PASS_ALREADY_EXISTS,
    REFUSAL_PASS_NOT_FOUND,
    REFUSAL_PASS_NOT_REGISTRABLE,
    REFUSAL_REGISTRATION_ALREADY_ENDED,
    REFUSAL_REGISTRATION_ENDS_BEFORE_IT_STARTS,
    REFUSAL_REGISTRATION_NOT_FOUND,
    REFUSAL_REGISTRATION_OUTLIVES_THE_PASS,
    REFUSAL_REPAIR_NEEDS_WHO_AND_WHY,
    REFUSAL_TENANT_NOT_FOUND,
    REFUSAL_VEHICLE_ON_ANOTHER_PASS,
    REFUSAL_VISIT_ALREADY_OPEN,
    Refused,
)
from garage_pass.garage import (
    Garage,
    garage_from_stored,
    refuse_enrols_at_contradiction,
    require_enrols_at,
    require_text,
)
from garage_pass.localday import day_of, require_aware, zone
from garage_pass.passes import EXPIRED, Holder, Pass, Registration, State, Visit
from garage_pass.states import effective_state, transition
from garage_pass.terms import (
    AllowancePeriod,
    Direction,
    GarageLanes,
    Terms,
    VisitAllowance,
    Window,
)

ONE_PASS_PER_GARAGE = "vehicle_registrations_one_pass_per_garage"
ONE_OPEN_VISIT = "visits_one_open_per_vehicle_per_garage"
ENDED_BY_REVOCATION = "pass revoked"
ENDED_BY_EXPIRY = "pass valid_to passed"
ENDED_BY_OWNER = "ended"

#: The typed states a vehicle may be registered onto. Enrolment (the next
#: round) registers onto the first two; ``suspended`` and ``revoked`` are not
#: here on purpose, and ``expired`` is derived, so it is checked beside these.
REGISTRABLE_STATES = frozenset({State.DRAFT, State.AWAITING_ENROLMENT, State.ACTIVE})


def as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


# ---------------------------------------------------------------------------
# garages
# ---------------------------------------------------------------------------


def store_garage(cursor: Any, tenant_id: Any, garage: Garage) -> UUID:
    """Store a garage. Its timezone was refused where the ``Garage`` value was
    built if the system does not carry it. A second garage with the same id is
    refused by name; the UNIQUE is the backstop for two writers racing.

    THE TENANT ROW IS READ FIRST. This is the first write anything makes for a
    tenant, so a ``--tenant`` nobody seeded arrives here before any garage
    could be looked up -- measured before this it was the database's foreign
    key, a traceback at the command line, while every other store command was
    already refusing GARAGE_NOT_FOUND. The tenant policy lets the role read
    exactly its own row, which is the row this asks for."""
    tenant_uuid = as_uuid(tenant_id)
    cursor.execute("SELECT 1 FROM tenants WHERE id = %s", (tenant_uuid,))
    if not cursor.fetchone():
        raise Refused(
            REFUSAL_TENANT_NOT_FOUND, "tenant",
            f"no tenant row has id {tenant_uuid}; seed the tenant before its first garage.",
        )
    cursor.execute(
        "SELECT 1 FROM garages WHERE tenant_id = %s AND external_id = %s",
        (tenant_uuid, garage.id),
    )
    if cursor.fetchone():
        raise Refused(REFUSAL_GARAGE_ALREADY_EXISTS, "garage.id", f"garage {garage.id!r}.")
    import psycopg

    try:
        cursor.execute(
            "INSERT INTO garages (tenant_id, external_id, timezone, transient_available, "
            "enrols_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (tenant_uuid, garage.id, garage.timezone, garage.transient_available,
             garage.enrols_at),
        )
    except psycopg.errors.UniqueViolation as violation:
        raise Refused(
            REFUSAL_CONSTRAINT, "garage.id",
            f"constraint {violation.diag.constraint_name}: another garage {garage.id!r} "
            "landed first. Roll back and read again.",
        ) from violation
    return as_uuid(cursor.fetchone()[0])


def load_garage(cursor: Any, tenant_id: Any, external_id: str) -> tuple[UUID, Garage]:
    cursor.execute(
        "SELECT id, timezone, transient_available, enrols_at FROM garages "
        "WHERE tenant_id = %s AND external_id = %s",
        (as_uuid(tenant_id), external_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise Refused(REFUSAL_GARAGE_NOT_FOUND, "garage", f"no garage {external_id!r}.")
    # A stored timezone the running system does not carry is an UNREADABLE
    # garage, not an exception: the access call answers, naming the field.
    return as_uuid(row[0]), garage_from_stored(external_id, row[1], row[2], row[3])


def load_readable_garage(cursor: Any, tenant_id: Any, external_id: str) -> tuple[UUID, Garage]:
    """The garage for a WRITE: an unreadable one is refused by name, with the
    refusal that made it unreadable and the command that repairs it.

    The same shape as a write against an unreadable pass: nothing can be
    written against a clock nobody can read. Measured before this, a pass and
    a registration were created at a garage stored with ``Mars/Olympus`` while
    the access call about them degraded to not-covered. Reads still load the
    garage as it is (``load_garage``), so the access answer names it; and
    ``set_garage_timezone`` is the one write that takes an unreadable garage,
    because without it an unreadable garage could never be fixed.
    """
    garage_uuid, garage = load_garage(cursor, tenant_id, external_id)
    if garage.unreadable is not None:
        u = garage.unreadable
        raise Refused(
            u.code, u.field,
            f"garage {external_id!r} is stored unreadable: {u.detail} Repair it with "
            "set-garage-timezone before writing against it.",
        )
    return garage_uuid, garage


def set_garage_timezone(
    cursor: Any, tenant_id: Any, garage_external_id: str, timezone: str,
    *, by: str, at: datetime, reason: str,
) -> dict:
    """THE REPAIR. Correct a stored garage's timezone -- the one write that
    does not require the garage to be readable first, because it is how an
    unreadable garage becomes readable. The new value is refused by name if
    the system does not carry it, so the repair cannot store the defect it
    repairs.

    **AND IT IS RECORDED**: who, when, why, the old value and the new, into
    ``garage_changes`` -- append-only, the shape of ``pass_state_changes``
    (migration 0002). A blank who or why is refused before anything changes.
    Measured before this: the repair moved every clock at the garage and left
    no record but the row."""
    tenant_uuid = as_uuid(tenant_id)
    new_value = require_text(timezone, "garage.timezone")
    zone(new_value)  # refuses an unknown zone by name
    require_aware(at, "at")
    if not isinstance(by, str) or not by.strip():
        raise Refused(REFUSAL_REPAIR_NEEDS_WHO_AND_WHY, "changed_by", f"who is {by!r}.")
    if not isinstance(reason, str) or not reason.strip():
        raise Refused(REFUSAL_REPAIR_NEEDS_WHO_AND_WHY, "reason", f"why is {reason!r}.")
    garage_uuid, garage = load_garage(cursor, tenant_uuid, garage_external_id)
    cursor.execute(
        "UPDATE garages SET timezone = %s WHERE tenant_id = %s AND id = %s",
        (new_value, tenant_uuid, garage_uuid),
    )
    cursor.execute(
        "INSERT INTO garage_changes (tenant_id, garage_id, field, old_value, new_value, "
        "changed_by, changed_at, reason) VALUES (%s, %s, 'timezone', %s, %s, %s, %s, %s)",
        (tenant_uuid, garage_uuid, garage.timezone, new_value, by.strip(), at, reason.strip()),
    )
    return {"garage": garage_external_id, "timezone": new_value, "was": garage.timezone,
            "was_readable": garage.unreadable is None, "changed_by": by.strip(),
            "changed_at": at, "reason": reason.strip()}


def set_garage_enrols_at(
    cursor: Any, tenant_id: Any, garage_external_id: str, enrols_at: str,
    *, by: str, at: datetime, reason: str,
) -> dict:
    """THE SECOND REPAIR: state, or correct, where a stored garage enrols --
    recorded into ``garage_changes`` with ``field = 'enrols_at'`` exactly as the
    timezone repair is (migration 0003 widens that history's CHECK to admit it).
    A garage field that can be set and never corrected is a trap, so this verb
    exists beside the field.

    **THE R1 CONTRADICTION BINDS THE REPAIR AS IT BINDS CREATION**: 'exit' on a
    garage with no transient parking is refused by name, and nothing changes.
    The value must be one of the two ends -- unstated is where a garage starts,
    not where a repair sends it. Unlike the timezone repair this one requires
    the garage to be READABLE first: a clock nobody can read is repaired with
    ``set-garage-timezone`` before anything else is written against it."""
    tenant_uuid = as_uuid(tenant_id)
    new_value = require_enrols_at(require_text(enrols_at, "garage.enrols_at"))
    require_aware(at, "at")
    # Spelled apart from the timezone repair's check on purpose: a fail control
    # anchors on that one and an anchor must appear exactly once.
    for value, field, word in ((by, "changed_by", "who"), (reason, "reason", "why")):
        if not (isinstance(value, str) and value.strip()):
            raise Refused(REFUSAL_REPAIR_NEEDS_WHO_AND_WHY, field, f"{word} is {value!r}.")
    garage_uuid, garage = load_readable_garage(cursor, tenant_uuid, garage_external_id)
    refuse_enrols_at_contradiction(garage.transient_available, new_value)
    cursor.execute(
        "UPDATE garages SET enrols_at = %s WHERE tenant_id = %s AND id = %s",
        (new_value, tenant_uuid, garage_uuid),
    )
    # the columns in another order than the timezone repair's INSERT on purpose:
    # a fail control anchors on that one and an anchor must appear exactly once
    cursor.execute(
        "INSERT INTO garage_changes (tenant_id, garage_id, changed_by, changed_at, reason, "
        "field, old_value, new_value) VALUES (%s, %s, %s, %s, %s, 'enrols_at', %s, %s)",
        (tenant_uuid, garage_uuid, by.strip(), at, reason.strip(), garage.enrols_at, new_value),
    )
    return {"garage": garage_external_id, "enrols_at": new_value, "was": garage.enrols_at,
            "changed_by": by.strip(), "changed_at": at, "reason": reason.strip()}


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
    _garage_uuid, _garage = load_readable_garage(cursor, tenant_uuid, garage_external_id)
    # MEMBERSHIP: the garage this is stored at is one the pass names. Refused
    # by name before anything is written, naming the garage and the set.
    if garage_external_id not in pass_.garage_ids:
        raise Refused(
            REFUSAL_GARAGE_MISMATCH,
            "pass.garage_ids",
            f"pass {pass_.id!r} names garages {sorted(pass_.garage_ids)}; asked to store it at "
            f"{garage_external_id!r}.",
        )
    # every garage of the set exists and is readable: a pass cannot name a
    # garage nobody stored, and nothing is written against a clock nobody can read
    garage_uuids = {
        garage_id: load_readable_garage(cursor, tenant_uuid, garage_id)[0]
        for garage_id in sorted(pass_.garage_ids)
    }
    # the id is unique per TENANT: a pass that spans garages cannot be
    # identified by one of them (the UNIQUE is the backstop for a race)
    cursor.execute(
        "SELECT 1 FROM passes WHERE tenant_id = %s AND external_id = %s",
        (tenant_uuid, pass_.id),
    )
    if cursor.fetchone():
        raise Refused(REFUSAL_PASS_ALREADY_EXISTS, "pass.id", f"pass {pass_.id!r}.")
    terms = pass_.terms
    cursor.execute(
        """
        INSERT INTO passes (tenant_id, external_id, label, holder_email, holder_name,
                            holder_phone, valid_from, valid_to, max_stay_minutes,
                            allowance_count, allowance_per, entry_allowed, exit_allowed,
                            lanes_stated, state)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            tenant_uuid, pass_.id, pass_.label, pass_.holder.email,
            pass_.holder.name, pass_.holder.phone, terms.valid_from, terms.valid_to,
            int(terms.max_stay.total_seconds() // 60) if terms.max_stay else None,
            terms.visit_allowance.count if terms.visit_allowance else None,
            terms.visit_allowance.per.value if terms.visit_allowance else None,
            Direction.ENTRY in terms.directions, Direction.EXIT in terms.directions,
            terms.allowed_lanes is not None, pass_.state.value,
        ),
    )
    pass_uuid = as_uuid(cursor.fetchone()[0])
    # THE SET, in the same transaction as the pass: one row per garage it names
    for garage_id in sorted(pass_.garage_ids):
        cursor.execute(
            "INSERT INTO pass_garages (tenant_id, pass_id, garage_id) VALUES (%s, %s, %s)",
            (tenant_uuid, pass_uuid, garage_uuids[garage_id]),
        )
    for position, window in enumerate(terms.windows):
        cursor.execute(
            "INSERT INTO pass_windows (tenant_id, pass_id, days, start_minute, end_minute, "
            "position) VALUES (%s, %s, %s, %s, %s, %s)",
            (tenant_uuid, pass_uuid, sorted(window.days), window.start_minute,
             window.end_minute, position),
        )
    # the lanes PER GARAGE: every entry names a garage of the set (the Pass
    # refused one that did not), and the database's key says so again
    for entry in sorted(terms.allowed_lanes or (), key=lambda e: e.garage_id):
        for lane in sorted(entry.lanes):
            cursor.execute(
                "INSERT INTO pass_lanes (tenant_id, pass_id, garage_id, lane) "
                "VALUES (%s, %s, %s, %s)",
                (tenant_uuid, pass_uuid, garage_uuids[entry.garage_id], lane),
            )
    cursor.execute(
        "INSERT INTO pass_state_changes (tenant_id, pass_id, from_state, to_state, changed_by, "
        "changed_at, reason) VALUES (%s, %s, NULL, %s, %s, %s, 'created')",
        (tenant_uuid, pass_uuid, pass_.state.value, require_text(by, "by"), at),
    )
    return pass_uuid


#: The pass row with its garage set beside it: the set's external ids and its
#: uuids, aggregated in one order, so the two arrays line up.
_PASS_COLUMNS = """
        SELECT p.id, p.label, p.holder_email, p.holder_name, p.holder_phone,
               p.valid_from, p.valid_to, p.max_stay_minutes, p.allowance_count,
               p.allowance_per, p.entry_allowed, p.exit_allowed, p.lanes_stated, p.state,
               (SELECT array_agg(g.external_id ORDER BY g.external_id)
                  FROM pass_garages pg
                  JOIN garages g ON g.tenant_id = pg.tenant_id AND g.id = pg.garage_id
                 WHERE pg.tenant_id = p.tenant_id AND pg.pass_id = p.id),
               (SELECT array_agg(g.id ORDER BY g.external_id)
                  FROM pass_garages pg
                  JOIN garages g ON g.tenant_id = pg.tenant_id AND g.id = pg.garage_id
                 WHERE pg.tenant_id = p.tenant_id AND pg.pass_id = p.id)
        FROM passes p
"""


def load_pass(
    cursor: Any, tenant_id: Any, garage_uuid: UUID, external_id: str
) -> tuple[UUID, Pass]:
    """The pass by ``(tenant, external id)``, with its full garage set -- AT
    THE GARAGE ASKED FOR: a pass that does not name that garage is refused by
    name, naming the set, with the refusal every caller already handles."""
    tenant_uuid = as_uuid(tenant_id)
    cursor.execute(
        _PASS_COLUMNS + "WHERE p.tenant_id = %s AND p.external_id = %s",
        (tenant_uuid, external_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise Refused(REFUSAL_PASS_NOT_FOUND, "pass.id", f"no pass {external_id!r}.")
    garage_exts, garage_uuids = row[-2] or [], [as_uuid(u) for u in (row[-1] or [])]
    # MEMBERSHIP: the garage asked for is one the pass names
    if as_uuid(garage_uuid) not in garage_uuids:
        cursor.execute(
            "SELECT external_id FROM garages WHERE tenant_id = %s AND id = %s",
            (tenant_uuid, garage_uuid),
        )
        asked = cursor.fetchone()
        raise Refused(
            REFUSAL_PASS_NOT_FOUND, "pass.id",
            f"pass {external_id!r} names garages {sorted(garage_exts)}, not "
            f"{asked[0] if asked else str(garage_uuid)!r}.",
        )
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
        (pass_uuid, label, *_rest, state, garage_exts, _garage_uuids) = row
        return Pass(
            id=external_id, garage_ids=frozenset(garage_exts), label=label, holder=None,
            terms=None, state=State(state), unreadable=refusal.as_unreadable(),
        )


def _readable_pass_from_row(
    cursor: Any, tenant_uuid: UUID, external_id: str, row: tuple
) -> Pass:
    (pass_uuid, label, email, name, phone, valid_from, valid_to, max_stay,
     count, per, entry, exit_, lanes_stated, state, garage_exts, _garage_uuids) = row
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
        # PER GARAGE, as stored; a garage of the set with no lane rows gets no
        # entry, and the Pass refuses that as it refuses it at creation -- the
        # row loads UNREADABLE and still answers (G17)
        cursor.execute(
            "SELECT g.external_id, l.lane FROM pass_lanes l "
            "JOIN garages g ON g.tenant_id = l.tenant_id AND g.id = l.garage_id "
            "WHERE l.tenant_id = %s AND l.pass_id = %s ORDER BY g.external_id, l.lane",
            (tenant_uuid, pass_uuid),
        )
        by_garage: dict[str, set[str]] = {}
        for garage_ext, lane in cursor.fetchall():
            by_garage.setdefault(garage_ext, set()).add(lane)
        lanes = tuple(
            GarageLanes(garage_id=garage_ext, lanes=frozenset(names))
            for garage_ext, names in sorted(by_garage.items())
        )
    directions = set()
    if entry:
        directions.add(Direction.ENTRY)
    if exit_:
        directions.add(Direction.EXIT)
    return Pass(
        id=external_id,
        garage_ids=frozenset(garage_exts),
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


#: THE ONE LOCK ORDER, everywhere a pass or its credentials are written: THE
#: PASS ROW FIRST, then the credential row, then the registrations. A redemption
#: takes it, a state change takes it, so two writers on one pass serialise on
#: the pass row and never meet the other's lock in the other order -- two lock
#: targets in two orders is an ABBA deadlock waiting for its first concurrent
#: day. Written for READ COMMITTED, the store's default (verified, not assumed:
#: SHOW default_transaction_isolation): under it a row read before the lock is a
#: STALE row, so everything the write depends on is re-read AFTER the lock.
LOCK_ORDER = ("passes", "enrolments/holder_links", "vehicle_registrations")


def lock_clause(alias: str | None = None) -> str:
    """The clause that takes a row lock in ``LOCK_ORDER``: ``FOR UPDATE``, or
    ``FOR UPDATE OF alias`` inside a join. ONE place on purpose: the pass lock
    and the credential lock each serialise a same-credential race on their own,
    so a control that removed one would stay green on the other -- the suite
    removes every lock at once through this seam and proves what the locks
    alone hold (G19), with the spend's backstop monkeypatched away."""
    return f"FOR UPDATE OF {alias}" if alias else "FOR UPDATE"


def lock_pass_row(cursor: Any, tenant_id: Any, pass_uuid: UUID) -> None:
    """``SELECT ... FOR UPDATE`` on the pass row: the first lock in
    ``LOCK_ORDER``. Re-entrant within one transaction. A caller that drives
    the store at REPEATABLE READ or SERIALIZABLE meets the database's
    serialization failure here when the row moved under it; that is a named
    refusal in the deadlock's own shape -- the database's DETAIL carried,
    no cause asserted -- never a traceback."""
    refuse_on_lock_failure(
        cursor, f"SELECT 1 FROM passes WHERE tenant_id = %s AND id = %s {lock_clause()}",
        (as_uuid(tenant_id), pass_uuid), "pass", f"pass row {pass_uuid}",
    )


def refuse_on_lock_failure(
    cursor: Any, statement: str, parameters: tuple, field: str, what: str
) -> None:
    """Run a locking statement; a serialization failure or a deadlock the
    database reports while taking the lock is a REFUSAL by name, carrying the
    database's own account verbatim and asserting no cause -- the one shape
    this module already uses for a deadlock at the registration constraint."""
    import psycopg

    try:
        cursor.execute(statement, parameters)
    except (psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected) as failure:
        detail = (failure.diag.message_detail or "").strip()
        primary = (failure.diag.message_primary or "").strip()
        raise Refused(
            REFUSAL_CONSTRAINT, field,
            f"the database would not grant this transaction the lock on {what}: {primary}. "
            "What the other transaction held is not something this module observed; "
            "PostgreSQL's own account: "
            + (detail if detail else "(no DETAIL was supplied)")
            + " Roll back and read again.",
        ) from failure


def change_state(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str, to: State,
    *, by: str, at: datetime, reason: str,
) -> dict:
    """Move a pass, record who/when/why, and -- on revocation -- end its
    registrations on the revocation day in the garage's local calendar.

    Takes ``LOCK_ORDER``: the pass row is locked FIRST and the pass re-read
    under that lock, so the transition is judged on the row as it stands, not
    on a read a concurrent redemption may have moved past; then the
    credentials, then the registrations. A revocation racing a redemption in
    either order therefore leaves no live registration and no issued
    credential on the revoked pass: revoke-first, the redemption re-reads a
    cancelled credential under the lock and refuses by name; redeem-first,
    this write reads the committed registration and ends it."""
    tenant_uuid = as_uuid(tenant_id)
    garage_uuid, garage = load_readable_garage(cursor, tenant_uuid, garage_external_id)
    pass_uuid, _stale = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    lock_pass_row(cursor, tenant_uuid, pass_uuid)
    # re-read under the lock: a check made before the lock is a check on a stale row
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
    cancelled = {"enrolments": 0, "holder_links": 0}
    if to is State.REVOKED:
        today = day_of(at, zone(garage.timezone))
        # LOCK_ORDER, second and third: the credentials, then the registrations
        # -- the pass row is already held above, so no redemption is mid-flight
        # on this pass and a committed one is visible to the statements below.
        #
        # A credential must not outlive the pass it opens (R5): every
        # OUTSTANDING enrolment and holder link on the pass is cancelled here,
        # in the same transaction as the revocation -- by the revoker, at the
        # revocation instant, for the one reason this module cancels anything.
        # Redeemed and already-cancelled ones are terminal and are not touched.
        # This is the revoked branch of set-state, not a second command.
        for table in ("enrolments", "holder_links"):
            cursor.execute(
                f"UPDATE {table} SET state = %s, cancelled_by = %s, cancelled_at = %s, "
                "cancelled_reason = %s WHERE tenant_id = %s AND pass_id = %s AND state = %s",
                (CredentialState.CANCELLED.value, change.changed_by, change.changed_at,
                 CANCELLED_BY_REVOCATION, tenant_uuid, pass_uuid, CredentialState.ISSUED.value),
            )
            cancelled[table] = cursor.rowcount
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
        "enrolments_cancelled": cancelled["enrolments"],
        "holder_links_cancelled": cancelled["holder_links"],
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


def garages_of(cursor: Any, tenant_uuid: UUID, pass_uuid: UUID) -> list[tuple[str, UUID]]:
    """The garages a stored pass names, as (external id, uuid), in external-id
    order -- THE ONE ORDER every fan-out walks, so two writers on one pass
    meet the same garages in the same sequence."""
    cursor.execute(
        "SELECT g.external_id, g.id FROM pass_garages pg "
        "JOIN garages g ON g.tenant_id = pg.tenant_id AND g.id = pg.garage_id "
        "WHERE pg.tenant_id = %s AND pg.pass_id = %s ORDER BY g.external_id",
        (tenant_uuid, pass_uuid),
    )
    return [(ext, as_uuid(uuid)) for ext, uuid in cursor.fetchall()]


def register_vehicle(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str,
    vehicle_identity: str, effective_day: date, end_day: date | None = None,
) -> dict:
    """Bind a vehicle identity to a pass from ``effective_day`` AT EVERY GARAGE
    THE PASS NAMES -- one row per garage, in this one transaction, all or
    none -- refusing by name if another pass holds the identity at any one of
    those garages on any of those days, naming that garage. ``effective_day``
    is the caller's: a redemption passes the local day of the garage the car
    is standing at, and that one day is the registration's day everywhere."""
    tenant_uuid = as_uuid(tenant_id)
    identity = require_text(vehicle_identity, "vehicle_identity")
    garage_uuid, _garage = load_readable_garage(cursor, tenant_uuid, garage_external_id)
    pass_uuid, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    garages = garages_of(cursor, tenant_uuid, pass_uuid)
    # The TARGET pass first, by name. Revoked outranks unreadable here as it
    # does in the access answer: a revoked pass is refused as revoked, and
    # there is nothing about it left to repair.
    if pass_.state not in REGISTRABLE_STATES:
        raise Refused(
            REFUSAL_PASS_NOT_REGISTRABLE, "pass.state",
            f"pass {pass_external_id!r} is {pass_.state.value}; a vehicle may be registered "
            f"onto a pass that is {', '.join(sorted(s.value for s in REGISTRABLE_STATES))}.",
        )
    if pass_.unreadable is not None or pass_.terms is None:
        # Nothing can be registered against terms the module cannot read; the
        # refusal that made the pass unreadable is the refusal here, by name.
        u = pass_.unreadable
        raise Refused(
            u.code if u else REFUSAL_FIELD_BLANK, u.field if u else "pass.terms",
            f"pass {pass_external_id!r} is stored unreadable: {u.detail if u else 'no terms'}",
        )
    last_day = pass_.terms.valid_to
    if effective_state(pass_, effective_day) == EXPIRED:
        # Derived, like everywhere else: the pass's valid_to is before the day
        # this registration would take effect, so it would cover no day.
        raise Refused(
            REFUSAL_PASS_NOT_REGISTRABLE, "pass.state",
            f"pass {pass_external_id!r} is {EXPIRED}: its valid_to {last_day} is before "
            f"effective_day {effective_day}.",
        )
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

    # 1. Refuse by name before anything is written -- AT EVERY GARAGE OF THE
    #    PASS, in one order, before the first row: a car held elsewhere in the
    #    set refuses the whole registration, and a partial fan-out is never an
    #    outcome. An OPEN registration is a holder whatever its pass's state
    #    -- revocation ends registrations, but a row a raw write (or an older
    #    version of this module) left open on a revoked pass is still the row
    #    the EXCLUDE would meet, and it is named here rather than met there. A
    #    registration on a pass whose valid_to has passed before this one
    #    takes effect holds nothing -- expiry is derived -- and is released in
    #    step 2, not named here.
    holders_by_garage = [
        (garage_ext, _holders(cursor, tenant_uuid, uuid, identity, effective_day, end_day))
        for garage_ext, uuid in garages
    ]
    for garage_ext, holders in holders_by_garage:
        for _rid, other, label, state, other_valid_to, other_from, other_end in holders:
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
                f"at garage {garage_ext!r}: {identity!r} is registered to pass {other!r} "
                f"({label}, {state}) from {other_from}, and that registration {ends}.",
            )

    # 2. Release what expiry has already freed, at every garage.
    for _garage_ext, holders in holders_by_garage:
        for rid, _other, _label, _state, other_valid_to, _from, other_end in holders:
            if other_end is None and other_valid_to is not None and other_valid_to < effective_day:
                cursor.execute(
                    "UPDATE vehicle_registrations SET end_day = GREATEST(%s, effective_day), "
                    "ended_reason = %s WHERE tenant_id = %s AND id = %s",
                    (other_valid_to + timedelta(days=1), ENDED_BY_EXPIRY, tenant_uuid, rid),
                )

    # 3. Write -- ONE ROW PER GARAGE OF THE PASS -- with the constraint as the
    #    backstop for a race at each. A violation at any garage aborts the
    #    transaction, and with it every row of the fan-out written before it.
    import psycopg

    for garage_ext, uuid in garages:
        try:
            cursor.execute(
                "INSERT INTO vehicle_registrations (tenant_id, garage_id, pass_id, "
                "vehicle_identity, effective_day, end_day, ended_reason) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (tenant_uuid, uuid, pass_uuid, identity, effective_day, end_day,
                 ENDED_BY_OWNER if end_day is not None else None),
            )
        except psycopg.errors.ExclusionViolation as violation:
            raise Refused(
                REFUSAL_CONSTRAINT, "vehicle_identity",
                f"constraint {violation.diag.constraint_name}: another registration of "
                f"{identity!r} at garage {garage_ext!r} landed first. Roll back and read again.",
            ) from violation
        except psycopg.errors.DeadlockDetected as deadlock:
            # The other shape a race at the EXCLUDE takes: each writer's INSERT
            # waits on the other's in-progress row and the database rolls one of
            # them back. Measured on the L3's 120-round probe: 0 in 120 on two
            # clusters, 1-3 in 120 on a third -- a timing property, and it reached
            # the caller as a traceback. The advice is the same as the constraint's.
            #
            # WHAT THIS SENTENCE SAYS IS ONLY WHAT THIS MODULE OBSERVED: its INSERT
            # was the writer the database rolled back. It does NOT say what the
            # other side of the cycle was. Measured before this: it said "two
            # registrations raced", and under a deadlock from a lock this module
            # never takes (a raw SELECT ... FOR UPDATE on the pass's row, by
            # another transaction) that sentence was false and PostgreSQL's own
            # DETAIL -- the one line that names the cycle -- was thrown away. The
            # DETAIL is carried now, verbatim, and no cause is asserted.
            detail = (deadlock.diag.message_detail or "").strip()
            raise Refused(
                REFUSAL_CONSTRAINT, "vehicle_identity",
                f"constraint {ONE_PASS_PER_GARAGE}: the database detected a deadlock while this "
                f"registration of {identity!r} waited on another transaction, and rolled this "
                "write back. What the other transaction held is not something this module "
                "observed; PostgreSQL's own account of the cycle: "
                + (detail if detail else "(no DETAIL was supplied)")
                + " Roll back and read again.",
            ) from deadlock
    return {
        "pass": pass_external_id, "vehicle_identity": identity,
        "garages": [garage_ext for garage_ext, _uuid in garages],
        "effective_day": effective_day, "end_day": end_day,
        "bounded_by_valid_to": last_day if end_day is None else None,
    }


def end_registration(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str,
    vehicle_identity: str, end_day: date,
) -> dict:
    """End a registration on a day -- AT EVERY GARAGE THE PASS NAMES, since the
    registration was written at every one. The identity is free FROM that day
    everywhere the pass answers. The registration is the latest one of this
    identity on this pass (one effective day, one row per garage)."""
    tenant_uuid = as_uuid(tenant_id)
    identity = require_text(vehicle_identity, "vehicle_identity")
    garage_uuid, _garage = load_readable_garage(cursor, tenant_uuid, garage_external_id)
    pass_uuid, _pass = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    cursor.execute(
        "SELECT r.id, r.effective_day, r.end_day, g.external_id FROM vehicle_registrations r "
        "JOIN garages g ON g.tenant_id = r.tenant_id AND g.id = r.garage_id "
        "WHERE r.tenant_id = %s AND r.pass_id = %s AND r.vehicle_identity = %s "
        "ORDER BY r.effective_day DESC, g.external_id",
        (tenant_uuid, pass_uuid, identity),
    )
    rows = cursor.fetchall()
    if not rows:
        raise Refused(
            REFUSAL_REGISTRATION_NOT_FOUND, "vehicle_identity",
            f"{identity!r} on pass {pass_external_id!r}.",
        )
    _rid, effective, current_end, _garage_ext = rows[0]
    latest = [row for row in rows if row[1] == effective]
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
        "WHERE tenant_id = %s AND id = ANY(%s) AND end_day IS NULL",
        (end_day, ENDED_BY_OWNER, tenant_uuid, [rid for rid, *_rest in latest]),
    )
    return {"pass": pass_external_id, "vehicle_identity": identity, "end_day": end_day,
            "garages": [garage_ext for *_rest, garage_ext in latest]}


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


def _open_visit(
    cursor: Any, tenant_uuid: UUID, garage_uuid: UUID, pass_uuid: UUID, identity: str,
) -> tuple | None:
    """The still-open recorded entry of this vehicle on this pass AT THIS
    GARAGE. Keyed on the garage, deliberately: the ledger is per garage, and
    a pass now names a set of them. Measured before this (the G3a L3): with
    the garage left out, an exit recorded at garage B closed the visit opened
    at garage A and wrote B's lane onto A's row, and an entry at B was refused
    for a visit still open at A. ``visits_on`` reads by PASS across the set
    on purpose -- the allowance is one set of terms (C5) -- and stays so."""
    cursor.execute(
        "SELECT id, entered_at FROM visits WHERE tenant_id = %s AND garage_id = %s "
        "AND pass_id = %s AND vehicle_identity = %s AND exited_at IS NULL",
        (tenant_uuid, garage_uuid, pass_uuid, identity),
    )
    return cursor.fetchone()


def record_entry(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str,
    vehicle_identity: str, lane: str, at: datetime,
) -> dict:
    tenant_uuid = as_uuid(tenant_id)
    identity = require_text(vehicle_identity, "vehicle_identity")
    require_aware(at, "at")
    garage_uuid, _garage = load_readable_garage(cursor, tenant_uuid, garage_external_id)
    pass_uuid, _pass = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    open_ = _open_visit(cursor, tenant_uuid, garage_uuid, pass_uuid, identity)
    if open_ is not None:
        raise Refused(
            REFUSAL_VISIT_ALREADY_OPEN, "vehicle_identity",
            f"{identity!r} entered garage {garage_external_id!r} on pass {pass_external_id!r} "
            f"at {open_[1].isoformat()} and has no recorded exit.",
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
    garage_uuid, _garage = load_readable_garage(cursor, tenant_uuid, garage_external_id)
    pass_uuid, _pass = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    open_ = _open_visit(cursor, tenant_uuid, garage_uuid, pass_uuid, identity)
    if open_ is None:
        raise Refused(
            REFUSAL_NO_OPEN_VISIT, "vehicle_identity",
            f"{identity!r} on pass {pass_external_id!r} at garage {garage_external_id!r}.",
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
