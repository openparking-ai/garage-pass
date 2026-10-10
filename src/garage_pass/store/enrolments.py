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

**A CREDENTIAL CARRIES NO GARAGE OF ITS OWN; IT DERIVES THE SET FROM ITS
PASS.** A pass names a set of garages, and a QR or a holder link of it may be
redeemed at any garage of that set and at no other: the comparison at both
doors is MEMBERSHIP -- this garage is one of the pass's garages -- refused by
name otherwise (``REFUSAL_GARAGE_MISMATCH``), naming the garage asked for, the
pass and its set. A redemption then writes ONE REGISTRATION ROW PER GARAGE OF
THE PASS, through ``records.register_vehicle``, inside the same transaction,
after the locks, never before them: all or none, and a car held by another
pass at any garage of the set refuses the whole redemption by name.

**THE ORDER OF THE REFUSALS IS PART OF THE CONTRACT**, and every one writes
nothing: the garage (unreadable; then where it enrols, ``transient_available``
before ``enrols_at``; then the wrong end); the credential (unknown; of a pass
that does not name this garage; then, under the locks, already used; cancelled; not yet started;
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
not the garages. A credential that arrives by email must not be able to rewrite
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
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from garage_pass.access import Answer
from garage_pass.enrolment import (
    EXPIRED_CREDENTIAL,
    Credential,
    CredentialState,
    MintedToken,
    digest,
    last_day,
    mint,
    plate_key,
    require_days_valid,
    token_of,
    where_enrolment_happens,
)
from garage_pass.findings import (
    REFUSAL_CONSTRAINT,
    REFUSAL_CREDENTIAL_ALREADY_EXISTS,
    REFUSAL_CREDENTIAL_ALREADY_REPLACED,
    REFUSAL_CREDENTIAL_ALREADY_USED,
    REFUSAL_CREDENTIAL_CANCELLED,
    REFUSAL_CREDENTIAL_EXIT_ONLY,
    REFUSAL_CREDENTIAL_EXPIRED,
    REFUSAL_CREDENTIAL_NOT_BOUND,
    REFUSAL_CREDENTIAL_NOT_STARTED,
    REFUSAL_CREDENTIAL_STAY_ENDED,
    REFUSAL_CREDENTIAL_UNKNOWN,
    REFUSAL_CREDENTIAL_WRONG_CAR,
    REFUSAL_DIRECTION_OUTSIDE_THE_PASS_TERMS,
    REFUSAL_ENROLMENT_AT_WRONG_END,
    REFUSAL_FIELD_BLANK,
    REFUSAL_GARAGE_MISMATCH,
    REFUSAL_LANE_OUTSIDE_THE_PASS_TERMS,
    REFUSAL_MATCH_DECIDED_BY_UNKNOWN,
    REFUSAL_PASS_NOT_REGISTRABLE,
    REFUSAL_PLATE_NOT_STATED,
    Refused,
)
from garage_pass.garage import require_text
from garage_pass.localday import day_of, local, require_aware, zone
from garage_pass.passes import EXPIRED, Pass, State
from garage_pass.states import effective_state
from garage_pass.store.access import answer_in_transaction, answer_on_the_stays_last_day
from garage_pass.store.records import (
    ENDED_AFTER_LAST_DAY,
    REGISTRABLE_STATES,
    as_uuid,
    change_state,
    ends_a_stay_that_day,
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
    #: True only on the FIRST use: the QR bound the car now.
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
    #: True when an ALREADY-BOUND QR was shown by its own car -- read by the
    #: lane, or confirmed by a picture match (``confirm_match``). The answer is
    #: the access answer for that car. ``redeemed`` is False: nothing was bound
    #: now.
    recognised: bool = False
    #: True when a BOUND QR was shown where the lane measured NO identity, or --
    #: on a QR made for a plate -- read anything but that plate: the module
    #: neither opens nor refuses ON THIS QR. The lane matches the car's
    #: picture to the bound car's earlier ones and answers with
    #: ``confirm_match``; until then nothing opens on this QR. The answer is
    #: the access answer for what the lane read: nothing read opens nothing;
    #: another plate read is that car's own answer -- a car with its own valid
    #: pass is let through on that pass, never on this QR. Nothing written.
    match_required: bool = False
    #: The identity the QR is bound to, when a match is required: the car whose
    #: earlier pictures the lane matches against. None otherwise.
    match_for: str | None = None
    #: What the lane read, when a match is required: None when it read nothing.
    match_read: str | None = None


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
    vehicle_description: str | None, plate: tuple[str, str] | None = None,
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
        columns += ", vehicle_description, plate_typed, plate"
        values += [vehicle_description, *(plate or (None, None))]
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


def _mint_enrolment(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str,
    external_id: str, starts_on: date, days_valid: object, *, by: str, at: datetime,
    vehicle_description: str | None = None, plate: tuple[str, str] | None = None,
) -> dict:
    """The mint itself: a token returned once, its digest stored, on a pass
    that takes a registration. ``plate`` is (as typed, ``plate_key`` form);
    None writes the row a QR had before plates were required -- reached by no
    public door now (``issue_enrolment`` requires the plate), kept because such
    rows exist and are read exactly as they always were."""
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
            at, description, plate)
    return _issued(ENROLMENT, external_id, pass_external_id, minted, starts_on, days, by, at,
                   description)


def require_plate(plate: object) -> tuple[str, str]:
    """The plate a QR is made for: (as typed, ``plate_key`` form), or a refusal
    by name -- absent, not text, or blank once normalised. Nothing is minted."""
    if not isinstance(plate, str) or not plate_key(plate):
        raise Refused(
            REFUSAL_PLATE_NOT_STATED, "plate",
            f"plate is {plate!r}; a QR is made for one car's plate.",
        )
    typed = require_text(plate, "plate")
    return typed, plate_key(typed)


def _stay_end(
    cursor: Any, tenant_uuid: UUID, garage_external_id: str, pass_external_id: str,
    starts_on: date, days_valid: object,
) -> date:
    """The day a QR's registration ends: the day after the QR's LAST DAY (the
    stay's checkout day) -- never open -- and never past the pass's own
    valid_to, which bounds every registration on the pass."""
    end = last_day(starts_on, require_days_valid(days_valid)) + timedelta(days=1)
    garage_uuid, _garage = load_readable_garage(cursor, tenant_uuid, garage_external_id)
    _u, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)
    valid_to = pass_.terms.valid_to if pass_.terms is not None else None
    if valid_to is not None and end > valid_to + timedelta(days=1):
        end = valid_to + timedelta(days=1)
    return end


