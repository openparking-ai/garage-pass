"""G18 -- the command line renders a refusal, never a traceback.

Every ``Refused`` the module raises reaches ``cli.main`` and is printed as the
JSON refusal -- code, field, detail -- with exit status 3. ``UnknownTimezone``
is a ``Refused``. What the libraries the boundary calls can raise is mapped
there too: a document that is missing or not JSON, an instant or a day that
does not parse, a naive instant, a list document that is not a list, a
database that does not connect (a sentence on stderr, exit 2).

**THE INSTRUMENT IS THE SWEEP, NOT A HUMAN WALKING THE PRODUCT.** The gate
found ``create-garage`` printing sixty lines of ``zoneinfo`` stack for a
mistyped zone -- by hand, which is not repeatable. ``test_every_raise_in_the_
package_is_classified`` enumerates every ``raise`` statement in
``src/garage_pass`` by AST and requires every exception class it names to be
in the classification below, in one of two categories: RENDERED (a ``Refused``
the boundary prints) or a PROGRAMMING ERROR no command can reach (a caller
contract the command line's own parsing makes unreachable, a test harness
assertion, argparse's own exit). A class in neither fails the test until
somebody classifies it; a classified class that nothing raises any more
fails it too, so the table cannot go stale.

Controls: the boundary planted to re-raise the timezone refusal (the traceback
is back); an unclassified exception class planted into the package.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from fixtures import pass_document
from garage_pass import findings as f
from garage_pass.cli import EXIT_REFUSED_REQUEST, main
from garage_pass.localday import UnknownTimezone

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "garage_pass"

RENDERED = "rendered as a JSON refusal, exit 3"
PROGRAMMING = "a programming error no command can reach"
CONFIGURATION = "the machine's configuration: a sentence on stderr, exit 2"

#: Every exception class a `raise` in the package names, and why it is fine.
#:
#: THE TWO CALLER-CONTRACT ERRORS, STATED IN SO MANY WORDS so the next reader
#: does not re-open them: ``ValueError`` (a naive instant) and ``TypeError`` (a
#: direction that is not a ``Direction``) are reachable ONLY from the pure API,
#: never from a command -- the command line's own parsing (``cli._at``,
#: ``documents._instant``, argparse ``choices``) refuses each before the module
#: sees it. They are dead by decision, not unfinished work; G4 names them as
#: what its sentence does not cover. The one raise that WAS reachable and IS
#: data -- a registration naming a pass not handed in, ``REFUSAL_PASS_NOT_FOUND``
#: from the access call -- became an answer, and this sweep's count dropped by
#: one with it.
CLASSIFIED: dict[str, tuple[str, str]] = {
    "Refused": (RENDERED, "caught by cli.main"),
    "UnknownTimezone": (RENDERED, "a Refused: REFUSAL_TIMEZONE_UNKNOWN, field garage.timezone"),
    "TimezoneDatabaseUnavailable": (CONFIGURATION, "no tz database on this machine at all: "
                                                   "caught by cli.main, one sentence on stderr, "
                                                   "exit 2 -- the shape of a DSN that does not "
                                                   "connect; never rendered as an unknown zone"),
    "TypeError": (PROGRAMMING, "a value of a type the signature does not accept -- a direction "
                               "that is not a Direction, a Pass built half-shaped, a Registration "
                               "or Visit with a wrong-typed field, a wrong-typed parameter of "
                               "access(): every value a command hands the module is loaded "
                               "through the document boundary, which refuses a wrong type BY "
                               "NAME against the dataclass's declared field types, so the "
                               "class is reachable only from the pure API, never from a "
                               "command -- and there it raises on the first touch, never "
                               "answers (G4 enumerates the signature and proves it). Note the "
                               "denominator: these are the raise STATEMENTS; the same class "
                               "born of an operator on a wrong-typed value used to reach a "
                               "command from a document, and the boundary closes that route"),
    "KeyError": (PROGRAMMING, "a refusal code invented at a raise site and never registered: "
                              "the contract test and the orphan scan catch it before it ships"),
    "ValueError": (PROGRAMMING, "require_aware on a naive datetime -- an instant with no "
                                "timezone is a value of a type the signature does not accept, "
                                "the same class as TypeError above: every instant the command "
                                "line hands the module goes through cli._at or documents._instant, "
                                "which refuse a naive one first -- reachable only from the pure "
                                "API, never from a command"),
    "AssertionError": (PROGRAMMING, "assert_role_cannot_bypass_rls: called by the isolation "
                                    "tests, by no command"),
    "SystemExit": (PROGRAMMING, "argparse's own exit on an unknown command, and __main__"),
}


def every_raise() -> dict[str, list[str]]:
    """``{exception class name: [file:line, ...]}`` for every ``raise X(...)``
    and ``raise X`` in the package. A bare ``raise`` (a re-raise) names no
    class and is not listed."""
    found: dict[str, list[str]] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(target, ast.Name):
                name = target.id
            elif isinstance(target, ast.Attribute):
                name = target.attr
            else:  # pragma: no cover - a raise of an expression; classify by hand
                name = ast.dump(target)
            where = f"{path.relative_to(ROOT)}:{node.lineno}"
            found.setdefault(name, []).append(where)
    return found


@pytest.mark.guarantee("G18")
def test_every_raise_in_the_package_is_classified():
    found = every_raise()
    assert found, "the sweep found no raise at all: the instrument is broken"
    unclassified = {name: where for name, where in found.items() if name not in CLASSIFIED}
    assert unclassified == {}, (
        f"exception class(es) raised in the package that nobody has classified as rendered "
        f"or a programming error: {unclassified}"
    )
    stale = sorted(set(CLASSIFIED) - set(found))
    assert stale == [], f"classified but raised nowhere any more: {stale}"


@pytest.mark.guarantee("G18")
def test_the_sweep_reports_its_count_and_the_two_dead_raises_are_named_in_words():
    """The instrument names its denominator: how many ``raise`` statements,
    of how many classes, and that the two caller-contract classes carry the
    sentence that closes them -- and, since the L3's census, that the same
    words say the denominator is the raise STATEMENTS, because the class born
    of an operator on a wrong-typed value reached a command by another route
    until the document boundary closed it. A reader of the ``-rA`` output sees
    the count."""
    found = every_raise()
    total = sum(len(where) for where in found.values())
    print(f"\nSWEEP: {total} raise statements naming {len(found)} classes: "
          + ", ".join(f"{name} {len(where)}" for name, where in sorted(found.items())))
    assert total > 50 and "Refused" in found
    for dead in ("ValueError", "TypeError"):
        assert "reachable only from the pure API, never from a command" in CLASSIFIED[dead][1]
    assert "denominator" in CLASSIFIED["TypeError"][1], "the sweep says what it does not count"
    in_access = [w for w in found.get("Refused", []) if "garage_pass/access.py:" in w]
    assert in_access == [], (
        f"the access call raises a Refused again ({in_access}); a registration naming a pass "
        "not handed in is an ANSWER now (G4), and the pure call raises on no data"
    )


@pytest.mark.guarantee("G18")
def test_every_rendered_class_is_a_refused_the_boundary_catches():
    """The RENDERED half of the table is not a promise: each class is a
    ``Refused`` (what ``cli.main`` catches), and ``UnknownTimezone`` carries
    the registered code and field."""
    for name, (category, _why) in CLASSIFIED.items():
        if category is RENDERED:
            assert issubclass(getattr(f, name, UnknownTimezone), f.Refused), name
    raised = UnknownTimezone("'Mars/Olympus' is not a timezone this system carries.")
    assert isinstance(raised, f.Refused) and isinstance(raised, ValueError)
    assert raised.code == f.REFUSAL_TIMEZONE_UNKNOWN and raised.field == "garage.timezone"
    assert "Mars/Olympus" in raised.detail


# ---------------------------------------------------------------------------
# The command line, exercised: each input that used to be a traceback.
# ---------------------------------------------------------------------------


def run(argv: list[str], capsys) -> tuple[int, dict]:
    """``main`` in-process; an exception escaping it IS the failure, asserted as one."""
    try:
        status = main(argv)
    except SystemExit as exc:  # argparse's own refusal of the arguments
        pytest.fail(f"argparse refused the arguments: {exc}")
    except Exception as exc:  # noqa: BLE001 -- any exception is the defect
        pytest.fail(f"the command line raised instead of rendering a refusal: {exc!r}")
    out = capsys.readouterr().out
    return status, json.loads(out) if out.strip() else {}


def _documents(tmp_path: Path, timezone: str = "America/Denver") -> tuple[Path, Path]:
    garage = tmp_path / "g.json"
    garage.write_text(json.dumps({"id": "garage-downtown", "timezone": timezone,
                                  "transient_available": True}))
    pass_ = tmp_path / "p.json"
    pass_.write_text(json.dumps(pass_document()))
    return garage, pass_


MOVE = ["--vehicle", "CAR-1", "--lane", "L1", "--direction", "entry",
        "--at", "2026-06-01T12:00:00-06:00"]


@pytest.mark.guarantee("G18")
def test_an_unknown_timezone_in_a_garage_document_is_a_json_refusal_naming_the_value(
    tmp_path, capsys
):
    garage, pass_ = _documents(tmp_path, timezone="Mars/Olympus")
    status, printed = run(["access", "--garage", str(garage), "--pass", str(pass_), *MOVE], capsys)
    assert status == EXIT_REFUSED_REQUEST
    assert printed["refused"] == f.REFUSAL_TIMEZONE_UNKNOWN
    assert printed["field"] == "garage.timezone" and "Mars/Olympus" in printed["detail"]


@pytest.mark.guarantee("G18")
def test_in_a_fresh_interpreter_the_refusal_is_the_whole_output_and_stderr_is_empty(tmp_path):
    """Not in-process: the actual process, so a traceback on stderr cannot
    hide behind a caught exception."""
    garage, pass_ = _documents(tmp_path, timezone="Mars/Olympus")
    completed = subprocess.run(
        [sys.executable, "-m", "garage_pass.cli", "access", "--garage", str(garage),
         "--pass", str(pass_), *MOVE],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert completed.returncode == EXIT_REFUSED_REQUEST, completed.stderr
    assert completed.stderr == "", completed.stderr
    assert "Traceback" not in completed.stdout
    assert json.loads(completed.stdout)["refused"] == f.REFUSAL_TIMEZONE_UNKNOWN


@pytest.mark.guarantee("G18")
@pytest.mark.parametrize(
    "at,why",
    [("2026-06-01T12:00:00", "naive: no offset"), ("noon", "not an instant"),
     ("2026-13-01T12:00:00-06:00", "no such month")],
)
def test_a_malformed_or_naive_instant_is_a_json_refusal_naming_the_option(
    tmp_path, capsys, at, why
):
    garage, pass_ = _documents(tmp_path)
    status, printed = run(["access", "--garage", str(garage), "--pass", str(pass_),
                           "--vehicle", "CAR-1", "--lane", "L1", "--direction", "entry",
                           "--at", at], capsys)
    assert status == EXIT_REFUSED_REQUEST, why
    assert printed["field"] == "--at" and repr(at) in printed["detail"], printed


@pytest.mark.guarantee("G18")
@pytest.mark.parametrize("what", ["missing", "not-json", "a-directory"])
def test_a_document_that_cannot_be_read_is_a_json_refusal_naming_the_path(tmp_path, capsys, what):
    garage, pass_ = _documents(tmp_path)
    if what == "missing":
        bad = tmp_path / "nowhere.json"
    elif what == "not-json":
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
    else:
        bad = tmp_path / "dir.json"
        bad.mkdir()
    status, printed = run(["access", "--garage", str(bad), "--pass", str(pass_), *MOVE], capsys)
    assert status == EXIT_REFUSED_REQUEST, what
    assert printed["refused"] == f.REFUSAL_DOCUMENT_UNREADABLE
    assert printed["field"] == "--garage" and str(bad) in printed["detail"]
    status, printed = run(["check-terms", "--pass", str(bad)], capsys)
    assert status == EXIT_REFUSED_REQUEST and printed["field"] == "--pass"


@pytest.mark.guarantee("G18")
def test_a_registrations_document_that_is_not_a_list_is_a_json_refusal(tmp_path, capsys):
    garage, pass_ = _documents(tmp_path)
    regs = tmp_path / "r.json"
    regs.write_text(json.dumps(42))
    status, printed = run(["access", "--garage", str(garage), "--pass", str(pass_),
                           "--registrations", str(regs), *MOVE], capsys)
    assert status == EXIT_REFUSED_REQUEST
    assert printed["field"] == "--registrations" and "JSON list" in printed["detail"]


@pytest.mark.guarantee("G18")
def test_a_machine_with_no_tz_database_is_a_sentence_on_stderr_exit_2_not_a_refusal_of_the_value(
    tmp_path, capsys, monkeypatch
):
    """The MACHINE's configuration, not the request: the shape of an unset
    DSN. Never the JSON refusal, which would name ``garage.timezone`` and send
    an operator hunting for a typo in a good name; never a traceback."""
    from garage_pass import localday

    garage, pass_ = _documents(tmp_path)
    monkeypatch.setattr(localday, "_tz_names", lambda: frozenset())
    try:
        status = main(["access", "--garage", str(garage), "--pass", str(pass_), *MOVE])
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"raised instead of a sentence: {exc!r}")
    captured = capsys.readouterr()
    assert status == 2 and captured.out == "", captured
    assert "no timezone database" in captured.err and "tzdata" in captured.err
    assert "REFUSAL_TIMEZONE_UNKNOWN" not in captured.err and "America/Denver" not in captured.err


@pytest.mark.guarantee("G18")
@pytest.mark.parametrize("option,value", [("--timezone", "-06:00"), ("--timezone", "-Mars"),
                                          ("--at", "-1")])
def test_a_value_that_starts_with_a_dash_reaches_the_module_and_is_refused_by_name(
    tmp_path, capsys, monkeypatch, option, value
):
    """THE RE-GATE'S OBSERVATION: ``--timezone -06:00`` was argparse's usage
    error, exit 2 -- a third shape beside the JSON refusal and the traceback.
    The value reaches the module now and comes back as the refusal naming the
    option or the field and the value, exit 3. Not against the store: the
    join is at the boundary, and ``access`` shows it without a database."""
    garage, pass_ = _documents(tmp_path)
    if option == "--at":
        argv = ["access", "--garage", str(garage), "--pass", str(pass_), "--vehicle", "CAR-1",
                "--lane", "L1", "--direction", "entry", "--at", value]
        status, printed = run(argv, capsys)
        assert status == EXIT_REFUSED_REQUEST and printed["field"] == "--at"
        assert repr(value) in printed["detail"]
        return
    garage.write_text(json.dumps({"id": "g", "timezone": "America/Denver",
                                  "transient_available": True}))
    # set-garage-timezone needs a store; the boundary is exercised on the
    # argument join itself, then through the store below with a DSN
    from garage_pass.cli import _parser, _values_that_start_with_a_dash

    argv = ["set-garage-timezone", "--tenant", "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            "--garage", "g", option, value, "--by", "op", "--at", "2026-06-01T12:00:00-06:00",
            "--reason", "r"]
    joined = _values_that_start_with_a_dash(_parser(), argv)
    assert f"{option}={value}" in joined and value not in joined
    with pytest.raises(SystemExit):  # the premise: unjoined, argparse refuses it as an option
        _parser().parse_args(argv)
    assert vars(_parser().parse_args(joined))["timezone"] == value
    # a following token that IS an option of the command is left alone: the
    # join reads the parser's option strings, it does not swallow the next flag
    missing_value = [a for a in argv if a != value]
    assert _values_that_start_with_a_dash(_parser(), missing_value) == missing_value


@pytest.mark.guarantee("G18")
def test_a_store_command_with_a_dsn_that_does_not_connect_is_a_sentence_not_a_traceback(
    tmp_path, capsys, monkeypatch
):
    garage, _pass = _documents(tmp_path)
    monkeypatch.setenv("GARAGE_PASS_DSN", "host=127.0.0.1 port=1 dbname=nowhere user=nobody "
                                          "password=secret-4f9c connect_timeout=1")
    try:
        status = main(["create-garage", "--tenant", "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                       "--garage", str(garage)])
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"raised instead of a sentence: {exc!r}")
    captured = capsys.readouterr()
    assert status == 2 and "did not connect" in captured.err and captured.out == ""
    assert "secret-4f9c" not in captured.err, "the DSN's password reached stderr"


# ---------------------------------------------------------------------------
# The store commands, in-process against the test database.
# ---------------------------------------------------------------------------

from store_harness import DSN, store_test  # noqa: E402


def _dsn_for_the_app(monkeypatch):
    from psycopg import conninfo

    from garage_pass.store.postgres import APP_ROLE
    from store_harness import APP_PASSWORD

    params = conninfo.conninfo_to_dict(DSN)
    monkeypatch.setenv("GARAGE_PASS_DSN", conninfo.make_conninfo(
        **{**params, "user": APP_ROLE, "password": APP_PASSWORD}))


@pytest.mark.guarantee("G18")
@store_test
def test_create_garage_with_an_unknown_timezone_is_the_json_refusal_the_gate_asked_for(
    app, tenant_id, tmp_path, capsys, monkeypatch
):
    """THE GATE'S OWN CASE: create-garage, Mars/Olympus. Exit 3, the JSON
    refusal naming the field and the value; nothing stored."""
    from store_harness import query

    _dsn_for_the_app(monkeypatch)
    garage, _pass = _documents(tmp_path, timezone="Mars/Olympus")
    status, printed = run(["create-garage", "--tenant", str(tenant_id), "--garage", str(garage)],
                          capsys)
    assert status == EXIT_REFUSED_REQUEST
    assert printed == {"refused": f.REFUSAL_TIMEZONE_UNKNOWN, "field": "garage.timezone",
                       "detail": printed["detail"]}
    assert "Mars/Olympus" in printed["detail"]
    assert query(app, tenant_id, "SELECT count(*) FROM garages") == [(0,)]


@pytest.mark.guarantee("G18")
@store_test
def test_the_store_commands_refuse_a_malformed_day_a_second_garage_and_a_bad_repair(
    app, tenant_id, tmp_path, capsys, monkeypatch
):
    _dsn_for_the_app(monkeypatch)
    garage, pass_ = _documents(tmp_path)
    tenant = ["--tenant", str(tenant_id)]
    status, printed = run(["create-garage", *tenant, "--garage", str(garage)], capsys)
    assert status == 0 and printed["stored"] == "garage-downtown"
    # a second garage with the same id: refused by name, not a UniqueViolation
    status, printed = run(["create-garage", *tenant, "--garage", str(garage)], capsys)
    assert status == EXIT_REFUSED_REQUEST and printed["refused"] == f.REFUSAL_GARAGE_ALREADY_EXISTS
    status, printed = run(["create-pass", *tenant, "--garage", "garage-downtown", "--pass",
                           str(pass_), "--by", "owner", "--at", "2026-06-01T12:00:00-06:00"],
                          capsys)
    assert status == 0, printed
    # a day that does not parse
    status, printed = run(["register-vehicle", *tenant, "--garage", "garage-downtown",
                           "--pass-id", "pass-1", "--vehicle", "CAR-1",
                           "--effective-day", "June 1st"], capsys)
    assert status == EXIT_REFUSED_REQUEST
    assert printed["field"] == "--effective-day" and "'June 1st'" in printed["detail"]
    # the repair with a zone the system does not carry
    who = ["--by", "operator", "--at", "2026-06-01T12:00:00-06:00", "--reason", "mistyped"]
    status, printed = run(["set-garage-timezone", *tenant, "--garage", "garage-downtown",
                           "--timezone", "Mars/Tharsis", *who], capsys)
    assert status == EXIT_REFUSED_REQUEST and printed["refused"] == f.REFUSAL_TIMEZONE_UNKNOWN
    assert "Mars/Tharsis" in printed["detail"]
    # and with one it does
    status, printed = run(["set-garage-timezone", *tenant, "--garage", "garage-downtown",
                           "--timezone", "America/Phoenix", *who], capsys)
    assert status == 0 and printed == {"garage": "garage-downtown", "timezone": "America/Phoenix",
                                       "was": "America/Denver", "was_readable": True,
                                       "changed_by": "operator",
                                       "changed_at": "2026-06-01T12:00:00-06:00",
                                       "reason": "mistyped"}


@pytest.mark.guarantee("G18")
@store_test
def test_set_garage_timezone_with_a_dash_leading_value_is_the_json_refusal_exit_3(
    app, tenant_id, tmp_path, capsys, monkeypatch
):
    """Through the store, as the operator typed it at the re-gate."""
    from store_harness import query

    _dsn_for_the_app(monkeypatch)
    garage, _pass = _documents(tmp_path)
    tenant = ["--tenant", str(tenant_id)]
    status, printed = run(["create-garage", *tenant, "--garage", str(garage)], capsys)
    assert status == 0
    who = ["--by", "operator", "--at", "2026-06-01T12:00:00-06:00", "--reason", "typo"]
    status, printed = run(["set-garage-timezone", *tenant, "--garage", "garage-downtown",
                           "--timezone", "-06:00", *who], capsys)
    assert status == EXIT_REFUSED_REQUEST, printed
    assert printed["refused"] == f.REFUSAL_TIMEZONE_UNKNOWN
    assert printed["field"] == "garage.timezone"
    assert "'-06:00'" in printed["detail"]
    assert query(app, tenant_id, "SELECT timezone FROM garages") == [("America/Denver",)]
    assert query(app, tenant_id, "SELECT count(*) FROM garage_changes") == [(0,)]


# ---------------------------------------------------------------------------
# The document boundary: every value checked against its declared type (W2, W3).
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, document: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document))
    return path


def _with(document: dict, dotted: str, value: object) -> dict:
    """A deep copy of ``document`` with one dotted key replaced (or removed
    when ``value`` is ``...``)."""
    import copy

    out = copy.deepcopy(document)
    cursor = out
    *parents, last = dotted.split(".")
    for part in parents:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
    if value is ...:
        del cursor[last]
    else:
        cursor[last] = value
    return out


REGISTRATION = {"pass_id": "pass-1", "vehicle_identity": "CAR-1", "effective_day": "2026-01-01"}
VISIT = {"pass_id": "pass-1", "vehicle_identity": "CAR-1", "entry_lane": "L1",
         "entered_at": "2026-06-01T09:00:00-06:00"}

#: The L3's census, the cases that were TRACEBACKS or SILENT MISREADS at the
#: command line: (which document, the dotted key, the wrong value, the refusal).
#: ``...`` removes the key. Every one is now the JSON refusal, exit 3, stderr
#: empty -- and the refusal names the field.
WRONG_TYPED_DOCUMENTS = [
    ("registration", "vehicle_identity", ..., f.REFUSAL_FIELD_BLANK),
    ("registration", "vehicle_identity", 1234, f.REFUSAL_FIELD_WRONG_TYPE),
    ("registration", "vehicle_identity", ["CAR-1"], f.REFUSAL_FIELD_WRONG_TYPE),
    ("registration", "pass_id", {"id": "x"}, f.REFUSAL_FIELD_WRONG_TYPE),
    ("registration", "pass_id", ["pass-1"], f.REFUSAL_FIELD_WRONG_TYPE),
    ("registration", "pass_id", 7, f.REFUSAL_FIELD_WRONG_TYPE),
    ("registration", "effective_day", 20260101, f.REFUSAL_FIELD_WRONG_TYPE),
    ("visit", "vehicle_identity", ..., f.REFUSAL_FIELD_BLANK),
    ("visit", "vehicle_identity", 5, f.REFUSAL_FIELD_WRONG_TYPE),
    ("visit", "pass_id", {"x": 1}, f.REFUSAL_FIELD_WRONG_TYPE),
    ("visit", "entry_lane", 1, f.REFUSAL_FIELD_WRONG_TYPE),
    ("visit", "entered_at", 5, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.allowed_lanes", "L1", f.REFUSAL_FIELD_WRONG_TYPE),  # W3: not {'1','L'}
    ("pass", "terms.allowed_lanes", 5, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.allowed_lanes", [1], f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.directions", 5, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.directions", "entry", f.REFUSAL_FIELD_WRONG_TYPE),  # W3
    ("pass", "terms.windows", 5, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.windows", {"days": [1]}, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.windows.0.days", 5, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.windows.0.days", "12345", f.REFUSAL_FIELD_WRONG_TYPE),  # W3
    ("pass", "terms.windows.0.days", [1.5], f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.windows.0.days", ["1"], f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.windows.0.start_minute", ..., f.REFUSAL_FIELD_BLANK),
    ("pass", "terms.windows.0.start_minute", "360", f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.windows.0.start_minute", 360.5, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.visit_allowance.count", "3", f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.visit_allowance.count", ..., f.REFUSAL_FIELD_BLANK),
    ("pass", "terms.visit_allowance.count", 2.5, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.visit_allowance.count", True, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.max_stay_minutes", 10**15, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.max_stay_minutes", "600", f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms.valid_from", 2026, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "terms", [], f.REFUSAL_FIELD_BLANK),
    ("pass", "holder", ..., f.REFUSAL_FIELD_BLANK),
    ("pass", "holder.email", 7, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "id", 7, f.REFUSAL_FIELD_WRONG_TYPE),
    ("garage", "timezone", 5, f.REFUSAL_FIELD_WRONG_TYPE),
    ("garage", "timezone", ..., f.REFUSAL_FIELD_BLANK),
    ("garage", "transient_available", "yes", f.REFUSAL_FIELD_WRONG_TYPE),
    ("garage", "transient_available", 1, f.REFUSAL_FIELD_WRONG_TYPE),
    ("garage", "id", 5, f.REFUSAL_FIELD_WRONG_TYPE),
]


@pytest.mark.guarantee("G18")
@pytest.mark.parametrize(
    "which,key,value,code", WRONG_TYPED_DOCUMENTS,
    ids=[f"{w}.{k}={'ABSENT' if v is ... else v!r}" for w, k, v, _ in WRONG_TYPED_DOCUMENTS],
)
def test_a_wrong_typed_document_field_is_the_json_refusal_naming_the_field(
    tmp_path, capsys, which, key, value, code
):
    """THE L3's CENSUS, CASE BY CASE: 19 of these were tracebacks at the command
    line and three were silent misreads (``allowed_lanes: "L1"`` became the lane
    set ``{'1', 'L'}``, a float allowance counted, a visit on an object pass_id
    was ignored). Every value a document carries is now checked against the
    type its dataclass declares -- derived from the annotation, not from a list
    -- so each is the JSON refusal, exit 3, the field named, stderr empty."""
    garage, pass_ = _documents(tmp_path)
    documents = {"garage": garage, "pass": pass_}
    argv = ["access", "--garage", str(garage), "--pass", str(pass_), *MOVE]
    base = {"garage": json.loads(garage.read_text()), "pass": json.loads(pass_.read_text()),
            "registration": REGISTRATION, "visit": VISIT}[which]
    broken = _with(base, key, value)
    if which in ("registration", "visit"):
        path = _write(tmp_path, f"{which}s.json", [broken])
        argv += [f"--{which}s", str(path)]
    else:
        documents[which].write_text(json.dumps(broken))
    status, printed = run(argv, capsys)
    assert status == EXIT_REFUSED_REQUEST, printed
    assert printed["refused"] == code, printed
    import re

    field = key.split(".")[-1] if not key.split(".")[-1].isdigit() else key.split(".")[-2]
    assert re.sub(r"\[\d+\]$", "", printed["field"]).endswith(field), printed
    assert capsys.readouterr().err == ""
    if value is not ...:
        shown = value[0] if isinstance(value, list) and len(value) == 1 else value
        assert repr(shown) in printed["detail"] or str(shown) in printed["detail"], printed


@pytest.mark.guarantee("G18")
def test_a_string_is_never_reinterpreted_as_a_collection(tmp_path, capsys):
    """W3 as the control reads: ``allowed_lanes: "L1"`` used to LOAD as the lane
    set ``{'1', 'L'}`` -- no traceback, no refusal, and a legitimate entry on L1
    was then WRONG_LANE. Now the load itself is refused; the same document with
    the list ``["L1"]`` is the control and covers."""
    from garage_pass.documents import load_pass

    with pytest.raises(f.Refused) as refused:
        load_pass(pass_document(terms={**pass_document()["terms"], "allowed_lanes": "L1"}))
    assert refused.value.code == f.REFUSAL_FIELD_WRONG_TYPE
    assert refused.value.field == "pass.terms.allowed_lanes"
    assert "a list of text" in refused.value.detail and "'L1'" in refused.value.detail
    loaded = load_pass(pass_document(terms={**pass_document()["terms"], "allowed_lanes": ["L1"]}))
    assert loaded.terms is not None and loaded.terms.allowed_lanes == frozenset({"L1"})
    garage, pass_ = _documents(tmp_path)
    pass_.write_text(json.dumps(pass_document(terms={**pass_document()["terms"],
                                                     "allowed_lanes": ["L1"]})))
    registrations = _write(tmp_path, "r.json", [REGISTRATION])
    status, printed = run(["access", "--garage", str(garage), "--pass", str(pass_),
                           "--registrations", str(registrations), *MOVE], capsys)
    assert status == 0 and printed["outcome"] == "covered", printed


@pytest.mark.guarantee("G18")
def test_the_document_keys_and_checks_are_derived_from_the_dataclass_not_listed():
    """THE ADD-A-FIELD CONTROL. A dataclass nobody listed anywhere is handed to
    the loader: its fields are the document's keys, each value is checked
    against its declared type, an unknown key is refused, a required field is
    required, a defaulted one is optional -- with no list edited. Then the
    published key sets are shown to be exactly what the dataclasses declare,
    and the two declared exceptions are exactly two."""
    from dataclasses import dataclass

    from garage_pass import documents as docs

    @dataclass(frozen=True)
    class Scratch:
        id: str
        count: int
        note: str | None = None
        tags: frozenset[str] = frozenset()

    assert docs.keys_of(Scratch) == {"id", "count", "note", "tags"}
    loaded = docs.load(Scratch, {"id": "s", "count": 2, "note": "n", "tags": ["a", "b"]}, "scratch")
    assert loaded == Scratch("s", 2, "n", frozenset({"a", "b"}))
    assert docs.load(Scratch, {"id": "s", "count": 2}, "scratch") == Scratch("s", 2)
    for document, code, field in (
        ({"id": "s", "count": "2"}, f.REFUSAL_FIELD_WRONG_TYPE, "scratch.count"),
        ({"id": "s", "count": True}, f.REFUSAL_FIELD_WRONG_TYPE, "scratch.count"),
        ({"id": "s", "count": 2, "note": 5}, f.REFUSAL_FIELD_WRONG_TYPE, "scratch.note"),
        ({"id": "s", "count": 2, "tags": "ab"}, f.REFUSAL_FIELD_WRONG_TYPE, "scratch.tags"),
        ({"id": "s", "count": 2, "tags": [1]}, f.REFUSAL_FIELD_WRONG_TYPE, "scratch.tags[0]"),
        ({"id": "s"}, f.REFUSAL_FIELD_BLANK, "scratch.count"),
        ({"id": "s", "count": None}, f.REFUSAL_FIELD_BLANK, "scratch.count"),
        ({"id": "s", "count": 2, "colour": "red"}, f.REFUSAL_UNKNOWN_FIELD, "scratch.colour"),
    ):
        with pytest.raises(f.Refused) as refused:
            docs.load(Scratch, document, "scratch")
        assert (refused.value.code, refused.value.field) == (code, field), refused.value
    # the published sets ARE the dataclasses' fields, minus the declared exceptions
    import dataclasses as dc

    from garage_pass.garage import Garage
    from garage_pass.passes import Holder, Pass, Registration, Visit
    from garage_pass.terms import Terms, VisitAllowance, Window

    for cls, published in ((Garage, docs.GARAGE_KEYS), (Pass, docs.PASS_KEYS),
                           (Holder, docs.HOLDER_KEYS), (Terms, docs.TERMS_KEYS),
                           (Window, docs.WINDOW_KEYS), (VisitAllowance, docs.ALLOWANCE_KEYS),
                           (Registration, docs.REGISTRATION_KEYS), (Visit, docs.VISIT_KEYS)):
        names = {fld.name for fld in dc.fields(cls)} - docs.STORE_ONLY.get(cls, frozenset())
        renamed = {docs.DOCUMENT_KEY_OF.get((cls, n), (n, None))[0] for n in names}
        assert published == renamed, cls
    assert docs.DOCUMENT_KEY_OF == {(Terms, "max_stay"): ("max_stay_minutes", "minutes")}
    assert docs.STORE_ONLY == {Pass: frozenset({"unreadable"}), Garage: frozenset({"unreadable"})}
    assert "unreadable" not in docs.PASS_KEYS | docs.GARAGE_KEYS
    assert "max_stay_minutes" in docs.TERMS_KEYS and "max_stay" not in docs.TERMS_KEYS


# ---------------------------------------------------------------------------
# What the driver raises and the module did not name: the machine's configuration.
# ---------------------------------------------------------------------------


@pytest.mark.guarantee("G18")
def test_a_dsn_that_is_not_a_conninfo_string_is_a_sentence_exit_2(tmp_path, capsys, monkeypatch):
    """``psycopg.ProgrammingError`` at connect -- a traceback in the L3's
    census. The same shape as a DSN that does not connect."""
    garage, _pass = _documents(tmp_path)
    monkeypatch.setenv("GARAGE_PASS_DSN", "this is not a dsn = secret-4f9c")
    try:
        status = main(["create-garage", "--tenant", "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                       "--garage", str(garage)])
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"raised instead of a sentence: {exc!r}")
    captured = capsys.readouterr()
    assert status == 2 and "did not connect" in captured.err and captured.out == ""
    assert "secret-4f9c" not in captured.err


@pytest.mark.guarantee("G18")
@store_test
def test_a_driver_error_the_store_did_not_name_is_a_sentence_and_a_named_one_is_still_the_refusal(
    app, owner, tenant_id, tmp_path, capsys, monkeypatch
):
    """THE GUARD ON THE GENERIC MAPPING, BOTH HALVES IN ONE RUN. The command
    line maps whatever the driver raises and the store did not name to one
    sentence on stderr with its SQLSTATE, exit 2 -- the shape of a DSN that
    does not connect. It is the LAST resort, after the store's own named
    refusals: a generic handler placed AHEAD of them would report a real
    refusal as a broken server, which is worse than the four tracebacks it
    replaces. So, in one test: (a) a database that is not set up (the schema
    out of the search path: ``UndefinedTable``, class 42) is the sentence;
    (b) a REAL deadlock at the one-car-one-pass INSERT, driven through the
    command line, is STILL the JSON refusal naming the constraint and carrying
    PostgreSQL's DETAIL, exit 3 -- and it is made deterministic the way G1's
    test does it, with the command's own transaction made to hold a row first
    (through ``_holders``, the module's read before its INSERT)."""
    import threading
    import time

    from fixtures import a_pass, transient_garage
    from garage_pass.store import records
    from garage_pass.store.postgres import connect
    from store_harness import query, seed

    garage_doc, _pass = _documents(tmp_path)
    tenant = ["--tenant", str(tenant_id)]
    # ---- (a) not set up: the sentence, exit 2, stdout empty, no traceback
    from psycopg import conninfo

    from garage_pass.store.postgres import APP_ROLE
    from store_harness import APP_PASSWORD

    params = conninfo.conninfo_to_dict(DSN)
    monkeypatch.setenv("GARAGE_PASS_DSN", conninfo.make_conninfo(
        **{**params, "user": APP_ROLE, "password": APP_PASSWORD,
           "options": "-c search_path=pg_catalog"}))
    try:
        status = main(["create-garage", *tenant, "--garage", str(garage_doc)])
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"the driver's error escaped as a traceback: {exc!r}")
    captured = capsys.readouterr()
    assert status == 2 and captured.out == "", captured
    assert "SQLSTATE 42" in captured.err and "UndefinedTable" in captured.err, captured.err
    assert "not set up" in captured.err and "\n" not in captured.err.strip(), captured.err
    assert str(APP_PASSWORD) not in captured.err
    # ---- (b) a real deadlock at the INSERT, through the command line: exit 3, named
    _dsn_for_the_app(monkeypatch)
    G = transient_garage()
    A, Z = a_pass(id="pass-a"), a_pass(id="pass-z")
    seed(app, tenant_id, G, (A, Z))
    ids = dict(query(app, tenant_id, "SELECT external_id, id FROM passes"))
    raw = connect(DSN)
    theirs: dict = {}
    original_holders = records._holders

    def holders_then_hold_z_and_wait(cursor, *args):
        """The module's own read before its INSERT, then -- on the COMMAND'S
        transaction -- a row lock on Z, the raw side made to wait on it, and
        the clock run past its deadlock_timeout; the INSERT that follows is
        the last waiter and the victim."""
        rows = original_holders(cursor, *args)
        cursor.execute("SELECT id FROM passes WHERE id = %s FOR UPDATE", (ids["pass-z"],))
        with raw.cursor() as c:
            c.execute("SELECT id FROM passes WHERE id = %s FOR UPDATE", (ids["pass-a"],))

        def wait_on_ours():
            try:
                with raw.cursor() as c:
                    c.execute("SELECT id FROM passes WHERE id = %s FOR UPDATE", (ids["pass-z"],))
                theirs["result"] = "acquired"
            except BaseException as exc:  # noqa: BLE001
                theirs["result"] = exc

        threading.Thread(target=wait_on_ours).start()

        def raw_is_waiting() -> bool:
            with owner.cursor() as c:
                c.execute("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' "
                          "AND query ILIKE 'SELECT id FROM passes%%FOR UPDATE'")
                return c.fetchone()[0] == 1

        deadline = time.monotonic() + 10
        while not raw_is_waiting() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert raw_is_waiting()
        time.sleep(1.5)
        return rows

    monkeypatch.setattr(records, "_holders", holders_then_hold_z_and_wait)
    try:
        status, printed = run(["register-vehicle", *tenant, "--garage", G.id, "--pass-id", A.id,
                               "--vehicle", "CAR-1", "--effective-day", "2026-01-01"], capsys)
    finally:
        raw.rollback()
        raw.close()
    assert status == EXIT_REFUSED_REQUEST, (status, printed, capsys.readouterr())
    assert printed["refused"] == f.REFUSAL_CONSTRAINT and printed["field"] == "vehicle_identity"
    assert "deadlock" in printed["detail"] and "blocked by process" in printed["detail"]
    assert "raced" not in printed["detail"]
    assert query(app, tenant_id, "SELECT count(*) FROM vehicle_registrations") == [(0,)]


