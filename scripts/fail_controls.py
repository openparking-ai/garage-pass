#!/usr/bin/env python3
"""Every guarantee, proven able to FAIL.

A test that has never failed is a decoration. For each registered guarantee this
script breaks the thing the guarantee guards, runs that guarantee's tests in a
fresh interpreter, and requires them to go RED. If a test stays green with its
subject broken, it was not measuring its subject and this script says so.

    python scripts/fail_controls.py            # every control
    python scripts/fail_controls.py G2 G9      # a subset
    python scripts/fail_controls.py --anchors  # anchors only, in a second

**The anchor pre-flight.** ``--anchors`` counts every plant's ``from`` string in
its file without running a single test. An anchor is a string in a source file,
and editing the line it sits on silently retires the control that depends on it
-- a sibling repository in this project had five dead controls killed exactly
that way. The pre-flight answers that whole failure mode in a second.

**Restores are written back, never `git checkout`.** Each plant is a context
manager whose ``finally`` writes the original bytes and verifies them.

**AND A CONTROL THAT REPORTS UNMEASURED IS REPORTING ON THE RUNNER.** If a target
is already red before anything is planted, or ran no tests at all, this says
UNMEASURED rather than counting a pass. Check the runner (is the package
installed? is a database reachable for the ones that need one?) before reading
anything into the subject.

**A TARGET WHOSE TESTS ALL SKIP IS REPORTED "NOT A CONTROL", NOT UNMEASURED.**
``_NOTHING_RAN`` matches "0 passed", "no tests ran" and "collected 0 items"; an
all-skipped target prints none of those, so the target stays green with its
subject broken and the verdict is DEAD. That is what happens to a store-backed
control on a machine with no database. Read a DEAD verdict on one of those as
"check whether you gave it a database" first. The exit status is 1 either way.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from _guarantees import GUARANTEES  # noqa: E402
from plant import planted, resolve  # noqa: E402


def source(*lines: str) -> str:
    """A block of source code, one argument per line."""
    return "\n".join(lines)


def guarantee_of(control_id: str) -> str:
    """``G7/elapsed`` -> ``G7``. One guarantee can need more than one plant."""
    return control_id.split("/", 1)[0]


G1 = "tests/test_g1_one_car_one_pass.py"
G3 = "tests/test_g3_no_money_crosses_the_answer.py"
G4 = "tests/test_g4_an_exit_is_never_refused.py"
G5 = "tests/test_g5_revoked_is_revoked.py"
G7 = "tests/test_g7_the_garages_local_day.py"
G8 = "tests/test_g8_an_unknown_identity_gets_a_stated_answer.py"
G9 = "tests/test_g9_visits_and_stays_from_the_ledger.py"
G10 = "tests/test_g10_rls_from_migration_0001.py"
G11 = "tests/test_g11_nothing_real_in_the_tree.py"
G12 = "tests/test_g12_state_changes_are_append_only.py"
MIGRATION = "migrations/0001_garages_passes_registrations_and_rls.sql"

#: control id -> (test target, source file, anchor, replacement, what breaks)
CONTROLS: dict[str, tuple[str, str, str, str, str]] = {
    "G1/refusal": (
        G1, "store/records.py",
        source(
            "        raise Refused(",
            "            REFUSAL_VEHICLE_ON_ANOTHER_PASS,",
        ),
        source(
            "        continue  # PLANTED: the second pass takes the vehicle",
            "        raise Refused(",
            "            REFUSAL_VEHICLE_ON_ANOTHER_PASS,",
        ),
        "the module no longer refuses by name; the INSERT reaches the EXCLUDE and "
        "the caller gets a constraint, not the surviving pass and the day it ends",
    ),
    "G1/overlap-query": (
        G1, "store/records.py",
        "          AND daterange(r.effective_day, r.end_day, '[)') && daterange(%s, %s, '[)')",
        "          AND r.end_day IS NULL  -- PLANTED: only open-ended registrations are seen",
        "a registration with an end day is invisible to the check, so a second pass "
        "is accepted over it -- the refusal that should name the end day never fires",
    ),
    "G1/exclude": (
        G1, MIGRATION,
        source(
            "  CONSTRAINT vehicle_registrations_one_pass_per_garage EXCLUDE USING gist (",
            "    tenant_id WITH =,",
            "    garage_id WITH =,",
            "    vehicle_identity WITH =,",
            "    daterange(effective_day, end_day, '[)') WITH &&",
            "  ),",
        ),
        "  -- PLANTED: the EXCLUDE removed",
        "the database backstop is gone: a raw insert of a second pass for the same "
        "vehicle is accepted, and so is the second of two writers racing",
    ),
    "G2": (
        "tests/test_g2_contradictions_refuse_at_creation.py", "terms.py",
        '    a contradictory ``Terms`` value cannot exist."""',
        source(
            '    a contradictory ``Terms`` value cannot exist."""',
            "    return  # PLANTED: the validator accepts everything",
        ),
        "every contradiction is accepted at creation and would be met at the gate",
    ),
    "G2/field": (
        "tests/test_g2_contradictions_refuse_at_creation.py", "terms.py",
        source(
            "                REFUSAL_VALID_TO_BEFORE_VALID_FROM,",
            '                "valid_to",',
        ),
        source(
            "                REFUSAL_VALID_TO_BEFORE_VALID_FROM,",
            '                "valid_from",  # PLANTED: the wrong field is named',
        ),
        "the refusal names the wrong field, sending the owner to the wrong box",
    ),
    "G3/answer": (
        G3, "access.py",
        "    exit_note: str | None\n",
        source(
            "    exit_note: str | None",
            "    amount_minor: int = 0  # PLANTED: money on the answer",
            "",
        ),
        "a monetary field sits on the answer every lane reads",
    ),
    "G3/schema": (
        G3, MIGRATION,
        "  holder_phone      text,",
        source(
            "  holder_phone      text,",
            "  fee_minor         bigint,  -- PLANTED: a money column",
        ),
        "the schema carries a money-shaped column",
    ),
    "G3/documents": (
        G3, "documents.py",
        "    unknown = sorted(set(document) - known)",
        "    unknown = []  # PLANTED: unknown keys are ignored",
        "a document field this module does not know is dropped silently -- a "
        "reservation-shaped or money-shaped field would be accepted and ignored",
    ),
    "G4/means": (
        G4, "access.py",
        source(
            "        if direction is Direction.EXIT:",
            "            means = MEANS_EXIT_OUT_OF_TERMS",
        ),
        source(
            "        if False:  # PLANTED: an exit is answered like an entry",
            "            means = MEANS_EXIT_OUT_OF_TERMS",
        ),
        "a not-covered exit at a no-transient garage means NOTHING_TO_ADMIT_AS -- "
        "the lane reads that as a refusal, and a car is inside",
    ),
    "G4/note": (
        G4, "access.py",
        "    exit_note = EXIT_IS_NEVER_REFUSED if direction is Direction.EXIT else None",
        "    exit_note = None  # PLANTED: the sentence is dropped",
        "the exit answers stop carrying the sentence that says the vehicle leaves",
    ),
    "G4/transient-at-exit": (
        G4, "access.py",
        "    if direction is Direction.ENTRY and garage.transient_available is None:",
        "    if garage.transient_available is None:  # PLANTED: exits read the field",
        "an exit at a garage with no stated transient mode is refused an answer -- "
        "an exit that depends on configuration",
    ),
    "G4/revoked-exit": (
        G4, "access.py",
        '        return not_covered(REVOKED, f"pass {pass_.id!r} is revoked.", pass_)',
        source(
            "        if direction is Direction.EXIT:  # PLANTED: a revoked exit is refused",
            '            return refused(MISSING_ONE_PASS, "revoked")',
            '        return not_covered(REVOKED, f"pass {pass_.id!r} is revoked.", pass_)',
        ),
        "a revoked pass refuses an answer at exit",
    ),
    "G5/revoked-branch": (
        G5, "access.py",
        "    if state == State.REVOKED.value:",
        "    if False:  # PLANTED: revoked falls through to its terms",
        "a revoked pass with satisfiable terms is covered at entry",
    ),
    "G5/terminal": (
        G5, "states.py",
        source(
            "    if pass_.state is State.REVOKED:",
            "        raise Refused(",
            "            REFUSAL_REVOKED_IS_TERMINAL,",
        ),
        source(
            "    if False:  # PLANTED: revoked is not special",
            "        raise Refused(",
            "            REFUSAL_REVOKED_IS_TERMINAL,",
        ),
        "leaving revoked is refused by the generic transition rule, not by name",
    ),
    "G5/revocation-ends": (
        G12, "store/records.py",
        "    if to is State.REVOKED:",
        "    if False:  # PLANTED: revocation leaves registrations open",
        "a revoked pass keeps holding its vehicles; they cannot be registered elsewhere",
    ),
    "G6": (
        "tests/test_g6_transient_mode_is_stated.py", "access.py",
        '        return refused(MISSING_TRANSIENT_MODE, f"garage {garage.id!r}.")',
        "        pass  # PLANTED: unstated falls through to a guessed default",
        "a garage that never said whether it sells transient answers as if it said "
        "no -- an uncovered entry is NOTHING_TO_ADMIT_AS by default",
    ),
    "G7/minute": (
        G7, "localday.py",
        "    wall = local(moment, tz)\n    return wall.hour * 60 + wall.minute",
        "    wall = require_aware(moment).astimezone(UTC)  # PLANTED: the UTC clock\n"
        "    return wall.hour * 60 + wall.minute",
        "a window's minutes are read off the UTC clock",
    ),
    "G7/weekday": (
        G7, "localday.py",
        "    return day_of(moment, tz).isoweekday()",
        "    return require_aware(moment).astimezone(UTC).isoweekday()  # PLANTED",
        "a window's weekday is the UTC weekday",
    ),
    "G7/day": (
        G7, "localday.py",
        "    return local(moment, tz).date()",
        "    return require_aware(moment).astimezone(UTC).date()  # PLANTED",
        "the valid range and the registration day are read on the UTC calendar",
    ),
    "G7/elapsed": (
        G7, "localday.py",
        source(
            '    return require_aware(end, "the end").astimezone(UTC) - require_aware(',
            '        start, "the start"',
            "    ).astimezone(UTC)",
        ),
        '    return require_aware(end, "the end") - require_aware(start, "the start")  # PLANTED',
        "a stay is measured by wall clocks: an hour short across fall-back",
    ),
    "G8/no-pass": (
        G8, "access.py",
        source(
            "        return not_covered(",
            "            NO_PASS,",
            '            f"no registration of {identity!r} at garage {garage.id!r} on {today}.",',
            "        )",
        ),
        '        return refused(MISSING_VEHICLE_IDENTITY, "PLANTED: unknown treated as missing")',
        "an unknown identity is refused an answer instead of being told NO_PASS",
    ),
    "G8/blank": (
        G8, "access.py",
        "    if not identity:\n        return refused(MISSING_VEHICLE_IDENTITY",
        "    if False:  # PLANTED: a blank identity is looked up\n"
        "        return refused(MISSING_VEHICLE_IDENTITY",
        "a blank identity is looked up as if it were a vehicle and answered NO_PASS",
    ),
    "G9/per-window": (
        G9, "access.py",
        "        if day_of(v.entered_at, tz) == today",
        "        if True or day_of(v.entered_at, tz) == today  # PLANTED: the whole life",
        "a per-window allowance counts every entry the pass ever recorded",
    ),
    "G9/denominator": (
        G9, "access.py",
        '            f"pass {pass_.id!r} over its life"',
        '            f"pass {pass_.id!r}"  # PLANTED: the denominator dropped',
        "the count no longer says what it was counted over",
    ),
    "G9/open-visit": (
        G9, "access.py",
        "        if v.pass_id == pass_.id and v.vehicle_identity.strip() == identity and v.is_open",
        "        if v.pass_id == pass_.id and v.is_open  # PLANTED: any vehicle's entry",
        "a stay is measured from whichever vehicle on the pass entered last",
    ),
    "G9/missing-entry": (
        G9, "access.py",
        "        if open_visit is None or at < open_visit.entered_at:",
        "        if False:  # PLANTED: no entry, and the stay is measured anyway",
        "an exit with no recorded entry is no longer refused an answer",
    ),
    "G10/force": (
        G10, MIGRATION,
        "ALTER TABLE passes FORCE  ROW LEVEL SECURITY;",
        "-- PLANTED: FORCE removed from passes",
        "one table ships without FORCE ROW LEVEL SECURITY",
    ),
    "G10/composite": (
        G10, MIGRATION,
        source(
            "  CONSTRAINT visits_pass_in_tenant",
            "    FOREIGN KEY (tenant_id, pass_id) REFERENCES passes (tenant_id, id) "
            "ON DELETE CASCADE",
        ),
        "  CONSTRAINT visits_pass_in_tenant FOREIGN KEY (pass_id) REFERENCES passes (id)"
        "  -- PLANTED",
        "one pass reference is a bare key, which a raw insert can point across tenants",
    ),
    "G10/with-check": (
        G10, MIGRATION,
        source(
            "CREATE POLICY garages_tenant_isolation ON garages",
            "  USING      (tenant_id = current_tenant_id())",
            "  WITH CHECK (tenant_id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY garages_tenant_isolation ON garages FOR SELECT",
            "  USING      (tenant_id = current_tenant_id());",
            "CREATE POLICY garages_planted_writes ON garages FOR INSERT",
            "  WITH CHECK (true);  -- PLANTED: reads isolated, writes open",
        ),
        "reads are isolated and writes are not: a tenant can insert another's row. "
        "(Merely dropping WITH CHECK is no plant: PostgreSQL then applies USING to "
        "writes as well, measured -- the first cut of this control stayed green.)",
    ),
    "G11/luhn": (
        G11, G11,
        "    return total % 10 == 0",
        "    return False  # PLANTED: nothing is card-shaped",
        "the card sweep cannot fire on anything",
    ),
    "G11/allowlist": (
        G11, G11,
        "        if not any(rule.search(address) for rule in _ALLOWED_EMAIL)",
        "        if False  # PLANTED: every address is allowed",
        "the email sweep cannot fire on anything",
    ),
    "G11/tokens": (
        G11, G11,
        "        if is_upper and previous_was_lower and current:",
        "        if False:  # PLANTED: no split on a case transition",
        "a name hidden inside an identifier is not found",
    ),
    "G12/history-row": (
        G12, "store/records.py",
        source(
            '        "INSERT INTO pass_state_changes (tenant_id, pass_id, from_state, to_state, '
            'changed_by, "',
            '        "changed_at, reason) VALUES (%s, %s, %s, %s, %s, %s, %s)",',
            "        (tenant_uuid, pass_uuid, change.from_state.value,",
        ),
        source(
            '        "SELECT %s, %s, %s, %s, %s, %s, %s",  # PLANTED: no history row',
            "        (tenant_uuid, pass_uuid, change.from_state.value,",
        ),
        "a state change leaves no record of who, when or why",
    ),
    "G12/grant": (
        G12, MIGRATION,
        "GRANT SELECT, INSERT ON pass_state_changes TO garage_pass_app;",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON pass_state_changes TO garage_pass_app;"
        "  -- PLANTED",
        "the history is no longer append-only: the application can rewrite it",
    ),
    "G12/who-why": (
        G12, "states.py",
        "    if not (isinstance(by, str) and by.strip()) or not (isinstance(reason, str) "
        "and reason.strip()):",
        "    if False:  # PLANTED: who and why may be blank",
        "a state change with nobody and no reason is recorded",
    ),
    "G13": (
        "tests/test_g13_the_label_is_only_a_label.py", "access.py",
        "    # --- the state, in the order that is the contract ------------------------",
        source(
            '    if pass_.label == "Vendor":  # PLANTED: behaviour keyed on the label',
            '        return not_covered(NO_PASS, "vendors are refused", pass_)',
            "    # --- the state, in the order that is the contract ------------------------",
        ),
        "a label decides an answer -- the fifth pass type, by the back door",
    ),
    "G14": (
        "tests/test_fixture_axes.py", "tests/fixtures.py",
        'SHIFTING_ZONE = "America/Denver"',
        'SHIFTING_ZONE = "America/Phoenix"  # PLANTED: the DST fixture stops shifting',
        "the zone the DST guarantee is measured against no longer observes daylight "
        "saving, so every transition-day assertion is measuring a fixture with nothing in it",
    ),
    "G15/count": (
        "tests/test_contract_is_generated.py", "scripts/generate_contract.py",
        '        f"That is {len(GUARANTEES)} guarantees. Every one of them has a fail control "',
        '        f"That is 16 guarantees. Every one of them has a fail control "  # PLANTED',
        "the published guarantee COUNT stops being derived and becomes a typed number",
    ),
    "G15/prose": (
        "tests/test_contract_is_generated.py", "scripts/generate_contract.py",
        source(
            "    if answer.outcome is Outcome.COVERED:",
            '        return f"**covered** by',
        ),
        source(
            "    if True:  # PLANTED: one sentence whatever the outcome",
            '        return f"**covered** by',
        ),
        "the worked example says covered whatever the module returned",
    ),
    "G16": (
        "tests/test_guarantee_guard.py", "tests/test_guarantee_guard.py",
        "        elif name not in UNGUARANTEED_MODULES:",
        "        elif False:  # PLANTED: a module with no mark is accepted",
        "a test module carrying no guarantee mark stops being reported",
    ),
    "G16/conftest": (
        "tests/test_guarantee_guard.py", "tests/conftest.py",
        "    session.exitstatus = 1",
        "    pass  # PLANTED: unrun guarantees are printed and the run stays green",
        "a registered guarantee that did not run is reported and the run passes anyway",
    ),
}


