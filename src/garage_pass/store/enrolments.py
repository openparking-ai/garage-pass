"""Issuing and redeeming the one-time credentials: the enrolment (the QR) and
the holder link. The store half of ``garage_pass.enrolment``.

Every function takes a cursor already inside a tenant's context and never
commits: the caller owns the transaction, as everywhere in this store.

**THE TOKEN IS RETURNED EXACTLY ONCE, BY THE ISSUE CALL, AND BY NOTHING ELSE.**
``issue_enrolment`` and ``issue_holder_link`` return the plaintext in their
result; the row holds the SHA-256 and nothing that yields the plaintext; no
read, no listing and no refusal detail carries it. A test issues tokens and
scans every column of every table in the catalogue for the plaintext, with the
digest as the positive control.

**ONE CREDENTIAL, ONE SPEND, AND THE LOCK ORDER THAT MAKES IT SO.** Two
lanes presenting one token at the same instant were measured, before this was
written, BOTH redeeming: two registrations for two cars, the row recording the
last writer, no refusal and no traceback -- a silent wrong answer on the whole
security property of the QR. The read and the write had nothing between them.
Now the credential is read unlocked ONLY to learn which pass it belongs to;
then the PASS ROW is locked, then the CREDENTIAL ROW (``records.LOCK_ORDER``:
one order everywhere, because two lock targets in two orders is an ABBA
deadlock waiting for its first concurrent day), and EVERYTHING the write
depends on is re-read and re-validated UNDER those locks -- the credential's
state and expiry, the pass's registrability -- because at READ COMMITTED (the
store's default, verified and not assumed) a check made before the lock is a
check made on a stale row. That is the PRIMARY: it is what makes the loser
refuse by name with the right sentence. The BACKSTOP is the spend itself:
``UPDATE ... WHERE ... AND state = 'issued'`` asserting ROWCOUNT 1 -- 0 rows
means another lane spent it, and that is the named refusal, never a silent
success. It catches a future caller that skips the lock. The two overlap, and
each would mask the removal of the other, so THE SUITE MEASURES EACH WITH THE
OTHER REMOVED (G19): the backstop's test runs with the lock monkeypatched
away, the lock's test with the predicate monkeypatched away. A caller driving
the store at REPEATABLE READ or SERIALIZABLE meets the database's
serialization failure at the lock; it is rendered as the named refusal the
deadlock already has (``records.refuse_on_lock_failure``), one shape, not two.

**A REDEMPTION IS ONE TRANSACTION -- ALL FOUR WRITES OR NONE**: the
registration (effective on the garage's local day of the instant), the pass's
move to ``active`` where it was not already (recorded, with the enrolment as
the actor), the enrolment marked redeemed with the identity, lane, direction
and instant, and the access answer for that same movement -- produced by
calling ``store.access.answer_in_transaction``, the module's own access path,
never a second implementation. The writes sit under a SAVEPOINT that is
rolled back on EVERY exception -- a refusal, the module's own by name or the
database's constraint as the backstop for a race, is then carried in the
answer; anything else is re-raised AFTER the rollback, so a defect SURFACES
and still writes nothing. Measured before this was written: only ``Refused``
rolled it back, and a planted programming error after the registration left
the registration live and the credential issued in the caller's transaction --
committed, a QR that worked twice. A rollback that also swallowed the defect
would be the same wrong answer in a new costume, so both halves are held at
once: it surfaces, and nothing persists.

**THE REDEMPTION CALL ALWAYS RETURNS AN ACCESS ANSWER FOR THE MOVEMENT,
INCLUDING WHEN THE REDEMPTION ITSELF IS REFUSED.** A lane asked a question and
must be told something it can act on, so ``Redemption`` carries two things:
what happened to the enrolment (redeemed, or the named refusal) and what the
lane does now. A refused redemption at an exit still answers, and the exit is
never refused (G4): a redemption refusal is a refusal to BIND, never a refusal
to LEAVE.

**THE ORDER OF THE REFUSALS IS PART OF THE CONTRACT**, and every one writes
nothing: the garage (unreadable; then where it enrols, ``transient_available``
before ``enrols_at``; then the wrong end); the credential (unknown; at another
garage; then, under the locks, already used; cancelled; not yet started;
expired -- derived in the garage's local day); the pass (not registrable:
suspended, revoked or expired, naming the state; unreadable, naming the
field); the lane outside the pass's stated lane set, naming the lane and the
set; then the DIRECTION outside the pass's terms -- the lane check stays
first, so a movement that is both wrong-lane and wrong-direction keeps the
answer that was measured before the direction refusal existed; the identity
(blank; already on another pass at this garage, by name, before the EXCLUDE).
The first thing that fails is the refusal; nothing after it is evaluated.

**ONLY A STRUCTURAL EXCLUSION REFUSES THE BIND.** A pass whose terms allow no
movement in the direction this garage enrols at would spend the QR on a
movement it can never cover, so that is refused by name and the credential
stays issued (nothing was written; it expires by derivation like any other).
Temporal non-coverage BINDS: a weekend on a Mon-Fri pass, a ``valid_from``
still ahead, a movement outside the hours -- an employee enrolling at the
weekend is the ordinary case, and a refusal there would be worse than the
defect. The suite holds both sides (G19).

**THE HOLDER LINK WRITES ``holder_name`` AND ``holder_phone`` ON THE PASS AND
NOTHING ELSE** -- not the email, not the label, not the terms, not the state,
not the garage. A credential that arrives by email must not be able to rewrite
the terms of the pass it opens; a test compares every other column of the row
before and after. Then it issues an enrolment for that pass, with the link as
the issuer, and is spent. **The owner-only path stands**: an owner issues an
enrolment without the holder ever using a link; the link exists for the
holder's own self-service, not as a gate on enrolment.

**NO EMAIL IS SENT.** This module has no network and no third-party service:
it mints a credential and records that it was issued; delivering it -- email,
SMS, print -- is the integrator's. **NO QR IMAGE**: the payload string is
returned, and rendering a bitmap is the client's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from garage_pass.access import Answer
from garage_pass.enrolment import (
    EXPIRED_CREDENTIAL,
    Credential,
    CredentialState,
    MintedToken,
    digest,
    last_day,
    mint,
    require_days_valid,
    token_of,
    where_enrolment_happens,
)
from garage_pass.findings import (
    REFUSAL_CONSTRAINT,
    REFUSAL_CREDENTIAL_ALREADY_EXISTS,
    REFUSAL_CREDENTIAL_ALREADY_USED,
    REFUSAL_CREDENTIAL_CANCELLED,
    REFUSAL_CREDENTIAL_EXPIRED,
    REFUSAL_CREDENTIAL_NOT_STARTED,
    REFUSAL_CREDENTIAL_UNKNOWN,
    REFUSAL_DIRECTION_OUTSIDE_THE_PASS_TERMS,
    REFUSAL_ENROLMENT_AT_WRONG_END,
    REFUSAL_FIELD_BLANK,
    REFUSAL_GARAGE_MISMATCH,
    REFUSAL_LANE_OUTSIDE_THE_PASS_TERMS,
    REFUSAL_PASS_NOT_REGISTRABLE,
    Refused,
)
from garage_pass.garage import require_text
from garage_pass.localday import day_of, require_aware, zone
from garage_pass.passes import EXPIRED, Pass, State
from garage_pass.states import effective_state
from garage_pass.store.access import answer_in_transaction
from garage_pass.store.records import (
    REGISTRABLE_STATES,
    as_uuid,
    change_state,
    load_garage,
    load_pass,
    load_readable_garage,
    lock_clause,
    lock_pass_row,
    refuse_on_lock_failure,
    register_vehicle,
)
from garage_pass.terms import Direction

ENROLMENT = "enrolment"
HOLDER_LINK = "holder_link"
_TABLE = {ENROLMENT: "enrolments", HOLDER_LINK: "holder_links"}
#: The typed states a credential may be issued onto: a pass that takes a
#: registration. A revoked pass is revoked; a suspended one is a hold.
ISSUABLE_STATES = REGISTRABLE_STATES
#: The savepoint every redemption's writes sit under.
SAVEPOINT = "garage_pass_redemption"


@dataclass(frozen=True)
class Redemption:
    """What a lane is told after presenting a QR: what happened to the
    enrolment, and the access answer for the movement -- always the latter."""

    #: The enrolment's external id, once the token matched one; None before.
    enrolment: str | None
    redeemed: bool
    #: The named refusal when ``redeemed`` is False. Nothing was written.
    refusal: Refused | None
    #: The registration written, when redeemed.
    registration: dict | None
    #: The pass's move to active, when redeemed and the pass was not already
    #: active: a pass already active takes no transition.
    pass_state_change: dict | None
    #: The access answer for this same movement, from the module's own access
    #: path -- on the rows as written, or as they stood when refused.
    answer: Answer


def _require_day(value: object, field: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{field} must be a date, not {value!r}")
    return value


def _issuable_pass(
    cursor: Any, tenant_uuid: UUID, garage_uuid: UUID, pass_external_id: str, on: date,
    what: str,
) -> tuple[UUID, Pass]:
    """The pass a credential is issued onto, or a refusal by name: revoked and
    suspended by their state, unreadable by the field, expired -- derived from
    its valid_to against the day the credential starts -- by name. Judged on
    the pass row LOCKED and re-read (``LOCK_ORDER``, first): measured without
    it, an issue racing a revocation read a registrable pass, the revocation
    cancelled nothing (the row was not yet there), and an ISSUED credential
    stood on a revoked pass -- the credential that outlives the pass R5
    forbids. Under the lock the issue waits, re-reads REVOKED and refuses."""
    pass_uuid, _stale = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    lock_pass_row(cursor, tenant_uuid, pass_uuid)
    pass_uuid, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    _refuse_unless_registrable(pass_, pass_external_id, on, what)
    return pass_uuid, pass_


def _refuse_unless_registrable(pass_: Pass, pass_external_id: str, on: date, what: str) -> None:
    if pass_.state not in REGISTRABLE_STATES:
        raise Refused(
            REFUSAL_PASS_NOT_REGISTRABLE, "pass.state",
            f"pass {pass_external_id!r} is {pass_.state.value}; {what} needs a pass that is "
            f"{', '.join(sorted(s.value for s in REGISTRABLE_STATES))}.",
        )
    if pass_.unreadable is not None or pass_.terms is None:
        u = pass_.unreadable
        raise Refused(
            u.code if u else REFUSAL_FIELD_BLANK, u.field if u else "pass.terms",
            f"pass {pass_external_id!r} is stored unreadable: {u.detail if u else 'no terms'}",
        )
    if effective_state(pass_, on) == EXPIRED:
        raise Refused(
            REFUSAL_PASS_NOT_REGISTRABLE, "pass.state",
            f"pass {pass_external_id!r} is {EXPIRED} on {on}: its valid_to "
            f"{pass_.terms.valid_to} is before it.",
        )


def _insert(
    cursor: Any, kind: str, tenant_uuid: UUID, pass_uuid: UUID, external_id: str,
    minted: MintedToken, starts_on: date, days_valid: int, by: str, at: datetime,
    vehicle_description: str | None,
) -> None:
    table = _TABLE[kind]
    cursor.execute(
        f"SELECT 1 FROM {table} WHERE tenant_id = %s AND external_id = %s",
        (tenant_uuid, external_id),
    )
    if cursor.fetchone():
        raise Refused(REFUSAL_CREDENTIAL_ALREADY_EXISTS, f"{kind}.id", f"{kind} {external_id!r}.")
    import psycopg

    columns = ("tenant_id, pass_id, external_id, token_sha256, starts_on, days_valid, issued_by, "
               "issued_at, state")
    values = [tenant_uuid, pass_uuid, external_id, minted.sha256, starts_on, days_valid, by, at,
              CredentialState.ISSUED.value]
    if kind == ENROLMENT:
        columns += ", vehicle_description"
        values.append(vehicle_description)
    try:
        cursor.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({', '.join('%s' for _ in values)})",
            values,
        )
    except psycopg.errors.UniqueViolation as violation:
        raise Refused(
            REFUSAL_CONSTRAINT, f"{kind}.id",
            f"constraint {violation.diag.constraint_name}: another {kind} landed first. "
            "Roll back and read again.",
        ) from violation


def _issued(
    kind: str, external_id: str, pass_external_id: str, minted: MintedToken, starts_on: date,
    days_valid: int, by: str, at: datetime, vehicle_description: str | None,
) -> dict:
    """THE ONE PLACE THE PLAINTEXT IS RETURNED. The token and the payload the
    QR carries, beside what was recorded about the credential."""
    out = {
        kind: external_id, "pass": pass_external_id, "token": minted.token,
        "payload": minted.payload, "starts_on": starts_on, "days_valid": days_valid,
        "last_day": last_day(starts_on, days_valid), "issued_by": by, "issued_at": at,
        "state": CredentialState.ISSUED.value,
    }
    if kind == ENROLMENT:
        out["vehicle_description"] = vehicle_description
    return out


def issue_enrolment(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str,
    external_id: str, starts_on: date, days_valid: object, *, by: str, at: datetime,
    vehicle_description: str | None = None,
) -> dict:
    """Mint the QR for a pass: a token returned once, its digest stored.
    ``days_valid`` is STATED -- ``None`` is refused by name, never defaulted."""
    tenant_uuid = as_uuid(tenant_id)
    external_id = require_text(external_id, "enrolment.id")
    days = require_days_valid(days_valid)
    _require_day(starts_on, "starts_on")
    require_aware(at, "issued_at")
    by = require_text(by, "issued_by")
    description = (
        None if vehicle_description is None
        else require_text(vehicle_description, "vehicle_description")
    )
    garage_uuid, _garage = load_readable_garage(cursor, tenant_uuid, garage_external_id)
    pass_uuid, _pass = _issuable_pass(cursor, tenant_uuid, garage_uuid, pass_external_id,
                                      starts_on, "an enrolment")
    minted = mint()
    _insert(cursor, ENROLMENT, tenant_uuid, pass_uuid, external_id, minted, starts_on, days, by,
            at, description)
    return _issued(ENROLMENT, external_id, pass_external_id, minted, starts_on, days, by, at,
                   description)


def issue_holder_link(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str,
    external_id: str, starts_on: date, days_valid: object, *, by: str, at: datetime,
) -> dict:
    """Mint the one-time link for a pass's holder: the same primitive as the
    enrolment, scoped to that pass, carrying no email of its own (the holder's
    email is on the pass). Delivering it is the integrator's."""
    tenant_uuid = as_uuid(tenant_id)
    external_id = require_text(external_id, "holder_link.id")
    days = require_days_valid(days_valid)
    _require_day(starts_on, "starts_on")
    require_aware(at, "issued_at")
    by = require_text(by, "issued_by")
    garage_uuid, _garage = load_readable_garage(cursor, tenant_uuid, garage_external_id)
    pass_uuid, _pass = _issuable_pass(cursor, tenant_uuid, garage_uuid, pass_external_id,
                                      starts_on, "a holder link")
    minted = mint()
    _insert(cursor, HOLDER_LINK, tenant_uuid, pass_uuid, external_id, minted, starts_on, days, by,
            at, None)
    return _issued(HOLDER_LINK, external_id, pass_external_id, minted, starts_on, days, by, at,
                   None)


