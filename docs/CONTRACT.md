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
| **G1** | ONE CAR, ONE PASS PER GARAGE. A vehicle identity is registered to one pass at a garage for any given day; a second registration overlapping it is refused BY NAME, naming the pass that holds the identity and the day that registration ends, BEFORE the database constraint has to -- and a refusal writes nothing. The database's EXCLUDE is the backstop for a raw insert and for two registrations racing. Ending a registration on day D frees the identity FROM D: a registration elsewhere effective D is accepted, and the old pass covers the vehicle up to and not including D. |
| **G2** | Contradictory terms are refused AT CREATION, naming the field: a valid_to before valid_from, a window that no day in the valid range can satisfy, an empty window, a maximum stay longer than a window it sits in, a visit allowance of zero, a per-window allowance with no windows, no direction, an empty lane set. A Terms value that fails the check cannot be constructed, so the access call never meets a contradiction; the schema's CHECKs are the backstop for a raw write. |
| **G3** | No fee, no amount, no balance and no barrier command ever crosses the access call: the answer's fields carry none, the schema has no money-shaped or reservation-shaped column, and a document with a field this module does not know is refused rather than ignored. This module never opens or closes a gate and never counts who is inside. |
| **G4** | AN EXIT IS NEVER REFUSED. No term, no state and no revocation refuses an exit to a vehicle that is inside: every exit answer -- covered, not covered, or refused to answer -- carries the sentence that says so, a not-covered exit means OUT-OF-TERMS and never a refusal, in every state including revoked, and the exit half of the call does not read the garage's transient mode. |
| **G5** | A revoked pass is refused at ENTRY in every configuration of terms, and revocation is terminal: no transition leaves revoked, and revoking a pass ends its registrations on the revocation day in the garage's local calendar so the identity is free from that day. |
| **G6** | A garage that has not stated whether transient parking is available makes the access call REFUSE TO ANSWER at entry, naming the field. There is no default and no inference; the store keeps the field nullable so that unstated is a state and not a false. |
| **G7** | Terms evaluate in the GARAGE'S LOCAL DAY: a window's minutes are the garage's wall clock and its days are the garage's weekdays, measured at the window edges on the spring-forward and fall-back days where a UTC reading disagrees; and a stay's length is elapsed time between instants, computed in UTC, so a stay across the fall-back hour is an hour longer than its wall clocks say. |
| **G8** | An unknown vehicle identity gets a STATED answer -- not covered, NO_PASS, with the nearest ended or future registration named when there is one -- never an accidental refusal and never a silent pass. A BLANK identity is refused an answer, naming the field, because there is nothing to look up. |
| **G9** | A visit allowance and a maximum stay are computed from the module's OWN recorded visits and from nothing else, and the answer names its denominator: how many entries were counted, on which pass, over its life or in which window on which day; and which entry a stay was measured from. A maximum stay with no recorded entry to measure from is refused an answer, naming the field, never guessed. |
| **G10** | Row-level security on every table from migration 0001: a tenant column, ENABLE, FORCE and a policy on each, read from the catalogue and never from a list; isolation proven by a role that COULD bypass being shown it cannot; and every garage and pass reference is half of a composite tenant key, so a row cannot name another tenant's garage or pass even by a raw insert. |
| **G11** | Nothing real in the tree: no email address that is not obviously invented, no card-shaped value, and no name from the maintainer's other software, in any file git tracks -- swept in Python over `git ls-files` with a positive control that fires before the result is read, and by CI guards that self-test the same way. |
| **G12** | Every state change records WHO, WHEN and WHY, none blank, into an append-only history: the application role holds SELECT and INSERT on it and nothing else, read from the catalogue and proven by a refused UPDATE. The allowed transitions are the published ones, `expired` is derived from valid_to and refused if typed, and revoked outranks expiry. |
| **G13** | THE LABEL IS ONLY A LABEL. 'Monthly', 'employee', 'vendor' and the rest are free text the owner types, and no behaviour keys off them: two passes that differ only in label answer identically across every state, direction and term, and the source reads the label nowhere but to report it. |
| **G14** | The fixtures are capable of exercising what they claim: the shifting zone really shifts on the named transition days, the fixed zone really does not, and the terms matrix holds cases on both sides of every axis the access answer branches on. |
| **G15** | docs/CONTRACT.md is DERIVED: the guarantees, the refusals, the not-covered reasons, the barrier meanings, the answer fields, the states and transitions, the document keys and the worked example are generated from the registries and by running the module -- and the derivation is proven by plants that contradict the prose and require it to change, never by comparing two copies of the same claim. |
| **G16** | No test module sits outside the guarantee registry: every test module carries a registered guarantee mark or is named in an empty allowance, a module that plants a defect may not be excused, and a registered guarantee whose test did not run and pass fails the whole run unless its id is named in a written-down allowance that CI leaves empty. |

