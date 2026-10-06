# Contributing to Open Parking AI

Open Parking AI does not accept outside contributions. Pull requests, issues and comments are limited to the maintainers.

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

**A name from outside this project.** No product, module or hostname from the
maintainer's other, private software appears here — not in code, a comment, a
document, a test, a fixture, a file's path or a commit message.
`.github/scripts/check-no-sibling-names.js` enforces it in CI.

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
