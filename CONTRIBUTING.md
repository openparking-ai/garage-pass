# Contributing to Open Parking AI

Contributions are welcome. This page is short on purpose; everything on it is
enforced mechanically, so there is nothing to remember.

## Before your first pull request: sign the CLA

Read [CLA.md](CLA.md), then open a pull request that adds one entry to
`cla/signatures.json` and changes nothing else:

```json
{ "github": "your-github-login", "name": "Your Full Legal Name", "date": "YYYY-MM-DD" }
```

That pull request is your signature. Once it is merged, your later pull requests
pass the CLA check automatically.

The CLA grants 72 Knots the right to relicense contributions. Section 3 of
[CLA.md](CLA.md) explains why in plain terms. If you are not comfortable with
that clause, please do not contribute — it is not negotiable, and it is better
to know before you spend time on a change.

## How a change gets in

1. Open an issue first for anything larger than a fix. Agreeing on the approach
   is cheaper than reviewing the wrong one.
2. Branch from `main`. Nobody pushes to `main` directly; the branch protection
   refuses it.
3. Open a pull request. Every check must be green before it can merge: `lint`,
   `test` on each interpreter, `controls`, `docs`, `cla` and `emails`.
4. A maintainer reviews and merges. Opening the pull request is not merging it.

## What gets rejected on sight

**Real personal data, anywhere in the repository.** Fixtures, tests, documents
and examples use invented values — `example.com` addresses, made-up names,
vehicle identities that belong to nobody. This applies to git metadata too:
commit with a masked address, not a personal one. The running system stores
real holders and real vehicle identities; that is the product, it is governed by
retention, and it is a different thing from what is committed here. The CI
guards enforce it and every one ships with a self-test that proves it can fail.

**Money, anywhere.** A pass does not know what anything costs. No fee, no
amount, no balance, no processor — not on the answer, not in the schema, not in
a document. A guarantee reads the answer's fields and the catalogue's columns
for it.

**A field that decides an exit.** An exit is never refused. There is no field
on the answer that could express one, and there will not be.

**A pass type.** "Monthly", "employee", "vendor" are labels the owner types.
Code that reads the label for anything but reporting it is rejected; a
guarantee scans the source for it.

**A dependency on Open Parking AI's platform, or on any hosted service.** This
module is standalone by definition. Our own platform is an ordinary client of
it.

**A test that has never been seen to fail.** If you add a guarantee, register it
in `tests/_guarantees.py` and add a control to `scripts/fail_controls.py` that
breaks the thing it guards and requires red. The suite refuses to finish with a
registered guarantee unproven, and the controls job refuses to run with one
uncontrolled.

**A silent guess.** Where the module cannot answer without guessing — a garage
that has not said whether it sells transient parking, a maximum stay with no
recorded entry to measure from — it refuses to answer and names the field. It
does not pick the likely answer and present it as a fact.

**A consumer-visible change to the answer without a version bump.**
`docs/CONTRACT.md` is the public surface. Adding a field is additive and does
not bump it; removing, renaming or redefining one does.

## Style

Match the code already there — its naming, its comment density, its idioms. A
change that reads like the file it lands in is easier to review than a better
one that does not.

Comments should say why, not what.

---

Built by 72 Knots Method by 72Knots.ai