#: What a bound QR's own stay is on a day: in force; ended TODAY by a checkout
#: or by the car's next stay (exit only, today); not begun; or over.
STAY_LIVE, STAY_LAST_DAY, STAY_NOT_STARTED, STAY_ENDED = (
    "live", "last_day", "not_started", "ended")


def _stay_of(
    cursor: Any, tenant_uuid: UUID, garage_uuid: UUID, pass_uuid: UUID, code: Credential,
    today: date,
) -> tuple[str, tuple | None]:
    """A BOUND QR IS JUDGED BY ITS OWN STAY, never by the car's next one: the
    registrations of the QR's car ON THE QR'S PASS at this garage, read on
    ``today``. Nothing carries over -- a plate the next stay holds is that
    stay's, and this QR does not answer for it."""
    cursor.execute(
        "SELECT effective_day, end_day, ended_reason FROM vehicle_registrations "
        "WHERE tenant_id = %s AND garage_id = %s AND pass_id = %s AND vehicle_identity = %s "
        "ORDER BY effective_day",
        (tenant_uuid, garage_uuid, pass_uuid, plate_key(code.bound)),
    )
    rows = cursor.fetchall()
    for row in rows:
        effective, end, _why = row
        if effective <= today and (end is None or today < end):
            return STAY_LIVE, row
    for row in rows:
        if row[1] == today and ends_a_stay_that_day(row[2]):
            return STAY_LAST_DAY, row
    if rows and all(row[0] > today for row in rows):
        return STAY_NOT_STARTED, rows[0]
    return STAY_ENDED, (rows[-1] if rows else None)


def _refuse_outside_the_stay(
    stay: str, row: tuple | None, code: Credential, direction: Direction,
) -> None:
    """The refusals a QR's own stay gives, in order: not begun; over; and on
    the day it ended early, an entry (the exit still answers)."""
    if stay == STAY_NOT_STARTED:
        raise Refused(
            REFUSAL_CREDENTIAL_NOT_STARTED, ENROLMENT,
            f"{ENROLMENT} {code.id!r}'s stay on pass {code.pass_id!r} begins on {row[0]}.",
        )
    if stay == STAY_ENDED:
        when = (f"ended on {row[1]} ({row[2]})" if row is not None and row[1] is not None
                else "is not in force")
        raise Refused(
            REFUSAL_CREDENTIAL_STAY_ENDED, ENROLMENT,
            f"{ENROLMENT} {code.id!r}'s stay on pass {code.pass_id!r} {when}.",
        )
    if stay == STAY_LAST_DAY and direction is Direction.ENTRY:
        raise Refused(
            REFUSAL_CREDENTIAL_EXIT_ONLY, "direction",
            f"{ENROLMENT} {code.id!r}'s stay on pass {code.pass_id!r} ended today, {row[1]} "
            f"({row[2]}); it answers at an exit only, today.",
        )


def _held_by_this_pass(
    cursor: Any, tenant_uuid: UUID, pass_external_id: str, key: str, starts_on: date,
) -> bool:
    """Whether THIS pass already holds the plate from ``starts_on`` on -- a
    registration of it on this pass overlapping that day onwards, at EVERY
    garage the pass names. Then a new QR for the same car (reissued after a
    cancel, or a replaced car coming back) REUSES that registration: the car
    is registered once, and the same car on the same pass is never "another
    pass". A plate another pass holds is not looked at here; register_vehicle
    refuses it by name, as before."""
    cursor.execute(
        "SELECT count(DISTINCT r.garage_id), "
        "(SELECT count(*) FROM pass_garages pg WHERE pg.tenant_id = p.tenant_id "
        "AND pg.pass_id = p.id) "
        "FROM passes p JOIN vehicle_registrations r "
        "ON r.tenant_id = p.tenant_id AND r.pass_id = p.id "
        "WHERE p.tenant_id = %s AND p.external_id = %s AND r.vehicle_identity = %s "
        "AND daterange(r.effective_day, r.end_day, '[)') && daterange(%s, NULL, '[)') "
        "GROUP BY p.id, p.tenant_id",
        (tenant_uuid, pass_external_id, key, starts_on),
    )
    row = cursor.fetchone()
    return row is not None and row[0] == row[1]


