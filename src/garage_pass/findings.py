"""Every refusal, every not-covered reason and every barrier meaning, as a code
with a plain-English sentence.

**The registries are the single source.** ``docs/CONTRACT.md`` is generated from
them, a refusal carries its code, and the tests derive their lists from here
rather than walking hand-written ones -- so a code added without a sentence
fails at the raise site, and a sentence published for a code nothing raises
fails ``scripts/generate_contract.py --check`` (measured: before that check
existed, regenerating the contract silenced an orphan and the suite stayed
green).

Three vocabularies live here and they are deliberately not one:

* **REFUSALS** -- the module will not do what it was asked: a pass whose terms
  contradict each other is not created, a vehicle another pass holds is not
  registered, a revoked pass is not reactivated. Each names the field or the
  thing that would have to change. A refusal is an exception; it is raised at
  CREATION, never discovered at a gate.

* **NOT_COVERED_REASONS** -- the access call CAN answer, and the answer is no.
  These reach a parking lane in plain English and carry no money, ever.

* **BARRIER_MEANINGS** -- what a not-covered answer means where the car is
  standing, which depends on the direction and on whether the garage sells
  transient parking. The one that matters most: **an exit is never refused.**
  An exit outside a pass's terms is answered, recorded and reported as
  out-of-terms -- at a transient garage that is what makes it chargeable -- but
  nothing this module answers can keep a car inside a garage.

* **REFUSED_TO_ANSWER** -- the access call cannot answer without guessing, and
  says which field would let it. Not a refusal of the car; a refusal to guess.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Unreadable:
    """A value this module refuses to read -- carried on the pass or the garage
    it came from instead of raised, so an access call about it produces a
    STATED answer and never an exception. Reached by a stored row (a raw write,
    or a validator tightened after the row was stored) and, at an EXIT, by a
    document handed to the command line (``documents.load_or_degrade``) -- the
    same carrier either way.

    ``code`` is a registered refusal (``UnknownTimezone`` is one), ``field`` the
    one that fails, ``detail`` the sentence an operator reads.
    """

    code: str
    field: str
    detail: str

    def describe(self) -> str:
        return f"{self.code} [{self.field}]: {self.detail}"


class Refused(Exception):
    """The module will not do this, and says which field is why.

    Carries the code so a caller can branch on it without parsing prose, the
    field it names so an owner's screen can point at it, and the sentence so a
    person reading a log does not have to look the code up.
    """

    def __init__(self, code: str, field: str, detail: str) -> None:
        if code not in REFUSALS:
            raise KeyError(
                f"{code!r} is not a registered refusal. Add it to findings.REFUSALS "
                "with the sentence an operator should read; the contract document "
                "and its test are generated from that registry, so a code invented "
                "at the raise site would be published nowhere and tested by nothing."
            )
        self.code = code
        self.field = field
        self.detail = detail
        super().__init__(f"{code} [{field}]: {REFUSALS[code]} — {detail}")

    def as_unreadable(self) -> Unreadable:
        return Unreadable(code=self.code, field=self.field, detail=self.detail)


# --------------------------------------------------------------------------
# Refusals. The module will not do what it was asked, and names the field.
# --------------------------------------------------------------------------

REFUSAL_VALID_TO_BEFORE_VALID_FROM = "REFUSAL_VALID_TO_BEFORE_VALID_FROM"
REFUSAL_WINDOW_HAS_NO_DAYS = "REFUSAL_WINDOW_HAS_NO_DAYS"
REFUSAL_WINDOW_DAY_UNKNOWN = "REFUSAL_WINDOW_DAY_UNKNOWN"
REFUSAL_WINDOW_MINUTE_OUT_OF_RANGE = "REFUSAL_WINDOW_MINUTE_OUT_OF_RANGE"
REFUSAL_WINDOW_ENDS_BEFORE_IT_STARTS = "REFUSAL_WINDOW_ENDS_BEFORE_IT_STARTS"
REFUSAL_WINDOW_NEVER_OCCURS = "REFUSAL_WINDOW_NEVER_OCCURS"
REFUSAL_MAX_STAY_NOT_POSITIVE = "REFUSAL_MAX_STAY_NOT_POSITIVE"
REFUSAL_VISIT_ALLOWANCE_NOT_POSITIVE = "REFUSAL_VISIT_ALLOWANCE_NOT_POSITIVE"
REFUSAL_ALLOWANCE_PER_WINDOW_WITHOUT_WINDOWS = "REFUSAL_ALLOWANCE_PER_WINDOW_WITHOUT_WINDOWS"
REFUSAL_NO_DIRECTIONS = "REFUSAL_NO_DIRECTIONS"
REFUSAL_LANES_STATED_BUT_EMPTY = "REFUSAL_LANES_STATED_BUT_EMPTY"
REFUSAL_LANE_NAME_BLANK = "REFUSAL_LANE_NAME_BLANK"
REFUSAL_FIELD_BLANK = "REFUSAL_FIELD_BLANK"
REFUSAL_HOLDER_EMAIL_MALFORMED = "REFUSAL_HOLDER_EMAIL_MALFORMED"
REFUSAL_UNKNOWN_FIELD = "REFUSAL_UNKNOWN_FIELD"
REFUSAL_STATE_UNKNOWN = "REFUSAL_STATE_UNKNOWN"
REFUSAL_STATE_TRANSITION_NOT_ALLOWED = "REFUSAL_STATE_TRANSITION_NOT_ALLOWED"
REFUSAL_REVOKED_IS_TERMINAL = "REFUSAL_REVOKED_IS_TERMINAL"
REFUSAL_EXPIRED_IS_DERIVED = "REFUSAL_EXPIRED_IS_DERIVED"
REFUSAL_STATE_CHANGE_NEEDS_WHO_AND_WHY = "REFUSAL_STATE_CHANGE_NEEDS_WHO_AND_WHY"
REFUSAL_REPAIR_NEEDS_WHO_AND_WHY = "REFUSAL_REPAIR_NEEDS_WHO_AND_WHY"
REFUSAL_VEHICLE_ON_ANOTHER_PASS = "REFUSAL_VEHICLE_ON_ANOTHER_PASS"
REFUSAL_PASS_NOT_REGISTRABLE = "REFUSAL_PASS_NOT_REGISTRABLE"
REFUSAL_REGISTRATION_OUTLIVES_THE_PASS = "REFUSAL_REGISTRATION_OUTLIVES_THE_PASS"
REFUSAL_REGISTRATION_ENDS_BEFORE_IT_STARTS = "REFUSAL_REGISTRATION_ENDS_BEFORE_IT_STARTS"
REFUSAL_REGISTRATION_NOT_FOUND = "REFUSAL_REGISTRATION_NOT_FOUND"
REFUSAL_REGISTRATION_ALREADY_ENDED = "REFUSAL_REGISTRATION_ALREADY_ENDED"
REFUSAL_PASS_NOT_FOUND = "REFUSAL_PASS_NOT_FOUND"
REFUSAL_GARAGE_NOT_FOUND = "REFUSAL_GARAGE_NOT_FOUND"
REFUSAL_PASS_ALREADY_EXISTS = "REFUSAL_PASS_ALREADY_EXISTS"
REFUSAL_GARAGE_ALREADY_EXISTS = "REFUSAL_GARAGE_ALREADY_EXISTS"
REFUSAL_TIMEZONE_UNKNOWN = "REFUSAL_TIMEZONE_UNKNOWN"
REFUSAL_DOCUMENT_UNREADABLE = "REFUSAL_DOCUMENT_UNREADABLE"
REFUSAL_GARAGE_MISMATCH = "REFUSAL_GARAGE_MISMATCH"
REFUSAL_NO_OPEN_VISIT = "REFUSAL_NO_OPEN_VISIT"
REFUSAL_VISIT_ALREADY_OPEN = "REFUSAL_VISIT_ALREADY_OPEN"
REFUSAL_EXIT_BEFORE_ENTRY = "REFUSAL_EXIT_BEFORE_ENTRY"
REFUSAL_CONSTRAINT = "REFUSAL_CONSTRAINT"
REFUSAL_FIELD_WRONG_TYPE = "REFUSAL_FIELD_WRONG_TYPE"
REFUSAL_TENANT_NOT_FOUND = "REFUSAL_TENANT_NOT_FOUND"
# --- enrolment (G2): the credential, where it may be redeemed, its refusals ---
REFUSAL_ENROLS_AT_CONTRADICTS_TRANSIENT = "REFUSAL_ENROLS_AT_CONTRADICTS_TRANSIENT"
REFUSAL_WHERE_TO_ENROL_UNSTATED = "REFUSAL_WHERE_TO_ENROL_UNSTATED"
REFUSAL_ENROLMENT_AT_WRONG_END = "REFUSAL_ENROLMENT_AT_WRONG_END"
REFUSAL_DAYS_VALID_NOT_STATED = "REFUSAL_DAYS_VALID_NOT_STATED"
REFUSAL_DAYS_VALID_NOT_POSITIVE = "REFUSAL_DAYS_VALID_NOT_POSITIVE"
REFUSAL_ENROLMENT_EXPIRED_IS_DERIVED = "REFUSAL_ENROLMENT_EXPIRED_IS_DERIVED"
REFUSAL_CREDENTIAL_UNKNOWN = "REFUSAL_CREDENTIAL_UNKNOWN"
REFUSAL_CREDENTIAL_ALREADY_USED = "REFUSAL_CREDENTIAL_ALREADY_USED"
REFUSAL_CREDENTIAL_CANCELLED = "REFUSAL_CREDENTIAL_CANCELLED"
REFUSAL_CREDENTIAL_EXPIRED = "REFUSAL_CREDENTIAL_EXPIRED"
REFUSAL_CREDENTIAL_NOT_STARTED = "REFUSAL_CREDENTIAL_NOT_STARTED"
REFUSAL_CREDENTIAL_ALREADY_EXISTS = "REFUSAL_CREDENTIAL_ALREADY_EXISTS"
REFUSAL_LANE_OUTSIDE_THE_PASS_TERMS = "REFUSAL_LANE_OUTSIDE_THE_PASS_TERMS"
REFUSAL_DIRECTION_OUTSIDE_THE_PASS_TERMS = "REFUSAL_DIRECTION_OUTSIDE_THE_PASS_TERMS"
REFUSAL_TEXT_HAS_CONTROL_CHARACTERS = "REFUSAL_TEXT_HAS_CONTROL_CHARACTERS"
# --- a pass spans many garages (G3a): the set, and the lanes stated per garage ---
REFUSAL_PASS_NAMES_NO_GARAGE = "REFUSAL_PASS_NAMES_NO_GARAGE"
REFUSAL_LANES_NOT_STATED_FOR_GARAGE = "REFUSAL_LANES_NOT_STATED_FOR_GARAGE"
REFUSAL_LANES_AT_A_GARAGE_THE_PASS_DOES_NOT_NAME = (
    "REFUSAL_LANES_AT_A_GARAGE_THE_PASS_DOES_NOT_NAME"
)
REFUSAL_LANES_GARAGE_REPEATED = "REFUSAL_LANES_GARAGE_REPEATED"

REFUSALS: dict[str, str] = {
    REFUSAL_VALID_TO_BEFORE_VALID_FROM: (
        "The pass ends before it starts: valid_to is earlier than valid_from. There "
        "is no day on which such a pass could cover anything, so it is not created."
    ),
    REFUSAL_WINDOW_HAS_NO_DAYS: (
        "A recurring window names no day of the week. A window that occurs on no "
        "day can never be satisfied; state at least one day, or remove the window."
    ),
    REFUSAL_WINDOW_DAY_UNKNOWN: (
        "A recurring window names a day that is not 1 (Monday) to 7 (Sunday)."
    ),
    REFUSAL_WINDOW_MINUTE_OUT_OF_RANGE: (
        "A window's start or end is outside 0 to 1440 minutes from local midnight. "
        "1440 means the end of the day."
    ),
    REFUSAL_WINDOW_ENDS_BEFORE_IT_STARTS: (
        "A recurring window ends at or before the minute it starts, so it is empty. "
        "A window that runs past midnight is two windows: one to 1440 on the first "
        "day and one from 0 on the next."
    ),
    REFUSAL_WINDOW_NEVER_OCCURS: (
        "None of the days a recurring window names falls inside the pass's valid "
        "range, so the window can never be satisfied. Widen the range or change the "
        "days."
    ),
    REFUSAL_MAX_STAY_NOT_POSITIVE: (
        "The maximum stay is zero or negative. A pass that allows no time inside "
        "covers nothing; state a positive duration, or no maximum."
    ),
    REFUSAL_VISIT_ALLOWANCE_NOT_POSITIVE: (
        "The visit allowance is zero or negative. A pass allowing no visits covers "
        "nothing; state a positive count, or no allowance."
    ),
    REFUSAL_ALLOWANCE_PER_WINDOW_WITHOUT_WINDOWS: (
        "The visit allowance is counted per window and the pass has no windows, so "
        "there is nothing to count it against."
    ),
    REFUSAL_NO_DIRECTIONS: (
        "The pass states no direction. Nothing is implicit: a privilege the terms "
        "do not state does not exist, so a pass that names neither entry nor exit "
        "covers nothing."
    ),
    REFUSAL_LANES_STATED_BUT_EMPTY: (
        "The allowed lanes are stated as an empty set -- no garage at all, or no lane at "
        "one of the garages. Absent means every lane at every garage the pass names; an "
        "empty set means no lane, which covers nothing."
    ),
    REFUSAL_LANE_NAME_BLANK: ("A lane name is blank."),
    REFUSAL_FIELD_BLANK: (
        "A required field is blank. The field is named beside this code."
    ),
    REFUSAL_HOLDER_EMAIL_MALFORMED: (
        "The holder's email address does not look like one -- it needs an @ with "
        "something before it and something after it. The email is the holder's "
        "identity in this "
        "module, so a malformed one identifies nobody."
    ),
    REFUSAL_UNKNOWN_FIELD: (
        "A document carries a field this module does not know. It is refused "
        "rather than ignored: a field silently dropped is a term the owner believes "
        "is in force and is not."
    ),
    REFUSAL_STATE_UNKNOWN: (
        "The state named is not one this module has."
    ),
    REFUSAL_STATE_TRANSITION_NOT_ALLOWED: (
        "The pass cannot move from its current state to the one asked for. The "
        "allowed moves are published in the contract."
    ),
    REFUSAL_REVOKED_IS_TERMINAL: (
        "A revoked pass is revoked. It never becomes active again; a new pass is a "
        "new pass."
    ),
    REFUSAL_EXPIRED_IS_DERIVED: (
        "Expired is derived from the pass's valid_to and is never typed by anyone. "
        "To end a pass early, revoke it; to end it on a day, that day is valid_to."
    ),
    REFUSAL_STATE_CHANGE_NEEDS_WHO_AND_WHY: (
        "A state change records who made it and why, and one of those is blank."
    ),
    REFUSAL_REPAIR_NEEDS_WHO_AND_WHY: (
        "A garage repair -- set-garage-timezone, which changes how every pass at the "
        "garage is read -- records who made it, when and why into an append-only "
        "history, and one of who or why is blank. The repair is refused and nothing "
        "changes: a change to every clock in the building with no record of who made "
        "it is the one write this module would not be able to explain afterwards."
    ),
    REFUSAL_VEHICLE_ON_ANOTHER_PASS: (
        "This vehicle identity is already registered to another pass, at one of the "
        "garages the target pass names, for days that overlap. One car, one pass per "
        "garage: a registration is written at EVERY garage the pass names, together or "
        "not at all, and the refusal names the garage where the identity is held, the "
        "pass that holds it and the day that registration ends. End that registration "
        "first, or register from the day it ends."
    ),
    REFUSAL_PASS_NOT_REGISTRABLE: (
        "A vehicle may be registered onto a pass that is draft, awaiting enrolment "
        "or active. This pass is not: the detail names its state. A suspended pass "
        "is a hold, and a car added to a hold is a claim the owner did not make; a "
        "revoked pass is revoked; an expired pass -- derived from its valid_to "
        "against the registration's effective day -- is over."
    ),
    REFUSAL_REGISTRATION_OUTLIVES_THE_PASS: (
        "The registration's end day is past the pass's valid_to. A vehicle cannot "
        "be on a pass on a day the pass does not cover; leave end_day unstated and "
        "it runs to the pass's last day."
    ),
    REFUSAL_REGISTRATION_ENDS_BEFORE_IT_STARTS: (
        "The registration ends on or before the day it takes effect, so it covers "
        "no day."
    ),
    REFUSAL_REGISTRATION_NOT_FOUND: (
        "No registration of that vehicle on that pass."
    ),
    REFUSAL_REGISTRATION_ALREADY_ENDED: (
        "That registration already has an end day. A registration is ended once; "
        "to move the day, that is a new registration."
    ),
    REFUSAL_PASS_NOT_FOUND: (
        "No pass with that id names that garage in this tenant. Where the pass exists and "
        "names other garages, the detail says which."
    ),
    REFUSAL_GARAGE_NOT_FOUND: ("No garage with that id in this tenant."),
    REFUSAL_PASS_ALREADY_EXISTS: (
        "A pass with that id already exists in this tenant. A pass's id is unique per "
        "tenant, not per garage: a pass that spans garages cannot be identified by one."
    ),
    REFUSAL_GARAGE_ALREADY_EXISTS: ("A garage with that id already exists in this tenant."),
    REFUSAL_TIMEZONE_UNKNOWN: (
        "The timezone named is not an IANA name this system carries. It is refused "
        "rather than defaulted to UTC: a pass evaluated on UTC clocks crosses its own "
        "window edges by hours, and nothing in the answer would say so. The detail "
        "names the value; a garage already stored with one is repaired with "
        "set-garage-timezone."
    ),
    REFUSAL_DOCUMENT_UNREADABLE: (
        "A document named on the command line could not be read: the file is "
        "missing, not a regular file, unreadable, not JSON, or JSON the decoder "
        "cannot decode (nested deeper than it can read, or a number longer than it "
        "will convert). The detail names the path and what went wrong."
    ),
    REFUSAL_GARAGE_MISMATCH: (
        "A pass names the garages it answers at, and was asked about a garage it does not "
        "name -- to be stored there, or a QR or holder link of it presented there. The "
        "detail names the garage asked for and the pass's own set. Nothing is written."
    ),
    REFUSAL_NO_OPEN_VISIT: (
        "No recorded entry of this vehicle on this pass at this garage is still open, "
        "so there is no visit for this exit to close. The ledger is per garage: an "
        "entry recorded at another garage of the pass is not the one this exit closes."
    ),
    REFUSAL_VISIT_ALREADY_OPEN: (
        "A recorded entry of this vehicle on this pass at this garage is still open. "
        "Record its exit before recording another entry here, or the visit ledger "
        "would hold a car inside this garage twice. A visit still open at another "
        "garage of the pass does not refuse an entry here."
    ),
    REFUSAL_EXIT_BEFORE_ENTRY: (
        "The exit instant is earlier than the entry it would close."
    ),
    REFUSAL_CONSTRAINT: (
        "The database refused the write by a constraint the module did not catch "
        "first, or rolled it back to break a deadlock at that constraint's lock. "
        "Named by its constraint so it is a refusal and not a traceback; two writers "
        "racing end here. Under a deadlock the detail carries the database's own "
        "account of the cycle and asserts no cause the module did not observe."
    ),
    REFUSAL_FIELD_WRONG_TYPE: (
        "A document field carries a value of the wrong type -- text where a list "
        "belongs, a number where text belongs, an object where an id belongs. The "
        "document is refused naming the field, the type it declares and the value; "
        "it is never reinterpreted (text is not read as a list of its characters) and "
        "never a traceback. The check is derived from the dataclass the document loads "
        "into, so a field added later is covered the day it is added."
    ),
    REFUSAL_TENANT_NOT_FOUND: (
        "No tenant row has the id given. The first write for a tenant -- create-garage "
        "-- reads the tenant row before it writes, so an id nobody seeded is refused by "
        "name rather than met at the database's foreign key."
    ),
    REFUSAL_ENROLS_AT_CONTRADICTS_TRANSIENT: (
        "The garage sells no transient parking and is stated to enrol at its exit. At a "
        "garage with no transient an unregistered vehicle is not admitted, so the "
        "registration must happen at the entry; enrolling at the exit there is a "
        "contradiction. Refused where the garage is created and where the field is "
        "repaired; the schema's CHECK is the backstop for a raw write."
    ),
    REFUSAL_WHERE_TO_ENROL_UNSTATED: (
        "A redemption cannot tell whether this lane is the end this garage enrols at. "
        "The field named beside this code is the one that would say: "
        "garage.transient_available decides first (a garage with no transient enrols at "
        "entry, derived, and need state nothing more); a transient garage has a choice "
        "and states it in garage.enrols_at. There is no default and no inference."
    ),
    REFUSAL_ENROLMENT_AT_WRONG_END: (
        "The QR was presented at the wrong end: this garage enrols at the end named in "
        "the detail, and this lane is the other. Nothing is written. The movement itself "
        "still gets its access answer -- and an exit is never refused."
    ),
    REFUSAL_DAYS_VALID_NOT_STATED: (
        "The credential's days_valid is not stated. It is refused rather than defaulted: "
        "this module refuses guessed defaults, and how long a QR may wait to be redeemed "
        "is the owner's to state (the monthly-parker product uses three days from the "
        "starting day; that is its number, not this module's)."
    ),
    REFUSAL_DAYS_VALID_NOT_POSITIVE: (
        "The credential's days_valid is zero or negative, so there is no day on which it "
        "could be redeemed. State a positive whole number of days."
    ),
    REFUSAL_ENROLMENT_EXPIRED_IS_DERIVED: (
        "A credential's 'expired' is derived from its starts_on and days_valid against "
        "the garage's local day and is never typed by anyone. To end one early, revoke "
        "the pass it belongs to; to end it on a day, that day is starts_on plus days_valid."
    ),
    REFUSAL_CREDENTIAL_UNKNOWN: (
        "No enrolment or holder link in this tenant matches the token presented. The "
        "token itself is never rendered and never stored: only its SHA-256 is compared."
    ),
    REFUSAL_CREDENTIAL_ALREADY_USED: (
        "This credential was already redeemed. An enrolment is one QR, one car: it binds "
        "exactly one vehicle identity and is then terminal; a holder link is used once. "
        "The detail names the credential and when it was redeemed. Nothing is written."
    ),
    REFUSAL_CREDENTIAL_CANCELLED: (
        "This credential was cancelled -- the pass it opens was revoked, and a credential "
        "must not outlive the pass. The detail names when and why. Nothing is written."
    ),
    REFUSAL_CREDENTIAL_EXPIRED: (
        "This credential's window has passed: its last day, starts_on plus days_valid "
        "less one, is before today in the garage's local day. Derived; nobody typed it. "
        "Nothing is written; issue a new one."
    ),
    REFUSAL_CREDENTIAL_NOT_STARTED: (
        "This credential's starts_on is after today in the garage's local day. Nothing "
        "is written; present it from that day."
    ),
    REFUSAL_CREDENTIAL_ALREADY_EXISTS: (
        "An enrolment or holder link with that id already exists in this tenant."
    ),
    REFUSAL_LANE_OUTSIDE_THE_PASS_TERMS: (
        "The pass names the lanes it may use, and the lane this QR was presented at is "
        "not one of them. Nothing is implicit: the pass carries its own terms, and a "
        "redemption at a lane they do not name is refused naming the lane and the set. "
        "The owner's fix is to state the lane on the pass. Nothing is written."
    ),
    REFUSAL_DIRECTION_OUTSIDE_THE_PASS_TERMS: (
        "The pass's terms allow no movement in the direction this garage enrols at, so "
        "the QR would be spent on a movement the pass can never cover. Refused by name, "
        "beside the lane refusal, before anything is written: the credential stays "
        "issued for a movement the pass can cover. ONLY a STRUCTURAL exclusion refuses "
        "-- the direction, or the lane outside the stated set. Temporal non-coverage "
        "(a weekend on a weekday pass, a valid_from still ahead, a movement outside the "
        "hours) still BINDS: enrolling at the weekend is the ordinary case."
    ),
    REFUSAL_TEXT_HAS_CONTROL_CHARACTERS: (
        "A text field carries a control character INSIDE it -- a NUL, a line break, a tab "
        "or another character whose Unicode category is Cc, between its first and last "
        "non-blank characters. Refused by name wherever the module reads text, so a driver "
        "never turns it into a configuration-class sentence. Whitespace at either edge was "
        "never part of the text and is removed before the check: the ten Cc code points "
        "Python counts as whitespace (TAB, LF, VT, FF, CR, U+001C to U+001F and U+0085) are "
        "stripped there, and NUL is never whitespace and never stripped. Letters in any "
        "script are text and are accepted."
    ),
    REFUSAL_PASS_NAMES_NO_GARAGE: (
        "The pass names no garage. A pass carries a non-empty SET of the garages it answers "
        "at -- stated by listing them, never an 'everywhere' flag and never inferred -- and "
        "a pass naming none would answer nowhere. A string where the list belongs is refused "
        "the same way, never read as a set of its characters."
    ),
    REFUSAL_LANES_NOT_STATED_FOR_GARAGE: (
        "The pass states its lanes, and one of the garages it names has no lane stated "
        "there. Lanes are stated PER GARAGE -- lane A1 at two garages is two barriers -- and "
        "a garage with none, on a pass whose lanes are stated, would be an implicit empty "
        "set: no lane at all. Nothing here is implicit; the detail names the garage."
    ),
    REFUSAL_LANES_AT_A_GARAGE_THE_PASS_DOES_NOT_NAME: (
        "The pass states lanes at a garage it does not name, so those lanes could never be "
        "used. The detail names the garage and the pass's own set; the database's key backs "
        "it for a raw write."
    ),
    REFUSAL_LANES_GARAGE_REPEATED: (
        "The pass states lanes for one garage twice. One entry per garage: a garage named "
        "twice with two sets is a contradiction the module will not merge."
    ),
}


# --------------------------------------------------------------------------
# Not-covered reasons. The module CAN answer, and the answer is no.
# --------------------------------------------------------------------------

NO_PASS = "NO_PASS"
NOT_ACTIVE = "NOT_ACTIVE"
NOT_STARTED = "NOT_STARTED"
EXPIRED = "EXPIRED"
SUSPENDED = "SUSPENDED"
REVOKED = "REVOKED"
DIRECTION_NOT_ALLOWED = "DIRECTION_NOT_ALLOWED"
WRONG_LANE = "WRONG_LANE"
OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
OUT_OF_VISITS = "OUT_OF_VISITS"
OVER_MAX_STAY = "OVER_MAX_STAY"
PASS_UNREADABLE = "PASS_UNREADABLE"
GARAGE_UNREADABLE = "GARAGE_UNREADABLE"
BLANK_IDENTITY = "BLANK_IDENTITY"
BLANK_LANE = "BLANK_LANE"
PASS_NOT_HANDED_IN = "PASS_NOT_HANDED_IN"
PASS_DUPLICATED = "PASS_DUPLICATED"
RECORD_UNREADABLE = "RECORD_UNREADABLE"

NOT_COVERED_REASONS: dict[str, str] = {
    NO_PASS: (
        "No pass that names this garage has this vehicle registered on this day. Where a "
        "registration once existed and has ended, the detail says which pass and "
        "when. A pass answers only at the garages it names: at any other it is not "
        "this garage's business, and the vehicle is answered as any unknown one."
    ),
    NOT_ACTIVE: (
        "The pass this vehicle is registered to has not been activated: it is a "
        "draft, or it is awaiting enrolment."
    ),
    NOT_STARTED: ("The pass's valid_from is after this day."),
    EXPIRED: (
        "The pass's valid_to is before this day. Derived from the terms; nobody "
        "typed it."
    ),
    SUSPENDED: ("The owner has put the pass on hold. The hold is reversible."),
    REVOKED: ("The pass was revoked. Revocation is terminal."),
    DIRECTION_NOT_ALLOWED: ("The pass's terms do not state this direction."),
    WRONG_LANE: (
        "The pass's terms name the lanes it may use AT THIS GARAGE, and this is not one. "
        "Lanes are stated per garage; a lane the pass allows at another of its garages "
        "is another barrier."
    ),
    OUTSIDE_WINDOW: (
        "The pass has recurring windows and this instant, in the garage's local "
        "day, is inside none of them."
    ),
    OUT_OF_VISITS: (
        "The pass's visit allowance is used up. The detail says how many were "
        "counted, out of how many, and over what."
    ),
    OVER_MAX_STAY: (
        "This exit comes later after the recorded entry than the pass's maximum "
        "stay allows. Measured in elapsed time between the two instants, not in "
        "wall-clock hours."
    ),
    PASS_UNREADABLE: (
        "The pass this vehicle is registered to carries a value this module "
        "refuses to read -- terms or a holder that would be refused at creation, a "
        "holder or terms field that is missing or of the wrong type, or a field this "
        "module does not know. "
        "Reached by a stored row (a raw write, or a validator tightened after the "
        "pass was stored) and, at an EXIT, by a pass document handed to the command "
        "line whose id, garage, label and state read. The detail names the pass and "
        "the field. At an EXIT this is "
        "out-of-terms and therefore chargeable at a transient garage: stated so "
        "nobody reads it as a free exit, and named so an operator can find the row "
        "and undo the charge."
    ),
    GARAGE_UNREADABLE: (
        "The garage carries a value this module refuses to read -- a stored row "
        "whose timezone this system does not carry, or, at an EXIT, a garage document "
        "handed to the command line whose id, timezone and transient mode read but "
        "which is refused for any reason (an unknown zone, an unknown field). Without "
        "a clock no window, day or registration range can be evaluated, so it is "
        "answered ahead of every term. At an EXIT this is out-of-terms; at an entry "
        "the call refuses to answer."
    ),
    BLANK_IDENTITY: (
        "The vehicle identity is blank at an EXIT, so there is nothing to look up -- "
        "and an exit is answered, never refused. At an entry the same input is refused "
        "an answer."
    ),
    BLANK_LANE: (
        "The lane is blank at an EXIT, so lane terms cannot be evaluated -- and an "
        "exit is answered, never refused. At an entry the same input is refused an "
        "answer."
    ),
    PASS_NOT_HANDED_IN: (
        "A registration of this vehicle, in force on this day, names a pass that was "
        "not handed in with the call -- the registrations and the passes disagree, "
        "which is INCONSISTENT data, not a term, a state or a revocation. At an EXIT "
        "it is answered, never raised: not-covered, naming the pass the registration "
        "names, so an integrator assembling registrations from their own store can "
        "see which one. Where another registration in force names a pass that was "
        "handed in, that pass is evaluated and covers the vehicle if it covers it, "
        "with the inconsistency named in the detail. (At an entry the call refuses to "
        "answer, naming the field.) The store cannot produce this: it loads the "
        "passes its registrations name."
    ),
    PASS_DUPLICATED: (
        "The pass this vehicle is registered to was handed in more than once under "
        "one id, and no copy covers this exit. Two passes carrying one id is "
        "INCONSISTENT data: the module never picks a copy, whatever the order they "
        "arrived in. At an EXIT every copy is evaluated -- the vehicle is covered if "
        "any copy covers it, the duplication named -- and where none does, this is the "
        "reason, with each copy's own reason in the detail. (At an entry the call "
        "refuses to answer, naming the id.) The store cannot produce this: one id, one "
        "pass, per garage."
    ),
    RECORD_UNREADABLE: (
        "A record handed in with the call at an EXIT cannot be read as what it claims to "
        "be -- a registration or a visit document with a field missing, of the wrong "
        "type or unknown, or a pass or garage document too malformed to carry the marker "
        "a stored row would (its id, garage, label or state unreadable). The module holds "
        "the record and cannot read its content, so the exit is ANSWERED, never refused: "
        "not-covered, naming the document and the field so the integrator can find it, "
        "with the exit note and the OUT-OF-TERMS meaning every exit answer carries -- at "
        "a transient garage chargeable, said so. A pass or garage document whose carrier "
        "fields read is not this: it degrades to the unreadable pass or garage a stored "
        "row becomes, and answers PASS_UNREADABLE or GARAGE_UNREADABLE only if the "
        "vehicle is on it. (At an entry the same document is refused by name. The module "
        "refuses only when it holds no record at all -- a file that is missing, not a "
        "regular file, or cannot be read as JSON -- or no instant to read it at.)"
    ),
}


# --------------------------------------------------------------------------
# What a not-covered answer means where the car is standing.
# --------------------------------------------------------------------------

MEANS_TRANSIENT_STAY = "TRANSIENT_STAY"
MEANS_NOTHING_TO_ADMIT_AS = "NOTHING_TO_ADMIT_AS"
MEANS_EXIT_OUT_OF_TERMS = "EXIT_OUT_OF_TERMS"
MEANS_COVERED = "COVERED"

BARRIER_MEANINGS: dict[str, str] = {
    MEANS_COVERED: (
        "The pass covers this movement. The lane acts on that; this module opens "
        "nothing."
    ),
    MEANS_TRANSIENT_STAY: (
        "Not covered at ENTRY, at a garage that sells transient parking: this is an "
        "ordinary paying customer. The lane treats it as one."
    ),
    MEANS_NOTHING_TO_ADMIT_AS: (
        "Not covered at ENTRY, at a garage that sells NO transient parking: there is "
        "nothing for this vehicle to be admitted as. The lane does not admit it."
    ),
    MEANS_EXIT_OUT_OF_TERMS: (
        "Not covered at EXIT. AN EXIT IS NEVER REFUSED: no term, no state and no "
        "revocation keeps a vehicle inside a garage. This exit is outside the pass's "
        "terms and is answered, recorded and reported as such -- at a transient "
        "garage that is what makes the stay chargeable."
    ),
}

#: The sentence every EXIT answer carries. An exit's outcome is always covered
#: or not covered -- refused-to-answer is not an outcome an exit can have. It is
#: the guarantee in one line.
EXIT_IS_NEVER_REFUSED = (
    "An exit is never refused. Whatever this answer says, the vehicle leaves."
)


# --------------------------------------------------------------------------
# Refused to answer. The call cannot answer without guessing.
# --------------------------------------------------------------------------

MISSING_TRANSIENT_MODE = "garage.transient_available"
MISSING_VEHICLE_IDENTITY = "vehicle_identity"
MISSING_LANE = "lane"
MISSING_ONE_PASS = "registration.pass_id"
MISSING_TIMEZONE = "garage.timezone"
UNREADABLE_TERMS = "pass.terms"
MISSING_PASS_HANDED_IN = "passes"
DUPLICATED_PASS_ID = "passes[].id"
MISSING_GARAGE_HANDED_IN = "garages"
DUPLICATED_GARAGE_ID = "garages[].id"

REFUSED_TO_ANSWER: dict[str, str] = {
    MISSING_TRANSIENT_MODE: (
        "The garage has not stated whether transient parking is available. There "
        "is no default and no inference: with it unstated, an uncovered entry is "
        "either an ordinary paying customer or a vehicle with nothing to be admitted "
        "as, and guessing between those is the difference between a car let in free "
        "and a fired employee driving into a building. State it on the garage."
    ),
    MISSING_VEHICLE_IDENTITY: (
        "The vehicle identity is blank at an ENTRY, so there is nothing to look up. "
        "An unknown identity gets a stated answer; a missing one gets none. (At an "
        "exit the same input is answered not-covered: an exit is never refused.)"
    ),
    MISSING_LANE: (
        "The lane is blank at an ENTRY, so lane terms cannot be evaluated. (At an "
        "exit the same input is answered not-covered.)"
    ),
    MISSING_ONE_PASS: (
        "More than one pass at this garage has this vehicle registered on this "
        "day, at an ENTRY. The module refuses to pick one. That state cannot be "
        "produced through this module; it was handed in or written raw. (At an exit "
        "every one of them is evaluated and the vehicle is covered if any covers it, "
        "the inconsistency named.)"
    ),
    MISSING_TIMEZONE: (
        "The garage is stored with a timezone this system does not carry, and an "
        "ENTRY cannot be evaluated without a clock. (An exit is answered "
        "not-covered, naming the field.)"
    ),
    UNREADABLE_TERMS: (
        "The pass this vehicle is registered to is stored with terms or a holder "
        "this module refuses to read, and an ENTRY on it is not guessed. The detail "
        "names the pass and the field. (An exit is answered not-covered, naming both.)"
    ),
    MISSING_PASS_HANDED_IN: (
        "A registration of this vehicle, in force on this day, names a pass that is "
        "not among the passes handed in, at an ENTRY. The registrations and the "
        "passes disagree and the module will not guess which is right: hand in the "
        "pass the registration names, or the registrations that match the passes. "
        "(At an exit the vehicle is answered not-covered naming that pass -- or "
        "covered by another pass in force that was handed in, the inconsistency "
        "named. An exit is never refused and never raises on data.)"
    ),
    DUPLICATED_PASS_ID: (
        "The pass this vehicle is registered to was handed in more than once under one "
        "id, at an ENTRY -- whether or not the copies agree, since the caller who sent "
        "one id twice does not know which they meant, and the module will not resolve "
        "an inconsistency it should be naming. Measured before this: the LAST copy in "
        "the list won silently, so the same inputs in a different order admitted or "
        "refused the same car. Hand in each pass once. (At an exit every copy is "
        "evaluated and the vehicle is covered if any covers it, the duplication named.)"
    ),
    MISSING_GARAGE_HANDED_IN: (
        "A per-window visit allowance counts each recorded entry in the local day of "
        "THE GARAGE IT WAS RECORDED AT -- a pass names a set of garages, and two of "
        "them can stand in different zones -- and an entry on this pass was recorded at "
        "a garage that is not among the garages handed in, so its day and window cannot "
        "be read. The module will not read it on this garage's clock instead: measured "
        "before this, a visit at a Tokyo garage read on a Denver clock fell on the day "
        "before and a one-per-window allowance was spent twice. Hand in every garage the "
        "pass names. (Only an ENTRY counts the allowance, so no exit reaches this.)"
    ),
    DUPLICATED_GARAGE_ID: (
        "The garage an entry on this pass was recorded at was handed in more than once "
        "under one id, at an ENTRY that must read that entry on that garage's clock -- "
        "whether or not the copies agree, since the caller who sent one id twice does "
        "not know which they meant. Hand in each garage once. (Only an ENTRY counts the "
        "allowance, so no exit reaches this.)"
    ),
}