_COLUMNS = ("c.id, c.pass_id, p.garage_id, p.external_id, c.external_id, c.starts_on, "
            "c.days_valid, c.state, c.issued_by, c.issued_at, c.redeemed_at, c.cancelled_at, "
            "c.cancelled_reason")


def _credential_from_row(kind: str, row: tuple) -> tuple[UUID, UUID, UUID, Credential]:
    (uuid, pass_uuid, garage_uuid, pass_ext, ext, starts_on, days_valid, state, issued_by,
     issued_at, redeemed_at, cancelled_at, cancelled_reason, *rest) = row
    credential = Credential(
        kind=kind, id=ext, pass_id=pass_ext, starts_on=starts_on, days_valid=days_valid,
        state=CredentialState(state), issued_by=issued_by, issued_at=issued_at,
        vehicle_description=rest[0] if rest else None, redeemed_at=redeemed_at,
        cancelled_at=cancelled_at, cancelled_reason=cancelled_reason,
    )
    return as_uuid(uuid), as_uuid(pass_uuid), as_uuid(garage_uuid), credential


def _select(kind: str, where: str) -> str:
    extra = ", c.vehicle_description" if kind == ENROLMENT else ""
    return (
        f"SELECT {_COLUMNS}{extra} FROM {_TABLE[kind]} c "
        "JOIN passes p ON p.tenant_id = c.tenant_id AND p.id = c.pass_id "
        f"WHERE c.tenant_id = %s AND {where}"
    )