def issue_enrolment(
    cursor: Any, tenant_id: Any, garage_external_id: str, pass_external_id: str,
    external_id: str, starts_on: date, days_valid: object, *, by: str, at: datetime,
    plate: object = None, vehicle_description: str | None = None,
) -> dict:
    """Mint the QR for ONE CAR, BY ITS PLATE: a token returned once, its digest
    stored. ``plate`` is REQUIRED -- absent or blank is refused by name and
    nothing is minted -- and the QR is BOUND to it from issue: in the same
    transaction, under a savepoint, the plate (in ``plate_key`` form) is
    registered on the pass from ``starts_on`` -- one car, one pass: a plate
    held by another pass is refused by name here, at the desk, not at the
    lane. A plate THIS pass already holds from ``starts_on`` (a QR reissued
    for the same car after a cancel, or a replaced car coming back) is not
    registered a second time: the registration it has is reused. The pass's
    state is not touched: its move to active is still the lane's, at the QR's
    first use, which binds nothing new.
    ``days_valid`` is STATED -- ``None`` is refused by name, never defaulted --
    and it is THE STAY: the plate's registration runs from ``starts_on`` to
    the QR's last day, the checkout day, and ends there (``_stay_end``) --
    never open. The car's next stay, on another pass, may start on that day
    (``register_vehicle``'s turnover)."""
    plate_pair = require_plate(plate)
    tenant_uuid = as_uuid(tenant_id)

    def write() -> dict:
        issued = _mint_enrolment(
            cursor, tenant_uuid, garage_external_id, pass_external_id, external_id, starts_on,
            days_valid, by=by, at=at, vehicle_description=vehicle_description, plate=plate_pair,
        )
        typed, key = plate_pair
        if not _held_by_this_pass(cursor, tenant_uuid, pass_external_id, key, starts_on):
            register_vehicle(cursor, tenant_uuid, garage_external_id, pass_external_id, key,
                             starts_on, _stay_end(cursor, tenant_uuid, garage_external_id,
                                                  pass_external_id, starts_on, days_valid),
                             ENDED_AFTER_LAST_DAY)
        return {**issued, "plate": typed, "plate_key": key}

    return _under_savepoint(cursor, write, "issue")


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


#: The credential row with its pass's GARAGE SET beside it -- the uuids and the
#: external ids, aggregated in one order -- read through the pass, never stored
#: on the credential (0003: a copy would be a second place for one fact to drift).
_COLUMNS = ("c.id, c.pass_id, "
            "(SELECT array_agg(pg.garage_id ORDER BY pg.garage_id) FROM pass_garages pg "
            " WHERE pg.tenant_id = p.tenant_id AND pg.pass_id = p.id), "
            "(SELECT array_agg(g.external_id ORDER BY g.external_id) FROM pass_garages pg "
            " JOIN garages g ON g.tenant_id = pg.tenant_id AND g.id = pg.garage_id "
            " WHERE pg.tenant_id = p.tenant_id AND pg.pass_id = p.id), "
            "p.external_id, c.external_id, c.starts_on, "
            "c.days_valid, c.state, c.issued_by, c.issued_at, c.redeemed_at, c.cancelled_at, "
            "c.cancelled_reason")


@dataclass(frozen=True)
class PassGarages:
    """The garages a credential's pass names, as the token lookup read them."""

    uuids: frozenset[UUID]
    external_ids: tuple[str, ...]


def _credential_from_row(kind: str, row: tuple) -> tuple[UUID, UUID, PassGarages, Credential]:
    (uuid, pass_uuid, garage_uuids, garage_exts, pass_ext, ext, starts_on, days_valid, state,
     issued_by, issued_at, redeemed_at, cancelled_at, cancelled_reason, *rest) = row
    description, bound, exit_only_at, plate = rest if rest else (None, None, None, None)
    credential = Credential(
        kind=kind, id=ext, pass_id=pass_ext, starts_on=starts_on, days_valid=days_valid,
        state=CredentialState(state), issued_by=issued_by, issued_at=issued_at,
        vehicle_description=description, redeemed_at=redeemed_at,
        cancelled_at=cancelled_at, cancelled_reason=cancelled_reason,
        bound_identity=bound, exit_only_at=exit_only_at, plate=plate,
    )
    garages = PassGarages(
        uuids=frozenset(as_uuid(u) for u in (garage_uuids or ())),
        external_ids=tuple(garage_exts or ()),
    )
    return as_uuid(uuid), as_uuid(pass_uuid), garages, credential


def _select(kind: str, where: str) -> str:
    extra = (", c.vehicle_description, c.redeemed_vehicle_identity, c.exit_only_at, c.plate"
             if kind == ENROLMENT else "")
    return (
        f"SELECT {_COLUMNS}{extra} FROM {_TABLE[kind]} c "
        "JOIN passes p ON p.tenant_id = c.tenant_id AND p.id = c.pass_id "
        f"WHERE c.tenant_id = %s AND {where}"
    )


def _by_token(
    cursor: Any, kind: str, tenant_uuid: UUID, presented: str
) -> tuple[UUID, UUID, PassGarages, Credential]:
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
) -> tuple[UUID, UUID, PassGarages, Credential]:
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


