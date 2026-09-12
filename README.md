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
lane saw, answer the lane from what is actually recorded.

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
maximum stay longer than the window it sits in, an allowance of zero — none of
them can be constructed, so none is ever discovered at a gate at seven in the
morning.

### States

`draft`, `awaiting_enrolment`, `active`, `suspended`, `revoked` — and `expired`,
which is derived from the terms and which nobody can type. **Revoked is
terminal.** Every change records who, when and why, into a history the
application can only append to.

### One car, one pass per garage

A vehicle identity is on one pass at a garage for any given day. A second
registration is refused by name — naming the pass that holds the identity and
the day that registration ends — before the database's own constraint has to;
the constraint is the backstop for a raw insert and for two writers racing.
Ending a registration on day D frees the identity **from** D.

## The answer

**Covered**, with the pass and the term that covers it. **Not covered**, with a
plain reason: no pass · not active · not started · expired · suspended ·
revoked · direction not allowed · wrong lane · outside window · out of visits ·
over maximum stay. Or **refused to answer**, naming the field that would let it
— a garage that has not stated whether it sells transient parking, a blank
identity, a maximum stay with no recorded entry to measure from. It does not
guess.

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
revocation keeps a vehicle inside a garage.** Every exit answer, whatever its
outcome, carries the sentence that says so, and the exit half of the call does
not read the garage's transient mode at all.

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

The store needs a database with the migration applied as its owner, and the
application role given a login:

```
psql "$DSN" -v ON_ERROR_STOP=1 -f migrations/0001_garages_passes_registrations_and_rls.sql
GARAGE_PASS_APP_PASSWORD=... python scripts/ensure-app-role.py "$DSN"
```

The suite reads `GARAGE_PASS_TEST_DSN` for a database it may drop and rebuild.
Without one, the store-backed tests skip and the run **fails**, on purpose: a
guarantee whose test did not run is not a guarantee.

## Licence

AGPL-3.0. Contributions need a signed CLA — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

Built by 72 Knots Method by 72Knots.ai
