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
    "TypeError": (PROGRAMMING, "a direction that is not a Direction, a Pass built half-shaped: "
                               "argparse choices and documents.py build the typed values, so "
                               "the command line cannot produce either -- reachable only from "
                               "the pure API, never from a command"),
    "KeyError": (PROGRAMMING, "a refusal code invented at a raise site and never registered: "
                              "the contract test and the orphan scan catch it before it ships"),
    "ValueError": (PROGRAMMING, "require_aware on a naive datetime: every instant the command "
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
    sentence that closes them. A reader of the ``-rA`` output sees the count."""
    found = every_raise()
    total = sum(len(where) for where in found.values())
    print(f"\nSWEEP: {total} raise statements naming {len(found)} classes: "
          + ", ".join(f"{name} {len(where)}" for name, where in sorted(found.items())))
    assert total > 50 and "Refused" in found
    for dead in ("ValueError", "TypeError"):
        assert "reachable only from the pure API, never from a command" in CLASSIFIED[dead][1]
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