def _refuse_unless_redeemable(
    kind: str, credential: Credential, today: date, tz: ZoneInfo
) -> None:
    """A credential that is not issued today, refused by name. The instant a
    refusal shows -- when the winner redeemed, when the revocation cancelled --
    is rendered as the GARAGE's wall clock reads it (``localday.local``), never
    the database session's zone and never the caller's offset: the rule G1's
    gate fixed for the visit ledger, applied here where the gate found it
    missing. The row holds the instant; only the rendering moves."""
    state = credential.state_on(today)
    if state == CredentialState.REDEEMED.value:
        raise Refused(
            REFUSAL_CREDENTIAL_ALREADY_USED, kind,
            f"{kind} {credential.id!r} was redeemed at "
            f"{local(credential.redeemed_at, tz).isoformat()}.",
        )
    if state == CredentialState.CANCELLED.value:
        raise Refused(
            REFUSAL_CREDENTIAL_CANCELLED, kind,
            f"{kind} {credential.id!r} was cancelled at "
            f"{local(credential.cancelled_at, tz).isoformat()}: {credential.cancelled_reason}.",
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


def _is_bound(cursor: Any, tenant_uuid: UUID, presented: str) -> bool:
    """Whether the token presented is an enrolment that is ALREADY BOUND to a
    car (redeemed, or cancelled after it was). Asked only at the end this
    garage does not enrol at: a bound QR answers at both ends, so the
    wrong-end refusal is for a QR that has not bound yet. Anything else -- an
    unknown token, a blank one, an unbound QR -- is False, and the wrong-end
    refusal stands exactly as it was."""
    try:
        _uuid, _pass_uuid, _garages, glimpse = _by_token(cursor, ENROLMENT, tenant_uuid, presented)
    except Refused:
        return False
    return glimpse.bound is not None


def _present_bound(
    enrolment: Credential, vehicle_identity: str, direction: Direction, tz: ZoneInfo,
) -> bool:
    """A BOUND QR shown again, judged on the row re-read under the locks. In
    this order: cancelled; then, where the lane measured NO identity, an entry
    on a replaced car is refused EXIT ONLY and anything else needs a PICTURE
    MATCH -- the module neither opens nor refuses blind, it returns True and
    the lane matches the car to the bound car's earlier pictures and answers
    with ``confirm_match``; where it measured one, the identity must be the
    one the QR is bound to, exact text, or it is refused WRONG CAR, and then
    an entry on a replaced car is refused EXIT ONLY. It writes nothing."""
    assert enrolment.bound is not None
    if enrolment.state is CredentialState.CANCELLED:
        raise Refused(
            REFUSAL_CREDENTIAL_CANCELLED, ENROLMENT,
            f"{ENROLMENT} {enrolment.id!r} was cancelled at "
            f"{local(enrolment.cancelled_at, tz).isoformat()}: {enrolment.cancelled_reason}.",
        )
    unread = isinstance(vehicle_identity, str) and not vehicle_identity.strip()
    if not unread:
        identity = require_text(vehicle_identity, "vehicle_identity")
        if enrolment.plate is not None:
            # A QR MADE FOR A PLATE: the plate SUPPORTS the match and never
            # refuses on its own. The same plate, in the one normal form, is
            # recognised; any other read -- part of it, a misread, another
            # plate -- is a picture match against the registered plate, and
            # only the match's own "no" (confirm_match) is wrong car
            unread = plate_key(identity) != enrolment.plate
        elif identity != enrolment.bound_identity:
            raise Refused(
                REFUSAL_CREDENTIAL_WRONG_CAR, "vehicle_identity",
                f"{ENROLMENT} {enrolment.id!r} is bound to another car since "
                f"{local(enrolment.redeemed_at, tz).isoformat()}.",
            )
    if direction is Direction.ENTRY and enrolment.exit_only_at is not None:
        raise Refused(
            REFUSAL_CREDENTIAL_EXIT_ONLY, "direction",
            f"{ENROLMENT} {enrolment.id!r}'s car was replaced on pass {enrolment.pass_id!r} "
            f"at {local(enrolment.exit_only_at, tz).isoformat()}; it answers at an exit only.",
        )
    return unread  # unread, or a plate read that is not the plate: a picture match decides


def redeem_enrolment(
    cursor: Any, tenant_id: Any, garage_external_id: str, presented: str,
    vehicle_identity: str, lane: str, direction: Direction, at: datetime,
) -> Redemption:
    """THE LANE BIND, AND A BOUND QR SHOWN AGAIN. See the module docstring for
    the lock order, the atomicity and the answer that is always returned. A
    garage that does not exist is the one refusal raised rather than carried:
    there is no lane to answer.

    A QR that is ALREADY BOUND is not bound again: shown by its own car it is
    ``recognised`` and answered for that car, at either end; shown by another
    car it is refused WRONG CAR; at an entry after its car was replaced, EXIT
    ONLY. Shown where the lane measured no identity -- or, on a QR made for a
    plate, read anything but that plate -- it is ``match_required``: nothing
    opens on THIS QR until the lane's picture match is confirmed
    (``confirm_match``); the answer is the access answer for what was read, so
    another plate with its own valid pass is let through on that pass. Nothing
    is written on any of those paths."""
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
        if direction.value != end and not _is_bound(cursor, tenant_uuid, presented):
            raise Refused(
                REFUSAL_ENROLMENT_AT_WRONG_END, "garage.enrols_at",
                f"garage {garage_external_id!r} enrols at {end}; this lane ({lane!r}) is an "
                f"{direction.value}.",
            )
        # read UNLOCKED, only to learn which pass this credential belongs to
        uuid, pass_uuid, pass_garages, glimpse = _by_token(
            cursor, ENROLMENT, tenant_uuid, presented,
        )
        enrolment_id = glimpse.id
        # MEMBERSHIP: this garage is one of the QR's pass's garages
        if garage_uuid not in pass_garages.uuids:  # the QR's pass
            raise Refused(
                REFUSAL_GARAGE_MISMATCH, "garage",
                f"enrolment {glimpse.id!r} belongs to pass {glimpse.pass_id!r}, which names "
                f"garages {list(pass_garages.external_ids)}, not {garage_external_id!r}.",
            )
        # LOCK_ORDER: the pass row first, then the credential row -- then every
        # check below is made on rows re-read UNDER the locks, never on the glimpse
        lock_pass_row(cursor, tenant_uuid, pass_uuid)
        uuid, pass_uuid, _same_garages, enrolment = _lock_credential(
            cursor, ENROLMENT, tenant_uuid, uuid,
        )
        tz = zone(garage.timezone)
        today = day_of(at, tz)
        if enrolment.bound is not None:
            # ALREADY BOUND -- by its plate from issue, or by its first use:
            # judged on the row re-read under the locks -- a QR that another
            # lane bound an instant ago is answered here, by name
            # (wrong car, recognised, or a picture match required), never bound
            # a second time
            match_required = _present_bound(enrolment, vehicle_identity, direction, tz)
            # ITS OWN STAY, never the car's next one: not begun, over, or -- on
            # the day it ended early -- an entry, refused by name before any
            # match or recognition (nothing carries over)
            stay, stay_row = _stay_of(cursor, tenant_uuid, garage_uuid, pass_uuid, enrolment,
                                      today)
            _refuse_outside_the_stay(stay, stay_row, enrolment, direction)
            cursor.execute(f"RELEASE SAVEPOINT {SAVEPOINT}")
            if match_required:
                # NOTHING OPENS ON THIS QR: the answer is for the identity the
                # lane measured, never the QR's car. Nothing read: an entry is
                # refused an answer and an exit is not covered (and still never
                # refused). Another plate read: that car's own answer -- a car
                # with its own valid pass is let through on THAT pass
                return Redemption(
                    enrolment=enrolment_id, redeemed=False, refusal=None, registration=None,
                    pass_state_change=None, answer=answer_in_transaction(
                        cursor, tenant_uuid, garage_external_id, vehicle_identity, lane,
                        direction, at,
                    ),
                    match_required=True, match_for=enrolment.bound,
                    match_read=(vehicle_identity.strip() or None
                                if isinstance(vehicle_identity, str)
                                and plate_key(vehicle_identity) else None),
                )
            # RECOGNISED. A QR bound from issue (its plate) on a pass still
            # waiting for its first car moves the pass to active here, at its
            # first use -- recorded, the QR as the actor -- and binds nothing:
            # the plate was registered when the QR was made
            change = None
            _u, pass_now = load_pass(cursor, tenant_uuid, garage_uuid, enrolment.pass_id)
            if pass_now.state in (State.DRAFT, State.AWAITING_ENROLMENT):
                change = _under_savepoint(cursor, lambda: change_state(
                    cursor, tenant_uuid, garage_external_id, enrolment.pass_id, State.ACTIVE,
                    by=enrolment.id, at=at, reason=f"first use at lane {lane!r}",
                ), "first_use")
            answer = (
                answer_on_the_stays_last_day(
                    cursor, tenant_uuid, garage_external_id, plate_key(enrolment.bound),
                    pass_uuid, enrolment.pass_id, stay_row[0], today, lane, direction, at,
                ) if stay == STAY_LAST_DAY else answer_in_transaction(
                    cursor, tenant_uuid, garage_external_id, enrolment.bound, lane, direction,
                    at,
                )
            )
            return Redemption(
                enrolment=enrolment_id, redeemed=False, refusal=None, registration=None,
                pass_state_change=change, answer=answer, recognised=True,
            )
        _refuse_unless_redeemable(ENROLMENT, enrolment, today, tz)
        _pass_uuid, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, enrolment.pass_id)
        _refuse_unless_registrable(pass_, enrolment.pass_id, today, "a redemption")
        assert pass_.terms is not None
        lane_name = require_text(lane, "lane")
        lanes_here = pass_.terms.lanes_at(garage_external_id)
        if lanes_here is not None and lane_name not in lanes_here:
            raise Refused(
                REFUSAL_LANE_OUTSIDE_THE_PASS_TERMS, "lane",
                f"pass {enrolment.pass_id!r} allows lanes {sorted(lanes_here)} at garage "
                f"{garage_external_id!r}, not {lane_name!r}.",
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
        #    EXCLUDE has to; effective on the garage's local day of this instant;
        #    ONE ROW PER GARAGE THE PASS NAMES, all or none (the fan-out)
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
    at: datetime, plate: object = None, vehicle_description: str | None = None,
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
    uuid, pass_uuid, pass_garages, glimpse = _by_token(
        cursor, HOLDER_LINK, tenant_uuid, presented,
    )
    # MEMBERSHIP: this garage is one of the link's pass's garages
    if garage_uuid not in pass_garages.uuids:  # the link's pass
        raise Refused(
            REFUSAL_GARAGE_MISMATCH, "garage",
            f"holder link {glimpse.id!r} belongs to pass {glimpse.pass_id!r}, which names "
            f"garages {list(pass_garages.external_ids)}, not {garage_external_id!r}.",
        )
    # LOCK_ORDER: the pass row first, then the link row; then re-read under them
    lock_pass_row(cursor, tenant_uuid, pass_uuid)
    uuid, pass_uuid, _same_garages, link = _lock_credential(cursor, HOLDER_LINK, tenant_uuid, uuid)
    tz = zone(garage.timezone)
    today = day_of(at, tz)
    _refuse_unless_redeemable(HOLDER_LINK, link, today, tz)
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
        days_valid, by=link.id, at=at, plate=plate, vehicle_description=vehicle_description,
    )
    _spend(cursor, HOLDER_LINK, tenant_uuid, uuid, "redeemed_at = %s", (at,))
    return {
        HOLDER_LINK: link.id, "pass": link.pass_id, "holder_name": holder_name,
        "holder_phone": holder_phone, "redeemed_at": at, "enrolment": issued,
    }


