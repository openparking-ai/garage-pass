# Garage pass — the contract

**Version 1.** The module answers one question:

> This vehicle, at this lane, going this direction, at this instant — does a
> pass cover it, and if not, why not?

This document is the public surface. The blocks between `GENERATED` markers are
produced by `scripts/generate_contract.py` from the code's own registries and by
running the module; CI fails if they drift, and `tests/test_contract_is_generated.py`
plants values that contradict them and requires them to change. Everything
outside those markers is **design documentation** — how the thing works — and is
marked as such rather than left looking measured.

## What is guaranteed

<!-- GENERATED:guarantees -->
| id | what is guaranteed |
|---|---|
| **G1** | ONE CAR, ONE PASS PER GARAGE -- AT EVERY GARAGE THE PASS NAMES, TOGETHER OR NOT AT ALL. A vehicle identity is registered to one pass at a garage for any given day; a second registration overlapping it is refused BY NAME, naming the garage, the pass that holds the identity, its state and the day that registration ends, BEFORE the database constraint has to -- every open registration is a holder whatever its pass's state -- and a refusal writes nothing. A registration is written at every garage the pass names, one row per garage in one transaction: a pass over three garages holds the car at all three from one enrolment, a car held by another pass at ANY of them refuses the whole registration by name, and a partial fan-out is never an outcome -- the EXCLUDE backstops each garage and a violation at any one takes every row of the fan-out back with it. Ending a registration ends it at every garage of the pass. The TARGET pass's state is read: a registration onto a suspended, revoked or expired pass is refused by name, naming the state; draft, awaiting enrolment and active take registrations. The database's EXCLUDE is the backstop for a raw insert and for two registrations genuinely racing -- in either shape the race takes, the constraint firing or the database rolling one writer back, the loser is refused by the constraint's name and never a traceback -- and is reached through the module by nothing else. Ending a registration on day D frees the identity FROM D: a registration elsewhere effective D is accepted, and the old pass covers the vehicle up to and not including D. |
| **G2** | Contradictory terms are refused AT CREATION, naming the field: a valid_to before valid_from, a window that no day in the valid range can satisfy, an empty window, a maximum stay of zero, a visit allowance of zero, a per-window allowance with no windows, no direction, an empty lane set -- and ONLY contradictions: a maximum stay longer than a window is slack, not a contradiction (windows bind instants, not stays), and such a pass is created and its maximum binds at the exit. A Terms value that fails the check cannot be constructed, so the access call never meets a contradiction. The schema's CHECKs back the single-table rules for a raw write; the three that span two tables are named in the migration and backed by the load path (G17). |
| **G3** | No fee, no amount, no balance and no barrier command ever crosses the access call: the answer's fields carry none, the schema has no money-shaped or reservation-shaped column, and a document with a field this module does not know is refused rather than ignored. This module never opens or closes a gate and never counts who is inside. |
| **G4** | AN EXIT IS NEVER REFUSED, AND EVERY EXIT IS ANSWERED. No term, no state, no revocation and no inconsistency in the data refuses an exit to a vehicle that is inside, or fails to answer it: every exit produces a stated COVERED or NOT-COVERED answer -- refused-to-answer is not an outcome an exit can have, and the absence of an answer, a refusal and an exception on any data are each a failure of this guarantee. Whatever cannot be evaluated at an exit is NAMED, never guessed: a blank identity or lane, an unmeasurable maximum stay, an unreadable pass or garage, two passes holding one car, a registration naming a pass that was not handed in, a pass handed in twice under one id -- which is never resolved by the order the copies arrived in: every copy is evaluated, the holder is covered if any copy covers, and the same inputs in any order give the same answer. Every exit answer carries the sentence that says so, a not-covered exit means OUT-OF-TERMS and never a refusal, in every state including revoked, and the exit half of the call does not read the garage's transient mode. What remains outside this sentence is named because it cannot be otherwise, and it is a CLASS proven closed by execution, not a list: a value of a type the signature does not accept -- for any parameter of access(), or any element of its sequences, an instant with no timezone among them -- raises on the first touch, before there is an instant, a pass or an answer to give, and never answers (a wrong-typed value that answered would be a defect, not an exclusion; the test enumerates the signature and proves each one raises); and one ENVIRONMENT error -- a machine with no timezone database at all -- which is raised by its own name, never as an unknown zone. THE MODULE ANSWERS WHEN IT HOLDS A RECORD WHOSE CONTENT IT CANNOT READ, AND REFUSES WHEN IT HOLDS NO RECORD AT ALL, OR NO INSTANT TO READ IT AT: a stored row it cannot read loads unreadable and answers, and a DOCUMENT it cannot read -- a field missing, of the wrong type or unknown, a contradiction, an unknown zone -- is answered at an exit the same way, a pass or garage document degrading to the unreadable pass or garage a stored row becomes and a registration or visit document to a not-covered answer naming the document and the field (RECORD_UNREADABLE); at an entry the same document is refused by name. A file that is missing or is not JSON, and an instant that does not parse, are refused in both directions: no record, or no instant. A garage carrying a timezone this system does not carry cannot be constructed through the pure API, and neither can a registration or visit with a wrong-typed field. |
| **G5** | A revoked pass is refused at ENTRY in every configuration of terms, and revocation is terminal: no transition leaves revoked, and revoking a pass ends its registrations on the revocation day in the garage's local calendar so the identity is free from that day. |
| **G6** | A garage that has not stated whether transient parking is available makes the access call REFUSE TO ANSWER at entry, naming the field. There is no default and no inference; the store keeps the field nullable so that unstated is a state and not a false. |
| **G7** | Terms evaluate in the GARAGE'S LOCAL DAY: a window's minutes are the garage's wall clock and its days are the garage's weekdays, measured at the window edges on the spring-forward and fall-back days where a UTC reading disagrees; and a stay's length is elapsed time between instants, computed in UTC, so a stay across the fall-back hour is an hour longer than its wall clocks say. |
| **G8** | An unknown vehicle identity gets a STATED answer -- not covered, NO_PASS, with the nearest ended or future registration named when there is one -- never an accidental refusal and never a silent pass. A BLANK identity is refused an answer AT AN ENTRY, naming the field, because there is nothing to look up; at an exit the same input is answered not-covered, naming the field. |
| **G9** | A visit allowance and a maximum stay are computed from the module's OWN recorded visits and from nothing else, and the answer names its denominator: how many entries were counted, on which pass, over its life or in which window on which day; and which entry a stay was measured from, both instants rendered as the garage's wall clock whatever offset each arrived with. A maximum stay with no open recorded entry to measure from is UNMEASURED and the answer says so by name while answering on the terms that can be evaluated -- never silently treated as satisfied, and never a refusal. |
| **G10** | Row-level security on every table from migration 0001: a tenant column, ENABLE, FORCE and a policy on each, read from the catalogue and never from a list; isolation proven ON EVERY TENANT-BEARING TABLE, from the catalogue, by a role that COULD bypass being shown it cannot read or write another tenant's rows -- and a stripped predicate on any one of the tables reddens it, every table of every migration having that control; and every garage and pass reference is half of a composite tenant key, so a row cannot name another tenant's garage or pass even by a raw insert. |
| **G11** | Nothing real in the tree: no email address that is not obviously invented, no card-shaped value, and no name from the maintainer's other software, in any file git tracks -- swept in Python over `git ls-files` with a positive control that fires before the result is read, and by CI guards that self-test the same way. |
| **G12** | Every state change records WHO, WHEN and WHY, none blank, into an append-only history: the application role holds SELECT and INSERT on it and nothing else, read from the catalogue and proven by a refused UPDATE -- and HOLDS DELETE ON NO TABLE IN THE SCHEMA, every table read from the catalogue with no hand list and no walk to miss a leaf, so the history cannot be erased by deleting what it belongs to and no row anywhere can be erased by the application at all (the module issues no DELETE); where an offending table also cascades into a history, the failure says so, the walk kept beside the grant. The allowed transitions are the published ones, `expired` is derived from valid_to and refused if typed, and revoked outranks expiry. THE OPERATOR WRITES ON A GARAGE -- the timezone repair, which changes how every pass at the garage is read, and the enrols-at repair, which decides where a QR may be redeemed -- are recorded the same way: who, when, why, the old value and the new, into a second append-only history with the same grant and the same cascade rule; a repair with no who or no why is refused and changes nothing, and the enrols-at repair refuses the R1 contradiction (no transient, enrols at exit) by name exactly as creation does. The set of append-only histories is read from the catalogue (every table the application role may only SELECT and INSERT) and must be exactly the two published ones. |
| **G13** | THE LABEL IS ONLY A LABEL. 'Monthly', 'employee', 'vendor' and the rest are free text the owner types, and no behaviour keys off them. THE PROOF IS THE MATRIX: two passes that differ only in label answer identically across every state, direction and term, and its power is measured -- twelve spellings of a label-keyed branch are planted as its controls, and it catches every one that changes an answer. An AST scan also reports the spellings it knows (a comparison, a string predicate, a match) and is a report, not the proof: a scan that must know every way to read a string is the wrong instrument. |
| **G14** | The fixtures are capable of exercising what they claim: the shifting zone really shifts on the named transition days, the fixed zone really does not, and the terms matrix holds cases on both sides of every axis the access answer branches on. |
| **G15** | docs/CONTRACT.md is DERIVED: the guarantees, the refusals, the not-covered reasons, the barrier meanings, the answer fields, the states and transitions, the document keys and the worked example are generated from the registries and by running the module -- and the derivation is proven by plants that contradict the prose and require it to change, never by comparing two copies of the same claim. |
| **G16** | No test module sits outside the guarantee registry: every test module carries a registered guarantee mark or is named in an empty allowance, a module that plants a defect may not be excused, and a registered guarantee whose test did not run and pass fails the whole run unless its id is named in a written-down allowance that CI leaves empty. |
| **G17** | A stored pass or garage this module cannot read degrades to a STATED answer, never an exception: at an entry refused-to-answer naming the field, at an exit not-covered naming the pass and the field (which at a transient garage means chargeable, and is said so). Terms are re-validated on every load, so a raw row no CHECK can reach, or a validator tightened after the row was stored, strands the pass -- and a stranded pass still answers. A timezone the system does not carry is refused where the garage is written -- checked CASE-EXACTLY against the tz database's own name set, so the answer is the same on a case-insensitive filesystem and a case-sensitive one, and a machine with no tz database at all is named as that, never as an unknown zone -- and an existing bad row answers first, naming the field. A WRITE against an unreadable pass or an unreadable garage is refused by name, naming the refusal that made it unreadable -- except the one write that repairs it: a garage's timezone can be corrected, so an unreadable garage is never permanently unfixable. |
| **G18** | THE COMMAND LINE RENDERS A REFUSAL, NEVER A TRACEBACK. Every Refused the module raises -- an unknown timezone is one -- is printed as the JSON refusal naming the field and the value, with exit status 3; a document that cannot be read, an instant or a day that does not parse, a naive instant, and -- at an ENTRY -- a document field of the WRONG TYPE -- a missing identity, an object where an id belongs, a number where a list belongs, text where a list belongs (never reinterpreted as the list of its characters) -- are refused the same way, naming the field; at an EXIT a document whose content cannot be read is ANSWERED not-covered naming the field, because an exit is never refused (G4): every value a document carries is checked against the type the dataclass it loads into declares, derived from the annotation and not from a list, so a field added later is covered the day it is added. A database that does not connect is a sentence on stderr with exit 2 -- as is a machine with no timezone database at all, named as that and never as an unknown zone, and as is whatever the database driver raises that the store did not turn into a named refusal (an unmigrated database, a role without its grants, a DSN that is not one): one sentence with its SQLSTATE, mapped LAST, after every named refusal has had its chance, so a deadlock at the one-car-one-pass INSERT is still the refusal that carries PostgreSQL's DETAIL. A tenant nobody seeded is refused by name at its first write, not met at the foreign key. A value that starts with a dash (`--timezone -06:00`) reaches the module and is refused by name, not read by argparse as an option. Every raise in the package is enumerated by AST and classified as rendered at that boundary, as the machine's configuration, or as a programming error no command can reach -- a value of a type the signature does not accept is reachable only from the pure API and never from a command, because the document boundary refuses it first -- and the sweep names its denominator, the raise statements, since an exception born of an operator on a wrong-typed value is not one; an exception class in none of the three fails the suite until it is classified. |
| **G19** | ONE QR, ONE CAR, ONCE. An enrolment is a one-time credential: it binds exactly one vehicle identity -- the one the lane measured and handed in -- and is then TERMINAL; a redeemed or cancelled enrolment can never be redeemed again, and neither can an expired one (derived from starts_on and days_valid against the garage's local day, never typed) or one not yet started. Several outstanding enrolments on one pass are allowed and intended -- a pass may carry several vehicles -- and each redeems to one car and dies. A redemption is ONE TRANSACTION: the registration, the pass's move to active where it was not already (recorded, with the enrolment as the actor), the enrolment marked redeemed and the access answer -- all or none, under a savepoint that is rolled back on EVERY exception: a refusal, the module's own or the database's backstop, writes nothing and is carried in the answer; anything else writes nothing and SURFACES, so a QR cannot half-land and be used twice and a defect is never swallowed. ONE CREDENTIAL, ONE SPEND UNDER CONCURRENCY: two lanes presenting one token at once get exactly one bind. The pass row is locked first, then the credential row (one lock order everywhere), and the state, the expiry and the pass's registrability are re-read under those locks -- the primary; the spend carries state = 'issued' and asserts one row -- the backstop; and the suite measures each with the other removed. Written for READ COMMITTED, the store's default; a caller at a stricter level meets the serialization failure as the named refusal a deadlock gets. ONLY A STRUCTURAL EXCLUSION REFUSES THE BIND: a pass whose terms allow no movement in the direction the garage enrols at is refused by name, beside the lane refusal and after it, and the credential stays issued; temporal non-coverage -- a weekday pass on a Sunday, a valid_from ahead, a movement outside the hours -- still binds. days_valid is STATED, refused by name when absent, never defaulted. The holder link is the same primitive, used once, under the same locks. Revoking a pass takes the same lock order -- the pass row, its credentials, its registrations -- so a revocation racing a redemption in either order leaves no live registration and no issued credential on the revoked pass; it cancels every outstanding enrolment and holder link in the same transaction, and the redemption's own state check refuses a revoked pass even with that cancellation planted away. |
| **G20** | THE ENROLMENT OPENS NOTHING ON ITS OWN. The answer a redemption returns is the module's own access answer for that same movement, produced by calling the one access path on the rows as written -- never a second implementation and never a hand-built answer -- and it is identical to calling access with the same inputs after the bind. Where the garage enrols follows from whether it sells transient parking (R1): a garage with no transient enrols at entry, DERIVED, and need not state it; a transient garage states entry or exit, and unstated makes the redemption refuse to answer naming garage.enrols_at (garage.transient_available first, when that is unstated); no transient AND enrols at exit is a contradiction refused by name where the garage is created and where the field is repaired, with the schema's CHECK as the backstop for a raw write. A QR presented at the wrong end is refused by name, naming the end this garage enrols at. |
| **G21** | A REDEMPTION REFUSAL IS NEVER AN EXIT REFUSAL, AND EVERY REDEMPTION IS ANSWERED. The redemption call always returns an access answer for the movement -- including when the redemption itself is refused, whatever the refusal: an unknown, used, cancelled, expired or not-yet-started credential, the wrong end, a pass that is not registrable, a lane outside the pass's terms, a direction outside the pass's terms, an identity on another pass, an unreadable garage. At an exit lane that answer is covered or not-covered with the exit note, never refused-to-answer (G4 holds through the enrolment path); at an entry it is whatever access says. The census of every refusal kind at every lane end is reported N/N with zero unanswered exits. Every refusal door is also driven through the command line in-process, so the rendered-sentence collector reads each refusal's detail, and a falsehood assembled at run time in any of them reddens the suite. |
| **G22** | THE TYPED VEHICLE DESCRIPTION DECIDES NOTHING. It is the holder's own statement of the car they will bring, recorded on the enrolment; the identity that binds is what the lane measured. The module cannot compare an opaque identity to free text and does not pretend to: a mismatch is not a refusal, and enrolments that differ only in their description redeem identically -- the same outcome, the same refusal, the same answer -- across every description and every identity. THE PROOF IS THE MATRIX, and its power is measured: five spellings of a description-keyed branch are planted as its controls and each reddens it. |
| **G23** | THE TOKEN IS NEVER STORED AND NEVER RENDERED. Only its SHA-256 goes in the row; the plaintext is returned exactly once, by the issue call, and by nothing else -- not by a read, not by a listing, not in a refusal detail, not in an answer. Proven by scanning every column of every table in the catalogue, and every detail the module rendered, for tokens it issued -- with the digest as the positive control that the scan reads the column that holds it, and a planted sentence as the positive control that the rendered scan can see one, because a zero from an unproven scan is UNMEASURED, not clean. secrets and hashlib from the standard library; no dependency; no QR image. |
| **G24** | A HOLDER LINK WRITES holder_name AND holder_phone ON THE PASS, AND NOTHING ELSE. Not the email, not the label, not the terms, not the state, not the garage: every other column of the pass row is the same after the redemption as before, and a wider write reddens the test naming the column it should not have touched. Redeeming the link, once, writes those two, issues an enrolment for that pass with the link as the issuer, and spends the link -- one transaction. The vehicle description goes on the enrolment, not the pass. The owner-only path stands: an owner issues an enrolment without the holder ever using a link. No email is sent and no account or password exists: the module mints and records; delivering is the integrator's. The holder's text is text in any script; a control character in it is refused by name by the module's one text validator, never handed to the database driver, and the same rule holds for every id, lane, label and actor the module reads. |
| **G25** | A PASS ANSWERS ONLY AT THE GARAGES IT NAMES. A pass carries a non-empty SET of garages, stated by listing them -- never an 'everywhere' flag, never inferred, an empty set or a blank member refused at creation naming the field -- and every door reads that set by MEMBERSHIP: the access call selects a pass for a garage only if the pass names it (at both places a pass is read for its garage, the duplicated-id grouping and the by-id map), the store refuses to store a pass at a garage it does not name and to load it at one, and a QR or a holder link of the pass redeems at any garage of the set and at no other, refused by name elsewhere. The terms are ONE set on the pass, evaluated at whichever garage the car is at -- a 20-visit allowance is 20 on the pass, not 20 per garage -- except the lanes, which are stated PER GARAGE because lane A1 at two garages is two barriers: where lanes are stated every garage the pass names has its own set, refused at creation otherwise naming the garage, and the lane check at each garage reads its own set and no other. A pass's id is unique per tenant, not per garage. Migration 0004 BACKFILLS: every pass that existed keeps exactly the one garage it had and every lane row carries its own pass's garage; a lane row it cannot place makes it fail naming the count rather than drop the row, and two passes of one tenant sharing an id make it fail naming the id rather than pick a winner. THE VISIT LEDGER STAYS PER GARAGE: one open visit per vehicle per pass PER GARAGE, by the module's own check and by the database's index, so an entry at one garage of the set is never refused for a visit still open at another and an exit never closes another garage's visit -- while the allowance still counts every garage of the set. And a membership row decides nothing recorded under it: removing a garage from a pass that holds a visit or a registration there fails by name (the keys are RESTRICT), never erases them; only the lanes stated at that garage go with it. |

That is 25 guarantees. Every one of them has a fail control that has been proven to fire, and the count above is derived from the registry rather than typed here.
<!-- END:guarantees -->

## The answer

*Design documentation.* The access call takes a garage, the passes the caller
holds (only those naming the garage are this garage's business), the
registrations and recorded visits the caller holds, a vehicle identity, a lane, a
direction and an instant. It returns exactly one of three outcomes: **covered**,
**not covered** with a reason, or **refused to answer** naming the field that
would let it answer — **and the third is an ENTRY outcome only: every exit is
answered covered or not covered.** What cannot be evaluated at an exit is named
(`unmeasured`, or a not-covered reason that names the field), never guessed —
and that includes inconsistent data, such as a registration naming a pass that
was not handed in, or a pass handed in twice under one id, or a document the
module cannot read (G4: the module answers when it holds a record whose content
it cannot read, and refuses only when it holds no record at all, or no instant).
What is not data is named in G4 as a class proven closed by execution: a value
of a type the signature does not accept raises on the first touch and never
answers; a machine with no timezone database raises by its own name. It holds
no session state, opens no gate and counts nobody.

<!-- GENERATED:answer-fields -->
| field | type |
|---|---|
| `outcome` | `Outcome` |
| `direction` | `Direction` |
| `vehicle_identity` | `str` |
| `lane` | `str` |
| `pass_id` | `str | None` |
| `pass_label` | `str | None` |
| `covering_term` | `str | None` |
| `reason` | `str | None` |
| `missing` | `str | None` |
| `means` | `str | None` |
| `detail` | `str` |
| `exit_note` | `str | None` |
| `unmeasured` | `str | None` |

That is the whole answer: 13 fields, none of which is money, and none of which could express a decision about a barrier. `outcome` is one of `covered`, `not_covered`, `refused_to_answer`.
<!-- END:answer-fields -->

### Not-covered reasons

*Design documentation.* The checks run in a fixed order and the first that fails
is the reason. First the garage (an unreadable one answers before anything), the
blank identity and lane, and — at entry — the transient mode; then which pass;
per pass: revoked, then an unreadable pass, then expired (derived), then
suspended, then not yet active, then not started; then direction, lane, window;
then — at entry — the visit allowance, and — at exit — the maximum stay, which
is UNMEASURED and named when no open recorded entry exists to measure it from.
Two passes holding one vehicle — a state the module refuses to create — are each
evaluated at an exit and the vehicle is covered if any covers it, the
inconsistency named; at an entry the call refuses to pick one.

<!-- GENERATED:not-covered -->
| reason | what the lane is told |
|---|---|
| `BLANK_IDENTITY` | The vehicle identity is blank at an EXIT, so there is nothing to look up -- and an exit is answered, never refused. At an entry the same input is refused an answer. |
| `BLANK_LANE` | The lane is blank at an EXIT, so lane terms cannot be evaluated -- and an exit is answered, never refused. At an entry the same input is refused an answer. |
| `DIRECTION_NOT_ALLOWED` | The pass's terms do not state this direction. |
| `EXPIRED` | The pass's valid_to is before this day. Derived from the terms; nobody typed it. |
| `GARAGE_UNREADABLE` | The garage carries a value this module refuses to read -- a stored row whose timezone this system does not carry, or, at an EXIT, a garage document handed to the command line whose id, timezone and transient mode read but which is refused for any reason (an unknown zone, an unknown field). Without a clock no window, day or registration range can be evaluated, so it is answered ahead of every term. At an EXIT this is out-of-terms; at an entry the call refuses to answer. |
| `NOT_ACTIVE` | The pass this vehicle is registered to has not been activated: it is a draft, or it is awaiting enrolment. |
| `NOT_STARTED` | The pass's valid_from is after this day. |
| `NO_PASS` | No pass that names this garage has this vehicle registered on this day. Where a registration once existed and has ended, the detail says which pass and when. A pass answers only at the garages it names: at any other it is not this garage's business, and the vehicle is answered as any unknown one. |
| `OUTSIDE_WINDOW` | The pass has recurring windows and this instant, in the garage's local day, is inside none of them. |
| `OUT_OF_VISITS` | The pass's visit allowance is used up. The detail says how many were counted, out of how many, and over what. |
| `OVER_MAX_STAY` | This exit comes later after the recorded entry than the pass's maximum stay allows. Measured in elapsed time between the two instants, not in wall-clock hours. |
| `PASS_DUPLICATED` | The pass this vehicle is registered to was handed in more than once under one id, and no copy covers this exit. Two passes carrying one id is INCONSISTENT data: the module never picks a copy, whatever the order they arrived in. At an EXIT every copy is evaluated -- the vehicle is covered if any copy covers it, the duplication named -- and where none does, this is the reason, with each copy's own reason in the detail. (At an entry the call refuses to answer, naming the id.) The store cannot produce this: one id, one pass, per garage. |
| `PASS_NOT_HANDED_IN` | A registration of this vehicle, in force on this day, names a pass that was not handed in with the call -- the registrations and the passes disagree, which is INCONSISTENT data, not a term, a state or a revocation. At an EXIT it is answered, never raised: not-covered, naming the pass the registration names, so an integrator assembling registrations from their own store can see which one. Where another registration in force names a pass that was handed in, that pass is evaluated and covers the vehicle if it covers it, with the inconsistency named in the detail. (At an entry the call refuses to answer, naming the field.) The store cannot produce this: it loads the passes its registrations name. |
| `PASS_UNREADABLE` | The pass this vehicle is registered to carries a value this module refuses to read -- terms or a holder that would be refused at creation, a holder or terms field that is missing or of the wrong type, or a field this module does not know. Reached by a stored row (a raw write, or a validator tightened after the pass was stored) and, at an EXIT, by a pass document handed to the command line whose id, garage, label and state read. The detail names the pass and the field. At an EXIT this is out-of-terms and therefore chargeable at a transient garage: stated so nobody reads it as a free exit, and named so an operator can find the row and undo the charge. |
| `RECORD_UNREADABLE` | A record handed in with the call at an EXIT cannot be read as what it claims to be -- a registration or a visit document with a field missing, of the wrong type or unknown, or a pass or garage document too malformed to carry the marker a stored row would (its id, garage, label or state unreadable). The module holds the record and cannot read its content, so the exit is ANSWERED, never refused: not-covered, naming the document and the field so the integrator can find it, with the exit note and the OUT-OF-TERMS meaning every exit answer carries -- at a transient garage chargeable, said so. A pass or garage document whose carrier fields read is not this: it degrades to the unreadable pass or garage a stored row becomes, and answers PASS_UNREADABLE or GARAGE_UNREADABLE only if the vehicle is on it. (At an entry the same document is refused by name. The module refuses only when it holds no record at all -- a file that is missing, not a regular file, or cannot be read as JSON -- or no instant to read it at.) |
| `REVOKED` | The pass was revoked. Revocation is terminal. |
| `SUSPENDED` | The owner has put the pass on hold. The hold is reversible. |
| `WRONG_LANE` | The pass's terms name the lanes it may use AT THIS GARAGE, and this is not one. Lanes are stated per garage; a lane the pass allows at another of its garages is another barrier. |
<!-- END:not-covered -->

### What not-covered means at the barrier

<!-- GENERATED:meanings -->
| meaning | at the barrier |
|---|---|
| `COVERED` | The pass covers this movement. The lane acts on that; this module opens nothing. |
| `EXIT_OUT_OF_TERMS` | Not covered at EXIT. AN EXIT IS NEVER REFUSED: no term, no state and no revocation keeps a vehicle inside a garage. This exit is outside the pass's terms and is answered, recorded and reported as such -- at a transient garage that is what makes the stay chargeable. |
| `NOTHING_TO_ADMIT_AS` | Not covered at ENTRY, at a garage that sells NO transient parking: there is nothing for this vehicle to be admitted as. The lane does not admit it. |
| `TRANSIENT_STAY` | Not covered at ENTRY, at a garage that sells transient parking: this is an ordinary paying customer. The lane treats it as one. |

Every EXIT answer, whatever its outcome, carries: *An exit is never refused. Whatever this answer says, the vehicle leaves.*
<!-- END:meanings -->

### When the call refuses to answer

<!-- GENERATED:refused-to-answer -->
| missing | why the call will not guess |
|---|---|
| `garage.timezone` | The garage is stored with a timezone this system does not carry, and an ENTRY cannot be evaluated without a clock. (An exit is answered not-covered, naming the field.) |
| `garage.transient_available` | The garage has not stated whether transient parking is available. There is no default and no inference: with it unstated, an uncovered entry is either an ordinary paying customer or a vehicle with nothing to be admitted as, and guessing between those is the difference between a car let in free and a fired employee driving into a building. State it on the garage. |
| `lane` | The lane is blank at an ENTRY, so lane terms cannot be evaluated. (At an exit the same input is answered not-covered.) |
| `pass.terms` | The pass this vehicle is registered to is stored with terms or a holder this module refuses to read, and an ENTRY on it is not guessed. The detail names the pass and the field. (An exit is answered not-covered, naming both.) |
| `passes` | A registration of this vehicle, in force on this day, names a pass that is not among the passes handed in, at an ENTRY. The registrations and the passes disagree and the module will not guess which is right: hand in the pass the registration names, or the registrations that match the passes. (At an exit the vehicle is answered not-covered naming that pass -- or covered by another pass in force that was handed in, the inconsistency named. An exit is never refused and never raises on data.) |
| `passes[].id` | The pass this vehicle is registered to was handed in more than once under one id, at an ENTRY -- whether or not the copies agree, since the caller who sent one id twice does not know which they meant, and the module will not resolve an inconsistency it should be naming. Measured before this: the LAST copy in the list won silently, so the same inputs in a different order admitted or refused the same car. Hand in each pass once. (At an exit every copy is evaluated and the vehicle is covered if any covers it, the duplication named.) |
| `registration.pass_id` | More than one pass at this garage has this vehicle registered on this day, at an ENTRY. The module refuses to pick one. That state cannot be produced through this module; it was handed in or written raw. (At an exit every one of them is evaluated and the vehicle is covered if any covers it, the inconsistency named.) |
| `vehicle_identity` | The vehicle identity is blank at an ENTRY, so there is nothing to look up. An unknown identity gets a stated answer; a missing one gets none. (At an exit the same input is answered not-covered: an exit is never refused.) |
<!-- END:refused-to-answer -->

## The pass

*Design documentation.* A pass names the garages it answers at — one or more,
a set the owner states by listing them, never an "everywhere" flag — carries an
owner-typed label that no behaviour reads, a holder (an email address,
optionally a name and a phone; no account), its terms, its state, and the
vehicles registered to it. It answers at every garage it names and at no other
(G25); its id is unique per tenant.

### Terms

*Design documentation.* Six things, each stated or absent, with no default:

1. **valid_from / valid_to** — inclusive calendar days in the garage's local day.
2. **windows** — recurring: ISO weekdays plus minutes from local midnight,
   half-open `[start, end)`, `1440` being the end of the day.
3. **max_stay** — a duration, measured at exit as elapsed time from the recorded entry.
4. **visit_allowance** — a count, over the pass's life or per window occurrence.
5. **directions** — entry, exit or both. Nothing is implicit.
6. **allowed_lanes** — a named set, stated **per garage** (`garage_id` plus its
   `lanes`, one entry per garage the pass names; lane `A1` at two garages is two
   barriers); absent means every lane at every garage the pass names.

The terms are one set, on the pass, evaluated at whichever garage the car is at:
a 20-visit allowance is 20 on the pass, not 20 per garage. Only the lanes are
per garage.

A contradiction between them is refused when the pass is created — and only a
contradiction: a maximum stay longer than a window is slack, not a contradiction
(windows bind the entry and exit instants, never the stay between them), and such
a pass is created and its maximum binds at the exit. A stored row that the
validator refuses — a raw write past the three cross-table rules the schema cannot
express, or a validator tightened after the row was stored — is not an exception
but an UNREADABLE pass, answered as G17 states.

<!-- GENERATED:refusals -->
| code | when, and what to do about it |
|---|---|
| `REFUSAL_ALLOWANCE_PER_WINDOW_WITHOUT_WINDOWS` | The visit allowance is counted per window and the pass has no windows, so there is nothing to count it against. |
| `REFUSAL_CONSTRAINT` | The database refused the write by a constraint the module did not catch first, or rolled it back to break a deadlock at that constraint's lock. Named by its constraint so it is a refusal and not a traceback; two writers racing end here. Under a deadlock the detail carries the database's own account of the cycle and asserts no cause the module did not observe. |
| `REFUSAL_CREDENTIAL_ALREADY_EXISTS` | An enrolment or holder link with that id already exists in this tenant. |
| `REFUSAL_CREDENTIAL_ALREADY_USED` | This credential was already redeemed. An enrolment is one QR, one car: it binds exactly one vehicle identity and is then terminal; a holder link is used once. The detail names the credential and when it was redeemed. Nothing is written. |
| `REFUSAL_CREDENTIAL_CANCELLED` | This credential was cancelled -- the pass it opens was revoked, and a credential must not outlive the pass. The detail names when and why. Nothing is written. |
| `REFUSAL_CREDENTIAL_EXPIRED` | This credential's window has passed: its last day, starts_on plus days_valid less one, is before today in the garage's local day. Derived; nobody typed it. Nothing is written; issue a new one. |
| `REFUSAL_CREDENTIAL_NOT_STARTED` | This credential's starts_on is after today in the garage's local day. Nothing is written; present it from that day. |
| `REFUSAL_CREDENTIAL_UNKNOWN` | No enrolment or holder link in this tenant matches the token presented. The token itself is never rendered and never stored: only its SHA-256 is compared. |
| `REFUSAL_DAYS_VALID_NOT_POSITIVE` | The credential's days_valid is zero or negative, so there is no day on which it could be redeemed. State a positive whole number of days. |
| `REFUSAL_DAYS_VALID_NOT_STATED` | The credential's days_valid is not stated. It is refused rather than defaulted: this module refuses guessed defaults, and how long a QR may wait to be redeemed is the owner's to state (the monthly-parker product uses three days from the starting day; that is its number, not this module's). |
| `REFUSAL_DIRECTION_OUTSIDE_THE_PASS_TERMS` | The pass's terms allow no movement in the direction this garage enrols at, so the QR would be spent on a movement the pass can never cover. Refused by name, beside the lane refusal, before anything is written: the credential stays issued for a movement the pass can cover. ONLY a STRUCTURAL exclusion refuses -- the direction, or the lane outside the stated set. Temporal non-coverage (a weekend on a weekday pass, a valid_from still ahead, a movement outside the hours) still BINDS: enrolling at the weekend is the ordinary case. |
| `REFUSAL_DOCUMENT_UNREADABLE` | A document named on the command line could not be read: the file is missing, not a regular file, unreadable, not JSON, or JSON the decoder cannot decode (nested deeper than it can read, or a number longer than it will convert). The detail names the path and what went wrong. |
| `REFUSAL_ENROLMENT_AT_WRONG_END` | The QR was presented at the wrong end: this garage enrols at the end named in the detail, and this lane is the other. Nothing is written. The movement itself still gets its access answer -- and an exit is never refused. |
| `REFUSAL_ENROLMENT_EXPIRED_IS_DERIVED` | A credential's 'expired' is derived from its starts_on and days_valid against the garage's local day and is never typed by anyone. To end one early, revoke the pass it belongs to; to end it on a day, that day is starts_on plus days_valid. |
| `REFUSAL_ENROLS_AT_CONTRADICTS_TRANSIENT` | The garage sells no transient parking and is stated to enrol at its exit. At a garage with no transient an unregistered vehicle is not admitted, so the registration must happen at the entry; enrolling at the exit there is a contradiction. Refused where the garage is created and where the field is repaired; the schema's CHECK is the backstop for a raw write. |
| `REFUSAL_EXIT_BEFORE_ENTRY` | The exit instant is earlier than the entry it would close. |
| `REFUSAL_EXPIRED_IS_DERIVED` | Expired is derived from the pass's valid_to and is never typed by anyone. To end a pass early, revoke it; to end it on a day, that day is valid_to. |
| `REFUSAL_FIELD_BLANK` | A required field is blank. The field is named beside this code. |
| `REFUSAL_FIELD_WRONG_TYPE` | A document field carries a value of the wrong type -- text where a list belongs, a number where text belongs, an object where an id belongs. The document is refused naming the field, the type it declares and the value; it is never reinterpreted (text is not read as a list of its characters) and never a traceback. The check is derived from the dataclass the document loads into, so a field added later is covered the day it is added. |
| `REFUSAL_GARAGE_ALREADY_EXISTS` | A garage with that id already exists in this tenant. |
| `REFUSAL_GARAGE_MISMATCH` | A pass names the garages it answers at, and was asked about a garage it does not name -- to be stored there, or a QR or holder link of it presented there. The detail names the garage asked for and the pass's own set. Nothing is written. |
| `REFUSAL_GARAGE_NOT_FOUND` | No garage with that id in this tenant. |
| `REFUSAL_HOLDER_EMAIL_MALFORMED` | The holder's email address does not look like one -- it needs an @ with something before it and something after it. The email is the holder's identity in this module, so a malformed one identifies nobody. |
| `REFUSAL_LANES_AT_A_GARAGE_THE_PASS_DOES_NOT_NAME` | The pass states lanes at a garage it does not name, so those lanes could never be used. The detail names the garage and the pass's own set; the database's key backs it for a raw write. |
| `REFUSAL_LANES_GARAGE_REPEATED` | The pass states lanes for one garage twice. One entry per garage: a garage named twice with two sets is a contradiction the module will not merge. |
| `REFUSAL_LANES_NOT_STATED_FOR_GARAGE` | The pass states its lanes, and one of the garages it names has no lane stated there. Lanes are stated PER GARAGE -- lane A1 at two garages is two barriers -- and a garage with none, on a pass whose lanes are stated, would be an implicit empty set: no lane at all. Nothing here is implicit; the detail names the garage. |
| `REFUSAL_LANES_STATED_BUT_EMPTY` | The allowed lanes are stated as an empty set -- no garage at all, or no lane at one of the garages. Absent means every lane at every garage the pass names; an empty set means no lane, which covers nothing. |
| `REFUSAL_LANE_NAME_BLANK` | A lane name is blank. |
| `REFUSAL_LANE_OUTSIDE_THE_PASS_TERMS` | The pass names the lanes it may use, and the lane this QR was presented at is not one of them. Nothing is implicit: the pass carries its own terms, and a redemption at a lane they do not name is refused naming the lane and the set. The owner's fix is to state the lane on the pass. Nothing is written. |
| `REFUSAL_MAX_STAY_NOT_POSITIVE` | The maximum stay is zero or negative. A pass that allows no time inside covers nothing; state a positive duration, or no maximum. |
| `REFUSAL_NO_DIRECTIONS` | The pass states no direction. Nothing is implicit: a privilege the terms do not state does not exist, so a pass that names neither entry nor exit covers nothing. |
| `REFUSAL_NO_OPEN_VISIT` | No recorded entry of this vehicle on this pass at this garage is still open, so there is no visit for this exit to close. The ledger is per garage: an entry recorded at another garage of the pass is not the one this exit closes. |
| `REFUSAL_PASS_ALREADY_EXISTS` | A pass with that id already exists in this tenant. A pass's id is unique per tenant, not per garage: a pass that spans garages cannot be identified by one. |
| `REFUSAL_PASS_NAMES_NO_GARAGE` | The pass names no garage. A pass carries a non-empty SET of the garages it answers at -- stated by listing them, never an 'everywhere' flag and never inferred -- and a pass naming none would answer nowhere. A string where the list belongs is refused the same way, never read as a set of its characters. |
| `REFUSAL_PASS_NOT_FOUND` | No pass with that id names that garage in this tenant. Where the pass exists and names other garages, the detail says which. |
| `REFUSAL_PASS_NOT_REGISTRABLE` | A vehicle may be registered onto a pass that is draft, awaiting enrolment or active. This pass is not: the detail names its state. A suspended pass is a hold, and a car added to a hold is a claim the owner did not make; a revoked pass is revoked; an expired pass -- derived from its valid_to against the registration's effective day -- is over. |
| `REFUSAL_REGISTRATION_ALREADY_ENDED` | That registration already has an end day. A registration is ended once; to move the day, that is a new registration. |
| `REFUSAL_REGISTRATION_ENDS_BEFORE_IT_STARTS` | The registration ends on or before the day it takes effect, so it covers no day. |
| `REFUSAL_REGISTRATION_NOT_FOUND` | No registration of that vehicle on that pass. |
| `REFUSAL_REGISTRATION_OUTLIVES_THE_PASS` | The registration's end day is past the pass's valid_to. A vehicle cannot be on a pass on a day the pass does not cover; leave end_day unstated and it runs to the pass's last day. |
| `REFUSAL_REPAIR_NEEDS_WHO_AND_WHY` | A garage repair -- set-garage-timezone, which changes how every pass at the garage is read -- records who made it, when and why into an append-only history, and one of who or why is blank. The repair is refused and nothing changes: a change to every clock in the building with no record of who made it is the one write this module would not be able to explain afterwards. |
| `REFUSAL_REVOKED_IS_TERMINAL` | A revoked pass is revoked. It never becomes active again; a new pass is a new pass. |
| `REFUSAL_STATE_CHANGE_NEEDS_WHO_AND_WHY` | A state change records who made it and why, and one of those is blank. |
| `REFUSAL_STATE_TRANSITION_NOT_ALLOWED` | The pass cannot move from its current state to the one asked for. The allowed moves are published in the contract. |
| `REFUSAL_STATE_UNKNOWN` | The state named is not one this module has. |
| `REFUSAL_TENANT_NOT_FOUND` | No tenant row has the id given. The first write for a tenant -- create-garage -- reads the tenant row before it writes, so an id nobody seeded is refused by name rather than met at the database's foreign key. |
| `REFUSAL_TEXT_HAS_CONTROL_CHARACTERS` | A text field carries a control character INSIDE it -- a NUL, a line break, a tab or another character whose Unicode category is Cc, between its first and last non-blank characters. Refused by name wherever the module reads text, so a driver never turns it into a configuration-class sentence. Whitespace at either edge was never part of the text and is removed before the check: the ten Cc code points Python counts as whitespace (TAB, LF, VT, FF, CR, U+001C to U+001F and U+0085) are stripped there, and NUL is never whitespace and never stripped. Letters in any script are text and are accepted. |
| `REFUSAL_TIMEZONE_UNKNOWN` | The timezone named is not an IANA name this system carries. It is refused rather than defaulted to UTC: a pass evaluated on UTC clocks crosses its own window edges by hours, and nothing in the answer would say so. The detail names the value; a garage already stored with one is repaired with set-garage-timezone. |
| `REFUSAL_UNKNOWN_FIELD` | A document carries a field this module does not know. It is refused rather than ignored: a field silently dropped is a term the owner believes is in force and is not. |
| `REFUSAL_VALID_TO_BEFORE_VALID_FROM` | The pass ends before it starts: valid_to is earlier than valid_from. There is no day on which such a pass could cover anything, so it is not created. |
| `REFUSAL_VEHICLE_ON_ANOTHER_PASS` | This vehicle identity is already registered to another pass, at one of the garages the target pass names, for days that overlap. One car, one pass per garage: a registration is written at EVERY garage the pass names, together or not at all, and the refusal names the garage where the identity is held, the pass that holds it and the day that registration ends. End that registration first, or register from the day it ends. |
| `REFUSAL_VISIT_ALLOWANCE_NOT_POSITIVE` | The visit allowance is zero or negative. A pass allowing no visits covers nothing; state a positive count, or no allowance. |
| `REFUSAL_VISIT_ALREADY_OPEN` | A recorded entry of this vehicle on this pass at this garage is still open. Record its exit before recording another entry here, or the visit ledger would hold a car inside this garage twice. A visit still open at another garage of the pass does not refuse an entry here. |
| `REFUSAL_WHERE_TO_ENROL_UNSTATED` | A redemption cannot tell whether this lane is the end this garage enrols at. The field named beside this code is the one that would say: garage.transient_available decides first (a garage with no transient enrols at entry, derived, and need state nothing more); a transient garage has a choice and states it in garage.enrols_at. There is no default and no inference. |
| `REFUSAL_WINDOW_DAY_UNKNOWN` | A recurring window names a day that is not 1 (Monday) to 7 (Sunday). |
| `REFUSAL_WINDOW_ENDS_BEFORE_IT_STARTS` | A recurring window ends at or before the minute it starts, so it is empty. A window that runs past midnight is two windows: one to 1440 on the first day and one from 0 on the next. |
| `REFUSAL_WINDOW_HAS_NO_DAYS` | A recurring window names no day of the week. A window that occurs on no day can never be satisfied; state at least one day, or remove the window. |
| `REFUSAL_WINDOW_MINUTE_OUT_OF_RANGE` | A window's start or end is outside 0 to 1440 minutes from local midnight. 1440 means the end of the day. |
| `REFUSAL_WINDOW_NEVER_OCCURS` | None of the days a recurring window names falls inside the pass's valid range, so the window can never be satisfied. Widen the range or change the days. |

59 refusals. Each is raised with the FIELD it is about, and none of them is raised by the access call about a term: a contradiction is refused when the pass is created.
<!-- END:refusals -->

### States

<!-- GENERATED:states -->
Typed states: `draft`, `awaiting_enrolment`, `active`, `suspended`, `revoked`. Derived: `expired`.

| from | may move to |
|---|---|
| `draft` | `active`, `awaiting_enrolment`, `revoked` |
| `awaiting_enrolment` | `active`, `revoked` |
| `active` | `revoked`, `suspended` |
| `suspended` | `active`, `revoked` |
| `revoked` | — (terminal) |
<!-- END:states -->

*Design documentation.* Every state change records who, when and why, into a
history the application role can only read and append to — it holds no UPDATE or
DELETE on the history, and no DELETE on any table in the schema (every table,
read from the catalogue: the module issues no DELETE anywhere). Revoking a pass
ends its registrations on the revocation day in the garage's local calendar and
cancels every outstanding enrolment and holder link on it, in the same
transaction.

## Enrolment — the QR, the lane bind, the holder's own details

*Design documentation.* **The email is the identity, the QR is the credential,
and there is no account and no password.** An **enrolment** is a one-time
credential minted for a pass: a token returned exactly once by the call that
issued it and known to the module afterwards only by its SHA-256 — no read, no
listing, no refusal detail and no answer carries the plaintext, and the row does
not hold it (G23). The module returns the token and the payload string the QR
carries; rendering a bitmap is the client's job. Nothing is emailed: the module
mints and records; delivering the credential — email, SMS, print — is the
integrator's. `days_valid` is stated, never defaulted (the monthly-parker product
uses three days from the starting day; that is its number, not this module's),
and `expired` is derived from it in the garage's local day.

<!-- GENERATED:credential-states -->
Typed credential states: `issued`, `redeemed`, `cancelled`. Derived: `expired` -- from `starts_on` and `days_valid` against the garage's local day; nobody types it, and typing it is refused by its own code.

A QR carries `openparking-garage-pass/1/<token>`; a lane may present the payload or the bare token. A garage enrols at `entry` or `exit`; a garage with no transient parking enrols at `entry`, derived, and need not state it.
<!-- END:credential-states -->

**Where a garage enrols follows from whether it sells transient parking** (R1).
A garage with no transient parking does not admit an unregistered vehicle, so it
enrols at entry — derived, and it need not state `enrols_at`. A transient garage
states `entry` or `exit`; unstated, a redemption refuses to answer naming
`garage.enrols_at` (`garage.transient_available` first, when that is unstated).
No transient and enrols at exit is a contradiction, refused by name where the
garage is created and where the field is repaired (`set-garage-enrols-at`,
recorded like the timezone repair), with the schema's CHECK as the backstop for a
raw write (G20).

**The redemption** (`redeem-enrolment`): a lane presents the QR with the vehicle
identity it measured — an opaque value; this module never identifies a car —
and the lane and direction. In ONE transaction: the registration, effective on
the garage's local day of that instant; the pass to `active` where it was `draft`
or `awaiting_enrolment` (recorded, with the enrolment as the actor; a pass
already active takes no transition — the ordinary case for a second car on a
pooled pass); the enrolment marked redeemed with the identity, lane, direction
and instant; and **the access answer for that same movement, produced by the
module's own access path — never a second implementation** (G20). A refusal
anywhere writes nothing (G19): an unknown, used, cancelled, expired or
not-yet-started credential; the wrong end; a pass that is not registrable
(suspended, revoked or expired, naming the state); a lane outside the pass's
stated lane set, naming the lane and the set (R6); an identity already on
another pass at this garage, by name, before the database's EXCLUDE. **The
redemption always returns an access answer for the movement, including when the
redemption is refused** — the response carries what happened to the enrolment
and what the lane does now — and **a redemption refusal is never an exit
refusal** (G21): at an exit lane the answer is covered or not-covered with the
exit note, never refused-to-answer.

**One QR, one car.** A redeemed enrolment is terminal and binds exactly one
vehicle identity. Several outstanding enrolments on one pass are allowed and
intended — a pass may carry several vehicles — and each redeems to one car and
dies; there is no one-outstanding-per-pass rule and none should be built. **The
swap** is the shipped `end-registration` followed by a new QR: no compound verb,
because one verb doing both would hide which half failed. **Revoking a pass
cancels every outstanding enrolment and holder link on it** in the same
transaction, and the redemption's own state check refuses a revoked pass even
with that cancellation planted away.

**The typed vehicle description decides nothing** (G22). It lives on the
enrolment as the holder's own statement of the car they will bring; the identity
that binds is what the lane measured. The module cannot compare an opaque
identity to free text and does not pretend to: a mismatch is not a refusal.

**The holder link** (`issue-holder-link`, `redeem-holder-link`) is the same
primitive scoped to one pass, whose `holder_email` is the identity — so the link
carries no email of its own. Redeeming it, once, writes `holder_name` and
`holder_phone` on the pass **and nothing else** (G24: every other column is the
same after as before), issues an enrolment for that pass with the link as its
issuer, and spends the link — one transaction. The owner-only path stands: an
owner issues an enrolment without the holder ever using a link; the link exists
for the holder's own self-service, not as a gate on enrolment.

### Registrations

*Design documentation.* A registration binds a vehicle identity to a pass for the
half-open range of local days `[effective_day, end_day)`. The identity is free
**from** `end_day`. One identity is on one pass per garage for any day; a pass
may carry many identities. Ending on day D and registering elsewhere effective D
is accepted, and the old pass covers the vehicle up to and not including D.

A vehicle is registered onto a pass that is `draft`, `awaiting_enrolment` or
`active`. A registration onto a `suspended`, `revoked` or `expired` pass is
refused by name (`REFUSAL_PASS_NOT_REGISTRABLE`), naming the state — expired
derived from `valid_to` against the registration's effective day. Every open
registration is a holder in the one-car-one-pass check whatever its pass's
state, so the database's `EXCLUDE` is reached through the module only by two
registrations genuinely racing.

## Documents

*Design documentation.* The command line reads JSON documents of these shapes.

<!-- GENERATED:document-keys -->
| document | keys |
|---|---|
| garage | `enrols_at`, `id`, `timezone`, `transient_available` |
| pass | `garage_ids`, `holder`, `id`, `label`, `state`, `terms` |
| holder | `email`, `name`, `phone` |
| terms | `allowed_lanes`, `directions`, `max_stay_minutes`, `valid_from`, `valid_to`, `visit_allowance`, `windows` |
| window | `days`, `end_minute`, `start_minute` |
| allowance | `count`, `per` |
| registration | `effective_day`, `end_day`, `pass_id`, `vehicle_identity` |
| visit | `entered_at`, `entry_lane`, `exit_lane`, `exited_at`, `pass_id`, `vehicle_identity` |

A key not in its document's list is refused, never ignored.
<!-- END:document-keys -->

## Worked example

<!-- GENERATED:worked-example -->
Produced by running the module over `tests/documents/` -- the garage, the employee pass, one registration and two recorded visits -- for these movements:

- `CAR-1` at lane `L1`, **entry**, `2026-06-01T12:00:00-06:00` → **covered** by `pass-employee-7` (Employee): valid 2026-01-01..2026-12-31; windows Mon,Tue,Wed,Thu,Fri 06:00-20:00; max stay 10:00:00; 3 visit(s) per window; directions entry+exit; lanes garage-downtown:L1,L2; in window Mon,Tue,Wed,Thu,Fri 06:00-20:00 on 2026-06-01; visit 3 of 3; counted 2 recorded entries on pass 'pass-employee-7' in window Mon,Tue,Wed,Thu,Fri 06:00-20:00 on 2026-06-01
- `CAR-1` at lane `L1`, **exit**, `2026-06-01T12:00:00-06:00` → **covered** by `pass-employee-7` (Employee): valid 2026-01-01..2026-12-31; windows Mon,Tue,Wed,Thu,Fri 06:00-20:00; max stay 10:00:00; 3 visit(s) per window; directions entry+exit; lanes garage-downtown:L1,L2; in window Mon,Tue,Wed,Thu,Fri 06:00-20:00 on 2026-06-01; stayed 3:00:00 of at most 10:00:00
  - exit note: *An exit is never refused. Whatever this answer says, the vehicle leaves.*
- `CAR-1` at lane `L1`, **entry**, `2026-06-01T05:30:00-06:00` → **not covered** — `OUTSIDE_WINDOW`, meaning `TRANSIENT_STAY`: 2026-06-01T05:30:00-06:00 is 2026-06-01 (Mon) 05:30 in America/Denver, inside none of: Mon,Tue,Wed,Thu,Fri 06:00-20:00.
- `CAR-1` at lane `L9`, **entry**, `2026-06-01T12:00:00-06:00` → **not covered** — `WRONG_LANE`, meaning `TRANSIENT_STAY`: pass 'pass-employee-7' allows lanes ['L1', 'L2'] at garage 'garage-downtown', not 'L9'.
- `NOBODY` at lane `L1`, **entry**, `2026-06-01T12:00:00-06:00` → **not covered** — `NO_PASS`, meaning `TRANSIENT_STAY`: no registration of 'NOBODY' at garage 'garage-downtown' on 2026-06-01.
- `NOBODY` at lane `L1`, **exit**, `2026-06-01T12:00:00-06:00` → **not covered** — `NO_PASS`, meaning `EXIT_OUT_OF_TERMS`: no registration of 'NOBODY' at garage 'garage-downtown' on 2026-06-01.
  - exit note: *An exit is never refused. Whatever this answer says, the vehicle leaves.*
<!-- END:worked-example -->

## The store

*Design documentation.* `migrations/0001_garages_passes_registrations_and_rls.sql`
creates the tables with row-level security from the first migration, an
application role that cannot bypass it, a composite tenant key on every garage
and pass reference, and the one-car-one-pass constraint as an `EXCLUDE` over the
registration's day range; `0002_garage_changes_are_recorded.sql` adds the garage
history in the same shape; `0003_enrolments_holder_links_and_where_a_garage_enrols.sql`
adds the two one-time credentials (the token's SHA-256, never the token), the
garage's `enrols_at` with its R1 CHECK, and admits the enrols-at repair to the
garage history; `0004_a_pass_spans_many_garages.sql` moves the pass-to-garage
key into `pass_garages` (one row per garage the pass names), stamps every lane
row with its garage, makes the pass's id unique per tenant, and says in the
database that a lane, a registration and a visit name a garage the pass holds —
backfilling every existing pass with the one garage it had, and refusing to run
over a lane row it cannot place or two passes of one tenant sharing an id.
Registrations stay keyed per garage: one enrolment writes one row per garage of
the pass, together or not at all. Apply them, in order, as the database owner:

```
for m in migrations/*.sql; do psql "$DSN" -v ON_ERROR_STOP=1 -f "$m"; done   # 0001, 0002, 0003
GARAGE_PASS_APP_PASSWORD=... python scripts/ensure-app-role.py "$DSN"
```

Both steps are run by the suite against the test cluster, not only published
here. The application connects as `garage_pass_app` and sets the tenant per
transaction (`SELECT set_config('garage_pass.tenant_id', ..., true)`). A
connection that has not set it sees nothing.

A garage or a pass stored with a value the module refuses to read (G17) takes
no write — every write against it is refused with the refusal that made it
unreadable — except the repair: `set-garage-timezone` corrects a stored
garage's timezone, and is the one write an unreadable garage takes, because
without it such a garage could never be fixed. The new zone is refused by name
if the system does not carry it, checked case-exactly against the tz database's
own name set so the answer does not depend on the filesystem's case rule. The
repair is recorded — who, when, why, the old value and the new — in
`garage_changes` (`migrations/0002_garage_changes_are_recorded.sql`), append-only
by the same grant as the pass history (G12); a repair with no who or no why is
refused and changes nothing.

A timezone database is required and is not shipped: on a machine with none the
module raises `TimezoneDatabaseUnavailable` by name — never an unknown-zone
refusal of a good name — and the command line prints that sentence on stderr
with exit 2.

## The command line

*Design documentation.* Exit status 0 covered, 1 not covered, 2 refused to
answer (or, for a store command, the machine's configuration — a sentence on
stderr: no database to connect to, one that is not migrated, a role without its
grants, no timezone database, or whatever else the driver raised that the store
did not name, with its SQLSTATE), 3 the request was refused. A refusal is always
rendered as the JSON `{"refused": code, "field": ..., "detail": ...}` and never
as a traceback (G18): an unknown timezone, a document that cannot be read, an
instant or a day that does not parse, a naive instant, a document field of the
wrong type — every value is checked against the type the dataclass it loads
into declares, derived from the annotation, and text is never reinterpreted as
a list. At an EXIT a document that is JSON but cannot be read as a garage, pass,
registration or visit is not refused but ANSWERED not-covered naming the field
(G4); a file that is missing or is not JSON, and an instant that does not
parse, refuse in both directions. A value that starts with a dash (`--timezone -06:00`) reaches the module
and is refused by name rather than read by argparse as an option. Every `raise`
in the package is enumerated by AST in the suite and classified as rendered at
that boundary, as the machine's configuration (a sentence on stderr, exit 2),
or as a programming error no command can reach — and the sweep names its
denominator, the raise statements, which is why the command line was also
measured by a census of what escapes it.

---

Built by 72 Knots Method by 72Knots.ai