def _by_token(
    cursor: Any, kind: str, tenant_uuid: UUID, presented: str
) -> tuple[UUID, UUID, UUID, Credential]:
    """The credential whose digest matches the token presented, or a refusal
    that names neither the token nor whether any credential exists."""
    cursor.execute(_select(kind, "c.token_sha256 = %s"), (tenant_uuid, digest(token_of(presented))))
    row = cursor.fetchone()
    if row is None:
        raise Refused(
            REFUSAL_CREDENTIAL_UNKNOWN, "token",
            f"no {kind} in this tenant matches the token presented.",
        )
    return _credential_from_row(kind, row)


def _lock_credential(
    cursor: Any, kind: str, tenant_uuid: UUID, uuid: UUID
) -> tuple[UUID, UUID, UUID, Credential]:
    """THE PRIMARY, second half of ``LOCK_ORDER``: the credential row locked
    (``FOR UPDATE OF c``: the pass row is already held) and RE-READ under
    that lock. What the caller read before the lock was only the pass to
    lock; the state the write depends on is this row."""
    refuse_on_lock_failure(
        cursor, f"{_select(kind, 'c.id = %s')} {lock_clause('c')}", (tenant_uuid, uuid), kind,
        f"{kind} row {uuid}",
    )
    row = cursor.fetchone()
    if row is None:  # pragma: no cover - the row was read an instant ago and rows are never deleted
        raise Refused(REFUSAL_CREDENTIAL_UNKNOWN, kind, f"no {kind} row {uuid} any more.")
    return _credential_from_row(kind, row)