# ---------------------------------------------------------------------------
# The two writes on one QR: replace its car, cancel it. Each takes LOCK_ORDER
# (the pass row, then the QR's row), re-reads the QR under those locks, and
# sits under a savepoint that is rolled back on EVERY exception -- a refusal
# writes nothing even in a caller that commits afterwards, the redemption's
# rule (X2) applied here.
# ---------------------------------------------------------------------------

#: The savepoint each write on one QR sits under -- ONE NAME PER WRITE, never
#: one shared name: ``replace_car`` calls ``issue_enrolment``, and a ROLLBACK TO
#: a name returns to the MOST RECENT savepoint of that name, so a shared name
#: would take back only the inner write and leave the outer one standing
#: (measured: a refused new QR left the old QR marked exit only).
SAVEPOINTS = {"issue": "garage_pass_issue", "replace": "garage_pass_replace",
              "cancel": "garage_pass_cancel", "match": "garage_pass_match",
              "first_use": "garage_pass_first_use"}


def _locked_code(
    cursor: Any, tenant_uuid: UUID, garage_external_id: str, enrolment_external_id: str,
) -> tuple[UUID, UUID, Credential]:
    """The QR by its id, at a garage its pass names, locked in LOCK_ORDER and
    re-read under the locks. A QR of a pass that does not name this garage is
    refused by name, as the redemption refuses it."""
    garage_uuid, _garage = load_readable_garage(cursor, tenant_uuid, garage_external_id)
    external_id = require_text(enrolment_external_id, "enrolment.id")
    cursor.execute(_select(ENROLMENT, "c.external_id = %s"), (tenant_uuid, external_id))
    row = cursor.fetchone()
    if row is None:
        raise Refused(REFUSAL_CREDENTIAL_UNKNOWN, "enrolment.id", f"no enrolment {external_id!r}.")
    uuid, pass_uuid, pass_garages, glimpse = _credential_from_row(ENROLMENT, row)
    if garage_uuid not in pass_garages.uuids:
        raise Refused(
            REFUSAL_GARAGE_MISMATCH, "garage",
            f"enrolment {glimpse.id!r} belongs to pass {glimpse.pass_id!r}, which names "
            f"garages {list(pass_garages.external_ids)}, not {garage_external_id!r}.",
        )
    lock_pass_row(cursor, tenant_uuid, pass_uuid)
    uuid, pass_uuid, _same, code = _lock_credential(cursor, ENROLMENT, tenant_uuid, uuid)
    return uuid, pass_uuid, code


