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

**AND AN ASSERTION IS READ BY WHAT IT IS ABOUT.** The merge gate handed this
runner a plant that raised at the first line of every redemption and it FIRED:
its "assertions" were the race harness's own premise (``the premise: lane B
waits on lane A's lock`` -- an assertion about the harness, raised in
``tests/enrolment_harness.py``) and a ``pytest.raises(match=)`` whose regex did
not match -- which is an unexpected exception reaching the test, spelled as an
assertion. Neither is about the subject. So an assertion red counts only when
it was raised in a TEST MODULE (``tests/test_*.py``) or in the very file the
plant went into (a plant in ``tests/fixtures.py`` is judged by the fixture's
own assertion -- G14), and not when its message is pytest's "Regex pattern did
not match". The others are printed beside the count as PREMISE or UNEXPECTED
EXCEPTION, and a control with nothing else is EXCEPTION-ONLY. The fourth
appearance of this family in this runner's life; the rule is now the file the
assertion was raised in, not the exception's name alone.

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
G18 = "tests/test_g18_the_command_line_refuses_never_tracebacks.py"
G19 = "tests/test_g19_one_qr_one_car_once.py"
G20 = "tests/test_g20_the_enrolment_opens_nothing_on_its_own.py"
G21 = "tests/test_g21_a_redemption_refusal_is_never_an_exit_refusal.py"
G22 = "tests/test_g22_the_vehicle_description_decides_nothing.py"
G23 = "tests/test_g23_the_token_is_never_stored_and_never_rendered.py"
G24 = "tests/test_g24_a_holder_link_writes_two_columns_and_nothing_else.py"
G25 = "tests/test_g25_a_pass_answers_only_at_the_garages_it_names.py"
MIGRATION = "migrations/0001_garages_passes_registrations_and_rls.sql"
MIGRATION_0002 = "migrations/0002_garage_changes_are_recorded.sql"
MIGRATION_0003 = "migrations/0003_enrolments_holder_links_and_where_a_garage_enrols.sql"
MIGRATION_0004 = "migrations/0004_a_pass_spans_many_garages.sql"