That is 16 guarantees. Every one of them has a fail control that has been proven to fire, and the count above is derived from the registry rather than typed here.
<!-- END:guarantees -->

## The answer

*Design documentation.* The access call takes a garage, the passes at it, the
registrations and recorded visits the caller holds, a vehicle identity, a lane, a
direction and an instant. It returns exactly one of three outcomes: **covered**,
**not covered** with a reason, or **refused to answer** naming the field that
would let it answer. It holds no session state, opens no gate and counts nobody.

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

That is the whole answer: 12 fields, none of which is money, and none of which could express a decision about a barrier. `outcome` is one of `covered`, `not_covered`, `refused_to_answer`.
<!-- END:answer-fields -->

### Not-covered reasons

*Design documentation.* The checks run in a fixed order and the first that fails
is the reason: revoked, then expired (derived), then suspended, then not yet
active, then not started; then direction, lane, window; then — at entry — the
visit allowance, and — at exit — the maximum stay.

<!-- GENERATED:not-covered -->
| reason | what the lane is told |
|---|---|
| `DIRECTION_NOT_ALLOWED` | The pass's terms do not state this direction. |
| `EXPIRED` | The pass's valid_to is before this day. Derived from the terms; nobody typed it. |
| `NOT_ACTIVE` | The pass this vehicle is registered to has not been activated: it is a draft, or it is awaiting enrolment. |
| `NOT_STARTED` | The pass's valid_from is after this day. |
| `NO_PASS` | No pass at this garage has this vehicle registered on this day. Where a registration once existed and has ended, the detail says which pass and when. |
| `OUTSIDE_WINDOW` | The pass has recurring windows and this instant, in the garage's local day, is inside none of them. |
| `OUT_OF_VISITS` | The pass's visit allowance is used up. The detail says how many were counted, out of how many, and over what. |
| `OVER_MAX_STAY` | This exit comes later after the recorded entry than the pass's maximum stay allows. Measured in elapsed time between the two instants, not in wall-clock hours. |
| `REVOKED` | The pass was revoked. Revocation is terminal. |
| `SUSPENDED` | The owner has put the pass on hold. The hold is reversible. |
| `WRONG_LANE` | The pass's terms name the lanes it may use, and this is not one. |
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
| `garage.transient_available` | The garage has not stated whether transient parking is available. There is no default and no inference: with it unstated, an uncovered entry is either an ordinary paying customer or a vehicle with nothing to be admitted as, and guessing between those is the difference between a car let in free and a fired employee driving into a building. State it on the garage. |
| `lane` | The lane is blank, so lane terms cannot be evaluated. |
| `registration.pass_id` | More than one pass at this garage has this vehicle registered on this day. The module refuses to pick one. That state cannot be produced through this module; it was handed in. |
| `vehicle_identity` | The vehicle identity is blank, so there is nothing to look up. An unknown identity gets a stated answer; a missing one gets none. |
| `visit.entered_at` | The pass has a maximum stay and no recorded entry of this vehicle on this pass is open, so the stay's length cannot be measured. It is not guessed. |
<!-- END:refused-to-answer -->

## The pass

*Design documentation.* A pass belongs to one garage, carries an owner-typed
label that no behaviour reads, a holder (an email address, optionally a name and
a phone; no account), its terms, its state, and the vehicles registered to it.

### Terms

*Design documentation.* Six things, each stated or absent, with no default:

1. **valid_from / valid_to** — inclusive calendar days in the garage's local day.
2. **windows** — recurring: ISO weekdays plus minutes from local midnight,
   half-open `[start, end)`, `1440` being the end of the day.
3. **max_stay** — a duration, measured at exit as elapsed time from the recorded entry.
4. **visit_allowance** — a count, over the pass's life or per window occurrence.
5. **directions** — entry, exit or both. Nothing is implicit.
6. **allowed_lanes** — a named set; absent means every lane of the garage.

A contradiction between them is refused when the pass is created:

<!-- GENERATED:refusals -->
| code | when, and what to do about it |
|---|---|
| `REFUSAL_ALLOWANCE_PER_WINDOW_WITHOUT_WINDOWS` | The visit allowance is counted per window and the pass has no windows, so there is nothing to count it against. |
| `REFUSAL_CONSTRAINT` | The database refused the write by a constraint the module did not catch first. Named by its constraint so it is a refusal and not a traceback; two writers racing end here. |
| `REFUSAL_EXIT_BEFORE_ENTRY` | The exit instant is earlier than the entry it would close. |
| `REFUSAL_EXPIRED_IS_DERIVED` | Expired is derived from the pass's valid_to and is never typed by anyone. To end a pass early, revoke it; to end it on a day, that day is valid_to. |
| `REFUSAL_FIELD_BLANK` | A required field is blank. The field is named beside this code. |
| `REFUSAL_GARAGE_MISMATCH` | A pass belongs to one garage and was asked about another. One garage per pass is the stated shape. |
| `REFUSAL_HOLDER_EMAIL_MALFORMED` | The holder's email address does not look like one -- it needs one @ with something on both sides. The email is the holder's identity in this module, so a malformed one identifies nobody. |
| `REFUSAL_LANES_STATED_BUT_EMPTY` | The allowed lanes are stated as an empty set. Absent means every lane; an empty set means no lane, which covers nothing. |
| `REFUSAL_LANE_NAME_BLANK` | A lane name is blank. |
| `REFUSAL_MAX_STAY_LONGER_THAN_WINDOW` | The maximum stay is longer than a recurring window it sits in. A stay that could not fit inside the window that admits it is a contradiction the gate would otherwise have to resolve; shorten the stay or widen the window. |
| `REFUSAL_MAX_STAY_NOT_POSITIVE` | The maximum stay is zero or negative. A pass that allows no time inside covers nothing; state a positive duration, or no maximum. |
| `REFUSAL_NO_DIRECTIONS` | The pass states no direction. Nothing is implicit: a privilege the terms do not state does not exist, so a pass that names neither entry nor exit covers nothing. |
| `REFUSAL_NO_OPEN_VISIT` | No recorded entry of this vehicle on this pass is still open, so there is no visit for this exit to close. |
| `REFUSAL_PASS_ALREADY_EXISTS` | A pass with that id already exists at that garage. |
| `REFUSAL_PASS_NOT_FOUND` | No pass with that id at that garage in this tenant. |
| `REFUSAL_REGISTRATION_ALREADY_ENDED` | That registration already has an end day. A registration is ended once; to move the day, that is a new registration. |
| `REFUSAL_REGISTRATION_ENDS_BEFORE_IT_STARTS` | The registration ends on or before the day it takes effect, so it covers no day. |
| `REFUSAL_REGISTRATION_NOT_FOUND` | No registration of that vehicle on that pass. |
| `REFUSAL_REGISTRATION_OUTLIVES_THE_PASS` | The registration's end day is past the pass's valid_to. A vehicle cannot be on a pass on a day the pass does not cover; leave end_day unstated and it runs to the pass's last day. |
| `REFUSAL_REVOKED_IS_TERMINAL` | A revoked pass is revoked. It never becomes active again; a new pass is a new pass. |
| `REFUSAL_STATE_CHANGE_NEEDS_WHO_AND_WHY` | A state change records who made it and why, and one of those is blank. |
| `REFUSAL_STATE_TRANSITION_NOT_ALLOWED` | The pass cannot move from its current state to the one asked for. The allowed moves are published in the contract. |
| `REFUSAL_STATE_UNKNOWN` | The state named is not one this module has. |
| `REFUSAL_UNKNOWN_FIELD` | A document carries a field this module does not know. It is refused rather than ignored: a field silently dropped is a term the owner believes is in force and is not. |
| `REFUSAL_VALID_TO_BEFORE_VALID_FROM` | The pass ends before it starts: valid_to is earlier than valid_from. There is no day on which such a pass could cover anything, so it is not created. |
| `REFUSAL_VEHICLE_ON_ANOTHER_PASS` | This vehicle identity is already registered to another pass at this garage for days that overlap. One car, one pass: the refusal names the pass that holds it and the day that registration ends. End that registration first, or register from the day it ends. |
| `REFUSAL_VISIT_ALLOWANCE_NOT_POSITIVE` | The visit allowance is zero or negative. A pass allowing no visits covers nothing; state a positive count, or no allowance. |
| `REFUSAL_VISIT_ALREADY_OPEN` | A recorded entry of this vehicle on this pass is still open. Record its exit before recording another entry, or the visit ledger would hold a car inside twice. |
| `REFUSAL_WINDOW_DAY_UNKNOWN` | A recurring window names a day that is not 1 (Monday) to 7 (Sunday). |
| `REFUSAL_WINDOW_ENDS_BEFORE_IT_STARTS` | A recurring window ends at or before the minute it starts, so it is empty. A window that runs past midnight is two windows: one to 1440 on the first day and one from 0 on the next. |
| `REFUSAL_WINDOW_HAS_NO_DAYS` | A recurring window names no day of the week. A window that occurs on no day can never be satisfied; state at least one day, or remove the window. |
| `REFUSAL_WINDOW_MINUTE_OUT_OF_RANGE` | A window's start or end is outside 0 to 1440 minutes from local midnight. 1440 means the end of the day. |
| `REFUSAL_WINDOW_NEVER_OCCURS` | None of the days a recurring window names falls inside the pass's valid range, so the window can never be satisfied. Widen the range or change the days. |