def _one_row(cursor: Any, what: str, code: Credential) -> None:
    """The write's backstop: exactly one row, or the named refusal -- the row
    moved between the read under the lock and the write, which only a caller
    that skipped the lock can produce."""
    if cursor.rowcount != 1:
        raise Refused(
            REFUSAL_CREDENTIAL_ALREADY_USED, ENROLMENT,
            f"enrolment {code.id!r} was no longer in the state {what} needs: "
            f"{cursor.rowcount} row(s) matched. Roll back and read again.",
        )


def _under_savepoint(cursor: Any, write: Any, which: str) -> Any:
    name = SAVEPOINTS[which]
    cursor.execute(f"SAVEPOINT {name}")
    try:
        result = write()
    except BaseException:
        cursor.execute(f"ROLLBACK TO SAVEPOINT {name}")
        raise
    cursor.execute(f"RELEASE SAVEPOINT {name}")
    return result


def replace_car(
    cursor: Any, tenant_id: Any, garage_external_id: str, enrolment_external_id: str,
    new_enrolment_external_id: str, starts_on: date, days_valid: object, *, by: str,
    at: datetime, reason: str, plate: object = None, vehicle_description: str | None = None,
) -> dict:
    """REPLACE THE CAR ON A PASS, ONE STEP. The named QR's car stops entering
    and keeps leaving: a BOUND QR is marked exit only (who, when, why), so the
    car left inside can go; a QR that never bound has no car inside and is
    cancelled instead. A new QR is issued on the SAME pass for the replacement
    car -- its token returned once, here. All of it or none of it. A QR that
    was cancelled, or whose car was already replaced, is refused by name."""
    tenant_uuid = as_uuid(tenant_id)
    require_aware(at, "at")
    by = require_text(by, "by")
    reason = require_text(reason, "reason")
    new_id = require_text(new_enrolment_external_id, "new_enrolment.id")
    require_plate(plate)  # the replacement car's plate: refused before anything is written

    def write() -> dict:
        _uuid, _pass_uuid, code = _locked_code(
            cursor, tenant_uuid, garage_external_id, enrolment_external_id,
        )
        tz = zone(load_readable_garage(cursor, tenant_uuid, garage_external_id)[1].timezone)
        if code.state is CredentialState.CANCELLED:
            raise Refused(
                REFUSAL_CREDENTIAL_CANCELLED, ENROLMENT,
                f"enrolment {code.id!r} was cancelled at "
                f"{local(code.cancelled_at, tz).isoformat()}: {code.cancelled_reason}.",
            )
        if code.exit_only_at is not None:
            raise Refused(
                REFUSAL_CREDENTIAL_ALREADY_REPLACED, ENROLMENT,
                f"enrolment {code.id!r}'s car was replaced at "
                f"{local(code.exit_only_at, tz).isoformat()}.",
            )
        why = f"car replaced, new QR {new_id!r}: {reason}"
        if code.bound is not None:
            cursor.execute(
                "UPDATE enrolments SET exit_only_at = %s, exit_only_by = %s, "
                "exit_only_reason = %s WHERE tenant_id = %s AND id = %s "
                "AND state = %s AND exit_only_at IS NULL",
                (at, by, why, tenant_uuid, _uuid, code.state.value),
            )
            _one_row(cursor, "a replacement", code)
            old = {"enrolment": code.id, "vehicle_identity": code.bound,
                   "now": "exit_only", "at": at}
        else:
            cursor.execute(
                "UPDATE enrolments SET state = %s, cancelled_by = %s, cancelled_at = %s, "
                "cancelled_reason = %s WHERE tenant_id = %s AND id = %s AND state = %s",
                (CredentialState.CANCELLED.value, by, at, why, tenant_uuid, _uuid,
                 CredentialState.ISSUED.value),
            )
            _one_row(cursor, "a replacement", code)
            old = {"enrolment": code.id, "vehicle_identity": None, "now": "cancelled",
                   "at": at}
        issued = issue_enrolment(
            cursor, tenant_uuid, garage_external_id, code.pass_id, new_id, starts_on,
            days_valid, by=by, at=at, plate=plate, vehicle_description=vehicle_description,
        )
        return {"pass": code.pass_id, "replaced": old, "reason": reason, "new": issued}

    return _under_savepoint(cursor, write, "replace")


