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
    """A stored value this module refuses to read -- carried on the pass or the
    garage it came from instead of raised, so an access call about it produces a
    STATED answer and never an exception. Reached by a raw write, or by a
    validator tightened after the row was stored.

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
        "The allowed lanes are stated as an empty set. Absent means every lane; an "
        "empty set means no lane, which covers nothing."
    ),
    REFUSAL_LANE_NAME_BLANK: ("A lane name is blank."),
    REFUSAL_FIELD_BLANK: (
        "A required field is blank. The field is named beside this code."
    ),
    REFUSAL_HOLDER_EMAIL_MALFORMED: (
        "The holder's email address does not look like one -- it needs one @ with "
        "something on both sides. The email is the holder's identity in this "
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
        "This vehicle identity is already registered to another pass at this "
        "garage for days that overlap. One car, one pass: the refusal names the "
        "pass that holds it and the day that registration ends. End that "
        "registration first, or register from the day it ends."
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
    REFUSAL_PASS_NOT_FOUND: ("No pass with that id at that garage in this tenant."),
    REFUSAL_GARAGE_NOT_FOUND: ("No garage with that id in this tenant."),
    REFUSAL_PASS_ALREADY_EXISTS: ("A pass with that id already exists at that garage."),
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
        "missing, unreadable, or not JSON. The detail names the path and what went "
        "wrong."
    ),
    REFUSAL_GARAGE_MISMATCH: (
        "A pass belongs to one garage and was asked about another. One garage per "
        "pass is the stated shape."
    ),
    REFUSAL_NO_OPEN_VISIT: (
        "No recorded entry of this vehicle on this pass is still open, so there is "
        "no visit for this exit to close."
    ),
    REFUSAL_VISIT_ALREADY_OPEN: (
        "A recorded entry of this vehicle on this pass is still open. Record its "
        "exit before recording another entry, or the visit ledger would hold a car "
        "inside twice."
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

NOT_COVERED_REASONS: dict[str, str] = {
    NO_PASS: (
        "No pass at this garage has this vehicle registered on this day. Where a "
        "registration once existed and has ended, the detail says which pass and "
        "when."
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
    WRONG_LANE: ("The pass's terms name the lanes it may use, and this is not one."),
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
        "The pass this vehicle is registered to is stored with a value this module "
        "refuses to read -- terms or a holder that would be refused at creation. "
        "Reached only by a raw write or by a validator tightened after the pass was "
        "stored. The detail names the pass and the field. At an EXIT this is "
        "out-of-terms and therefore chargeable at a transient garage: stated so "
        "nobody reads it as a free exit, and named so an operator can find the row "
        "and undo the charge."
    ),
    GARAGE_UNREADABLE: (
        "The garage is stored with a timezone this system does not carry, so no "
        "window, day or registration range can be evaluated. Answered ahead of every "
        "term. At an EXIT this is out-of-terms; at an entry the call refuses to answer."
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
}