@pytest.mark.guarantee("G18")
@store_test
def test_create_garage_for_a_tenant_nobody_seeded_is_the_json_refusal_not_the_foreign_key(
    app, tenant_id, tmp_path, capsys, monkeypatch
):
    """W5. Measured at the re-run of the walk: a ``--tenant`` with no row was a
    ``ForeignKeyViolation`` traceback at ``create-garage`` -- and at
    create-garage ONLY, the L3 measured: the other eight store commands load
    the garage first and were already refusing GARAGE_NOT_FOUND. The first
    write for a tenant now reads the tenant row first and refuses by name;
    the seeded tenant in the same run is the control, and nothing is stored
    for the unseeded one."""
    import uuid

    from store_harness import query

    _dsn_for_the_app(monkeypatch)
    garage, _pass = _documents(tmp_path)
    nobody = str(uuid.uuid4())
    status, printed = run(["create-garage", "--tenant", nobody, "--garage", str(garage)], capsys)
    assert status == EXIT_REFUSED_REQUEST, printed
    assert printed["refused"] == f.REFUSAL_TENANT_NOT_FOUND and printed["field"] == "tenant"
    assert nobody in printed["detail"] and capsys.readouterr().err == ""
    status, printed = run(["create-garage", "--tenant", str(tenant_id), "--garage", str(garage)],
                          capsys)
    assert status == 0 and printed["stored"] == "garage-downtown", "the control: a seeded tenant"
    assert query(app, tenant_id, "SELECT count(*) FROM garages") == [(1,)]
    with app.cursor() as cursor:  # as the application role, no tenant set: nothing for nobody
        cursor.execute("SELECT count(*) FROM garages WHERE tenant_id = %s", (nobody,))
        assert cursor.fetchone() == (0,)
    app.rollback()