def cancel_code(
    cursor: Any, tenant_id: Any, garage_external_id: str, enrolment_external_id: str, *,
    by: str, at: datetime, reason: str,
) -> dict:
    """CANCEL ONE QR, AND ONLY IT. Bound or not; the pass, its other QRs and
    every registration stay exactly as they were -- a car the QR had bound
    stays on the pass (ending the car is end-registration's). A QR already
    cancelled is refused by name. Issue a fresh QR with issue-enrolment."""
    tenant_uuid = as_uuid(tenant_id)
    require_aware(at, "at")
    by = require_text(by, "by")
    reason = require_text(reason, "reason")

    def write() -> dict:
        _uuid, _pass_uuid, code = _locked_code(
            cursor, tenant_uuid, garage_external_id, enrolment_external_id,
        )
        tz = zone(load_readable_garage(cursor, tenant_uuid, garage_external_id)[1].timezone)
        if code.state is CredentialState.CANCELLED:
            raise Refused(
                REFUSAL_CREDENTIAL_CANCELLED, ENROLMENT,
                f"enrolment {code.id!r} was cancelled at "
                f"{local(code.cancelled_at, tz).isoformat()}: {code.cancelled_reason}.",
            )
        cursor.execute(
            "UPDATE enrolments SET state = %s, cancelled_by = %s, cancelled_at = %s, "
            "cancelled_reason = %s WHERE tenant_id = %s AND id = %s AND state = %s",
            (CredentialState.CANCELLED.value, by, at, reason, tenant_uuid, _uuid,
             code.state.value),
        )
        _one_row(cursor, "a cancellation", code)
        return {"enrolment": code.id, "pass": code.pass_id, "was": code.state.value,
                "vehicle_identity": code.bound, "state": "cancelled",
                "cancelled_by": by, "cancelled_at": at, "reason": reason}

    return _under_savepoint(cursor, write, "cancel")


def _same_car(read: str, code: Credential) -> bool:
    """Whether an identity the lane read can be the QR's car once a picture
    matched it: on a QR made for a plate the picture decides whatever was read
    (the plate supports the match, it never refuses on its own); a QR stored
    without a plate takes its bound identity exactly, as it always did."""
    if code.plate is not None:
        return True
    return read == code.bound_identity


#: Who may decide a picture match: the car's own fingerprint against its earlier
#: pictures, or an outside picture check when the fingerprint was unclear.
MATCH_DECIDERS = ("fingerprint", "api")