33 refusals. Each is raised with the FIELD it is about, and none of them is raised by the access call about a term: a contradiction is refused when the pass is created.
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
history the application role can only read and append to. Revoking a pass ends
its registrations on the revocation day in the garage's local calendar.

### Registrations

*Design documentation.* A registration binds a vehicle identity to a pass for the
half-open range of local days `[effective_day, end_day)`. The identity is free
**from** `end_day`. One identity is on one pass per garage for any day; a pass
may carry many identities. Ending on day D and registering elsewhere effective D
is accepted, and the old pass covers the vehicle up to and not including D.

## Documents

*Design documentation.* The command line reads JSON documents of these shapes.

<!-- GENERATED:document-keys -->
| document | keys |
|---|---|
| garage | `id`, `timezone`, `transient_available` |
| pass | `garage_id`, `holder`, `id`, `label`, `state`, `terms` |
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

- `CAR-1` at lane `L1`, **entry**, `2026-06-01T12:00:00-06:00` → **covered** by `pass-employee-7` (Employee): valid 2026-01-01..2026-12-31; windows Mon,Tue,Wed,Thu,Fri 06:00-20:00; max stay 10:00:00; 3 visit(s) per window; directions entry+exit; lanes L1,L2; in window Mon,Tue,Wed,Thu,Fri 06:00-20:00 on 2026-06-01; visit 3 of 3; counted 2 recorded entries on pass 'pass-employee-7' in window Mon,Tue,Wed,Thu,Fri 06:00-20:00 on 2026-06-01
- `CAR-1` at lane `L1`, **exit**, `2026-06-01T12:00:00-06:00` → **covered** by `pass-employee-7` (Employee): valid 2026-01-01..2026-12-31; windows Mon,Tue,Wed,Thu,Fri 06:00-20:00; max stay 10:00:00; 3 visit(s) per window; directions entry+exit; lanes L1,L2; in window Mon,Tue,Wed,Thu,Fri 06:00-20:00 on 2026-06-01; stayed 3:00:00 of at most 10:00:00
  - exit note: *An exit is never refused. Whatever this answer says, the vehicle leaves.*
- `CAR-1` at lane `L1`, **entry**, `2026-06-01T05:30:00-06:00` → **not covered** — `OUTSIDE_WINDOW`, meaning `TRANSIENT_STAY`: 2026-06-01T05:30:00-06:00 is 2026-06-01 (Mon) 05:30 in America/Denver, inside none of: Mon,Tue,Wed,Thu,Fri 06:00-20:00.
- `CAR-1` at lane `L9`, **entry**, `2026-06-01T12:00:00-06:00` → **not covered** — `WRONG_LANE`, meaning `TRANSIENT_STAY`: pass 'pass-employee-7' allows lanes ['L1', 'L2'], not 'L9'.
- `NOBODY` at lane `L1`, **entry**, `2026-06-01T12:00:00-06:00` → **not covered** — `NO_PASS`, meaning `TRANSIENT_STAY`: no registration of 'NOBODY' at garage 'garage-downtown' on 2026-06-01.
- `NOBODY` at lane `L1`, **exit**, `2026-06-01T12:00:00-06:00` → **not covered** — `NO_PASS`, meaning `EXIT_OUT_OF_TERMS`: no registration of 'NOBODY' at garage 'garage-downtown' on 2026-06-01.
  - exit note: *An exit is never refused. Whatever this answer says, the vehicle leaves.*
<!-- END:worked-example -->

## The store

*Design documentation.* `migrations/0001_garages_passes_registrations_and_rls.sql`
creates the tables with row-level security from the first migration, an
application role that cannot bypass it, a composite tenant key on every garage
and pass reference, and the one-car-one-pass constraint as an `EXCLUDE` over the
registration's day range. Apply it as the database owner:

```
psql "$DSN" -v ON_ERROR_STOP=1 -f migrations/0001_garages_passes_registrations_and_rls.sql
GARAGE_PASS_APP_PASSWORD=... python scripts/ensure-app-role.py "$DSN"
```

The application connects as `garage_pass_app` and sets the tenant per transaction
(`SELECT set_config('garage_pass.tenant_id', ..., true)`). A connection that has
not set it sees nothing.

---

Built by 72 Knots Method by 72Knots.ai