def _spend(cursor: Any, kind: str, tenant_uuid: UUID, uuid: UUID, assignments: str,
           values: tuple) -> None:
    """THE BACKSTOP: the spend carries ``AND state = 'issued'`` and asserts
    ROWCOUNT 1. Zero rows means the credential was no longer issued when this
    lane wrote -- another lane spent it, or a revocation cancelled it -- and
    that is the named refusal, never a silent success. It is what catches a
    caller that reaches this write without the lock above."""
    cursor.execute(
        f"UPDATE {_TABLE[kind]} SET state = %s, {assignments} "
        "WHERE tenant_id = %s AND id = %s AND state = %s",
        (CredentialState.REDEEMED.value, *values, tenant_uuid, uuid,
         CredentialState.ISSUED.value),
    )
    if cursor.rowcount != 1:
        raise Refused(
            REFUSAL_CREDENTIAL_ALREADY_USED, kind,
            f"the {kind} was no longer issued when this lane wrote it: {cursor.rowcount} row(s) "
            "matched state 'issued'. Another lane spent it, or it was cancelled, between this "
            "lane's read and its write. Roll back and read again.",
        )


def load_credential(cursor: Any, tenant_id: Any, kind: str, external_id: str) -> Credential:
    """A credential by its id, as recorded -- never the token. A read yields
    no working QR."""
    cursor.execute(_select(kind, "c.external_id = %s"), (as_uuid(tenant_id), external_id))
    row = cursor.fetchone()
    if row is None:
        raise Refused(REFUSAL_CREDENTIAL_UNKNOWN, f"{kind}.id", f"no {kind} {external_id!r}.")
    return _credential_from_row(kind, row)[3]


