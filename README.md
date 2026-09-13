# Open Parking AI — garage pass

**This vehicle, at this lane, going this direction, at this instant — does a
pass cover it, and if not, why not?** That question, and nothing else.

Standalone. It runs with no parking system around it, no platform, and — for
the answer itself — no database and no dependencies at all.

```
$ garage-pass check-terms --pass pass.json
$ garage-pass access --garage garage.json --pass pass.json \
      --registrations registrations.json --visits visits.json \
      --vehicle CAR-1 --lane L1 --direction entry --at 2026-06-01T12:00:00-06:00
```

And, against the store: create the pass, register the vehicle, record what the
lane saw, answer the lane from what is actually recorded. Exit status 0 covered,
1 not covered, 2 refused to answer or the machine's configuration (one sentence
on stderr: no DSN, a database that does not connect or is not migrated, a role
without its grants, no timezone database), 3 the request was refused — and a
refusal is always the JSON `{"refused", "field", "detail"}`, never a traceback:
a mistyped timezone, a document that is not JSON, an instant without an offset,
a day that does not parse, and — at an entry — a field of the wrong type are each
refused naming the field and the value; at an exit a document the module cannot
read is answered not-covered naming the field, because an exit is never refused. **Every value a document carries is checked against
the type the dataclass it loads into declares** — derived from the annotation,
not from a list, so a field added later is covered the day it is added — and a
string is never reinterpreted as a list of its characters. What the database
driver raises that the store did not turn into a named refusal is the sentence
on stderr with its SQLSTATE, exit 2, mapped last: the refusals the store names
(a unique violation, the one-car-one-pass exclusion, a deadlock with its DETAIL)
keep their names.

```
$ garage-pass create-pass --tenant T --garage garage-downtown --pass pass.json --by owner --at ...
$ garage-pass register-vehicle --tenant T --garage garage-downtown --pass-id pass-1 \
      --vehicle CAR-1 --effective-day 2026-06-01
$ garage-pass record-entry --tenant T --garage garage-downtown --pass-id pass-1 \
      --vehicle CAR-1 --lane L1 --at 2026-06-01T09:00:00-06:00
$ garage-pass access-in-store --tenant T --garage garage-downtown \
      --vehicle CAR-1 --lane L1 --direction exit --at 2026-06-01T12:00:00-06:00
```

## What a pass is

One garage. An owner-typed **label** — "Employee", "Monthly", "Vendor", whatever
the owner needs — that no behaviour reads. A **holder**: an email address, and
optionally a name and a phone; no account, no login. Its **terms**. Its
**state**. The **vehicles** registered to it.

**There are not five pass types.** The only structural difference between
passes is which other module is connected to them, and in this version none is.

### Terms — six things, each stated or absent, no defaults

A valid-from / valid-to range in the garage's local day. Recurring windows: days
of the week plus minutes of the local day. A maximum stay per visit. A visit
allowance, over the pass's life or per window. The directions the pass states —
entry, exit or both; nothing is implicit. The lanes it may use; absent means
every lane.

**A contradiction is refused when the pass is created, naming the field.** A
valid-to before valid-from, a weekend window on a Monday-to-Wednesday pass, a
maximum stay of zero, an allowance of zero — none of them can be constructed, so
none is ever discovered at a gate at seven in the morning. And only a
contradiction is refused: a maximum stay longer than a window is slack, not a
contradiction — windows bind the moments a car enters and leaves, never the stay
between them — so a six-hour maximum beside two four-hour windows is created,
and binds at the exit.

### States

`draft`, `awaiting_enrolment`, `active`, `suspended`, `revoked` — and `expired`,
which is derived from the terms and which nobody can type. **Revoked is
terminal.** Every change records who, when and why, into a history the
application can only append to — it holds no UPDATE or DELETE on the history
and no DELETE on anything the history belongs to, so it cannot be erased by
deleting the pass.

### One car, one pass per garage

A vehicle identity is on one pass at a garage for any given day. A second
registration is refused by name — naming the pass that holds the identity, its
state and the day that registration ends — before the database's own constraint
has to; every open registration counts as a holder whatever its pass's state,
so the constraint is the backstop for a raw insert and for two writers
genuinely racing, and nothing else reaches it through the module. Ending a
registration on day D frees the identity **from** D.