#: control id -> (test target, source file, anchor, replacement, what breaks)
CONTROLS: dict[str, tuple[str, str, str, str, str]] = {
    "G1/refusal": (
        G1, "store/records.py",
        source(
            "            raise Refused(",
            "                REFUSAL_VEHICLE_ON_ANOTHER_PASS,",
        ),
        source(
            "            continue  # PLANTED: the second pass takes the vehicle",
            "            raise Refused(",
            "                REFUSAL_VEHICLE_ON_ANOTHER_PASS,",
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
        source(
            "    if to is State.REVOKED:",
            "        # LOCK_ORDER, second and third: the credentials, then the registrations",
        ),
        source(
            "    if False:  # PLANTED: revocation leaves registrations open",
            "        # LOCK_ORDER, second and third: the credentials, then the registrations",
        ),
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
        "            day_of(v.entered_at, clock) == today",
        "            True or day_of(v.entered_at, clock) == today  # PLANTED: the whole life",
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
        source(
            "        if v.pass_id == pass_.id and v.garage_id == garage.id",
            "        and v.vehicle_identity.strip() == identity and v.is_open",
        ),
        source(
            "        if v.pass_id == pass_.id and v.garage_id == garage.id",
            "        and v.is_open  # PLANTED: any vehicle's entry",
        ),
        "a stay is measured from whichever vehicle on the pass entered last",
    ),
    "G9/open-visit-any-garage": (
        G9, "access.py",
        source(
            "        if v.pass_id == pass_.id and v.garage_id == garage.id",
            "        and v.vehicle_identity.strip() == identity and v.is_open",
        ),
        source(
            "        if v.pass_id == pass_.id",
            "        and v.vehicle_identity.strip() == identity and v.is_open  # PLANTED: anywhere",
        ),
        "the stay's entry is chosen from every garage of the pass again: an exit at B is measured "
        "from an entry recorded at A and answered OVER_MAX_STAY quoting A's instant",
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
    "G14/far-zone": (
        "tests/test_fixture_axes.py", "tests/fixtures.py",
        'FAR_ZONE = "Asia/Tokyo"',
        'FAR_ZONE = "America/Denver"  # PLANTED: the mixed-zone fixture is not mixed',
        "the far garage of the mixed-zone pass sits in the shifting zone itself, so every "
        "per-garage-clock assertion is measuring a pass whose garages share one clock -- "
        "the absence the G3a merge gate found",
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
    "G16/premise-credited": (
        "tests/test_guarantee_guard.py", "scripts/fail_controls.py",
        '    if where == planted_file.resolve() or where.name.startswith("test_"):\n'
        '        return None\n'
        '    return "PREMISE"',
        '    return None  # PLANTED: a harness premise assertion is credited to the subject',
        "an assertion about the harness's own premise, raised in a harness file, counts as an "
        "assertion about the subject -- the gate's raise-everything plant fires again",
    ),
    "G16/regex-mismatch-credited": (
        "tests/test_guarantee_guard.py", "scripts/fail_controls.py",
        source(
            "    if reason[2].startswith(_UNEXPECTED_EXCEPTION):",
            '        return "UNEXPECTED EXCEPTION"',
        ),
        source(
            "    if False:  # PLANTED: a regex mismatch on a caught exception is an assertion",
            '        return "UNEXPECTED EXCEPTION"',
        ),
        "pytest's 'Regex pattern did not match' -- an unexpected exception reaching the test -- "
        "is credited as an assertion about the subject",
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
        "        for _rid, other, label, state, other_valid_to, other_from, other_end in "
        "holders:\n",
        "        for _rid, other, label, state, other_valid_to, other_from, other_end in "
        "holders:\n"
        "            if state == State.REVOKED.value:\n"
        "                continue  # PLANTED: holders on revoked passes are skipped\n",
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
        "    zone(new_value)  # refuses an unknown zone by name",
        "    pass  # PLANTED: any text is a timezone",
        "the repair stores a zone the system does not carry -- the defect it exists to repair",
    ),
    "G18/traceback": (
        "tests/test_g18_the_command_line_refuses_never_tracebacks.py", "cli.py",
        "    except Refused as refused:\n        print(json.dumps(_refusal(refused), indent=2))",
        "    except Refused as refused:\n"
        "        if refused.field == \"garage.timezone\":\n"
        "            raise  # PLANTED: the traceback is back\n"
        "        print(json.dumps(_refusal(refused), indent=2))",
        "an unknown timezone at the command line is a traceback again -- the gate's finding",
    ),
    "G18/sweep": (
        "tests/test_g18_the_command_line_refuses_never_tracebacks.py", "localday.py",
        "        raise ValueError(\n            f\"{what} must carry a timezone.",
        "        raise RuntimeError(  # PLANTED: an exception class nobody classified\n"
        "            f\"{what} must carry a timezone.",
        "a new exception class is raised in the package and the sweep does not notice it",
    ),
    # --- the outside pass's fixes ------------------------------------------------
    "G4/dangling-registration": (
        G4, "access.py",
        source(
            "    if dangling and not effective:",
            "        r = dangling[0]",
        ),
        source(
            "    if dangling and not effective:",
            "        r = dangling[0]",
            "        from garage_pass.findings import REFUSAL_PASS_NOT_FOUND, Refused  # PLANTED",
            "        raise Refused(REFUSAL_PASS_NOT_FOUND, 'registration.pass_id',",
            "                      f'PLANTED: the raise is back for {r.pass_id!r}')",
        ),
        "THE RAISE PLANTED BACK: a registration naming a pass not handed in raises at an "
        "exit again -- the outside review's counterexample, an exception at an exit lane",
    ),
    "G17/case-fold": (
        G17, "localday.py",
        "    if name not in names:\n        raise UnknownTimezone(",
        "    name = next((n for n in names if n.lower() == name.lower()), name)  # PLANTED\n"
        "    if name not in names:\n        raise UnknownTimezone(",
        "the lookup folds its case and canonicalises: 'america/denver' is accepted as "
        "America/Denver on EVERY filesystem, so this control reads the same on a "
        "case-insensitive Mac and on case-sensitive CI -- which is the whole defect",
    ),
    "G17/empty-set-blames-the-value": (
        G17, "localday.py",
        "    if not names:\n        raise TimezoneDatabaseUnavailable()",
        "    if not names:\n        raise UnknownTimezone('PLANTED: an empty set refuses the "
        "value as unknown')",
        "a machine with no tz database refuses every good zone as UNKNOWN, blaming the "
        "caller's input for the machine's missing data -- the shape worse than the bug",
    ),
    "G1/deadlock-cause": (
        G1, "store/records.py",
        source(
            '            detail = (deadlock.diag.message_detail or "").strip()',
            "            raise Refused(",
            '                REFUSAL_CONSTRAINT, "vehicle_identity",',
            '                f"constraint {ONE_PASS_PER_GARAGE}: the database detected a deadlock '
            'while this "',
            '                f"registration of {identity!r} waited on another transaction, and '
            'rolled this "',
        ),
        source(
            '            detail = ""  # PLANTED: the DETAIL dropped, a cause asserted',
            "            raise Refused(",
            '                REFUSAL_CONSTRAINT, "vehicle_identity",',
            '                f"constraint {ONE_PASS_PER_GARAGE}: two registrations of {identity!r} '
            'raced and "',
            '                "the database rolled this one back (deadlock detected). "',
        ),
        "the deadlock refusal names a cause it did not observe ('two registrations raced') "
        "and throws PostgreSQL's DETAIL away -- under a deadlock from a raw FOR UPDATE the "
        "module never takes, that sentence is false",
    ),
    "G18/dash-value": (
        G18, "cli.py",
        "    args = parser.parse_args(_values_that_start_with_a_dash(parser, argv))",
        "    args = parser.parse_args(argv)  # PLANTED: a dash-leading value is an option again",
        "`--timezone -06:00` is argparse's usage error and exit 2 again -- the re-gate's "
        "third shape beside the refusal and the traceback",
    ),
    "G18/tz-database-sentence": (
        G18, "cli.py",
        "    except TimezoneDatabaseUnavailable as missing:\n",
        "    except TimezoneDatabaseUnavailable as missing:\n        raise  # PLANTED\n",
        "a machine with no tz database is a traceback at the command line, not a sentence",
    ),
    "G12/garage-history-row": (
        G12, "store/records.py",
        '    cursor.execute(\n        "INSERT INTO garage_changes (tenant_id, garage_id, field, ',
        '    _ = (  # PLANTED: the repair is not recorded\n'
        '        "INSERT INTO garage_changes (tenant_id, garage_id, field, ',
        "the repair changes the garage and writes no history row: who, when and why are "
        "lost again",
    ),
    "G12/garage-grant": (
        G12, MIGRATION_0002,
        "GRANT SELECT, INSERT ON garage_changes TO garage_pass_app;",
        "GRANT SELECT, INSERT, UPDATE ON garage_changes TO garage_pass_app;  -- PLANTED",
        "the application role can rewrite the garage history: the widened grant is read "
        "from the catalogue and the derived set of append-only histories no longer matches",
    ),
    "G10/predicate-garage_changes": (
        G10, MIGRATION_0002,
        source(
            "CREATE POLICY garage_changes_tenant_isolation ON garage_changes",
            "  USING      (tenant_id = current_tenant_id())",
            "  WITH CHECK (tenant_id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY garage_changes_tenant_isolation ON garage_changes",
            "  USING      (true)",
            "  WITH CHECK (true);  -- PLANTED: the tenant predicate stripped",
        ),
        "the policy on garage_changes still EXISTS -- the catalogue is satisfied -- but "
        "isolates nothing: every tenant reads and writes every other's rows there. The "
        "ninth table gets the same control as the eight; the isolation test's denominator "
        "is the catalogue, so it sees the table without being told",
    ),
    # --- the document boundary, and the answer that depended on list order (W1-W5) ---
    "G4/duplicate-last-wins": (
        G4, "access.py",
        source(
            "    duplicated = {",
            "        pid: sorted(ps, key=_copy_order)",
            "        for pid, ps in copies.items()",
            "        if len(ps) > 1 and any(garage.id in p.garage_ids for p in ps)",
            "    }",
        ),
        source(
            "    duplicated: dict = {}  # PLANTED: last-wins is back; a repeated id is not seen",
        ),
        "a pass handed in twice under one id is resolved by ORDER again: by_id is a dict, "
        "the last copy wins silently, and [revoked p1, active p1] admits at an entry the "
        "car that [active p1, revoked p1] refuses -- the L3's order-dependent answer",
    ),
    "G4/wrong-type-answers": (
        G4, "access.py",
        source(
            '    for name, value in (("vehicle_identity", vehicle_identity), ("lane", lane)):',
            "        if not isinstance(value, str):",
            "            raise TypeError(f\"{name} must be text, not {value!r}\")",
        ),
        source(
            "    return  # PLANTED: a wrong-typed identity or lane is read as blank and ANSWERED",
        ),
        "a wrong-typed identity or lane is no longer refused at the signature: it reaches "
        ".strip() and is an AttributeError at an exit lane (the L3's shape through the pure "
        "API) -- and with the old blank-reading back it would be an ANSWER, a caller's bug "
        "read as a car with no plate. The signature enumeration reddens either way; the "
        "naive-at and direction checks stay",
    ),
    "G4/registration-untyped": (
        G4, "passes.py",
        source(
            "        # without complaint and raised at an EXIT lane instead.",
            "        require_typed(self)",
        ),
        source(
            "        # without complaint and raised at an EXIT lane instead.",
            "        return  # PLANTED: Registration validates nothing again",
        ),
        "a Registration with a None identity or a string day is constructed again and "
        "raises at an exit lane -- the eight pure-API raises the L3 found",
    ),
    "G18/document-untyped-scalar": (
        G18, "documents.py",
        source(
            "    if arm is str:",
            "        if not isinstance(value, str):",
            "            _refuse_wrong_type(field, hint, value)",
        ),
        source(
            "    if arm is str:",
            "        pass  # PLANTED: text fields take any value; a number where an id belongs",
        ),
        "a registration document whose vehicle_identity is a number reaches the module "
        "and is an AttributeError at an exit again (the loader's type check for text is gone)",
    ),
    "G18/string-as-collection": (
        G18, "documents.py",
        source(
            "        if not isinstance(value, list):",
            "            _refuse_wrong_type(field, hint, value)",
        ),
        source(
            "        if isinstance(value, str):  # PLANTED: text is read as its characters",
            "            value = list(value)",
            "        elif not isinstance(value, list):",
            "            _refuse_wrong_type(field, hint, value)",
        ),
        "allowed_lanes: 'L1' loads as the lane set {'1', 'L'} again -- no traceback, no "
        "refusal, a silently wrong pass, WRONG_LANE on a legitimate lane",
    ),
    "G18/keys-hand-listed": (
        G18, "documents.py",
        "    return frozenset(f.key for f in document_fields(cls))",
        source(
            "    listed = {  # PLANTED: the keys are a hand-written list again",
            '        "Garage": {"id", "timezone", "transient_available"},',
            '        "Pass": {"id", "garage_ids", "label", "holder", "terms", "state"},',
            '        "Holder": {"email", "name", "phone"},',
            '        "Terms": {"valid_from", "valid_to", "windows", "max_stay_minutes",',
            '                  "visit_allowance", "directions", "allowed_lanes"},',
            '        "GarageLanes": {"garage_id", "lanes"},',
            '        "Window": {"days", "start_minute", "end_minute"},',
            '        "VisitAllowance": {"count", "per"},',
            '        "Registration": {"pass_id", "vehicle_identity", "effective_day", "end_day"},',
            '        "Visit": {"pass_id", "garage_id", "vehicle_identity", "entry_lane",',
            '                  "entered_at", "exited_at", "exit_lane"},',
            "    }",
            "    return frozenset(listed.get(cls.__name__, set()))",
        ),
        "the document keys are typed by hand again: a field added to a dataclass -- the "
        "add-a-field control's scratch class -- is not a document key until somebody edits "
        "the list, which is exactly how the L3's holes were made",
    ),
    "G18/driver-generic": (
        G18, "cli.py",
        source(
            "    except psycopg.Error as exc:",
            "        # THE LAST RESORT, deliberately after Refused: a driver error the store",
        ),
        source(
            "    except psycopg.Error as exc:",
            "        raise  # PLANTED: the driver's error is a traceback again",
            "        # THE LAST RESORT, deliberately after Refused: a driver error the store",
        ),
        "an unmigrated database, a role without its grants: UndefinedTable and "
        "InsufficientPrivilege escape the command line as tracebacks again -- the L3's "
        "census, four of the nineteen",
    ),
    "G18/driver-generic-first": (
        G18, "store/records.py",
        "    except psycopg.errors.DeadlockDetected as deadlock:",
        "    except psycopg.errors.NoDataFound as deadlock:  # PLANTED: the deadlock is not named",
        "THE GUARD: a real deadlock at the one-car-one-pass INSERT is no longer turned into "
        "its named refusal inside the store, so it falls through to the command line's "
        "generic mapping and a REAL REFUSAL is reported as a broken server -- exit 2 and a "
        "sentence instead of exit 3 and the JSON refusal carrying PostgreSQL's DETAIL. "
        "The generic mapping is the last resort or it is a worse defect than the four "
        "tracebacks it replaced",
    ),
    "G18/tenant-row": (
        G18, "store/records.py",
        '    cursor.execute("SELECT 1 FROM tenants WHERE id = %s", (tenant_uuid,))',
        '    cursor.execute("SELECT 1 WHERE %s IS NOT NULL", (tenant_uuid,))  # PLANTED',
        "create-garage with a --tenant nobody seeded reaches the INSERT and is the "
        "database's ForeignKeyViolation again -- which the generic mapping now renders as "
        "a configuration sentence, exit 2, instead of the refusal by name, exit 3",
    ),
    # --- the exit that the document boundary refused (V1) ---------------------------
    "G4/exit-document-refuses": (
        G18, "cli.py",
        "    if direction is not Direction.EXIT:\n        return access(",
        "    if True:  # PLANTED: the exit takes the entry's path; a bad document REFUSES\n"
        "        return access(",
        "a document the module cannot read is a refusal at an EXIT again, exit 3 and no "
        "outcome -- chat's six probes, six refusals; the red must name the exit that went "
        "unanswered",
    ),
    "G4/exit-records-raise": (
        G18, "access.py",
        "    named = \"; \".join(u.describe() for u in unreadable)\n    return Answer(",
        "    named = \"; \".join(u.describe() for u in unreadable)\n"
        "    from garage_pass.findings import REFUSAL_FIELD_BLANK, Refused  # PLANTED\n"
        "    raise Refused(REFUSAL_FIELD_BLANK, unreadable[0].field, named)  # PLANTED\n"
        "    return Answer(",
        "the exit on an unreadable registration or visit is a Refused again -- rendered "
        "as exit 3 by the boundary -- instead of the not-covered answer",
    ),
    "G4/carrier-not-built": (
        G18, "documents.py",
        "        names = CARRIER_FIELDS.get(cls)\n"
        "        if not names or not isinstance(document, dict):",
        "        names = None  # PLANTED: no pass or garage document is ever a carrier\n"
        "        if not names or not isinstance(document, dict):",
        "a pass document the module cannot read is no longer the unreadable pass a stored "
        "row becomes: it is RECORD_UNREADABLE even when the car is on ANOTHER, readable "
        "pass, and the parity with the store is gone (an unreadable pass is an unreadable "
        "pass, A1.2)",
    ),
    # --- the document that crashes the decoder (U1, the L5 gate's B1) ------------
    "G18/decoder-recursion": (
        G18, "cli.py",
        "    except (OSError, ValueError, RecursionError) as exc:",
        "    except (OSError, ValueError) as exc:  # PLANTED: the decoder's RecursionError escapes",
        "a document that is valid JSON nested past what json.loads decodes is a TRACEBACK at "
        "the command line again -- RecursionError is a RuntimeError, not a ValueError -- in "
        "both directions, exit 1 with no answer; the red must name the traceback",
    ),
    # --- the T round: the sentence the operator reads, and the boundary that let a
    # --- document through unread ----------------------------------------------------
    "G4/unreadable-detail-says-stored": (
        G18, "access.py",
        '                f"pass {pass_.id!r} ({pass_.label}) carries a value this module "',
        '                f"pass {pass_.id!r} ({pass_.label}) is stored with a value this module "'
        '  # PLANTED: the old sentence, false on the document door',
        "the PASS_UNREADABLE detail tells the operator a row is stored on a route where "
        "nothing is -- the red must name the falsehood (a DOCUMENT route rendered 'stored'), "
        "and the stored-row door's own assertion reads the same sentence",
    ),
    "G4/unreadable-sentence-names-only-terms-or-holder": (
        G18, "findings.py",
        source(
            '        "refuses to read -- terms or a holder that would be refused at creation, a "',
            '        "holder or terms field that is missing or of the wrong type, or a field '
            'this "',
            '        "module does not know. "',
        ),
        source(
            '        "refuses to read -- terms or a holder that would be refused at creation. "'
            "  # PLANTED: the unknown-field door unnamed",
        ),
        "the registry sentence enumerates two of the doors to PASS_UNREADABLE while an unknown "
        "field reaches it too; the derived door test must name the door the sentence lost",
    ),
    "G18/document-not-a-regular-file": (
        G18, "cli.py",
        "            if not stat.S_ISREG(os.fstat(fd).st_mode):",
        "            if False and not stat.S_ISREG(os.fstat(fd).st_mode):  # PLANTED: the check on "
        "the descriptor is gone; a device that never stops producing bytes is read to EOF",
        "/dev/zero is read without end and the command line never returns; the bounded process "
        "test must fail as a HANG, not hang the suite (a pipe with no writer no longer hangs "
        "with the check gone -- O_NONBLOCK reads EOF -- so the pipe test is not this control)",
    ),
    "G18/document-check-and-read-are-one-file": (
        G18, "cli.py",
        '            handle = os.fdopen(fd, "r")',
        '            os.close(fd); handle = open(path, "r")  # PLANTED: the read resolves the '
        'NAME again -- the split is back',
        "the bytes decoded come from a second resolution of the path, not from the descriptor "
        "that was checked; the deterministic test that forbids every name-based open must go "
        "red naming the open(path)",
    ),
    "G18/document-descriptor-closed-on-refusal": (
        G18, "cli.py",
        "        except BaseException:\n            os.close(fd)\n            raise",
        "        except BaseException:\n            pass  # PLANTED: the descriptor leaks on "
        "every refusal\n            raise",
        "a refused document leaves its descriptor open; the fd-count test must read the leak",
    ),
    "G18/empty-option-read-as-not-given-at-exit": (
        G18, "cli.py",
        "        if path is None:  # the option was not given -- NOT ``if not path``: an empty",
        "        if not path:  # PLANTED: '' is 'not given' again -- the document is never opened",
        "--visits '' at an EXIT drops the visits document unread; the control case (a spent "
        "allowance) is what shows it, and the empty-string case must read as refused",
    ),
    "G18/empty-option-read-as-not-given-at-entry": (
        G18, "cli.py",
        "            if args.visits is not None else [],",
        "            if args.visits else [],  # PLANTED: '' is 'not given' at an entry",
        "--visits '' at an ENTRY answers COVERED on a spent allowance -- the silent wrong "
        "answer the control case names",
    ),
    "G15/route-sweep-blind-to-stored": (
        "tests/test_contract_is_generated.py", "scripts/sweep_route_sentences.py",
        '    r"\\b(raw write|raw insert|written raw|stored with|is stored|are stored|stored row|"',
        '    r"\\b(raw write|raw insert|written raw|stored row|"  # PLANTED: blind to '
        '"is stored with"',
        "the sweep no longer flags a sentence that says a value 'is stored with' -- the "
        "self-test's planted falsehood goes unnamed and the judged set turns stale",
    ),
    "G15/judgement-follows-the-text-not-the-file": (
        "tests/test_contract_is_generated.py", "scripts/sweep_route_sentences.py",
        "    return (sentence, file)",
        '    return (sentence, "")  # PLANTED: the file is dropped from the key -- a verdict '
        "travels with the text again",
        "a judged-TRUE sentence copied verbatim into another file inherits TRUE there -- the "
        "self-test's copy step must read judged instead of UNJUDGED, and the test that reads the "
        "self-test's lines must go red",
    ),
    "G15/rendered-collector-collects-nothing": (
        "tests/test_contract_is_generated.py", "tests/_rendered_sentences.py",
        "        if self.detail:\n            _rendered.append((self.detail, _stack_files()))",
        "        if False and self.detail:  # PLANTED: the collector sees nothing\n"
        "            _rendered.append((self.detail, _stack_files()))",
        "the rendered half collects no Answer; the test that renders its own denominator must "
        "read the collector as unproven (3 renders, fewer collected), never as clean",
    ),
    "G15/rendered-match-accounts-for-everything": (
        "tests/test_contract_is_generated.py", "scripts/sweep_route_sentences.py",
        '    phrases = [m.span() for m in ROUTE.finditer(text)]\n    if not phrases:\n'
        '        return "covered", []',
        '    phrases = [m.span() for m in ROUTE.finditer(text)]\n    if True or not phrases:'
        '  # PLANTED: every rendered text reads covered\n        return "covered", []',
        "the rendered matcher accounts for every text; the self-test's run-time spelling and its "
        "inserted word both read covered, and the test that reads the self-test's lines goes red",
    ),
    "G15/rendered-detail-falsehood": (
        "tests/test_contract_is_generated.py", "access.py",
        '        what = f"garage {garage.id!r}: {garage.unreadable.describe()}"',
        '        what = f"garage {garage.id!r} is stored with a value this module refuses to read: '
        '{garage.unreadable.describe()}"  # PLANTED: a falsehood in a rendered detail',
        "a 'stored' falsehood in a rendered detail the old sweep never read -- the shipped "
        "sweep must go red naming the sentence as unjudged",
    ),
    "G12/garage-who-why": (
        G12, "store/records.py",
        source(
            "    if not isinstance(reason, str) or not reason.strip():",
            '        raise Refused(REFUSAL_REPAIR_NEEDS_WHO_AND_WHY, "reason", '
            'f"why is {reason!r}.")',
        ),
        source(
            "    if not isinstance(reason, str) or not reason.strip():",
            '        reason = "(unstated)"  # PLANTED: a blank why is defaulted, not refused',
        ),
        "a repair with no reason is accepted and recorded with a guessed one -- the silent "
        "default this module exists to refuse",
    ),
    # --- G2: enrolment (migration 0003) --------------------------------------------
    "G10/predicate-enrolments": (
        G10, MIGRATION_0003,
        source(
            "CREATE POLICY enrolments_tenant_isolation ON enrolments",
            "  USING      (tenant_id = current_tenant_id())",
            "  WITH CHECK (tenant_id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY enrolments_tenant_isolation ON enrolments",
            "  USING      (true)",
            "  WITH CHECK (true);  -- PLANTED: the tenant predicate stripped",
        ),
        "the policy on enrolments still EXISTS -- the catalogue is satisfied -- but isolates "
        "nothing: every tenant reads and writes every other's credentials there",
    ),
    "G10/predicate-holder_links": (
        G10, MIGRATION_0003,
        source(
            "CREATE POLICY holder_links_tenant_isolation ON holder_links",
            "  USING      (tenant_id = current_tenant_id())",
            "  WITH CHECK (tenant_id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY holder_links_tenant_isolation ON holder_links",
            "  USING      (true)",
            "  WITH CHECK (true);  -- PLANTED: the tenant predicate stripped",
        ),
        "the policy on holder_links still EXISTS -- the catalogue is satisfied -- but "
        "isolates nothing",
    ),
    "G12/delete-grant-leaf": (
        G12, MIGRATION_0003,
        "GRANT SELECT, INSERT, UPDATE ON enrolments, holder_links TO garage_pass_app;",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON enrolments, holder_links TO garage_pass_app;"
        "  -- PLANTED: DELETE on a LEAF",
        "DELETE granted on a leaf table that cascades into no history: the first cut's walk "
        "from the histories could not see it (G2's brief correction 1); the whole-schema "
        "assertion names the leaf",
    ),
    "G12/enrols-at-history-row": (
        G12, "store/records.py",
        source(
            '        "INSERT INTO garage_changes (tenant_id, garage_id, changed_by, changed_at, '
            'reason, "',
            "        \"field, old_value, new_value) VALUES (%s, %s, %s, %s, %s, 'enrols_at', "
            '%s, %s)",',
            "        (tenant_uuid, garage_uuid, by.strip(), at, reason.strip(), garage.enrols_at, "
            "new_value),",
        ),
        source(
            '        "SELECT 1",  # PLANTED: the enrols-at repair leaves no record',
            "        (),",
        ),
        "the enrols-at repair moves the field and leaves no record of who, when or why",
    ),
    "G12/enrols-at-contradiction-on-repair": (
        G12, "store/records.py",
        "    refuse_enrols_at_contradiction(garage.transient_available, new_value)",
        "    pass  # PLANTED: the repair accepts 'exit' on a no-transient garage",
        "the R1 contradiction is refused at creation and accepted on the repair: the "
        "repair reaches the CHECK as a bare constraint instead of the refusal by name",
    ),
    "G19/redeem-twice": (
        G19, "store/enrolments.py",
        "    if state == CredentialState.REDEEMED.value:\n        raise Refused(",
        "    if False:  # PLANTED: a redeemed credential is redeemed again\n        raise Refused(",
        "a used QR binds a second car -- the registration is written twice",
    ),
    "G19/atomic": (
        G19, "store/enrolments.py",
        source(
            "    except Refused as refused:",
            "        # Nothing written -- the module's own refusal or the database's backstop",
            "        # alike: the savepoint takes every write back and the transaction goes on.",
            '        cursor.execute(f"ROLLBACK TO SAVEPOINT {SAVEPOINT}")',
        ),
        source(
            "    except Refused as refused:",
            '        cursor.execute(f"RELEASE SAVEPOINT {SAVEPOINT}")  # PLANTED: the writes stand',
        ),
        "a refusal after the registration was written leaves the registration standing: a "
        "half-landed redemption, the QR still issued -- usable twice",
    ),
    "G19/session-zone-redeemed": (
        G19, "store/enrolments.py",
        '            f"{local(credential.redeemed_at, tz).isoformat()}.",',
        '            f"{credential.redeemed_at.isoformat()}.",  # PLANTED: the session\'s zone',
        "the instant a refusal names is rendered in the database session's zone, not the "
        "garage's wall clock -- what the merge gate found; across the DST edge the offset is wrong",
    ),
    "G19/session-zone-cancelled": (
        G19, "store/enrolments.py",
        '            f"{local(credential.cancelled_at, tz).isoformat()}: '
        '{credential.cancelled_reason}.",',
        '            f"{credential.cancelled_at.isoformat()}: {credential.cancelled_reason}.",'
        "  # PLANTED: the session's zone",
        "the same, for the instant a revocation cancelled the credential",
    ),
    "G19/days-valid-default": (
        G19, "enrolment.py",
        '        raise Refused(REFUSAL_DAYS_VALID_NOT_STATED, "days_valid", '
        '"days_valid is not stated.")',
        "        return 3  # PLANTED: the product's number as a silent default",
        "an absent days_valid is defaulted to three instead of refused by name",
    ),
    "G19/expiry-derived": (
        G19, "enrolment.py",
        "    if today > last_day(starts_on, days_valid):\n        return EXPIRED_CREDENTIAL",
        "    if False:  # PLANTED: a credential never expires\n        return EXPIRED_CREDENTIAL",
        "a QR presented a day late is redeemed; the window is decoration",
    ),
    "G19/revocation-cancels": (
        G19, "store/records.py",
        '        for table in ("enrolments", "holder_links"):',
        "        for table in ():  # PLANTED: revocation leaves the credentials outstanding",
        "a revoked pass's outstanding QRs and links stay issued: the credential outlives "
        "the pass (the state check still refuses the redemption -- G19's in-test control "
        "proves which layer is load-bearing)",
    ),
    "G19/state-check": (
        G19, "store/records.py",
        "REGISTRABLE_STATES = frozenset({State.DRAFT, State.AWAITING_ENROLMENT, State.ACTIVE})",
        "REGISTRABLE_STATES = frozenset({State.DRAFT, State.AWAITING_ENROLMENT, State.ACTIVE, "
        "State.REVOKED})  # PLANTED: revoked takes a registration",
        "with the cancellation put back by a raw write, a revoked pass's QR binds a car: the "
        "state check the brief requires to be load-bearing is gone from both layers at once "
        "(both read this set)",
    ),
    # --- the fix round: one credential, one spend; the savepoint on every
    #     exception; the direction; the revoke races; the rendered doors ---
    "G19/lock-order": (
        G19, "store/records.py",
        '    return f"FOR UPDATE OF {alias}" if alias else "FOR UPDATE"',
        '    return ""  # PLANTED: no row lock anywhere -- every lock reads through this seam',
        "the PRIMARY removed at its one seam (both locks at once, since either alone serialises "
        "a same-credential race): with the spend's backstop monkeypatched away in the test, two "
        "lanes both redeem one token; two QRs on a draft pass write draft->active twice; the "
        "revocation racing a redemption records draft->revoked",
    ),
    "G19/spend-predicate": (
        G19, "store/enrolments.py",
        source(
            '        "WHERE tenant_id = %s AND id = %s AND state = %s",',
            "        (CredentialState.REDEEMED.value, *values, tenant_uuid, uuid,",
            "         CredentialState.ISSUED.value),",
            "    )",
            "    if cursor.rowcount != 1:",
        ),
        source(
            '        "WHERE tenant_id = %s AND id = %s",  # PLANTED: no state predicate',
            "        (CredentialState.REDEEMED.value, *values, tenant_uuid, uuid),",
            "    )",
            "    if False:  # PLANTED: no rowcount",
        ),
        "the BACKSTOP removed: with the locks monkeypatched away in the test, the second lane's "
        "spend overwrites the first -- two registrations, the row records the last writer",
    ),
    "G19/rollback-on-every-exception": (
        G19, "store/enrolments.py",
        source(
            "    except BaseException:",
            "        # A defect, a driver error the store did not name, an interrupt: the",
            "        # savepoint takes every write back FIRST, then it surfaces unchanged.",
            "        # Nothing persists, and nothing is swallowed.",
            '        cursor.execute(f"ROLLBACK TO SAVEPOINT {SAVEPOINT}")',
        ),
        source(
            "    except BaseException:",
            "        pass  # PLANTED: only Refused rolls the savepoint back",
        ),
        "a planted programming error after the registration surfaces but leaves the registration "
        "live in the caller's transaction: committed, a QR that works twice",
    ),
    "G19/direction": (
        G19, "store/enrolments.py",
        "        if direction not in pass_.terms.directions:",
        "        if False:  # PLANTED: an exit-only pass binds at an entry-enrolling garage",
        "a pass whose terms exclude the enrolling direction binds and burns the QR on a "
        "movement it can never cover",
    ),
    "G19/direction-over-reach": (
        G19, "store/enrolments.py",
        "        if direction not in pass_.terms.directions:",
        "        if direction not in pass_.terms.directions or pass_.terms.windows or "
        "pass_.terms.valid_from:  # PLANTED: temporal non-coverage refused too",
        "the direction refusal over-reaches into temporal non-coverage: a weekday pass on a "
        "Sunday, a valid_from ahead, office hours at 23:00 are all REFUSED instead of bound -- "
        "the control that matters more than the fix",
    ),
    "G19/revocation-lock": (
        G19, "store/records.py",
        source(
            "    lock_pass_row(cursor, tenant_uuid, pass_uuid)",
            "    # re-read under the lock: a check made before the lock is a check on a stale row",
            "    pass_uuid, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)",
            "    moved, change = transition(pass_, to, by=by, at=at, reason=reason)",
        ),
        source(
            "    pass_ = _stale  # PLANTED: the revocation judges the row it read before any lock",
            "    moved, change = transition(pass_, to, by=by, at=at, reason=reason)",
        ),
        "a revocation racing a first redemption records draft->revoked: a transition from a "
        "state the pass had already left",
    ),
    "G19/issue-lock": (
        G19, "store/enrolments.py",
        source(
            "    pass_uuid, _stale = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)",
            "    lock_pass_row(cursor, tenant_uuid, pass_uuid)",
            "    pass_uuid, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)",
        ),
        source(
            "    pass_uuid, pass_ = load_pass(cursor, tenant_uuid, garage_uuid, pass_external_id)",
            "    # PLANTED: the issue judges the row it read before any lock",
        ),
        "an issue racing a revocation, revoke first, leaves an ISSUED credential on the "
        "revoked pass: the credential outlives the pass",
    ),
    "G21/rendered-garage-mismatch": (
        G21, "store/enrolments.py",
        '                f"garages {list(pass_garages.external_ids)}, not '
        '{garage_external_id!r}.",',
        '                f"garages {list(pass_garages.external_ids)}, not '
        '{garage_external_id!r}. " + "The pass is " + "stored" + " raw.",'
        '  # PLANTED: a run-time spelling of a route falsehood',
        "a falsehood assembled at run time in the GARAGE_MISMATCH refusal detail -- the door the "
        "rendered collector was blind to at the L3 -- must read UNJUDGED in the test that drives "
        "that door through the command line in-process",
    ),
    "G21/rendered-lane-outside": (
        G21, "store/enrolments.py",
        '                f"{garage_external_id!r}, not {lane_name!r}.",',
        '                f"{garage_external_id!r}, not {lane_name!r}. " + "The lane is " + "stored"'
        ' + " raw.",  # PLANTED: a run-time spelling of a route falsehood',
        "the same, in the LANE_OUTSIDE refusal detail",
    ),
    "G24/control-characters": (
        G24, "garage.py",
        '    control = [ch for ch in text if unicodedata.category(ch) == "Cc"]',
        "    control = []  # PLANTED: a NUL in the holder's name reaches the driver",
        "a control character in the holder's text is not refused by name: it reaches the "
        "database driver and comes back as a configuration-class sentence",
    ),
    "G24/ascii-rule": (
        G24, "garage.py",
        '    control = [ch for ch in text if unicodedata.category(ch) == "Cc"]',
        '    control = [ch for ch in text if unicodedata.category(ch) == "Cc" or ord(ch) > 127]'
        "  # PLANTED: the fix became an ASCII rule",
        "a name with accented letters or in a non-Latin script is refused: a worse defect than "
        "the one being fixed",
    ),
    "G24/edge-strip-gone": (
        G24, "garage.py",
        "    text = value.strip()",
        "    text = value  # PLANTED: edge whitespace is refused as a control character",
        "the validator tightened to make the old sentence true: a scanner's trailing line break "
        "after a QR payload is refused, and the edge census reads 0 stripped instead of ten",
    ),
    "G24/old-wording": (
        G24, "findings.py",
        '        "A text field carries a control character INSIDE it -- a NUL, a line break, '
        'a tab "',
        '        "A text field carries a control character -- a NUL, a line break, a tab "'
        "  # PLANTED: the old wording",
        "the registry sentence the gate found over-reaching, planted back: it no longer says the "
        "check is on the INSIDE; the census test measuring sentence and behaviour together reddens",
    ),
    "G20/divergence": (
        G20, "store/enrolments.py",
        source(
            "    answer = answer_in_transaction(",
            "        cursor, tenant_uuid, garage_external_id, vehicle_identity, lane, direction, "
            "at,",
            "    )",
            "    return Redemption(",
        ),
        source(
            "    answer = answer_in_transaction(",
            "        cursor, tenant_uuid, garage_external_id, vehicle_identity, lane, direction, "
            "at,",
            "    )",
            '    answer = Answer(**{**answer.__dict__, "detail": "PLANTED: opened by the '
            'enrolment"})',
            "    return Redemption(",
        ),
        "the redemption's answer diverges from the access call's -- a second layer deciding "
        "one concept, the trap this estate keeps re-learning",
    ),
    "G20/unstated-defaulted": (
        G20, "enrolment.py",
        source(
            "    if garage.enrols_at is None:",
            "        raise Refused(",
            '            REFUSAL_WHERE_TO_ENROL_UNSTATED, "garage.enrols_at",',
        ),
        source(
            "    if garage.enrols_at is None:",
            "        return ENROLS_AT_ENTRY  # PLANTED: a guessed default",
            "        raise Refused(",
            '            REFUSAL_WHERE_TO_ENROL_UNSTATED, "garage.enrols_at",',
        ),
        "a transient garage that never said where it enrols is read as enrolling at entry",
    ),
    "G20/derived-entry": (
        G20, "enrolment.py",
        "    if garage.transient_available is False:\n        return ENROLS_AT_ENTRY",
        "    if garage.transient_available is False:\n        return 'exit'  # PLANTED: R1 "
        "inverted",
        "a no-transient garage is derived as enrolling at exit -- the R1 contradiction as "
        "the derived answer",
    ),
    "G20/contradiction": (
        G20, "garage.py",
        "    if transient_available is False and enrols_at == ENROLS_AT_EXIT:",
        "    if False:  # PLANTED: the R1 contradiction is accepted at creation",
        "a garage that sells no transient and enrols at exit is built; the CHECK is the only "
        "thing left, for a raw write",
    ),
    "G20/check": (
        G20, MIGRATION_0003,
        source(
            "ALTER TABLE garages",
            "  ADD CONSTRAINT garages_no_transient_means_enrols_at_entry CHECK (",
            "    NOT (transient_available = false AND enrols_at = 'exit')",
            "  );",
        ),
        "-- PLANTED: the CHECK removed",
        "the backstop for a raw write is gone: a raw row can say no transient AND enrols at "
        "exit",
    ),
    "G20/wrong-end": (
        G20, "store/enrolments.py",
        "        if direction.value != end:",
        "        if False:  # PLANTED: a QR at either end is redeemed",
        "a QR is redeemed at the end the garage does not enrol at",
    ),
    "G21/answer-withheld": (
        G21, "store/enrolments.py",
        "        refusal = refused\n        registration = change = None",
        "        refusal = refused\n        registration = change = None\n        raise refused"
        "  # PLANTED: a refused redemption gives the lane no answer",
        "a refused redemption raises instead of answering -- the lane asked a question and "
        "was told nothing it can act on; at an exit that is the unanswered exit G4 forbids",
    ),
    "G21/exit-refused": (
        G21, "store/enrolments.py",
        source(
            "    return Redemption(",
            "        enrolment=enrolment_id, redeemed=refusal is None, refusal=refusal,",
        ),
        source(
            "    if refusal is not None and direction is Direction.EXIT:  # PLANTED",
            '        answer = Answer(**{**answer.__dict__, "outcome": answer.outcome.__class__(',
            '            "refused_to_answer"), "missing": "enrolment", "means": None})',
            "    return Redemption(",
            "        enrolment=enrolment_id, redeemed=refusal is None, refusal=refusal,",
        ),
        "a redemption refusal at an exit lane becomes a refused-to-answer exit: a car that "
        "presented a bad QR on the way out is kept inside",
    ),
    "G22/spelling-eq": (
        G22, "store/enrolments.py",
        "        _refuse_unless_redeemable(ENROLMENT, enrolment, today, tz)",
        source(
            "        if enrolment.vehicle_description == vehicle_identity:  # PLANTED",
            '            raise Refused(REFUSAL_CREDENTIAL_UNKNOWN, "token", "described car")',
            "        _refuse_unless_redeemable(ENROLMENT, enrolment, today, tz)",
        ),
        "the description decides: an identity that spells it is refused",
    ),
    "G22/spelling-in": (
        G22, "store/enrolments.py",
        "        _refuse_unless_redeemable(ENROLMENT, enrolment, today, tz)",
        source(
            "        if enrolment.vehicle_description and vehicle_identity in "
            "enrolment.vehicle_description:  # PLANTED",
            '            raise Refused(REFUSAL_CREDENTIAL_UNKNOWN, "token", "described car")',
            "        _refuse_unless_redeemable(ENROLMENT, enrolment, today, tz)",
        ),
        "the description decides: an identity the description contains is refused",
    ),
    "G22/spelling-lower": (
        G22, "store/enrolments.py",
        "        _refuse_unless_redeemable(ENROLMENT, enrolment, today, tz)",
        source(
            "        if (enrolment.vehicle_description or '').lower() == "
            "vehicle_identity.lower():  # PLANTED",
            '            raise Refused(REFUSAL_CREDENTIAL_UNKNOWN, "token", "described car")',
            "        _refuse_unless_redeemable(ENROLMENT, enrolment, today, tz)",
        ),
        "the description decides, case-folded",
    ),
    "G22/spelling-startswith": (
        G22, "store/enrolments.py",
        "        _refuse_unless_redeemable(ENROLMENT, enrolment, today, tz)",
        source(
            "        if (enrolment.vehicle_description or '').startswith(vehicle_identity[:3]):"
            "  # PLANTED",
            '            raise Refused(REFUSAL_CREDENTIAL_UNKNOWN, "token", "described car")',
            "        _refuse_unless_redeemable(ENROLMENT, enrolment, today, tz)",
        ),
        "the description decides, by its first characters",
    ),
    "G22/spelling-len": (
        G22, "store/enrolments.py",
        "        _refuse_unless_redeemable(ENROLMENT, enrolment, today, tz)",
        source(
            "        if len(enrolment.vehicle_description or '') > 8:  # PLANTED",
            '            raise Refused(REFUSAL_CREDENTIAL_UNKNOWN, "token", "described car")',
            "        _refuse_unless_redeemable(ENROLMENT, enrolment, today, tz)",
        ),
        "the description decides, by its length -- the spelling the G13 scan could not see",
    ),
    "G23/stored-plaintext": (
        G23, "store/enrolments.py",
        "        values.append(vehicle_description)",
        "        values.append(minted.token)  # PLANTED: the plaintext stored beside the digest",
        "the token is stored in a column of the row: a database read yields a working QR",
    ),
    "G23/rendered-plaintext": (
        G23, "store/enrolments.py",
        '            f"no {kind} in this tenant matches the token presented.",',
        '            f"no {kind} in this tenant matches the token {presented!r}.",  # PLANTED',
        "the unknown-credential refusal renders the token that was presented: a token issued "
        "to one tenant and presented at another is echoed back in a refusal detail",
    ),
    "G24/narrow-write": (
        G24, "store/enrolments.py",
        '        f"UPDATE passes SET {HOLDER_WRITES[0]} = %s, {HOLDER_WRITES[1]} = %s "',
        '        f"UPDATE passes SET {HOLDER_WRITES[0]} = %s, {HOLDER_WRITES[1]} = %s, '
        "label = 'PLANTED' \"",
        "the holder link writes a third column -- the label -- and the test must name it",
    ),
    "G24/issuer": (
        G24, "store/enrolments.py",
        "        days_valid, by=link.id, at=at, vehicle_description=vehicle_description,",
        '        days_valid, by="owner", at=at, vehicle_description=vehicle_description,'
        "  # PLANTED",
        "the enrolment a link issues records the owner as its issuer, not the link: the row "
        "that issued it no longer records the human",
    ),
    "G24/spend": (
        G24, "store/enrolments.py",
        '    _spend(cursor, HOLDER_LINK, tenant_uuid, uuid, "redeemed_at = %s", (at,))',
        '    pass  # PLANTED: the link is never spent',
        "a holder link is redeemed and stays issued: usable again",
    ),
    # --- G3a: a pass spans many garages. EVERY site that reads the set has a
    # control, and the fan-out's two halves are each measured alone. ---------
    "G25/access-by-id-membership": (
        G25, "access.py",
        "    by_id = {p.id: p for p in passes if garage.id in p.garage_ids and p.id not in "
        "duplicated}",
        "    by_id = {p.id: p for p in passes if p.id not in duplicated}"
        "  # PLANTED: every pass is every garage's business",
        "the by-id map no longer reads membership: a pass naming {A, B} covers at C",
    ),
    "G25/access-duplicated-membership": (
        G25, "access.py",
        "        if len(ps) > 1 and any(garage.id in p.garage_ids for p in ps)",
        "        if len(ps) > 1  # PLANTED: duplicated wherever it is, named or not",
        "the duplicated-id grouping no longer reads membership: two copies of a pass naming "
        "only B, handed in at A, refuse the entry at A naming an id A never reads",
    ),
    "G25/store-membership": (
        G25, "store/records.py",
        "    if garage_external_id not in pass_.garage_ids:",
        "    if False and garage_external_id not in pass_.garage_ids:  # PLANTED",
        "a pass naming {A} is stored at B without a refusal",
    ),
    "G25/load-membership": (
        G25, "store/records.py",
        "    if as_uuid(garage_uuid) not in garage_uuids:",
        "    if False:  # PLANTED: any garage loads any pass",
        "a pass naming {A, B} loads at C: the refusal every caller relies on never fires",
    ),
    "G25/enrolment-membership": (
        G25, "store/enrolments.py",
        "        if garage_uuid not in pass_garages.uuids:  # the QR's pass",
        "        if False:  # PLANTED: a QR redeems at any garage",
        "the QR's membership test is gone; what remains is load_pass's refusal, and the lane "
        "hears PASS_NOT_FOUND instead of GARAGE_MISMATCH naming the set",
    ),
    "G25/holder-link-membership": (
        G25, "store/enrolments.py",
        "    if garage_uuid not in pass_garages.uuids:  # the link's pass",
        "    if False:  # PLANTED: a link redeems at any garage",
        "the holder link's membership test is gone (the same shape, the other credential)",
    ),
    "G25/lanes-at-this-garage": (
        G25, "access.py",
        "        lanes_here = terms.lanes_at(garage.id)",
        "        lanes_here = None if terms.allowed_lanes is None else frozenset(  # PLANTED\n"
        "            lane for entry in terms.allowed_lanes for lane in entry.lanes)",
        "the lane check reads the UNION of every garage's lanes: a lane valid at A covers at B",
    ),
    "G25/lanes-every-garage": (
        G25, "passes.py",
        "    for garage_id in sorted(garage_ids - stated):",
        "    for garage_id in ():  # PLANTED: a garage with no stated lane is accepted",
        "a pass over {A, B} with lanes stated at A only is created; B has an implicit empty set",
    ),
    "G25/garage-set-empty": (
        G25, "passes.py",
        "    if not value:\n        raise Refused(\n"
        "            REFUSAL_PASS_NAMES_NO_GARAGE, field,",
        "    if False:  # PLANTED: the empty set is accepted\n        raise Refused(\n"
        "            REFUSAL_PASS_NAMES_NO_GARAGE, field,",
        "a pass naming no garage is constructed: it would answer nowhere, silently",
    ),
    "G1/fan-out": (
        G25, "store/records.py",
        "    for garage_ext, uuid in garages:\n        try:",
        "    for garage_ext, uuid in garages[:1]:  # PLANTED: one row, the first garage\n"
        "        try:",
        "a registration is written at the FIRST garage of the pass only: one redemption on a "
        "three-garage pass writes one row, and the car is uncovered at the other two",
    ),
    "G1/fan-out-collision": (
        G25, "store/records.py",
        "        for garage_ext, uuid in garages\n    ]",
        "        for garage_ext, uuid in garages[:1]  # PLANTED: holders read at the first only\n"
        "    ]",
        "the collision check reads the first garage only: a car held at the SECOND garage "
        "reaches the EXCLUDE there as a bare constraint, not the named refusal naming the garage "
        "and the survivor",
    ),
    "G10/predicate-pass_garages": (
        G10, MIGRATION_0004,
        source(
            "CREATE POLICY pass_garages_tenant_isolation ON pass_garages",
            "  USING      (tenant_id = current_tenant_id())",
            "  WITH CHECK (tenant_id = current_tenant_id());",
        ),
        source(
            "CREATE POLICY pass_garages_tenant_isolation ON pass_garages",
            "  USING      (true)",
            "  WITH CHECK (true);  -- PLANTED: the tenant predicate stripped",
        ),
        "the policy on pass_garages still EXISTS -- the catalogue is satisfied -- but "
        "isolates nothing",
    ),
    "G12/delete-grant-pass_garages": (
        G12, MIGRATION_0004,
        "GRANT SELECT, INSERT, UPDATE ON pass_garages TO garage_pass_app;",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON pass_garages TO garage_pass_app;"
        "  -- PLANTED: DELETE on the set",
        "DELETE granted on the pass-to-garage set: the whole-schema assertion names it",
    ),
    "G25/backfill-passes": (
        G25, MIGRATION_0004,
        "INSERT INTO pass_garages (tenant_id, pass_id, garage_id)\n"
        "SELECT tenant_id, id, garage_id FROM passes;",
        "-- PLANTED: no backfill; every existing pass names no garage",
        "an existing pass keeps no garage: 0004 fails at the lane key (the seeded-at-0003 test "
        "reports the failure as its own) -- and on an empty cluster nothing would have said so",
    ),
    "G25/backfill-lanes": (
        G25, MIGRATION_0004,
        "UPDATE pass_lanes l\n   SET garage_id = p.garage_id\n  FROM passes p\n"
        " WHERE p.tenant_id = l.tenant_id AND p.id = l.pass_id;",
        "-- PLANTED: lane rows are not stamped with their pass's garage",
        "an existing lane row carries no garage: the orphan check refuses every seeded lane",
    ),
    "G25/orphan-dropped": (
        G25, MIGRATION_0004,
        "    RAISE EXCEPTION 'migration 0004 refuses to run: % pass_lanes row(s) name a pass "
        "that '",
        "    DELETE FROM pass_lanes WHERE garage_id IS NULL; RAISE NOTICE '% dropped, PLANTED: '",
        "a lane row the migration cannot place is DROPPED silently instead of stopping the "
        "migration by name",
    ),
    "G25/unique-winner": (
        G25, MIGRATION_0004,
        "    RAISE EXCEPTION 'migration 0004 refuses to run: a pass''s external id becomes "
        "unique per '",
        "    DELETE FROM passes p USING passes q WHERE p.tenant_id = q.tenant_id "
        "AND p.external_id = q.external_id AND p.id > q.id; RAISE NOTICE 'PLANTED: winner picked '",
        "the UNIQUE tightening picks a winner and drops the other pass instead of failing by name",
    ),
    # --- the G3a fix round: the ledger per garage (X1), the keys RESTRICT (X2),
    #     the G12 classification from the catalogue (X3). Every anchor below is
    #     multi-line on purpose: a second line's indentation is inside the match,
    #     so a deeper re-indent of the code reads DEAD here rather than planting
    #     at the wrong depth (the L3's F3, dead by grade, still worth not buying).
    "G25/open-visit-any-garage": (
        G25, "store/records.py",
        source(
            '        "SELECT id, entered_at FROM visits WHERE tenant_id = %s AND garage_id = %s "',
            '        "AND pass_id = %s AND vehicle_identity = %s AND exited_at IS NULL",',
        ),
        source(
            '        "SELECT id, entered_at FROM visits WHERE tenant_id = %s AND %s::uuid IS NOT '
            'NULL "',
            '        "AND pass_id = %s AND vehicle_identity = %s AND exited_at IS NULL",  '
            '# PLANTED',

        ),
        "the open-visit lookup ignores the garage again: an entry at B is refused for a visit "
        "open at A, and an exit at B closes A's visit",
    ),
    "G25/open-visit-index-per-pass": (
        G25, MIGRATION_0004,
        source(
            "CREATE UNIQUE INDEX visits_one_open_per_vehicle_per_garage",
            "  ON visits (tenant_id, pass_id, garage_id, vehicle_identity) WHERE exited_at IS "
            "NULL;",
        ),
        source(
            "CREATE UNIQUE INDEX visits_one_open_per_vehicle_per_garage",
            "  ON visits (tenant_id, pass_id, vehicle_identity) WHERE exited_at IS NULL;  "
            "-- PLANTED",
        ),
        "the database's backstop is keyed per pass again: with the module's check per garage, "
        "the entry at B while A is open meets the index as a bare constraint",
    ),
    "G25/visits-cascade": (
        G25, MIGRATION_0004,
        source(
            "  ADD CONSTRAINT visits_garage_of_pass",
            "    FOREIGN KEY (tenant_id, pass_id, garage_id)",
            "    REFERENCES pass_garages (tenant_id, pass_id, garage_id) ON DELETE RESTRICT;",
        ),
        source(
            "  ADD CONSTRAINT visits_garage_of_pass",
            "    FOREIGN KEY (tenant_id, pass_id, garage_id)",
            "    REFERENCES pass_garages (tenant_id, pass_id, garage_id) ON DELETE CASCADE;  "
            "-- PLANTED",
        ),
        "removing a garage from a pass silently erases that garage's visits again",
    ),
    "G25/registrations-cascade": (
        G25, MIGRATION_0004,
        source(
            "  ADD CONSTRAINT vehicle_registrations_garage_of_pass",
            "    FOREIGN KEY (tenant_id, pass_id, garage_id)",
            "    REFERENCES pass_garages (tenant_id, pass_id, garage_id) ON DELETE RESTRICT;",
        ),
        source(
            "  ADD CONSTRAINT vehicle_registrations_garage_of_pass",
            "    FOREIGN KEY (tenant_id, pass_id, garage_id)",
            "    REFERENCES pass_garages (tenant_id, pass_id, garage_id) ON DELETE CASCADE;  "
            "-- PLANTED",
        ),
        "removing a garage from a pass silently erases that garage's registrations again",
    ),
    "G12/leaf-by-assumption": (
        G12, "store/postgres.py",
        source(
            "            (table,),",
            "        )",
            "        return frozenset(row[0] for row in cursor.fetchall())",
        ),
        source(
            "            (table,),",
            "        )",
            "        return frozenset()  # PLANTED: every table is a leaf",
        ),
        "the catalogue read of a table's children is planted empty, so a DELETE grant on a "
        "table with children is named as a leaf again",
    ),
    # --- each recorded entry is read on its own garage's clock (the G3a gate-fix round)
    "G9/asking-clock": (
        G9, "access.py",
        source(
            "        if garage_id == garage.id:",
            "            return tz",
        ),
        source(
            "        if True:  # PLANTED: every entry read on the asking garage's clock",
            "            return tz",
        ),
        "the per-window count reads every garage's entries on the asking garage's clock "
        "again: a Tokyo visit at 09:00 Monday reads at Denver as 18:00 Sunday, counts "
        "nothing, and a one-per-window allowance is spent twice",
    ),
    "G25/asking-clock": (
        G25, "access.py",
        source(
            "        if garage_id == garage.id:",
            "            return tz",
        ),
        source(
            "        if True:  # PLANTED: every entry read on the asking garage's clock",
            "            return tz",
        ),
        "the same plant, measured on the mixed-zone pass's DST edge and through the store: "
        "two Denver entries in the doubled hour read at Phoenix as one in the window",
    ),
    "G25/refusal-instant-session-zone": (
        G25, "access.py",
        '{v.garage_id!r} at {absolute(v.entered_at)} must be read on that garage',
        '{v.garage_id!r} at {v.entered_at.isoformat()} must be read on that garage',
        "the clock-not-here refusal quotes the entry in whatever offset the value arrived with "
        "-- through the store the DATABASE SESSION's zone, under a Denver session the asking "
        "clock's day, inside the sentence that says the entry is not read on the asking clock; "
        "visible only when three zones are compared, never in one reading",
    ),
    "G25/allowance-per-garage": (
        G25, "access.py",
        "            counted = _visits_used(visits, pass_, window, today, clock_at)",
        "            counted = _visits_used([v for v in visits if v.garage_id == garage.id], "
        "pass_, window, today, clock_at)  # PLANTED: per garage",
        "THE OVER-REACH: the allowance is counted per garage -- 12 at A and 8 at B read 12 "
        "of 20 at A -- a silent reversal of C5, the product rule the fix must not touch",
    ),
    "G25/garage-not-handed-in": (
        G25, "access.py",
        "        copies = handed_in_garages.get(garage_id, [])",
        "        copies = handed_in_garages.get(garage_id) or [garage]"
        "  # PLANTED: the asking garage stands in",
        "an entry at a garage that was not handed in is read on the asking garage's clock "
        "instead of refused by name",
    ),
    "G25/store-hands-in-garages": (
        G25, "store/access.py",
        "        garages=list(garages.values()),",
        "        garages=[],  # PLANTED: the store hands the engine no garage",
        "the store no longer hands the engine the pass's garages: an entry at Denver with a "
        "Tokyo visit on the ledger is refused to answer instead of counted on Tokyo's clock",
    ),
    "G25/cli-garages": (
        G25, "cli.py",
        source(
            '            garages=[load_garage(g) for g in _list(args.garages, "--garages")]',
            "            if args.garages is not None else [],",
        ),
        source(
            "            garages=[],  # PLANTED: --garages read and dropped",
            "            # if args.garages is not None else [],",
        ),
        "the documents door drops --garages at an entry: the gate's case through the "
        "command line is refused to answer with the Tokyo document handed in",
    ),
    "G5/revocation-day-per-garage": (
        G25, "store/records.py",
        "            days_at.append((uuid, day_of(at, zone(at_garage.timezone))))",
        "            days_at.append((uuid, day_of(at, zone(_garage.timezone))))"
        "  # PLANTED: the asking garage's day everywhere",
        "a revocation ends every garage's registrations on the asking garage's day again: "
        "2026-06-01T20:00-06:00 ends the Tokyo row on June 1 from Denver and June 2 from Tokyo",
    ),
    "G5/revocation-unreadable-garage-named": (
        G25, "store/records.py",
        "            _uuid, at_garage = load_readable_garage(cursor, tenant_uuid, external_id)",
        "            _uuid, at_garage = load_garage(cursor, tenant_uuid, external_id)"
        "  # PLANTED: unreadable loads as stored",
        "a garage of the pass whose zone cannot be read no longer refuses the revocation by "
        "name with the repair; the zone read raises the bare timezone refusal instead",
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


#: pytest's wording when ``pytest.raises(match=...)`` caught an exception of the
#: right type carrying the wrong message: an UNEXPECTED exception reached the
#: test. Evidence of an exception, not of the subject.
_UNEXPECTED_EXCEPTION = "Regex pattern did not match"


def _is_assertion(reason: tuple[str, str, str]) -> bool:
    return reason[1].rsplit(".", 1)[-1] in _ASSERTION_EXCEPTIONS


def _raised_in(reason: tuple[str, str, str]) -> Path:
    return Path(reason[0].rsplit(":", 1)[0]).resolve()


def about_the_subject(reason: tuple[str, str, str], planted_file: Path) -> str | None:
    """Why an assertion red does NOT count, or ``None`` when it does. A red
    counts when it is an assertion raised in a test module, or in the file the
    plant went into, and is not pytest's regex-mismatch on a caught exception."""
    if not _is_assertion(reason):
        return "not an assertion"
    if reason[2].startswith(_UNEXPECTED_EXCEPTION):
        return "UNEXPECTED EXCEPTION"
    where = _raised_in(reason)
    if where == planted_file.resolve() or where.name.startswith("test_"):
        return None
    return "PREMISE"


def assertion_reds(
    reasons: list[tuple[str, str, str]], planted_file: Path
) -> list[tuple[str, str, str]]:
    """The reds that are assertions ABOUT THE SUBJECT: see ``about_the_subject``."""
    return [r for r in reasons if about_the_subject(r, planted_file) is None]


def set_aside(
    reasons: list[tuple[str, str, str]], planted_file: Path
) -> list[tuple[str, str, tuple[str, str, str]]]:
    """The assertion reds that were NOT counted, each with its reason."""
    out = []
    for r in reasons:
        why = about_the_subject(r, planted_file)
        if why is not None and why != "not an assertion":
            out.append((why, r[0], r))
    return out


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
    planted_file = resolve(path)
    assertions = assertion_reds(reasons, planted_file)
    aside = set_aside(reasons, planted_file)
    others = [r for r in reasons if not _is_assertion(r)]
    if not reasons:
        # A red with no failure line is a collection error or a crash before
        # any test ran -- a plant that broke the import, say. Not a control.
        print(f"    EXCEPTION-ONLY: {target} went red with no test failure to read.")
        print(red.stdout[-1200:])
        return False
    if not assertions:
        print(f"    EXCEPTION-ONLY: {target} went red, but not one red is an assertion about "
              f"the subject -- {len(others)} exception(s): "
              + "; ".join(f"{e} at {w}" for w, e, _m in others[:4])
              + (f"; {len(aside)} assertion(s) set aside" if aside else "")
              + ". The plant is reporting on itself, not on the subject. NOT A CONTROL.")
        for why, where, (_w, exception, message) in aside[:4]:
            print(f"      (set aside: {why}) {where}: {exception}: {message[:100]}")
        return False
    print(f"    RED, as required — {summary} — {len(assertions)} assertion red(s)"
          + (f", {len(others)} other exception(s) beside them" if others else "")
          + (f", {len(aside)} assertion(s) set aside" if aside else ""))
    for where, exception, message in assertions[:4]:
        print(f"      {where}: {exception}: {message[:140]}")
    for why, where, (_w, exception, message) in aside[:2]:
        print(f"      (set aside: {why}) {where}: {exception}: {message[:100]}")
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
