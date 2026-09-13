"""Enrolment: the one-time credential, where a garage enrols, and what is
derived. The pure half -- nothing here touches a database.

**THE EMAIL IS THE IDENTITY, THE QR IS THE CREDENTIAL, AND THERE IS NO
ACCOUNT AND NO PASSWORD.** An enrolment is a token minted once, returned once
by the call that issued it, and known to this module afterwards only by its
SHA-256. A lane presents the token with the vehicle identity it measured; the
store binds that identity to the pass, marks the credential redeemed, and
answers the movement by the module's own access call. A holder link is the
same primitive scoped to one pass: redeemed once, it lets the holder write
their own name and phone and ask for an enrolment.

**NO QR IMAGE.** This module returns the token and the payload string the QR
carries (``payload_of``). Rendering a bitmap is the client's job and a
dependency this package will not take. ``secrets`` and ``hashlib`` from the
standard library, nothing else.

**WHERE A GARAGE ENROLS FOLLOWS FROM WHETHER IT SELLS TRANSIENT (R1).** A
garage with no transient parking does not admit an unregistered vehicle, so the
registration must happen at its entry: ``where_enrolment_happens`` DERIVES
``'entry'`` for it, from a stated field, the way a pass's ``expired`` is
derived -- not a guessed default. A transient garage has a choice and states
``enrols_at``; unstated, the redemption refuses to answer naming the field.
The order when both are unstated is deterministic and stated here:
``garage.transient_available`` first (it is the field that decides), and
``garage.enrols_at`` only when transient is stated true.

**``expired`` IS DERIVED** from ``starts_on`` + ``days_valid`` against the
garage's local day, exactly as ``states.effective_state`` derives a pass's --
nobody may type it, and ``parse_credential_state`` refuses it by its own code.
A credential issued for ``starts_on`` with ``days_valid`` N may be redeemed on
N local days: ``starts_on`` through ``last_day`` = ``starts_on`` + N - 1. His
product's number is three ("one-time use, valid 3 days from the starting
day"); it is documented, never defaulted: ``days_valid`` is STATED, and
``require_days_valid`` refuses an absent one by name.

**ONE QR PER CAR.** A redeemed enrolment is TERMINAL and binds exactly one
vehicle identity. Several outstanding enrolments on one pass are allowed and
intended -- a pass may carry several vehicles -- and each redeems to one car
and dies. Nobody should build a one-outstanding-per-pass rule: his pooling
forbids it.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum

from garage_pass.findings import (
    REFUSAL_DAYS_VALID_NOT_POSITIVE,
    REFUSAL_DAYS_VALID_NOT_STATED,
    REFUSAL_ENROLMENT_EXPIRED_IS_DERIVED,
    REFUSAL_STATE_UNKNOWN,
    REFUSAL_WHERE_TO_ENROL_UNSTATED,
    Refused,
)
from garage_pass.garage import ENROLS_AT_ENTRY, Garage, require_text
from garage_pass.localday import require_aware
from garage_pass.typed import require_typed

#: What the QR carries: a prefix naming the module and the credential's format
#: version, then the token. A lane may present the whole payload or the bare
#: token; ``token_of`` reads either.
PAYLOAD_PREFIX = "openparking-garage-pass/1/"


class CredentialState(Enum):
    """The states somebody TYPES -- for an enrolment and for a holder link
    alike. ``expired`` is not here: it is derived by ``credential_state``."""

    ISSUED = "issued"
    REDEEMED = "redeemed"
    CANCELLED = "cancelled"


#: The derived state's name, for answers and the contract. Not a CredentialState.
EXPIRED_CREDENTIAL = "expired"

#: The one reason this module cancels a credential: the pass it opens was
#: revoked, and a credential must not outlive the pass (R5).
CANCELLED_BY_REVOCATION = "pass revoked"


@dataclass(frozen=True)
class MintedToken:
    """The plaintext, and the only thing about it that is ever stored."""

    token: str
    sha256: str

    @property
    def payload(self) -> str:
        return payload_of(self.token)


def mint() -> MintedToken:
    """A fresh credential: 32 bytes from the operating system's CSPRNG, URL-safe,
    and its SHA-256 hex digest."""
    token = secrets.token_urlsafe(32)
    return MintedToken(token=token, sha256=digest(token))


def digest(token: str) -> str:
    """The SHA-256 hex digest of a token -- the only form the store compares."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def payload_of(token: str) -> str:
    return PAYLOAD_PREFIX + token


