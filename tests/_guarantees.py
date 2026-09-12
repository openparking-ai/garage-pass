"""The canonical registry of what this module guarantees.

**ONE SOURCE, THREE CONSUMERS.** ``conftest.py`` requires every registered id to
have RUN; ``scripts/fail_controls.py`` requires every registered id to have a
control PROVEN TO FAIL and refuses to run if one has none; ``docs/CONTRACT.md``
is generated from this file. A guarantee therefore cannot be quietly dropped from
any of the three, and a number of them cannot go stale in a comment, because
nothing types the number anywhere.

**A GUARANTEE IS A SENTENCE SOMEBODY COULD ACT ON.** Not "the validator checks
the terms" -- that is a description of a mechanism. "A contradiction between two
terms is refused when the pass is created, naming the field, and no contradiction
is ever resolved at the access call" is a claim with a failing case, and the
failing case is what the control plants.
"""

from __future__ import annotations

GUARANTEES: dict[str, str] = {
    "G1": (
        "ONE CAR, ONE PASS PER GARAGE. A vehicle identity is registered to one pass "
        "at a garage for any given day; a second registration overlapping it is "
        "refused BY NAME, naming the pass that holds the identity, its state and the "
        "day that registration ends, BEFORE the database constraint has to -- every "
        "open registration is a holder whatever its pass's state -- and a refusal "
        "writes nothing. The TARGET pass's state is read: a registration onto a "
        "suspended, revoked or expired pass is refused by name, naming the state; "
        "draft, awaiting enrolment and active take registrations. The database's "
        "EXCLUDE is the backstop for a raw insert and for two registrations "
        "genuinely racing -- in either shape the race takes, the constraint firing or "
        "the database rolling one writer back, the loser is refused by the constraint's "
        "name and never a traceback -- and is reached through the module by nothing "
        "else. Ending "
        "a registration on day D frees the identity FROM D: a registration elsewhere "
        "effective D is accepted, and the old pass covers the vehicle up to and not "
        "including D."
    ),
    "G2": (
        "Contradictory terms are refused AT CREATION, naming the field: a valid_to "
        "before valid_from, a window that no day in the valid range can satisfy, an "
        "empty window, a maximum stay of zero, a visit allowance of zero, a per-window "
        "allowance with no windows, no direction, an empty lane set -- and ONLY "
        "contradictions: a maximum stay longer than a window is slack, not a "
        "contradiction (windows bind instants, not stays), and such a pass is created "
        "and its maximum binds at the exit. A Terms value that fails the check cannot "
        "be constructed, so the access call never meets a contradiction. The schema's "
        "CHECKs back the single-table rules for a raw write; the three that span two "
        "tables are named in the migration and backed by the load path (G17)."
    ),
    "G3": (
        "No fee, no amount, no balance and no barrier command ever crosses the access "
        "call: the answer's fields carry none, the schema has no money-shaped or "
        "reservation-shaped column, and a document with a field this module does not "
        "know is refused rather than ignored. This module never opens or closes a "
        "gate and never counts who is inside."
    ),
    "G4": (
        "AN EXIT IS NEVER REFUSED, AND EVERY EXIT IS ANSWERED. No term, no state and "
        "no revocation refuses an exit to a vehicle that is inside: every exit produces "
        "a stated COVERED or NOT-COVERED answer -- refused-to-answer is not an outcome "
        "an exit can have, and the absence of an answer, a refusal and an exception are "
        "each a failure of this guarantee. Whatever cannot be evaluated at an exit is "
        "NAMED, never guessed: a blank identity or lane, an unmeasurable maximum stay, "
        "an unreadable pass or garage, two passes holding one car. Every exit answer "
        "carries the sentence that says so, a not-covered exit means OUT-OF-TERMS and "
        "never a refusal, in every state including revoked, and the exit half of the "
        "call does not read the garage's transient mode."
    ),
    "G5": (
        "A revoked pass is refused at ENTRY in every configuration of terms, and "
        "revocation is terminal: no transition leaves revoked, and revoking a pass "
        "ends its registrations on the revocation day in the garage's local calendar "
        "so the identity is free from that day."
    ),
    "G6": (
        "A garage that has not stated whether transient parking is available makes "
        "the access call REFUSE TO ANSWER at entry, naming the field. There is no "
        "default and no inference; the store keeps the field nullable so that unstated "
        "is a state and not a false."
    ),
    "G7": (
        "Terms evaluate in the GARAGE'S LOCAL DAY: a window's minutes are the garage's "
        "wall clock and its days are the garage's weekdays, measured at the window "
        "edges on the spring-forward and fall-back days where a UTC reading disagrees; "
        "and a stay's length is elapsed time between instants, computed in UTC, so a "
        "stay across the fall-back hour is an hour longer than its wall clocks say."
    ),
    "G8": (
        "An unknown vehicle identity gets a STATED answer -- not covered, NO_PASS, "
        "with the nearest ended or future registration named when there is one -- "
        "never an accidental refusal and never a silent pass. A BLANK identity is "
        "refused an answer AT AN ENTRY, naming the field, because there is nothing to "
        "look up; at an exit the same input is answered not-covered, naming the field."
    ),
    "G9": (
        "A visit allowance and a maximum stay are computed from the module's OWN "
        "recorded visits and from nothing else, and the answer names its denominator: "
        "how many entries were counted, on which pass, over its life or in which "
        "window on which day; and which entry a stay was measured from, both instants "
        "rendered as the garage's wall clock whatever offset each arrived with. A "
        "maximum stay with no open recorded entry to measure from is UNMEASURED and the "
        "answer says so by name while answering on the terms that can be evaluated -- "
        "never silently treated as satisfied, and never a refusal."
    ),
    "G10": (
        "Row-level security on every table from migration 0001: a tenant column, "
        "ENABLE, FORCE and a policy on each, read from the catalogue and never from a "
        "list; isolation proven ON EVERY TENANT-BEARING TABLE, from the catalogue, by a "
        "role that COULD bypass being shown it cannot read or write another tenant's "
        "rows -- and a stripped predicate on any one of the eight tables reddens it; "
        "and every garage and pass reference is half of a composite tenant key, so a "
        "row cannot name another tenant's garage or pass even by a raw insert."
    ),
    "G11": (
        "Nothing real in the tree: no email address that is not obviously invented, "
        "no card-shaped value, and no name from the maintainer's other software, in "
        "any file git tracks -- swept in Python over `git ls-files` with a positive "
        "control that fires before the result is read, and by CI guards that "
        "self-test the same way."
    ),
    "G12": (
        "Every state change records WHO, WHEN and WHY, none blank, into an "
        "append-only history: the application role holds SELECT and INSERT on it and "
        "nothing else, read from the catalogue and proven by a refused UPDATE -- and "
        "holds no DELETE on any table whose deletion cascades into it, the set read "
        "from the catalogue and walked transitively, so the history cannot be erased "
        "by deleting what it belongs to. The "
        "allowed transitions are the published ones, `expired` is derived from "
        "valid_to and refused if typed, and revoked outranks expiry."
    ),
    "G13": (
        "THE LABEL IS ONLY A LABEL. 'Monthly', 'employee', 'vendor' and the rest are "
        "free text the owner types, and no behaviour keys off them. THE PROOF IS THE "
        "MATRIX: two passes that differ only in label answer identically across every "
        "state, direction and term, and its power is measured -- twelve spellings of a "
        "label-keyed branch are planted as its controls, and it catches every one that "
        "changes an answer. An AST scan also reports the spellings it knows (a "
        "comparison, a string predicate, a match) and is a report, not the proof: a "
        "scan that must know every way to read a string is the wrong instrument."
    ),
    "G14": (
        "The fixtures are capable of exercising what they claim: the shifting zone "
        "really shifts on the named transition days, the fixed zone really does not, "
        "and the terms matrix holds cases on both sides of every axis the access "
        "answer branches on."
    ),
    "G15": (
        "docs/CONTRACT.md is DERIVED: the guarantees, the refusals, the not-covered "
        "reasons, the barrier meanings, the answer fields, the states and transitions, "
        "the document keys and the worked example are generated from the registries "
        "and by running the module -- and the derivation is proven by plants that "
        "contradict the prose and require it to change, never by comparing two "
        "copies of the same claim."
    ),
    "G17": (
        "A stored pass or garage this module cannot read degrades to a STATED answer, "
        "never an exception: at an entry refused-to-answer naming the field, at an exit "
        "not-covered naming the pass and the field (which at a transient garage means "
        "chargeable, and is said so). Terms are re-validated on every load, so a raw row "
        "no CHECK can reach, or a validator tightened after the row was stored, strands "
        "the pass -- and a stranded pass still answers. A timezone the system does not "
        "carry is refused where the garage is written, and an existing bad row answers "
        "first, naming the field. A WRITE against an unreadable pass or an unreadable "
        "garage is refused by name, naming the refusal that made it unreadable -- "
        "except the one write that repairs it: a garage's timezone can be corrected, "
        "so an unreadable garage is never permanently unfixable."
    ),
    "G18": (
        "THE COMMAND LINE RENDERS A REFUSAL, NEVER A TRACEBACK. Every Refused the "
        "module raises -- an unknown timezone is one -- is printed as the JSON refusal "
        "naming the field and the value, with exit status 3; a document that cannot be "
        "read, an instant or a day that does not parse, and a naive instant are refused "
        "the same way, and a database that does not connect is a sentence on stderr "
        "with exit 2. Every raise in the package is enumerated by AST and classified as "
        "rendered at that boundary or as a programming error no command can reach; an "
        "exception class in neither fails the suite until it is classified."
    ),
    "G16": (
        "No test module sits outside the guarantee registry: every test module "
        "carries a registered guarantee mark or is named in an empty allowance, a "
        "module that plants a defect may not be excused, and a registered guarantee "
        "whose test did not run and pass fails the whole run unless its id is named "
        "in a written-down allowance that CI leaves empty."
    ),
}


def guarantee_ids() -> tuple[str, ...]:
    """Sorted numerically, not lexically -- G10 follows G9, not G1."""
    return tuple(sorted(GUARANTEES, key=lambda g: int(g[1:])))


#: Naming an id here lets the suite finish with that guarantee unproven. It is a
#: DECISION somebody writes down, never a default -- CI names nothing, and a
#: guarantee that did not run and pass fails the run.
ALLOW_ENV = "GARAGE_PASS_ALLOW_UNRUN"