**A vehicle is registered onto a draft, awaiting-enrolment or active pass.** A
registration onto a suspended pass (a hold; a car added to a hold is a claim the
owner did not make), a revoked pass (revoked is revoked) or an expired one (over,
derived from `valid_to` against the registration's effective day) is refused by
name, naming the state.

## The answer

**Covered**, with the pass and the term that covers it. **Not covered**, with a
plain reason: no pass · not active · not started · expired · suspended ·
revoked · direction not allowed · wrong lane · outside window · out of visits ·
over maximum stay · a pass or garage carrying a value the module cannot read
· at an exit, a blank identity or lane. Or — **at an entry only** — **refused to
answer**, naming the field that would let it: a garage that has not stated
whether it sells transient parking, a blank identity, a pass whose stored terms
cannot be read. It does not guess: a maximum stay with no recorded entry to
measure from is answered on the terms that can be evaluated and named
**unmeasured**, never silently satisfied.

**No fee, no amount, no balance ever crosses this call.** It is an access fact.

**This module never opens or closes a gate**, never counts who is inside and
holds no session state. It answers; the lane acts. What it holds is a ledger of
the visits the lane told it about, because a visit allowance and a maximum stay
are computed from those rows and from nothing else — and the answer says what
it counted, on which pass, over what.

### An exit is never refused

A pass's terms govern entry and which lanes may be used. At exit the same terms
are evaluated — an exit outside them is answered not-covered with its reason, so
that a transient garage can charge the stay — but **no term, no state and no
revocation keeps a vehicle inside a garage.** Every exit is answered covered or
not covered — refused-to-answer is not an outcome an exit can have; whatever
cannot be evaluated is named — every exit answer carries the sentence that says
so, and the exit half of the call does not read the garage's transient mode at
all. A pass stored with terms the module refuses to read — a raw write, or a
validator tightened after the pass was stored — is answered not-covered at the
exit, naming the pass and the field, which at a transient garage means the stay
is chargeable: said so, so nobody reads it as a free exit, and named so the
operator can find the row. Inconsistent data is answered too: a registration
naming a pass that was not handed in is not-covered at the exit, naming that
pass, never an exception; a pass handed in twice under one id is never resolved
by the order the copies arrived in — every copy is evaluated, the holder is
covered if any copy covers, the duplication is named, and the same inputs in any
order give the same answer (at an entry the call refuses to answer, naming the
id, whether or not the copies agree).

**What that sentence does not cover, named because it cannot be otherwise — a
class proven closed by execution, not a list:** a value of a type the signature
does not accept — for any parameter of the call, or any element of its
sequences; an instant with no timezone is one — raises on the first touch,
before there is a movement to answer about, and never answers (the test
enumerates the signature and hands every parameter a wrong-typed value); and a
machine with no timezone database at all raises by its own name, never as an
unknown zone, because nothing can be read on it. Neither is a term, a state, a
revocation or data.

**The module answers when it holds a record whose content it cannot read, and
refuses when it holds no record at all, or no instant to read it at.** A stored
row it cannot read loads unreadable and answers; a document it cannot read — a
field missing, of the wrong type or unknown, a contradiction, an unknown zone —
is answered at an exit the same way: a pass or garage document degrades to the
unreadable pass or garage a stored row becomes, a registration or visit
document to a not-covered answer naming the document and the field. At an entry
the same document is refused by name. A file that is missing or is not JSON,
and an instant that does not parse, are refused in both directions: there is no
record, or no now. (A missing file breaks the integrator's own invocation at
every lane in both directions — an outage of the integration, not a wrong
answer; a malformed record breaks one parker while everything else works, and
that is the car that must not be stuck.)

### What not-covered means depends on the garage

At a garage that sells transient parking, an uncovered entry is an ordinary
paying customer. At a garage that sells none — staff only — there is nothing for
an uncovered vehicle to be admitted as. **Which one a garage is, it states; there
is no default and no inference.** Left unstated, the access call refuses to
answer an entry and names the field.

## A calendar day is the garage's local day

A window of 06:00–20:00 is the wall clock on the garage's door, and "Monday" is
Monday where the garage stands. The tests measure this at the window edges on the
spring-forward and fall-back days, where a UTC reading disagrees — and a stay's
length is elapsed time between instants, so a stay across the fall-back hour is
an hour longer than its wall clocks say.

## What is guaranteed, and how you can tell

`docs/CONTRACT.md` lists every guarantee. Each one has a test that CI requires
to run and pass, and a fail control in `scripts/fail_controls.py` that breaks
the thing it guards and requires the test to go red. The contract's tables are
generated from the code's own registries and checked on every run; a number or a
sentence edited by hand fails the build.

## What this version does not do

No enrolment — no QR, no token, no email, no lane binding, no vehicle
identification; a vehicle identity here is an opaque value the caller supplies.
No money. No connection to any billing module, and no reservations of either
kind. No accounts, no screens. One garage per pass.

## Install

```
pip install -e .            # the engine: standard library only
pip install -e '.[store]'   # with the Postgres store
pip install -e '.[dev]'     # to run the suite and the controls
```

The store needs a database with the migrations applied in order as its owner,
and the application role given a login:

```
for m in migrations/*.sql; do psql "$DSN" -v ON_ERROR_STOP=1 -f "$m"; done   # 0001, then 0002
GARAGE_PASS_APP_PASSWORD=... python scripts/ensure-app-role.py "$DSN"
```

Both steps are run by the suite, not only described here: a test applies the
migration and runs `ensure-app-role.py` against the test cluster, logs in as the
application role with the password it set, and shows a wrong one refused.

A garage stored with a timezone the running system does not carry — a raw
write, or tzdata that lost the name — still answers (not-covered at an exit,
refused-to-answer at an entry, naming `garage.timezone`), but takes no write
until it is repaired; the repair is the one write it takes:

```
$ garage-pass set-garage-timezone --tenant T --garage garage-downtown --timezone America/Denver \
      --by operator --at 2026-06-01T12:00:00-06:00 --reason "stored from a laptop as america/denver"
```

The repair is recorded — who, when, why, the old value and the new — into a
garage history the application can only append to, exactly as a pass state
change is; a repair with no who or no why is refused and changes nothing. The
zone name is checked case-exactly against the tz database's own names, so
`america/denver` is refused on every filesystem, not only a case-sensitive one.

**A timezone database is required.** The engine reads every term in the
garage's local day and cannot read one without a tz database; it does not ship
one. On a machine with none — no system zoneinfo and no Python `tzdata`
package — every command says so by name on stderr and exits 2, rather than
refusing each good zone as unknown. Install the system tz database (`tzdata`
on Debian, Ubuntu, Alpine and the RPM family) or `pip install tzdata`.

The suite reads `GARAGE_PASS_TEST_DSN` for a database it may drop and rebuild.
Without one, the store-backed tests skip and the run **fails**, on purpose: a
guarantee whose test did not run is not a guarantee.

## Licence

AGPL-3.0. Contributions need a signed CLA — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

Built by 72 Knots Method by 72Knots.ai