def token_of(presented: str) -> str:
    """The bare token from what a lane presented: the payload the QR carried,
    or the token on its own. Whitespace around it is not part of it."""
    text = require_text(presented, "token")
    if text.startswith(PAYLOAD_PREFIX):
        return text[len(PAYLOAD_PREFIX):]
    return text


def parse_credential_state(name: object) -> CredentialState:
    """A typed state by name. ``expired`` is refused by its own code, because
    somebody typing it is the mistake the derivation exists to prevent."""
    if name == EXPIRED_CREDENTIAL:
        raise Refused(REFUSAL_ENROLMENT_EXPIRED_IS_DERIVED, "state", "'expired' was typed.")
    try:
        return CredentialState(name)
    except ValueError:
        raise Refused(
            REFUSAL_STATE_UNKNOWN, "state",
            f"{name!r}; the typed credential states are {[s.value for s in CredentialState]}.",
        ) from None


def require_days_valid(value: object) -> int:
    """A stated, positive whole number of days -- or a refusal by name. ``None``
    is refused as NOT STATED, never read as a default: how long a QR may wait
    is the owner's to state."""
    if value is None:
        raise Refused(REFUSAL_DAYS_VALID_NOT_STATED, "days_valid", "days_valid is not stated.")
    if isinstance(value, bool) or not isinstance(value, int):
        raise Refused(
            REFUSAL_DAYS_VALID_NOT_POSITIVE, "days_valid",
            f"days_valid must be a positive whole number of days, not {value!r}.",
        )
    if value <= 0:
        raise Refused(
            REFUSAL_DAYS_VALID_NOT_POSITIVE, "days_valid", f"days_valid is {value}."
        )
    return value


def last_day(starts_on: date, days_valid: int) -> date:
    """The last local day a credential may be redeemed on: ``starts_on`` plus
    ``days_valid`` less one, inclusive. Three days from June 1st is June 1st,
    2nd and 3rd."""
    return starts_on + timedelta(days=days_valid - 1)


def credential_state(
    starts_on: date, days_valid: int, state: CredentialState, today: date
) -> str:
    """The state a redemption reads: the typed one, or ``expired``. The
    terminal states outrank expiry -- a redeemed credential is redeemed and a
    cancelled one is cancelled, whatever the day."""
    if state is not CredentialState.ISSUED:
        return state.value
    if today > last_day(starts_on, days_valid):
        return EXPIRED_CREDENTIAL
    return state.value


def where_enrolment_happens(garage: Garage) -> str:
    """``'entry'`` or ``'exit'``, or a refusal naming the field that would
    decide -- ``garage.transient_available`` first, ``garage.enrols_at`` only
    when transient is stated true. Derivation, not a default: a garage with no
    transient enrols at entry because R1 leaves it nowhere else."""
    if garage.transient_available is None:
        raise Refused(
            REFUSAL_WHERE_TO_ENROL_UNSTATED, "garage.transient_available",
            f"garage {garage.id!r} has not stated whether transient parking is available, "
            "which decides where it enrols.",
        )
    if garage.transient_available is False:
        return ENROLS_AT_ENTRY
    if garage.enrols_at is None:
        raise Refused(
            REFUSAL_WHERE_TO_ENROL_UNSTATED, "garage.enrols_at",
            f"garage {garage.id!r} sells transient parking and has not stated whether it "
            "enrols at entry or at exit.",
        )
    return garage.enrols_at


@dataclass(frozen=True)
class Credential:
    """An enrolment or a holder link as the store reads it: never the token,
    only what was recorded about it. ``vehicle_description`` is the holder's
    own statement of the car they will bring and DECIDES NOTHING (enrolments
    only; a link carries none)."""

    kind: str
    id: str
    pass_id: str
    starts_on: date
    days_valid: int
    state: CredentialState
    issued_by: str
    issued_at: datetime
    vehicle_description: str | None = None
    redeemed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancelled_reason: str | None = None

    def __post_init__(self) -> None:
        require_typed(self)
        require_aware(self.issued_at, "issued_at")
        require_days_valid(self.days_valid)

    @property
    def last_day(self) -> date:
        return last_day(self.starts_on, self.days_valid)

    def state_on(self, today: date) -> str:
        return credential_state(self.starts_on, self.days_valid, self.state, today)
