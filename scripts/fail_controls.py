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

**A RED IS READ BY ITS REASON, NOT ITS COLOUR.** Under each plant the runner
records every failure's reason line (``--tb=line``) and requires AT LEAST ONE
red that is an ASSERTION about the subject -- ``AssertionError``, or pytest's
own ``Failed`` from ``pytest.raises``/``pytest.fail``. A control whose only reds
are some other exception is reporting on the plant, not the subject: this
module has produced that shape three times (a plant that dropped two SQL
placeholders; a plant that dereferenced ``None`` on the next line; and a
near-miss where one of six reds was a driver's aborted-transaction error). The
first two looked exactly like controls that work. A control may produce
non-assertion reds BESIDE its assertions -- that near-miss is allowed -- but
zero assertions is reported EXCEPTION-ONLY and counted dead.

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
G13 = "tests/test_g13_the_label_is_only_a_label.py"
G17 = "tests/test_g17_a_stored_row_the_module_cannot_read_still_answers.py"
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
        "          AND r.end_day IS NULL AND daterange(r.effective_day, NULL, '[)') "
        "&& daterange(%s, %s, '[)')  -- PLANTED: registrations with an end day are unseen",
        "a registration with an end day is invisible to the check, so a second pass "
        "is accepted over it and the EXCLUDE fires as a bare constraint -- the refusal "
        "that should name the end day never fires. (The first cut of this plant dropped "
        "two placeholders and went red on a malformed query, which proves nothing about "
        "the subject; measured in CI, corrected here.)",
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
        "    unmeasured: str | None\n",
        source(
            "    unmeasured: str | None",
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
            "        if is_exit:",
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
        "    exit_note = EXIT_IS_NEVER_REFUSED if is_exit else None",
        "    exit_note = None  # PLANTED: the sentence is dropped",
        "the exit answers stop carrying the sentence that says the vehicle leaves",
    ),
    "G4/transient-at-exit": (
        G4, "access.py",
        "    if not is_exit and garage.transient_available is None:",
        "    if garage.transient_available is None:  # PLANTED: exits read the field",
        "an exit at a garage with no stated transient mode is refused an answer -- "
        "an exit that depends on configuration",
    ),
    "G4/revoked-exit": (
        G4, "access.py",
        '            return not_covered(REVOKED, f"pass {pass_.id!r} is revoked.", pass_)',
        source(
            "            if is_exit:  # PLANTED: a revoked exit is refused an answer",
            "                return replace(",
            "                    not_covered(REVOKED, 'revoked', pass_),",
            '                    outcome=Outcome.REFUSED_TO_ANSWER, missing="revoked",',
            "                )",
            '            return not_covered(REVOKED, f"pass {pass_.id!r} is revoked.", pass_)',
        ),
        "a revoked pass refuses an answer at exit",
    ),
    "G5/revoked-branch": (
        G5, "access.py",
        "        if pass_.state is State.REVOKED:\n            return not_covered(REVOKED",
        "        if False:  # PLANTED: revoked falls through to its terms\n"
        "            return not_covered(REVOKED",
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
        "    if not identity:\n        if is_exit:",
        "    if False:  # PLANTED: a blank identity is looked up\n        if is_exit:",
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
        source(
            "                unmeasured = (",
            '                    f"max_stay {terms.max_stay} of pass {pass_.id!r} could not be '
            'measured for "',
        ),
        source(
            "                unmeasured = None  # PLANTED: silently satisfied",
            "                _unused = (",
            '                    f"max_stay {terms.max_stay} of pass {pass_.id!r} could not be '
            'measured for "',
        ),
        "an exit with no recorded entry treats the maximum stay as satisfied SILENTLY -- "
        "wrong-silently, which this project does not do. (The first cut planted the None "
        "check to `if False:` and crashed on the next line: both reds were AttributeError, "
        "an exception-only red that proved nothing; the runner now refuses that shape.)",
    ),
    "G10/force": (
        G10, MIGRATION,
        "ALTER TABLE passes FORCE  ROW LEVEL SECURITY;",
        "-- PLANTED: FORCE removed from passes",
        "one table ships without FORCE ROW LEVEL SECURITY. (Catalogue-only: the application "
        "role is not the table owner, so FORCE never bites at runtime and no behavioural test "
        "can see this plant; the catalogue assertion is the right and only witness.)",
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
        "one pass reference is a bare key, which a raw insert can point across tenants. "
        "(Catalogue-only: the behavioural cross-tenant-key test is on passes.garage_id; this "
        "plant on visits.pass_id is seen by the catalogue assertion alone.)",
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
        "        # --- the state ------------------------------------------------------",
        source(
            '        if pass_.label == "Vendor":  # PLANTED: behaviour keyed on the label',
            '            return not_covered(NO_PASS, "vendors are refused", pass_)',
            "        # --- the state ------------------------------------------------------",
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

    # --- the fix round's controls ------------------------------------------------
    "G2/slack-maximum": (
        "tests/test_g2_contradictions_refuse_at_creation.py", "terms.py",
        "        # A maximum LONGER than a window is not a contradiction. Windows bind",
        source(
            "        for _i, _w in enumerate(terms.windows):  # PLANTED: the removed refusal",
            "            if terms.max_stay > _w.length:",
            '                raise Refused(REFUSAL_MAX_STAY_NOT_POSITIVE, "max_stay", "PLANTED")',
            "        # A maximum LONGER than a window is not a contradiction. Windows bind",
        ),
        "a maximum longer than a window is refused at creation again -- a legitimate pass "
        "(6h beside two 4h windows) cannot be created",
    ),
    "G4/exit-refused": (
        G4, "access.py",
        source(
            "        if is_exit:",
            '            return not_covered(BLANK_IDENTITY, '
            'f"vehicle_identity is {vehicle_identity!r}.")',
        ),
        source(
            "        if False:  # PLANTED: a blank identity is refused an answer at exit too",
            '            return not_covered(BLANK_IDENTITY, '
            'f"vehicle_identity is {vehicle_identity!r}.")',
        ),
        "refused-to-answer reaches an exit path, and the "
        "exit produces no covered/not-covered answer",
    ),
    "G12/delete-grant": (
        G12, MIGRATION,
        source(
            "GRANT SELECT, INSERT, UPDATE ON",
            "  tenants, garages, passes, pass_windows, pass_lanes",
            "TO garage_pass_app;",
        ),
        source(
            "GRANT SELECT, INSERT, UPDATE ON",
            "  tenants, garages, passes, pass_windows, pass_lanes",
            "TO garage_pass_app;",
            "GRANT DELETE ON passes TO garage_pass_app;  -- PLANTED: the history erasable again",
        ),
        "the application role can erase the append-only history by deleting the pass it "
        "belongs to, through ON DELETE CASCADE",
    ),
    "G17/pass-catch": (
        G17, "store/records.py",
        source(
            "    try:",
            "        return _readable_pass_from_row(cursor, tenant_uuid, external_id, row)",
            "    except Refused as refusal:",
        ),
        source(
            "    try:",
            "        return _readable_pass_from_row(cursor, tenant_uuid, external_id, row)",
            "    except ImportError as refusal:  # PLANTED: a stored contradiction raises again",
        ),
        "a stored pass the validator refuses raises at load, so every access call about it "
        "-- exits included -- is an exception",
    ),
    "G17/garage-catch": (
        G17, "garage.py",
        "    except UnknownTimezone as exc:",
        "    except ImportError as exc:  # PLANTED: a stored bad timezone raises again",
        "a stored garage whose timezone the system lacks raises at load; the exit is an "
        "exception",
    ),
    "G16/reason": (
        "tests/test_guarantee_guard.py", "scripts/fail_controls.py",
        '    if not assertions:\n        print(f"    EXCEPTION-ONLY:',
        '    if False:  # PLANTED: an exception-only red counts as a control\n'
        '        print(f"    EXCEPTION-ONLY:',
        "a control whose only reds are exceptions -- a plant that crashes on the next line "
        "-- is counted as a control that fired",
    ),
    "G10/predicate-tenants": (
        G10, MIGRATION,
        source(
            "CREATE POLICY tenants_self_only ON tenants",
            "  USING      (id = current_tenant_id())",
            "  WITH CHECK (id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY tenants_self_only ON tenants",
            "  USING      (true)",
            "  WITH CHECK (true);  -- PLANTED: the tenant predicate stripped",
        ),
        "the policy on tenants still EXISTS -- the catalogue is satisfied -- but isolates "
        "nothing: every tenant reads and writes every other's rows there",
    ),
    "G10/predicate-garages": (
        G10, MIGRATION,
        source(
            "CREATE POLICY garages_tenant_isolation ON garages",
            "  USING      (tenant_id = current_tenant_id())",
            "  WITH CHECK (tenant_id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY garages_tenant_isolation ON garages",
            "  USING      (true)",
            "  WITH CHECK (true);  -- PLANTED: the tenant predicate stripped",
        ),
        "the policy on garages still EXISTS -- the catalogue is satisfied -- but isolates "
        "nothing: every tenant reads and writes every other's rows there",
    ),
    "G10/predicate-passes": (
        G10, MIGRATION,
        source(
            "CREATE POLICY passes_tenant_isolation ON passes",
            "  USING      (tenant_id = current_tenant_id())",
            "  WITH CHECK (tenant_id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY passes_tenant_isolation ON passes",
            "  USING      (true)",
            "  WITH CHECK (true);  -- PLANTED: the tenant predicate stripped",
        ),
        "the policy on passes still EXISTS -- the catalogue is satisfied -- but isolates "
        "nothing: every tenant reads and writes every other's rows there",
    ),
    "G10/predicate-pass_windows": (
        G10, MIGRATION,
        source(
            "CREATE POLICY pass_windows_tenant_isolation ON pass_windows",
            "  USING      (tenant_id = current_tenant_id())",
            "  WITH CHECK (tenant_id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY pass_windows_tenant_isolation ON pass_windows",
            "  USING      (true)",
            "  WITH CHECK (true);  -- PLANTED: the tenant predicate stripped",
        ),
        "the policy on pass_windows still EXISTS -- the catalogue is satisfied -- but isolates "
        "nothing: every tenant reads and writes every other's rows there",
    ),
    "G10/predicate-pass_lanes": (
        G10, MIGRATION,
        source(
            "CREATE POLICY pass_lanes_tenant_isolation ON pass_lanes",
            "  USING      (tenant_id = current_tenant_id())",
            "  WITH CHECK (tenant_id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY pass_lanes_tenant_isolation ON pass_lanes",
            "  USING      (true)",
            "  WITH CHECK (true);  -- PLANTED: the tenant predicate stripped",
        ),
        "the policy on pass_lanes still EXISTS -- the catalogue is satisfied -- but isolates "
        "nothing: every tenant reads and writes every other's rows there",
    ),
    "G10/predicate-pass_state_changes": (
        G10, MIGRATION,
        source(
            "CREATE POLICY pass_state_changes_tenant_isolation ON pass_state_changes",
            "  USING      (tenant_id = current_tenant_id())",
            "  WITH CHECK (tenant_id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY pass_state_changes_tenant_isolation ON pass_state_changes",
            "  USING      (true)",
            "  WITH CHECK (true);  -- PLANTED: the tenant predicate stripped",
        ),
        "the policy on pass_state_changes still EXISTS -- the catalogue is satisfied -- "
        "but isolates "
        "nothing: every tenant reads and writes every other's rows there",
    ),
    "G10/predicate-vehicle_registrations": (
        G10, MIGRATION,
        source(
            "CREATE POLICY vehicle_registrations_tenant_isolation ON vehicle_registrations",
            "  USING      (tenant_id = current_tenant_id())",
            "  WITH CHECK (tenant_id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY vehicle_registrations_tenant_isolation ON vehicle_registrations",
            "  USING      (true)",
            "  WITH CHECK (true);  -- PLANTED: the tenant predicate stripped",
        ),
        "the policy on vehicle_registrations still EXISTS -- the catalogue is satisfied -- "
        "but isolates "
        "nothing: every tenant reads and writes every other's rows there",
    ),
    "G10/predicate-visits": (
        G10, MIGRATION,
        source(
            "CREATE POLICY visits_tenant_isolation ON visits",
            "  USING      (tenant_id = current_tenant_id())",
            "  WITH CHECK (tenant_id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY visits_tenant_isolation ON visits",
            "  USING      (true)",
            "  WITH CHECK (true);  -- PLANTED: the tenant predicate stripped",
        ),
        "the policy on visits still EXISTS -- the catalogue is satisfied -- but isolates "
        "nothing: every tenant reads and writes every other's rows there",
    ),
    "G13/spelling-in-tuple": (
        G13, "access.py",
        '        # --- the state ------------------------------------------------------',
        source(
            '        if pass_.label in ("Vendor",):  # PLANTED',
            '            return not_covered(NO_PASS, "vendors", pass_)',
            '        # --- the state ------------------------------------------------------',
        ),
        "behaviour keyed on the label, spelled `in-tuple` -- one of the twelve spellings the "
        "L3 planted; the matrix must catch every one that changes an answer",
    ),
    "G13/spelling-dict-lookup": (
        G13, "access.py",
        '        # --- the state ------------------------------------------------------',
        source(
            '        _RULES = {"Vendor": True}  # PLANTED',
            '        if _RULES.get(pass_.label, False):',
            '            return not_covered(NO_PASS, "vendors", pass_)',
            '        # --- the state ------------------------------------------------------',
        ),
        "behaviour keyed on the label, spelled `dict-lookup` -- one of the twelve spellings the "
        "L3 planted; the matrix must catch every one that changes an answer",
    ),
    "G13/spelling-lower-eq": (
        G13, "access.py",
        '        # --- the state ------------------------------------------------------',
        source(
            '        if pass_.label.lower() == "vendor":  # PLANTED',
            '            return not_covered(NO_PASS, "vendors", pass_)',
            '        # --- the state ------------------------------------------------------',
        ),
        "behaviour keyed on the label, spelled `lower-eq` -- one of the twelve spellings the "
        "L3 planted; the matrix must catch every one that changes an answer",
    ),
    "G13/spelling-match": (
        G13, "access.py",
        '        # --- the state ------------------------------------------------------',
        source(
            '        match pass_.label:  # PLANTED',
            '            case "Vendor":',
            '                return not_covered(NO_PASS, "vendors", pass_)',
            '        # --- the state ------------------------------------------------------',
        ),
        "behaviour keyed on the label, spelled `match` -- one of the twelve spellings the "
        "L3 planted; the matrix must catch every one that changes an answer",
    ),
    "G13/spelling-variable-first": (
        G13, "access.py",
        '        # --- the state ------------------------------------------------------',
        source(
            '        _lbl = pass_.label  # PLANTED',
            '        if _lbl == "Vendor":',
            '            return not_covered(NO_PASS, "vendors", pass_)',
            '        # --- the state ------------------------------------------------------',
        ),
        "behaviour keyed on the label, spelled `variable-first` -- one of the twelve spellings the "
        "L3 planted; the matrix must catch every one that changes an answer",
    ),
    "G13/spelling-strip-eq": (
        G13, "access.py",
        '        # --- the state ------------------------------------------------------',
        source(
            '        if pass_.label.strip() == "Vendor":  # PLANTED',
            '            return not_covered(NO_PASS, "vendors", pass_)',
            '        # --- the state ------------------------------------------------------',
        ),
        "behaviour keyed on the label, spelled `strip-eq` -- one of the twelve spellings the "
        "L3 planted; the matrix must catch every one that changes an answer",
    ),
    "G13/spelling-len-gt": (
        G13, "access.py",
        '        # --- the state ------------------------------------------------------',
        source(
            '        if len(pass_.label) > 5:  # PLANTED',
            '            return not_covered(NO_PASS, "long", pass_)',
            '        # --- the state ------------------------------------------------------',
        ),
        "behaviour keyed on the label, spelled `len-gt` -- one of the twelve spellings the "
        "L3 planted; the matrix must catch every one that changes an answer",
    ),
    "G13/spelling-getattr": (
        G13, "access.py",
        '        # --- the state ------------------------------------------------------',
        source(
            '        if getattr(pass_, "label") == "Vendor":  # PLANTED',
            '            return not_covered(NO_PASS, "vendors", pass_)',
            '        # --- the state ------------------------------------------------------',
        ),
        "behaviour keyed on the label, spelled `getattr` -- one of the twelve spellings the "
        "L3 planted; the matrix must catch every one that changes an answer",
    ),
    "G13/spelling-fstring-in": (
        G13, "access.py",
        '        # --- the state ------------------------------------------------------',
        source(
            '        if "Vendor" in f"{pass_.label}":  # PLANTED',
            '            return not_covered(NO_PASS, "vendors", pass_)',
            '        # --- the state ------------------------------------------------------',
        ),
        "behaviour keyed on the label, spelled `fstring-in` -- one of the twelve spellings the "
        "L3 planted; the matrix must catch every one that changes an answer",
    ),
    "G13/spelling-startswith": (
        G13, "access.py",
        '        # --- the state ------------------------------------------------------',
        source(
            '        if pass_.label.startswith("Vend"):  # PLANTED',
            '            return not_covered(NO_PASS, "vendors", pass_)',
            '        # --- the state ------------------------------------------------------',
        ),
        "behaviour keyed on the label, spelled `startswith` -- one of the twelve spellings the "
        "L3 planted; the matrix must catch every one that changes an answer",
    ),
    "G13/spelling-first-char": (
        G13, "access.py",
        '        # --- the state ------------------------------------------------------',
        source(
            '        if pass_.label[0] == "V":  # PLANTED',
            '            return not_covered(NO_PASS, "v", pass_)',
            '        # --- the state ------------------------------------------------------',
        ),
        "behaviour keyed on the label, spelled `first-char` -- one of the twelve spellings the "
        "L3 planted; the matrix must catch every one that changes an answer",
    ),
    "G13/spelling-label-as-lane": (
        G13, "access.py",
        '        # --- the state ------------------------------------------------------',
        source(
            '        if lane_name == pass_.label:  # PLANTED',
            '            return not_covered(NO_PASS, "x", pass_)',
            '        # --- the state ------------------------------------------------------',
        ),
        "behaviour keyed on the label, spelled `label-as-lane` -- one of the twelve spellings the "
        "L3 planted; the matrix must catch every one that changes an answer",
    ),
    "G16/conftest": (
        "tests/test_guarantee_guard.py", "tests/conftest.py",
        "    session.exitstatus = 1",
        "    pass  # PLANTED: unrun guarantees are printed and the run stays green",
        "a registered guarantee that did not run is reported and the run passes anyway",
    ),
    # ---- the merge gate's five findings ------------------------------------
    "G1/holder-skip": (
        G1, "store/records.py",
        "    for _rid, other, label, state, other_valid_to, other_from, other_end in holders:\n",
        "    for _rid, other, label, state, other_valid_to, other_from, other_end in holders:\n"
        "        if state == State.REVOKED.value:\n"
        "            continue  # PLANTED: holders on revoked passes are skipped\n",
        "the overlap check skips holders on revoked passes again, so a registration a raw "
        "write left open on a revoked pass is invisible: the live pass meets the EXCLUDE "
        "and the caller is told to roll back and read again, where there is no race",
    ),
    "G1/target-state": (
        G1, "store/records.py",
        "    if pass_.state not in REGISTRABLE_STATES:",
        "    if False:  # PLANTED: the target pass's state is never read",
        "a vehicle is registered onto a revoked or a suspended pass again -- the gate's "
        "finding, reachable through the command line",
    ),
    "G1/deadlock": (
        G1, "store/records.py",
        "    except psycopg.errors.DeadlockDetected as deadlock:",
        "    except ImportError as deadlock:  # PLANTED: the deadlock is a traceback again",
        "the other shape of a genuine race -- the database rolling one writer back with "
        "DeadlockDetected -- reaches the caller as a traceback instead of the constraint's name",
    ),
    "G9/rendering": (
        G9, "access.py",
        '                        f"entered {rendered(open_visit.entered_at)}, '
        'exiting {rendered(at)} "',
        '                        f"entered {open_visit.entered_at.isoformat()}, '
        'exiting {at.isoformat()} "  # PLANTED: each instant in its own offset',

        "the OVER_MAX_STAY detail shows the recorded entry in whatever offset the store handed "
        "it back in -- the database session's zone -- beside the exit in the caller's",
    ),
    "G10/install-script": (
        G10, "scripts/ensure-app-role.py",
        source(
            '                sql.SQL("ALTER ROLE garage_pass_app LOGIN PASSWORD {}").format(',
            "                    sql.Literal(password)",
            "                )",
        ),
        source(
            '                "ALTER ROLE garage_pass_app LOGIN PASSWORD %s", (password,)'
            "  # PLANTED: a bind parameter in a utility statement",
        ),
        "the published install step dies on `syntax error at or near \"$1\"` again -- and "
        "only a test that RUNS the script can see it",
    ),
    "G17/garage-write-gate": (
        G17, "store/records.py",
        "    if garage.unreadable is not None:\n        u = garage.unreadable",
        "    if False:  # PLANTED: writes against an unreadable garage go through\n"
        "        u = garage.unreadable",
        "a pass and a registration are created at a garage stored with a timezone the "
        "system does not carry, while the same write against an unreadable pass is refused",
    ),
    "G17/repair-validates": (
        G17, "store/records.py",
        '    zone(require_text(timezone, "garage.timezone"))  # refuses an unknown zone by name',
        '    require_text(timezone, "garage.timezone")  # PLANTED: any text is a timezone',
        "the repair stores a zone the system does not carry -- the defect it exists to repair",
    ),
    "G18/traceback": (
        "tests/test_g18_the_command_line_refuses_never_tracebacks.py", "cli.py",
        "    except Refused as refused:\n        print(json.dumps({\"refused\": refused.code,",
        "    except Refused as refused:\n"
        "        if refused.field == \"garage.timezone\":\n"
        "            raise  # PLANTED: the traceback is back\n"
        "        print(json.dumps({\"refused\": refused.code,",
        "an unknown timezone at the command line is a traceback again -- the gate's finding",
    ),
    "G18/sweep": (
        "tests/test_g18_the_command_line_refuses_never_tracebacks.py", "localday.py",
        "        raise ValueError(\n            f\"{what} must carry a timezone.",
        "        raise RuntimeError(  # PLANTED: an exception class nobody classified\n"
        "            f\"{what} must carry a timezone.",
        "a new exception class is raised in the package and the sweep does not notice it",
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
        [
            sys.executable, "-m", "pytest", target, "-q", "--no-header", "-p", "no:cacheprovider",
            "--tb=line", "-rf",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


#: One line per failure under ``--tb=line``: ``<path>:<line>: <Exception>: <message>``,
#: or, for a bare ``assert`` with no message, ``<path>:<line>: assert <expression>``.
#: pytest's own ``Failed`` is what ``pytest.raises`` / ``pytest.fail`` raise --
#: "DID NOT RAISE" is an assertion about the subject, spelled by pytest.
_REASON = re.compile(
    r"^(?P<where>\S+?\.py:\d+): (?P<exception>[A-Za-z_][\w.]*)(?::| |$)(?P<rest>.*)$"
)
_ASSERTION_EXCEPTIONS = {"AssertionError", "Failed", "assert"}


def failure_reasons(stdout: str) -> list[tuple[str, str, str]]:
    """Every failure's (where, exception, message) from a ``--tb=line`` run."""
    out = []
    for line in stdout.splitlines():
        match = _REASON.match(line.strip())
        if match and not line.startswith(("FAILED", "ERROR", "E ")):
            out.append((match["where"], match["exception"], match["rest"].strip()))
    return out


def assertion_reds(reasons: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    return [r for r in reasons if r[1].rsplit(".", 1)[-1] in _ASSERTION_EXCEPTIONS]


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

    summary = red.stdout.strip().splitlines()[-1] if red.stdout.strip() else ""
    if red.returncode == 0:
        print(f"    NOT A CONTROL: {target} stayed GREEN with its subject broken.")
        return False
    reasons = failure_reasons(red.stdout)
    assertions = assertion_reds(reasons)
    others = [r for r in reasons if r not in assertions]
    if not reasons:
        # A red with no failure line is a collection error or a crash before
        # any test ran -- a plant that broke the import, say. Not a control.
        print(f"    EXCEPTION-ONLY: {target} went red with no test failure to read.")
        print(red.stdout[-1200:])
        return False
    if not assertions:
        print(f"    EXCEPTION-ONLY: {target} went red, but not one red is an assertion about "
              f"the subject -- {len(others)} exception(s): "
              + "; ".join(f"{e} at {w}" for w, e, _m in others[:4]) + ". The plant is "
              "reporting on itself, not on the subject. NOT A CONTROL.")
        return False
    print(f"    RED, as required — {summary} — {len(assertions)} assertion red(s)"
          + (f", {len(others)} other exception(s) beside them" if others else ""))
    for where, exception, message in assertions[:4]:
        print(f"      {where}: {exception}: {message[:140]}")
    for where, exception, message in others[:2]:
        print(f"      (beside) {where}: {exception}: {message[:100]}")
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