def _refuse_unless_redeemable(kind: str, credential: Credential, today: date) -> None:
    state = credential.state_on(today)
    if state == CredentialState.REDEEMED.value:
        raise Refused(
            REFUSAL_CREDENTIAL_ALREADY_USED, kind,
            f"{kind} {credential.id!r} was redeemed at {credential.redeemed_at.isoformat()}.",
        )
    if state == CredentialState.CANCELLED.value:
        raise Refused(
            REFUSAL_CREDENTIAL_CANCELLED, kind,
            f"{kind} {credential.id!r} was cancelled at {credential.cancelled_at.isoformat()}: "
            f"{credential.cancelled_reason}.",
        )
    if today < credential.starts_on:
        raise Refused(
            REFUSAL_CREDENTIAL_NOT_STARTED, kind,
            f"{kind} {credential.id!r} starts on {credential.starts_on}; today is {today} in "
            "the garage's local day.",
        )
    if state == EXPIRED_CREDENTIAL:
        raise Refused(
            REFUSAL_CREDENTIAL_EXPIRED, kind,
            f"{kind} {credential.id!r} started on {credential.starts_on} for "
            f"{credential.days_valid} day(s), so its last day was {credential.last_day}; today "
            f"is {today} in the garage's local day.",
        )


def redeem_enrolment(
    cursor: Any, tenant_id: Any, garage_external_id: str, presented: str,
    vehicle_identity: str, lane: str, direction: Direction, at: datetime,
) -> Redemption:
    """THE LANE BIND. See the module docstring for the lock order, the
    atomicity and the answer that is always returned. A garage that does not
    exist is the one refusal raised rather than carried: there is no lane to
    answer."""
    tenant_uuid = as_uuid(tenant_id)
    require_aware(at, "at")
    if not isinstance(direction, Direction):
        raise TypeError(f"direction must be a Direction, not {direction!r}")
    garage_uuid, garage = load_garage(cursor, tenant_uuid, garage_external_id)
    enrolment_id: str | None = None
    registration: dict | None = None
    change: dict | None = None
    refusal: Refused | None = None
    cursor.execute(f"SAVEPOINT {SAVEPOINT}")
    try:
        # everything below the savepoint is taken back on EVERY exception (X2):
        # a Refused is carried in the answer; anything else is re-raised after
        # the rollback, so a defect surfaces AND nothing persists
        if garage.unreadable is not None:
            u = garage.unreadable
            raise Refused(
                u.code, u.field,
                f"garage {garage_external_id!r} is stored unreadable: {u.detail} Repair it "
                "with set-garage-timezone before a QR can be redeemed there.",
            )
        end = where_enrolment_happens(garage)
        if direction.value != end:
            raise Refused(
                REFUSAL_ENROLMENT_AT_WRONG_END, "garage.enrols_at",
                f"garage {garage_external_id!r} enrols at {end}; this lane ({lane!r}) is an "
                f"{direction.value}.",
            )
        # read UNLOCKED, only to learn which pass this credential belongs to
        uuid, pass_uuid, pass_garage_uuid, glimpse = _by_token(
            cursor, ENROLMENT, tenant_uuid, presented,
        )
        enrolment_id = glimpse.id
        if pass_garage_uuid != garage_uuid:
            raise Refused(
                REFUSAL_GARAGE_MISMATCH, "garage",
                f"enrolment {glimpse.id!r} belongs to pass {glimpse.pass_id!r}, which is "
                f"not at garage {garage_external_id!r}.",
            )
        # LOCK_ORDER: the pass row first, then the credential row -- then every
        # check below is made on rows re-read UNDER the locks, never on the glimpse
        lock_pass_row(cursor, tenant_uuid, pass_uuid)
        uuid, pass_uuid, _same_garage, enrolment = _lock_credential(
            cursor, ENROLMENT, tenant_uuid, uuid,
        )
        today = day_of(at, zone(garage.timezone))
        _refuse_unless_redeemable(ENROLMENT, enrolment, today)
        _pass_uuid, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, enrolment.pass_id)
        _refuse_unless_registrable(pass_, enrolment.pass_id, today, "a redemption")
        assert pass_.terms is not None
        lane_name = require_text(lane, "lane")
        if pass_.terms.allowed_lanes is not None and lane_name not in pass_.terms.allowed_lanes:
            raise Refused(
                REFUSAL_LANE_OUTSIDE_THE_PASS_TERMS, "lane",
                f"pass {enrolment.pass_id!r} allows lanes {sorted(pass_.terms.allowed_lanes)}, "
                f"not {lane_name!r}.",
            )
        # the direction AFTER the lane, deliberately: the lane check was measured
        # first before this refusal existed, and a movement that is both keeps
        # that answer. STRUCTURAL only -- a window, a valid_from ahead or spent
        # allowance is temporal and still binds (see the module docstring).
        if direction not in pass_.terms.directions:
            raise Refused(
                REFUSAL_DIRECTION_OUTSIDE_THE_PASS_TERMS, "direction",
                f"pass {enrolment.pass_id!r} allows directions "
                f"{sorted(d.value for d in pass_.terms.directions)}, and this garage enrols at "
                f"{direction.value}: the pass can never cover the movement the QR would be "
                "spent on.",
            )
        identity = require_text(vehicle_identity, "vehicle_identity")
        # 1. the registration -- one car, one pass, refused by name before the
        #    EXCLUDE has to; effective on the garage's local day of this instant
        registration = register_vehicle(
            cursor, tenant_uuid, garage_external_id, enrolment.pass_id, identity, today,
        )
        # 2. the pass to active, recorded, the enrolment as the actor -- unless it
        #    already is: the ordinary case for a second car on a pooled pass
        if pass_.state is not State.ACTIVE:
            change = change_state(
                cursor, tenant_uuid, garage_external_id, enrolment.pass_id, State.ACTIVE,
                by=enrolment.id, at=at, reason=f"redeemed at lane {lane_name!r}",
            )
        # 3. the enrolment redeemed: the identity, lane, direction and instant --
        #    the spend, with its backstop predicate and rowcount
        _spend(
            cursor, ENROLMENT, tenant_uuid, uuid,
            "redeemed_vehicle_identity = %s, redeemed_lane = %s, redeemed_direction = %s, "
            "redeemed_at = %s",
            (identity, lane_name, direction.value, at),
        )
        cursor.execute(f"RELEASE SAVEPOINT {SAVEPOINT}")
    except Refused as refused:
        # Nothing written -- the module's own refusal or the database's backstop
        # alike: the savepoint takes every write back and the transaction goes on.
        cursor.execute(f"ROLLBACK TO SAVEPOINT {SAVEPOINT}")
        refusal = refused
        registration = change = None
    except BaseException:
        # A defect, a driver error the store did not name, an interrupt: the
        # savepoint takes every write back FIRST, then it surfaces unchanged.
        # Nothing persists, and nothing is swallowed.
        cursor.execute(f"ROLLBACK TO SAVEPOINT {SAVEPOINT}")
        registration = change = None
        raise
    # 4. the access answer for this same movement, from the module's own access
    #    path -- on the rows as written, or as they stood when the bind was refused
    answer = answer_in_transaction(
        cursor, tenant_uuid, garage_external_id, vehicle_identity, lane, direction, at,
    )
    return Redemption(
        enrolment=enrolment_id, redeemed=refusal is None, refusal=refusal,
        registration=registration, pass_state_change=change, answer=answer,
    )