def check_anchors() -> int:
    """Count every anchor. Zero or two is a dead control, and it is silent."""
    bad = 0
    for gid, (_target, path, anchor, _to, _why) in sorted(CONTROLS.items()):
        count = resolve(path).read_text().count(anchor)
        status = "ok" if count == 1 else "DEAD"
        if count != 1:
            bad += 1
        print(f"  {status:4}  {gid}  {path}  anchor appears {count}x")
    if bad:
        print(
            f"\n{bad} control(s) have no live anchor. An anchor that matches zero times "
            "plants nothing, and the control then reports green against unmodified "
            "source. Fix the anchors before trusting any result from this script."
        )
        return 1
    print(f"\nall {len(CONTROLS)} anchors live.")
    return 0


def _pytest(target: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


#: ``"0 passed" in stdout`` would be WRONG: "10 passed" contains it.
_NOTHING_RAN = re.compile(r"(?<!\d)0 passed|no tests ran|collected 0 items")


def run_control(gid: str) -> bool:
    target, path, anchor, replacement, why = CONTROLS[gid]
    print(f"\n=== {gid} — {GUARANTEES[guarantee_of(gid)]}")
    print(f"    plant: {path}")
    print(f"    breaks: {why}")

    green = _pytest(target)
    if green.returncode != 0:
        print(f"    UNMEASURED: {target} is already failing before anything was planted.")
        print(green.stdout[-1500:])
        return False
    if _NOTHING_RAN.search(green.stdout):
        print(f"    UNMEASURED: {target} ran no tests, so nothing here can go red.")
        print(green.stdout[-800:])
        return False

    with planted(path, anchor, replacement):
        red = _pytest(target)

    tail = [ln for ln in red.stdout.splitlines() if ln.startswith(("FAILED", "ERROR"))]
    summary = red.stdout.strip().splitlines()[-1] if red.stdout.strip() else ""
    if red.returncode == 0:
        print(f"    NOT A CONTROL: {target} stayed GREEN with its subject broken.")
        return False
    print(f"    RED, as required — {summary}")
    for line in tail[:6]:
        print(f"      {line}")
    return True


def main(argv: list[str]) -> int:
    if "--anchors" in argv:
        return check_anchors()

    named = [a for a in argv if not a.startswith("-")]
    wanted = [c for c in sorted(CONTROLS) if c in named or guarantee_of(c) in named]
    unknown = [
        a for a in named
        if a not in CONTROLS and a not in {guarantee_of(c) for c in CONTROLS}
    ]
    if unknown:
        print(f"no such control: {', '.join(unknown)}")
        return 2
    wanted = wanted or sorted(CONTROLS)

    missing = sorted(set(GUARANTEES) - {guarantee_of(c) for c in CONTROLS})
    if missing:
        print(
            f"registered guarantees with no fail-control: {', '.join(missing)}. "
            "Every guarantee is proven able to fail, or it is not a guarantee."
        )
        return 1

    if check_anchors():
        return 1

    results = {gid: run_control(gid) for gid in wanted}
    dead = [gid for gid, ok in results.items() if not ok]
    print(f"\n{len(results) - len(dead)}/{len(results)} controls fired.")
    if dead:
        print(f"DEAD CONTROLS: {', '.join(dead)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