def confirm_match(
    cursor: Any, tenant_id: Any, garage_external_id: str, enrolment_external_id: str, *,
    matched: bool, identity_read: str | None, decided_by: str, lane: str,
    direction: Direction, at: datetime,
) -> Redemption:
    """THE LANE'S ANSWER AFTER A PICTURE MATCH, for a bound QR that asked for
    one (``match_required``). Matched, and no other identity read: a
    RECOGNISED use, answered for the bound car (an entry on a replaced car is
    still refused EXIT ONLY). Not matched, or an identity read that is not the
    bound car's: refused WRONG CAR -- nothing opens on this QR; the answer is
    for what was read (another plate with its own valid pass, on that pass).
    EVERY ANSWER IS KEPT on the QR's own row (``enrolments.matches``), in
    order, with its instant, so a car that keeps needing a match is visible;
    the record and the outcome are one write under the lock order and a
    savepoint. A QR that does not exist, is not bound or is cancelled, and a
    decider this module does not record, are refused by name and write
    nothing."""
    import json

    tenant_uuid = as_uuid(tenant_id)
    require_aware(at, "at")
    if not isinstance(direction, Direction):
        raise TypeError(f"direction must be a Direction, not {direction!r}")
    if not isinstance(matched, bool):
        raise TypeError(f"matched must be a bool, not {matched!r}")
    if decided_by not in MATCH_DECIDERS:
        raise Refused(
            REFUSAL_MATCH_DECIDED_BY_UNKNOWN, "decided_by",
            f"{decided_by!r}; a match is decided by one of {list(MATCH_DECIDERS)}.",
        )
    lane_name = require_text(lane, "lane")
    read = (None if identity_read is None or (isinstance(identity_read, str)
                                              and not identity_read.strip())
            else require_text(identity_read, "vehicle_identity"))

    def write() -> tuple[Credential, Refused | None, dict | None, tuple | None]:
        uuid, pass_uuid, code = _locked_code(
            cursor, tenant_uuid, garage_external_id, enrolment_external_id,
        )
        tz = zone(load_readable_garage(cursor, tenant_uuid, garage_external_id)[1].timezone)
        if code.bound is None:
            raise Refused(
                REFUSAL_CREDENTIAL_NOT_BOUND, ENROLMENT,
                f"enrolment {code.id!r} is bound to no car.",
            )
        if code.state is CredentialState.CANCELLED:
            raise Refused(
                REFUSAL_CREDENTIAL_CANCELLED, ENROLMENT,
                f"enrolment {code.id!r} was cancelled at "
                f"{local(code.cancelled_at, tz).isoformat()}: {code.cancelled_reason}.",
            )
        refusal: Refused | None = None
        if not matched or (read is not None and not _same_car(read, code)):
            refusal = Refused(
                REFUSAL_CREDENTIAL_WRONG_CAR, "vehicle_identity",
                f"{ENROLMENT} {code.id!r} is bound to another car; the picture match "
                f"({decided_by}) did not find it.",
            )
        elif direction is Direction.ENTRY and code.exit_only_at is not None:
            refusal = Refused(
                REFUSAL_CREDENTIAL_EXIT_ONLY, "direction",
                f"{ENROLMENT} {code.id!r}'s car was replaced on pass {code.pass_id!r} at "
                f"{local(code.exit_only_at, tz).isoformat()}; it answers at an exit only.",
            )
        last_day_of_stay = None
        if refusal is None:
            # a match decides WHICH CAR, never WHICH STAY: the QR's own stay
            # still bounds it, and nothing carries over to the car's next one
            garage_uuid_, _g = load_readable_garage(cursor, tenant_uuid, garage_external_id)
            stay, stay_row = _stay_of(cursor, tenant_uuid, garage_uuid_, pass_uuid, code,
                                      day_of(at, tz))
            try:
                _refuse_outside_the_stay(stay, stay_row, code, direction)
            except Refused as outside:
                refusal = outside
            if refusal is None and stay == STAY_LAST_DAY:
                last_day_of_stay = (pass_uuid, stay_row[0], day_of(at, tz))
        record = {
            "at": at.isoformat(), "matched": matched, "identity_read": read,
            "decided_by": decided_by, "lane": lane_name, "direction": direction.value,
            "outcome": "recognised" if refusal is None else refusal.code,
        }
        cursor.execute(
            "UPDATE enrolments SET matches = matches || %s::jsonb "
            "WHERE tenant_id = %s AND id = %s",
            (json.dumps([record]), tenant_uuid, uuid),
        )
        _one_row(cursor, "a picture match", code)
        change = None
        if refusal is None:
            # a recognised use is a USE: a pass still waiting for its first car
            # moves to active here as it does on a recognised read
            garage_uuid, _g = load_readable_garage(cursor, tenant_uuid, garage_external_id)
            _u, pass_now = load_pass(cursor, tenant_uuid, garage_uuid, code.pass_id)
            if pass_now.state in (State.DRAFT, State.AWAITING_ENROLMENT):
                change = change_state(
                    cursor, tenant_uuid, garage_external_id, code.pass_id, State.ACTIVE,
                    by=code.id, at=at, reason=f"first use at lane {lane_name!r}, by a picture "
                    f"match ({decided_by})",
                )
        return code, refusal, change, last_day_of_stay

    code, refusal, change, last_day_of_stay = _under_savepoint(cursor, write, "match")
    if last_day_of_stay is not None:
        pass_uuid, effective, today = last_day_of_stay
        answer = answer_on_the_stays_last_day(
            cursor, tenant_uuid, garage_external_id, plate_key(code.bound), pass_uuid,
            code.pass_id, effective, today, lane_name, direction, at,
        )
    else:
        answer = answer_in_transaction(
            cursor, tenant_uuid, garage_external_id,
            code.bound if refusal is None else (read or ""), lane_name, direction, at,
        )
    return Redemption(
        enrolment=code.id, redeemed=False, refusal=refusal, registration=None,
        pass_state_change=change, answer=answer, recognised=refusal is None,
    )