#: The two columns a holder link may write on the pass, and no other.
HOLDER_WRITES = ("holder_name", "holder_phone")


def redeem_holder_link(
    cursor: Any, tenant_id: Any, garage_external_id: str, presented: str, *,
    name: str, phone: str, enrolment_external_id: str, starts_on: date, days_valid: object,
    at: datetime, vehicle_description: str | None = None,
) -> dict:
    """THE HOLDER'S OWN DETAILS, then their QR -- one transaction. The link
    is checked (unknown, used, cancelled, not started, expired -- in the
    garage's local day), the pass must take a registration, the holder's name
    and phone are written onto the pass -- THOSE TWO COLUMNS AND NOTHING ELSE
    -- an enrolment is issued with the link as the issuer, and the link is
    spent. The enrolment's token is returned once, here."""
    tenant_uuid = as_uuid(tenant_id)
    require_aware(at, "at")
    holder_name = require_text(name, "holder.name")
    holder_phone = require_text(phone, "holder.phone")
    garage_uuid, garage = load_readable_garage(cursor, tenant_uuid, garage_external_id)
    # read UNLOCKED, only to learn which pass this link belongs to
    uuid, pass_uuid, pass_garage_uuid, glimpse = _by_token(
        cursor, HOLDER_LINK, tenant_uuid, presented,
    )
    if pass_garage_uuid != garage_uuid:
        raise Refused(
            REFUSAL_GARAGE_MISMATCH, "garage",
            f"holder link {glimpse.id!r} belongs to pass {glimpse.pass_id!r}, which is not at "
            f"garage {garage_external_id!r}.",
        )
    # LOCK_ORDER: the pass row first, then the link row; then re-read under them
    lock_pass_row(cursor, tenant_uuid, pass_uuid)
    uuid, pass_uuid, _same_garage, link = _lock_credential(cursor, HOLDER_LINK, tenant_uuid, uuid)
    today = day_of(at, zone(garage.timezone))
    _refuse_unless_redeemable(HOLDER_LINK, link, today)
    _pass_uuid, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, link.pass_id)
    _refuse_unless_registrable(pass_, link.pass_id, today, "a holder link")
    # THE NARROW WRITE: the holder's name and phone, on the pass, nothing else.
    cursor.execute(
        f"UPDATE passes SET {HOLDER_WRITES[0]} = %s, {HOLDER_WRITES[1]} = %s "
        "WHERE tenant_id = %s AND id = %s",
        (holder_name, holder_phone, tenant_uuid, pass_uuid),
    )
    issued = issue_enrolment(
        cursor, tenant_uuid, garage_external_id, link.pass_id, enrolment_external_id, starts_on,
        days_valid, by=link.id, at=at, vehicle_description=vehicle_description,
    )
    _spend(cursor, HOLDER_LINK, tenant_uuid, uuid, "redeemed_at = %s", (at,))
    return {
        HOLDER_LINK: link.id, "pass": link.pass_id, "holder_name": holder_name,
        "holder_phone": holder_phone, "redeemed_at": at, "enrolment": issued,
    }
