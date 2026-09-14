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
@pytest.mark.parametrize("option", ["--garage", "--pass", "--registrations", "--visits",
                                    "--garages"])
def test_a_document_nested_past_the_decoder_is_the_json_refusal_on_every_document_argument(
    tmp_path, capsys, option
):
    """THE L5 GATE'S B1. A file that is valid JSON nested deeper than
    ``json.loads`` decodes makes it raise ``RecursionError`` -- a ``RuntimeError``,
    not a ``ValueError`` -- and ``cli._document`` did not name it: a traceback in
    BOTH directions, exit 1 with no answer, the one shape G18 forbids. It is the
    refusing side of the line (no record: the file cannot be read as JSON), so
    it is ``REFUSAL_DOCUMENT_UNREADABLE`` naming the option, exit 3, at an ENTRY
    and at an EXIT alike. The fix is at the ONE decode boundary, so it is proven
    on every document argument, not the two the gate found; and the CONTROL in
    the same test is the same shape 60 deep, which decodes: at an exit it is a
    record the module holds and cannot read (RECORD_UNREADABLE), at an entry it
    is refused naming the document -- so the refusal here is about the decoder,
    not about the shape."""
    garage, pass_ = _documents(tmp_path)
    good = _write(tmp_path, "r.json", [REGISTRATION])
    deep = tmp_path / "deep.json"
    deep.write_text(PAST_THE_DECODER)
    shallow = tmp_path / "shallow.json"
    shallow.write_text(SHALLOW)

    def argv(path: Path) -> list[str]:
        base = {"--garage": str(garage), "--pass": str(pass_), "--registrations": str(good)}
        base[option] = str(path)
        out = ["access", "--garage", base["--garage"], "--pass", base["--pass"],
               "--registrations", base["--registrations"]]
        if option in ("--visits", "--garages"):
            out += [option, str(path)]
        return out

    for direction in ("entry", "exit"):
        status, printed = run([*argv(deep), "--vehicle", "CAR-1", "--lane", "L1",
                               "--direction", direction, "--at", "2026-06-01T12:00:00-06:00"],
                              capsys)
        assert status == EXIT_REFUSED_REQUEST, (
            f"{option} nested past the decoder at {direction}: exit {status}, {printed}"
        )
        assert printed["refused"] == f.REFUSAL_DOCUMENT_UNREADABLE and printed["field"] == option
        assert "recursion" in printed["detail"].lower() and str(deep) in printed["detail"]
    # the control: the same shape, decodable -- answered at an exit, refused at an entry
    entry, exit_ = _either_way(argv(shallow), capsys)
    _assert_entry_refused(*entry, f.REFUSAL_FIELD_BLANK)
    _assert_exit_answered(*exit_, f.RECORD_UNREADABLE)
    # and not in-process only: the actual process, so stderr is seen
    completed = subprocess.run(
        [sys.executable, "-m", "garage_pass.cli", *argv(deep), "--vehicle", "CAR-1", "--lane", "L1",
         "--direction", "exit", "--at", "2026-06-01T12:00:00-06:00"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert completed.returncode == EXIT_REFUSED_REQUEST, completed.stderr[-400:]
    assert "Traceback" not in completed.stderr and completed.stderr == "", completed.stderr[-400:]
    assert json.loads(completed.stdout)["refused"] == f.REFUSAL_DOCUMENT_UNREADABLE


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


@pytest.mark.guarantee("G18")
@store_test
def test_the_enrolment_commands_render_every_refusal_and_the_redemption_exits_by_the_answer(
    app, tenant_id, tmp_path, capsys, monkeypatch
):
    """Each new verb, each input that would have been a traceback or an
    argparse usage error: --days-valid absent (the module's refusal BY NAME,
    not argparse's), --days-valid not a number, --enrols-at neither end, the
    R1 contradiction on the repair, a blank --token, a link redeemed twice; and
    the redemption's exit status follows the ANSWER while the enrolment half is
    in the JSON."""
    from store_harness import query

    _dsn_for_the_app(monkeypatch)
    garage, pass_ = _documents(tmp_path)
    T = ["--tenant", str(tenant_id), "--garage", "garage-downtown"]
    assert run(["create-garage", "--tenant", str(tenant_id), "--garage", str(garage)],
               capsys)[0] == 0
    assert run(["create-pass", *T, "--pass", str(pass_), "--by", "owner",
                "--at", "2026-06-01T12:00:00-06:00"], capsys)[0] == 0
    who = ["--by", "owner", "--at", "2026-06-01T12:00:00-06:00"]
    issue = ["issue-enrolment", *T, "--pass-id", "pass-1", "--enrolment-id", "qr-1",
             "--starts-on", "2026-06-01", *who]
    status, printed = run(issue, capsys)  # --days-valid absent
    assert status == EXIT_REFUSED_REQUEST
    assert printed["refused"] == f.REFUSAL_DAYS_VALID_NOT_STATED
    assert printed["field"] == "days_valid"
    status, printed = run([*issue, "--days-valid", "three"], capsys)
    assert status == EXIT_REFUSED_REQUEST and printed["field"] == "--days-valid"
    status, printed = run([*issue, "--days-valid", "0"], capsys)
    assert status == EXIT_REFUSED_REQUEST
    assert printed["refused"] == f.REFUSAL_DAYS_VALID_NOT_POSITIVE
    status, printed = run([*issue, "--days-valid", "3", "--starts-on", "June 1st"], capsys)
    assert status == EXIT_REFUSED_REQUEST and printed["field"] == "--starts-on"
    assert query(app, tenant_id, "SELECT count(*) FROM enrolments") == [(0,)]
    # the repair: neither end, then the value that lands
    repair = ["set-garage-enrols-at", *T, *who, "--reason", "stated"]
    status, printed = run([*repair, "--enrols-at", "middle"], capsys)
    assert status == EXIT_REFUSED_REQUEST and printed["refused"] == f.REFUSAL_FIELD_BLANK
    assert printed["field"] == "garage.enrols_at" and "'middle'" in printed["detail"]
    status, printed = run([*repair, "--enrols-at", "entry"], capsys)
    assert status == 0 and printed["enrols_at"] == "entry" and printed["was"] is None
    # a token nobody issued, presented at the right end: the enrolment half is the
    # refusal rendered through the one seam, the answer half is the lane's, and the
    # exit status is the ANSWER's -- not covered, 1
    status, printed = run(["redeem-enrolment", *T, "--token", "nothing", *MOVE], capsys)
    assert status == 1, printed
    assert printed["enrolment"] == {"enrolment": None, "redeemed": False,
                                    "refused": f.REFUSAL_CREDENTIAL_UNKNOWN, "field": "token",
                                    "detail": printed["enrolment"]["detail"]}
    assert printed["answer"]["outcome"] == "not_covered"
    assert printed["answer"]["reason"] == "NO_PASS"
    status, printed = run(["redeem-enrolment", *T, "--token", "   ", *MOVE], capsys)
    assert status == 1 and printed["enrolment"]["refused"] == f.REFUSAL_FIELD_BLANK
    assert printed["enrolment"]["field"] == "token"
    # issued, redeemed: covered, 0; redeemed again: the refusal half, and STILL 0 --
    # the car is on the pass, the lane hears that
    status, printed = run([*issue, "--days-valid", "3"], capsys)
    assert status == 0 and printed["enrolment"] == "qr-1"
    token = printed["token"]
    status, printed = run(["redeem-enrolment", *T, "--token", token, *MOVE], capsys)
    assert status == 0 and printed["enrolment"]["redeemed"] is True
    assert printed["enrolment"]["pass_state_change"] is None, "the document's pass is active"
    assert printed["enrolment"]["registration"]["vehicle_identity"] == "CAR-1"
    assert printed["answer"]["outcome"] == "covered"
    assert "token" not in json.dumps(printed["enrolment"]) or token not in json.dumps(printed)
    status, printed = run(["redeem-enrolment", *T, "--token", token, *MOVE], capsys)
    assert status == 0 and printed["enrolment"]["refused"] == f.REFUSAL_CREDENTIAL_ALREADY_USED
    assert printed["answer"]["outcome"] == "covered"
    # the holder link, twice
    link = ["issue-holder-link", *T, "--pass-id", "pass-1", "--link-id", "link-1",
            "--starts-on", "2026-06-01", "--days-valid", "3", *who]
    status, printed = run(link, capsys)
    assert status == 0 and printed["holder_link"] == "link-1"
    redeem_link = ["redeem-holder-link", *T, "--token", printed["token"], "--name", "Her",
                   "--phone", "1", "--enrolment-id", "qr-2", "--starts-on", "2026-06-01",
                   "--days-valid", "3", "--at", "2026-06-01T12:00:00-06:00"]
    status, printed = run(redeem_link, capsys)
    assert status == 0 and printed["enrolment"]["enrolment"] == "qr-2"
    status, printed = run(redeem_link, capsys)
    assert status == EXIT_REFUSED_REQUEST
    assert printed["refused"] == f.REFUSAL_CREDENTIAL_ALREADY_USED
    assert query(app, tenant_id, "SELECT count(*) FROM enrolments") == [(2,)]


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
VISIT = {"pass_id": "pass-1", "garage_id": "garage-downtown", "vehicle_identity": "CAR-1",
         "entry_lane": "L1", "entered_at": "2026-06-01T09:00:00-06:00"}

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
    ("pass", "terms.allowed_lanes", [1], f.REFUSAL_FIELD_BLANK),  # an entry is an object
    ("pass", "terms.allowed_lanes", ["L1"], f.REFUSAL_FIELD_BLANK),  # the pre-G3a flat shape
    ("pass", "terms.allowed_lanes.0.lanes", "L1", f.REFUSAL_FIELD_WRONG_TYPE),  # W3, per garage
    ("pass", "terms.allowed_lanes.0.garage_id", 5, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "garage_ids", "garage-downtown", f.REFUSAL_FIELD_WRONG_TYPE),  # W3: not a set of chars
    ("pass", "garage_ids", 5, f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "garage_ids", [5], f.REFUSAL_FIELD_WRONG_TYPE),
    ("pass", "garage_ids", [], f.REFUSAL_PASS_NAMES_NO_GARAGE),
    ("pass", "garage_ids", ..., f.REFUSAL_FIELD_BLANK),
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
    the list is the control and covers. Since G3a the lanes are stated per
    garage -- ``[{"garage_id": ..., "lanes": ["L1"]}]`` -- and the string is
    refused at the outer list and at the inner one alike."""
    from garage_pass.documents import load_pass
    from garage_pass.terms import GarageLanes

    with pytest.raises(f.Refused) as refused:
        load_pass(pass_document(terms={**pass_document()["terms"], "allowed_lanes": "L1"}))
    assert refused.value.code == f.REFUSAL_FIELD_WRONG_TYPE
    assert refused.value.field == "pass.terms.allowed_lanes"
    assert "a list of" in refused.value.detail and "'L1'" in refused.value.detail
    stated = [{"garage_id": "garage-downtown", "lanes": ["L1"]}]
    with pytest.raises(f.Refused) as refused:
        load_pass(pass_document(terms={**pass_document()["terms"], "allowed_lanes": [
            {"garage_id": "garage-downtown", "lanes": "L1"}]}))
    assert refused.value.code == f.REFUSAL_FIELD_WRONG_TYPE
    assert refused.value.field == "pass.terms.allowed_lanes[0].lanes"
    loaded = load_pass(pass_document(terms={**pass_document()["terms"], "allowed_lanes": stated}))
    assert loaded.terms is not None and loaded.terms.allowed_lanes == (
        GarageLanes("garage-downtown", frozenset({"L1"})),)
    garage, pass_ = _documents(tmp_path)
    pass_.write_text(json.dumps(pass_document(terms={**pass_document()["terms"],
                                                     "allowed_lanes": stated})))
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


# ---------------------------------------------------------------------------
# THE EXIT THAT THE DOCUMENT BOUNDARY USED TO REFUSE (V1). The line: the module
# answers when it holds a record whose content it cannot read; it refuses when
# it holds no record at all, or no instant to read it at.
# ---------------------------------------------------------------------------

EXIT = ["--vehicle", "CAR-1", "--lane", "L1", "--direction", "exit",
        "--at", "2026-06-01T12:00:00-06:00"]


def _either_way(
    argv_without_direction: list[str], capsys
) -> tuple[tuple[int, dict], tuple[int, dict]]:
    """The same call at an ENTRY and at an EXIT: ((status, printed), (status, printed))."""
    common = argv_without_direction
    entry = run([*common, "--vehicle", "CAR-1", "--lane", "L1", "--direction", "entry",
                 "--at", "2026-06-01T12:00:00-06:00"], capsys)
    exit_ = run([*common, "--vehicle", "CAR-1", "--lane", "L1", "--direction", "exit",
                 "--at", "2026-06-01T12:00:00-06:00"], capsys)
    return entry, exit_


def _assert_exit_answered(status: int, printed: dict, reason: str, *names: str) -> None:
    assert status == 1 and printed.get("outcome") == "not_covered", (
        f"the exit went UNANSWERED: exit {status}, {printed}"
    )
    assert printed["reason"] == reason, printed
    assert printed["exit_note"] == f.EXIT_IS_NEVER_REFUSED
    assert printed["means"] == f.MEANS_EXIT_OUT_OF_TERMS
    for name in names:
        assert name in printed["detail"], (name, printed["detail"])


def _assert_entry_refused(status: int, printed: dict, code: str) -> None:
    assert status == EXIT_REFUSED_REQUEST and printed.get("refused") == code, printed


@pytest.mark.guarantee("G4")
def test_a_document_the_module_cannot_read_is_answered_at_an_exit_and_refused_at_an_entry(
    tmp_path, capsys
):
    """THE SIX PROBES, both directions, the well-formed exit as the control in
    the same run. Measured before this: six exits, six refusals, no outcome --
    while the identical content from the STORE answered (a stored row with bad
    content degrades to an unreadable pass or garage, G17). The document door
    now takes the same path: a pass or garage document that refuses becomes
    the carrier a stored row would (PASS_UNREADABLE / GARAGE_UNREADABLE); a
    registration document that refuses is the ledger the module cannot read
    (RECORD_UNREADABLE). At an entry every one is still refused by name."""
    garage, pass_ = _documents(tmp_path)
    good = _write(tmp_path, "r.json", [REGISTRATION])
    base = ["access", "--garage", str(garage), "--pass", str(pass_), "--registrations", str(good)]
    entry, exit_ = _either_way(base, capsys)
    assert entry[1]["outcome"] == "covered" and exit_[1]["outcome"] == "covered", "the control"
    # three registration documents
    for name, broken, code in (
        ("missing", {k: v for k, v in REGISTRATION.items() if k != "vehicle_identity"},
         f.REFUSAL_FIELD_BLANK),
        ("null", {**REGISTRATION, "vehicle_identity": None}, f.REFUSAL_FIELD_BLANK),
        ("1234", {**REGISTRATION, "vehicle_identity": 1234}, f.REFUSAL_FIELD_WRONG_TYPE),
    ):
        bad = _write(tmp_path, f"r_{name}.json", [broken])
        entry, exit_ = _either_way(["access", "--garage", str(garage), "--pass", str(pass_),
                                    "--registrations", str(bad)], capsys)
        _assert_entry_refused(*entry, code)
        _assert_exit_answered(*exit_, f.RECORD_UNREADABLE, "registration[0].vehicle_identity")
    # two pass documents: the carrier, so the pass's own reason
    for value in (5, "L1"):
        bad = _write(tmp_path, "p_lanes.json",
                     pass_document(terms={**pass_document()["terms"], "allowed_lanes": value}))
        entry, exit_ = _either_way(["access", "--garage", str(garage), "--pass", str(bad),
                                    "--registrations", str(good)], capsys)
        _assert_entry_refused(*entry, f.REFUSAL_FIELD_WRONG_TYPE)
        _assert_exit_answered(*exit_, f.PASS_UNREADABLE, "'pass-1'", "allowed_lanes", repr(value))
        assert exit_[1]["pass_id"] == "pass-1"
    # the garage document: the carrier, so the garage's own reason
    (tmp_path / "tz").mkdir()
    badtz, _ = _documents(tmp_path / "tz", timezone="Mars/Olympus")
    entry, exit_ = _either_way(["access", "--garage", str(badtz), "--pass", str(pass_),
                                "--registrations", str(good)], capsys)
    _assert_entry_refused(*entry, f.REFUSAL_TIMEZONE_UNKNOWN)
    _assert_exit_answered(*exit_, f.GARAGE_UNREADABLE, "Mars/Olympus", "garage.timezone")
    # a visit document without its garage (the field the engine-stay round
    # added): a stated record refusal at the boundary, no new mechanism --
    # keys are derived from the dataclass, so the missing key is named
    for name, broken, code in (
        ("missing", {k: v for k, v in VISIT.items() if k != "garage_id"}, f.REFUSAL_FIELD_BLANK),
        ("wrong", {**VISIT, "garage_id": 7}, f.REFUSAL_FIELD_WRONG_TYPE),
    ):
        bad = _write(tmp_path, f"v_{name}.json", [broken])
        entry, exit_ = _either_way(["access", "--garage", str(garage), "--pass", str(pass_),
                                    "--registrations", str(good), "--visits", str(bad)], capsys)
        _assert_entry_refused(*entry, code)
        _assert_exit_answered(*exit_, f.RECORD_UNREADABLE, "visit[0].garage_id")


@pytest.mark.guarantee("G4")
def test_the_carrier_rule_and_store_parity_at_an_exit(tmp_path, capsys):
    """A pass document whose carrier fields (id, garage_id, label, state) READ
    degrades to the unreadable pass a stored row becomes and answers only if
    the vehicle is on it; one whose carrier fields cannot be read has no object
    to hold the marker and is RECORD_UNREADABLE naming the field (A1.3). A
    registrations document that is JSON but not a list is a record whose
    content cannot be read; a registration entry that is a number, the same."""
    garage, pass_ = _documents(tmp_path)
    good = _write(tmp_path, "r.json", [REGISTRATION])
    other = _write(tmp_path, "p9.json", pass_document(id="pass-9"))
    # the car is on pass-9, readable; pass-1 is unreadable: covered by pass-9, parity with the store
    bad = _write(tmp_path, "p_bad.json", pass_document(holder={"email": "no-at-sign"}))
    on_nine = _write(tmp_path, "r9.json", [{**REGISTRATION, "pass_id": "pass-9"}])
    both = ["access", "--garage", str(garage), "--pass", str(bad), "--pass", str(other)]
    status, printed = run([*both, "--registrations", str(on_nine), *EXIT], capsys)
    assert status == 0 and printed["outcome"] == "covered", printed
    assert printed["pass_id"] == "pass-9", printed
    # the car is on pass-1, the unreadable one: PASS_UNREADABLE naming the field
    status, printed = run([*both, "--registrations", str(good), *EXIT], capsys)
    _assert_exit_answered(status, printed, f.PASS_UNREADABLE, "'pass-1'", "holder.email")
    # a contradiction in the terms: the carrier too (a raw row failing check_terms is the same)
    contradiction = Path("tests/documents/pass_contradiction.json").resolve()
    on_it = _write(tmp_path, "rc.json", [{**REGISTRATION, "pass_id": "pass-contradiction"}])
    entry, exit_ = _either_way(["access", "--garage", str(garage), "--pass", str(contradiction),
                                "--registrations", str(on_it)], capsys)
    _assert_entry_refused(*entry, f.REFUSAL_VALID_TO_BEFORE_VALID_FROM)
    _assert_exit_answered(*exit_, f.PASS_UNREADABLE, "'pass-contradiction'", "valid_to")
    # the carrier cannot be built: id, state
    for name, document, field in (
        ("id5", pass_document(id=5), "pass.id"),
        ("state", pass_document(state="frozen"), "state"),
        ("label", pass_document(label=None), "pass.label"),
    ):
        broken = _write(tmp_path, f"p_{name}.json", document)
        entry, exit_ = _either_way(["access", "--garage", str(garage), "--pass", str(broken),
                                    "--registrations", str(good)], capsys)
        assert entry[0] == EXIT_REFUSED_REQUEST
        _assert_exit_answered(*exit_, f.RECORD_UNREADABLE, field)
    # the garage's carrier cannot be built
    g5 = _write(tmp_path, "g5.json",
                {"id": 5, "timezone": "America/Denver", "transient_available": True})
    entry, exit_ = _either_way(["access", "--garage", str(g5), "--pass", str(pass_),
                                "--registrations", str(good)], capsys)
    _assert_entry_refused(*entry, f.REFUSAL_FIELD_WRONG_TYPE)
    _assert_exit_answered(*exit_, f.RECORD_UNREADABLE, "garage.id")
    # a registrations document that is JSON but not a list; an entry that is a number
    not_list = _write(tmp_path, "rd.json", {"pass_id": "pass-1"})
    entry, exit_ = _either_way(["access", "--garage", str(garage), "--pass", str(pass_),
                                "--registrations", str(not_list)], capsys)
    _assert_entry_refused(*entry, f.REFUSAL_FIELD_BLANK)
    _assert_exit_answered(*exit_, f.RECORD_UNREADABLE, "--registrations")
    number = _write(tmp_path, "rn.json", [7])
    entry, exit_ = _either_way(["access", "--garage", str(garage), "--pass", str(pass_),
                                "--registrations", str(number)], capsys)
    _assert_entry_refused(*entry, f.REFUSAL_FIELD_BLANK)
    _assert_exit_answered(*exit_, f.RECORD_UNREADABLE, "registration[0]")
    # more than one unreadable record: every one named
    two = _write(tmp_path, "r2.json",
                 [{**REGISTRATION, "vehicle_identity": 1}, {**REGISTRATION, "pass_id": []}])
    status, printed = run(["access", "--garage", str(garage), "--pass", str(pass_),
                           "--registrations", str(two), *EXIT], capsys)
    _assert_exit_answered(status, printed, f.RECORD_UNREADABLE, "2 record(s)",
                          "registration[0].vehicle_identity", "registration[1].pass_id")


#: What the module REFUSES in both directions: no record at all, or no instant.
NO_RECORD_OR_NO_INSTANT = ["missing --garage file", "--garage not JSON",
                           "--garage JSON nested past the decoder",
                           "missing --registrations file", "--at naive", "--at malformed"]

#: Deeper than any interpreter this package supports decodes (3.11 stops near 1,000
#: levels, 3.12 near 10,000): ``json.loads`` raises ``RecursionError`` on it.
PAST_THE_DECODER = "[" * 50_000 + "]" * 50_000
#: The same shape, decodable: a JSON list where an object or a list of objects belongs.
SHALLOW = "[" * 60 + "]" * 60


@pytest.mark.guarantee("G4")
def test_every_malformed_case_reads_entry_refuses_and_exit_answers_or_both_refuse(tmp_path, capsys):
    """A1.1's CONTROL: every malformed case the census knows, classified BOTH
    ways in one run. Each must read (entry refuses, exit answers) -- a record
    the module holds and cannot read -- or (entry refuses, exit refuses) -- no
    record at all, or no instant. Which bucket a case belongs to is derived
    from the principle, not from a list of readings: the no-record cases are
    the files and the instant, named once above; EVERYTHING ELSE is content.
    Any (entry answers, ...) or a content case reading (..., exit refuses) is
    a defect. The counts are printed for the receipt."""
    garage, pass_ = _documents(tmp_path)
    good = _write(tmp_path, "r.json", [REGISTRATION])
    cases: dict[str, list[str]] = {}
    for which, key, value, _code in WRONG_TYPED_DOCUMENTS:
        base = {"garage": json.loads(garage.read_text()), "pass": json.loads(pass_.read_text()),
                "registration": REGISTRATION, "visit": VISIT}[which]
        broken = _with(base, key, value)
        label = f"{which}.{key}={'ABSENT' if value is ... else value!r}"
        if which in ("registration", "visit"):
            path = _write(tmp_path, f"c_{len(cases)}.json", [broken])
            cases[label] = ["access", "--garage", str(garage), "--pass", str(pass_),
                            "--registrations", str(good), f"--{which}s", str(path)]
        else:
            path = _write(tmp_path, f"c_{len(cases)}.json", broken)
            g, p = (str(path), str(pass_)) if which == "garage" else (str(garage), str(path))
            cases[label] = ["access", "--garage", g, "--pass", p, "--registrations", str(good)]
    # the dataclasses' own validators, and the shapes of the ledger documents
    for label, document in (
        ("pass: a contradiction (valid_to < valid_from)",
         Path("tests/documents/pass_contradiction.json").resolve()),
        ("pass: holder email malformed",
         _write(tmp_path, "he.json", pass_document(holder={"email": "x"}))),
        ("pass: unknown field", _write(tmp_path, "uf.json", pass_document(colour="red"))),
        ("pass: a store-only field in the document",
         _write(tmp_path, "so.json", pass_document(unreadable="x"))),
        ("pass: document is a list", _write(tmp_path, "pl.json", [])),
    ):
        cases[label] = ["access", "--garage", str(garage), "--pass", str(document),
                        "--registrations", str(good)]
    (tmp_path / "tz2").mkdir()
    badtz, _ = _documents(tmp_path / "tz2", timezone="Mars/Olympus")
    base = ["access", "--garage", str(garage), "--pass", str(pass_)]
    cases["garage: timezone unknown"] = ["access", "--garage", str(badtz), "--pass", str(pass_),
                                        "--registrations", str(good)]
    cases["registrations: JSON but not a list"] = [
        *base, "--registrations", str(_write(tmp_path, "rd.json", {}))]
    cases["registrations: an entry is a number"] = [
        *base, "--registrations", str(_write(tmp_path, "rn.json", [7]))]
    cases["visits: an entry is a list"] = [
        *base, "--registrations", str(good), "--visits", str(_write(tmp_path, "vl.json", [[]]))]
    # --garages: the other garages of the passes, a JSON list of garage documents
    cases["garages: JSON but not a list"] = [
        *base, "--registrations", str(good), "--garages", str(_write(tmp_path, "gd.json", {}))]
    cases["garages: an entry is a number"] = [
        *base, "--registrations", str(good), "--garages", str(_write(tmp_path, "gn.json", [7]))]
    cases["garages: a member's timezone unknown"] = [
        *base, "--registrations", str(good), "--garages", str(_write(tmp_path, "gz.json", [
            {"id": "garage-far", "timezone": "Mars/Olympus", "transient_available": True}]))]
    cases["garages: a member missing its timezone"] = [
        *base, "--registrations", str(good), "--garages", str(_write(tmp_path, "gm.json", [
            {"id": "garage-far", "transient_available": True}]))]
    # no record at all, or no instant: refuses both ways
    cases["missing --garage file"] = ["access", "--garage", str(tmp_path / "nope.json"),
                                     "--pass", str(pass_)]
    (tmp_path / "nj.json").write_text("{not json")  # raw text, not a JSON string
    cases["--garage not JSON"] = ["access", "--garage", str(tmp_path / "nj.json"),
                                 "--pass", str(pass_)]
    (tmp_path / "deep.json").write_text(PAST_THE_DECODER)  # valid JSON the decoder cannot decode
    cases["--garage JSON nested past the decoder"] = [
        "access", "--garage", str(tmp_path / "deep.json"), "--pass", str(pass_)]
    cases["missing --registrations file"] = [*base, "--registrations", str(tmp_path / "nope2.json")]
    # (the instant cases are run with their own --at below)
    buckets: dict[str, list[str]] = {"entry refuses, exit answers": [],
                                     "entry refuses, exit refuses": []}
    defects = []
    for label, argv in cases.items():
        if label in NO_RECORD_OR_NO_INSTANT:
            expected = "entry refuses, exit refuses"
        else:
            expected = "entry refuses, exit answers"
        entry, exit_ = _either_way(argv, capsys)
        e = ("refuses" if entry[0] == EXIT_REFUSED_REQUEST
             else f"answers ({entry[1].get('outcome')})")
        x = "refuses" if exit_[0] == EXIT_REFUSED_REQUEST else (
            "answers" if exit_[1].get("outcome") in ("covered", "not_covered") else f"?? {exit_}")
        read = f"entry {e}, exit {x}"
        if read != expected:
            defects.append(f"{label}: {read} (expected {expected})")
        else:
            buckets[expected].append(label)
    for at in ("2026-06-01T12:00:00", "June 1st"):
        label = "--at naive" if "T" in at else "--at malformed"
        for direction in ("entry", "exit"):
            status, printed = run(["access", "--garage", str(garage), "--pass", str(pass_),
                                   "--vehicle", "CAR-1", "--lane", "L1", "--direction", direction,
                                   "--at", at], capsys)
            if status != EXIT_REFUSED_REQUEST:
                defects.append(f"{label} at {direction}: {status} {printed}")
        buckets["entry refuses, exit refuses"].append(label)
    print("\nBUCKETS: " + "; ".join(f"{k}: {len(v)}" for k, v in buckets.items())
          + f"; defects: {len(defects)}")
    assert defects == [], "\n".join(defects)
    assert len(buckets["entry refuses, exit answers"]) >= 50
    assert sorted(buckets["entry refuses, exit refuses"]) == sorted(NO_RECORD_OR_NO_INSTANT)


@pytest.mark.guarantee("G4")
def test_the_exit_answer_on_unreadable_records_has_every_exit_answers_shape():
    from garage_pass.access import exit_on_unreadable_records
    from garage_pass.findings import Unreadable

    marker = Unreadable(f.REFUSAL_FIELD_BLANK, "registration[0].vehicle_identity", "is required.")
    answer = exit_on_unreadable_records([marker], vehicle_identity=" CAR-1 ", lane="L1")
    assert answer.outcome.value == "not_covered" and answer.reason == f.RECORD_UNREADABLE
    assert answer.exit_note == f.EXIT_IS_NEVER_REFUSED and answer.means == f.MEANS_EXIT_OUT_OF_TERMS
    assert answer.vehicle_identity == "CAR-1" and answer.direction.value == "exit"
    assert "registration[0].vehicle_identity" in answer.detail and answer.missing is None
    for bad in (dict(vehicle_identity=None, lane="L1"), dict(vehicle_identity="C", lane=1)):
        with pytest.raises(TypeError):
            exit_on_unreadable_records([marker], **bad)
    with pytest.raises(TypeError):
        exit_on_unreadable_records([], vehicle_identity="C", lane="L1")


# ---------------------------------------------------------------------------
# The T round: the sentence the operator reads, and the boundary that let a
# document through unread (a pipe that hangs; an empty path read as "not given").
# ---------------------------------------------------------------------------

BOUND_SECONDS = 10  #: a call that has not returned by then is a HANG, and a failure


def _process(argv: list[str]) -> subprocess.CompletedProcess:
    """The actual process, under a bound. A command line that never returns is the
    purest unanswered exit, and it is not a traceback, so no sweep that counts
    tracebacks sees it; this is where it is counted."""
    try:
        return subprocess.run(
            [sys.executable, "-m", "garage_pass.cli", *argv],
            capture_output=True, text=True, cwd=ROOT, timeout=BOUND_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"the command line HUNG: no return within {BOUND_SECONDS}s for {argv[:4]}")


def _process_capped(
    argv: list[str], seconds: float, address_space: int
) -> subprocess.CompletedProcess:
    """``_process`` for a shape whose failure mode is UNBOUNDED GROWTH, not a
    quiet block: a shorter bound, the child's address space capped where the
    system enforces ``RLIMIT_AS`` (Linux does; a Mac accepts and ignores it),
    and on the bound the child is killed and not waited for."""
    import resource

    def cap() -> None:
        try:
            resource.setrlimit(resource.RLIMIT_AS, (address_space, address_space))
        except (ValueError, OSError):
            pass  # the system does not take the cap; the bound below still holds

    process = subprocess.Popen(
        [sys.executable, "-m", "garage_pass.cli", *argv],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT,
        stdin=subprocess.DEVNULL, preexec_fn=cap,
    )
    try:
        out, err = process.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        pytest.fail(f"the command line HUNG: no return within {seconds}s for {argv[:4]}")
    return subprocess.CompletedProcess(process.args, process.returncode, out, err)


def _argv(garage: Path, pass_: Path, **documents: Path | str) -> list[str]:
    out = ["access", "--garage", str(garage), "--pass", str(pass_)]
    for option, path in documents.items():
        out += [f"--{option}", str(path)]
    return out


@pytest.mark.guarantee("G4")
def test_the_unreadable_pass_detail_says_carries_on_both_doors_never_stored(tmp_path, capsys):
    """THE SENTENCE THE OPERATOR READS. The PASS_UNREADABLE answer's detail is what
    the registry tells the operator to use to "find the row and undo the charge".
    Measured before this: on a pass DOCUMENT handed to the command line -- a
    route where nothing is stored -- 66 of 199 answered exits in the gate's
    census said the pass "is stored with a value this module refuses to read",
    the falsehood the registry sentence had already been corrected for, at its
    other end. ONE string feeds both doors, so it must be true at both: it says
    "carries", and the stored-row door (the shape ``records._pass_from_row``
    builds) renders the SAME sentence."""
    garage, pass_ = _documents(tmp_path)
    bad = _write(tmp_path, "p_bad.json", _with(pass_document(), "terms.allowed_lanes", []))
    regs = _write(tmp_path, "r.json", [REGISTRATION])
    status, printed = run([*_argv(garage, bad, registrations=regs),
                           "--vehicle", "CAR-1", "--lane", "L1", "--direction", "exit",
                           "--at", "2026-06-01T12:00:00-06:00"], capsys)
    _assert_exit_answered(status, printed, f.PASS_UNREADABLE, "pass-1",
                          f.REFUSAL_LANES_STATED_BUT_EMPTY)
    assert "stored" not in printed["detail"], (
        f"a DOCUMENT route rendered 'stored' -- nothing is stored: {printed['detail']!r}"
    )
    assert "carries a value this module refuses to read" in printed["detail"], printed["detail"]
    # the other door: the carrier a stored row becomes (holder=None, terms=None, the marker)
    from datetime import UTC, datetime

    from fixtures import transient_garage
    from garage_pass.access import access
    from garage_pass.findings import Unreadable
    from garage_pass.passes import Pass, Registration, State
    from garage_pass.terms import Direction

    stored = Pass(id="pass-1", garage_ids={"garage-downtown"}, label="Employee", holder=None,
                  terms=None, state=State.ACTIVE,
                  unreadable=Unreadable(f.REFUSAL_LANES_STATED_BUT_EMPTY, "allowed_lanes",
                                        "allowed_lanes is an empty set."))
    answer = access(garage=transient_garage("America/Denver"), passes=[stored],
                    registrations=[Registration(pass_id="pass-1", vehicle_identity="CAR-1",
                                                effective_day=REGISTRATION_DAY)],
                    visits=[], vehicle_identity="CAR-1", lane="L1", direction=Direction.EXIT,
                    at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC))
    assert answer.reason == f.PASS_UNREADABLE
    assert "carries a value this module refuses to read" in answer.detail, answer.detail
    assert answer.detail.split(" -- ")[0] == printed["detail"].split(" -- ")[0], (
        "the two doors render different sentences", answer.detail, printed["detail"]
    )


REGISTRATION_DAY = __import__("datetime").date(2026, 1, 1)


@pytest.mark.guarantee("G4")
def test_pass_unreadable_names_every_door_the_load_can_open(tmp_path, capsys):
    """DERIVED, NOT LISTED FROM A BRIEF. What can set ``Pass.unreadable`` with the
    carrier fields readable is every ``Refused`` ``documents.load`` raises for a
    pass: an unknown key (``_only``), a missing or wrong-typed holder/terms field
    (the type checks), and the dataclasses' own validators (the creation-time
    refusals). Each is handed in as a document at an EXIT here, must answer
    PASS_UNREADABLE naming its code, and the registry sentence must name the
    CLASS it belongs to -- so the sentence cannot say "terms or a holder" while
    an unknown field reaches the same reason (measured before this: it did)."""
    garage, pass_ = _documents(tmp_path)
    regs = _write(tmp_path, "r.json", [REGISTRATION])
    doors = {
        "an unknown field": (_with(pass_document(), "x", 1), f.REFUSAL_UNKNOWN_FIELD,
                             "does not know"),
        "a missing holder field": (_with(pass_document(), "holder.email", ...),
                                   f.REFUSAL_FIELD_BLANK, "missing"),
        "a wrong-typed terms field": (_with(pass_document(), "terms.max_stay_minutes", "ten"),
                                      f.REFUSAL_FIELD_WRONG_TYPE, "wrong type"),
        "a validator's refusal": (_with(pass_document(), "terms.allowed_lanes", []),
                                  f.REFUSAL_LANES_STATED_BUT_EMPTY, "refused at creation"),
    }
    sentence = f.NOT_COVERED_REASONS[f.PASS_UNREADABLE]
    for door, (document, code, phrase) in doors.items():
        path = _write(tmp_path, "p.json", document)
        status, printed = run([*_argv(garage, path, registrations=regs), "--vehicle", "CAR-1",
                               "--lane", "L1", "--direction", "exit",
                               "--at", "2026-06-01T12:00:00-06:00"], capsys)
        _assert_exit_answered(status, printed, f.PASS_UNREADABLE, code)
        assert phrase in sentence, (
            f"{door} reaches PASS_UNREADABLE ({code}) and the sentence does not name it: "
            f"{sentence!r}"
        )


@pytest.mark.guarantee("G18")
@pytest.mark.parametrize("option", ["garage", "pass", "registrations", "visits"])
def test_a_named_pipe_with_no_writer_is_refused_by_name_under_a_bound(tmp_path, option):
    """Measured before this: ``open()`` on a FIFO with no writer blocked forever,
    on all four document arguments, in both directions -- the command line never
    returned. Not a traceback, so every sweep that counts tracebacks read it
    clean. Now anything that is not a regular file is refused BEFORE the read,
    by name, the same refusal a missing file gets; and this test runs the actual
    process UNDER A BOUND so a regression is a failure, not a hung suite."""
    garage, pass_ = _documents(tmp_path)
    fifo = tmp_path / "a_fifo"
    __import__("os").mkfifo(fifo)
    docs = {"garage": garage, "pass": pass_,
            "registrations": _write(tmp_path, "r.json", [REGISTRATION]),
            "visits": _write(tmp_path, "v.json", [])}
    docs[option] = fifo
    for direction in ("entry", "exit"):
        done = _process([*_argv(docs["garage"], docs["pass"], registrations=docs["registrations"],
                                visits=docs["visits"]), "--vehicle", "CAR-1", "--lane", "L1",
                         "--direction", direction, "--at", "2026-06-01T12:00:00-06:00"])
        assert done.returncode == EXIT_REFUSED_REQUEST and done.stderr == "", (
            option, direction, done.returncode, done.stderr[-300:]
        )
        printed = json.loads(done.stdout)
        assert printed["refused"] == f.REFUSAL_DOCUMENT_UNREADABLE
        assert printed["field"] == f"--{option}" and "not a regular file" in printed["detail"]


@pytest.mark.guarantee("G18")
def test_the_regular_file_guard_keeps_a_symlink_and_refuses_a_device_a_socket_and_a_directory(
    tmp_path, capsys
):
    """The controls for the guard above, in one run: ``os.open`` follows
    symlinks, so a symlink to a regular file STILL READS (breaking that would be
    worse than the hang); a device and a directory open and are refused by
    ``S_ISREG`` on the descriptor before any read, naming the shape -- the
    device (``/dev/null``) used to be refused for reading as empty; a unix
    socket cannot be opened at all (``ENXIO`` on Linux, ``EOPNOTSUPP`` on a Mac)
    and is refused with the system's own text -- the SAME code for all three;
    and the well-formed call still answers covered."""
    import socket

    garage, pass_ = _documents(tmp_path)
    regs = _write(tmp_path, "r.json", [REGISTRATION])
    link = tmp_path / "link_to_pass.json"
    link.symlink_to(pass_)
    for direction in ("entry", "exit"):
        status, printed = run([*_argv(garage, link, registrations=regs), "--vehicle", "CAR-1",
                               "--lane", "L1", "--direction", direction,
                               "--at", "2026-06-01T12:00:00-06:00"], capsys)
        assert status == 0 and printed["outcome"] == "covered", (direction, status, printed)
    a_dir = tmp_path / "a_dir"
    a_dir.mkdir()
    # a unix socket's path is bounded (~104 bytes on a Mac), and pytest's tmp_path
    # is longer than that; a short directory of our own, removed after
    import shutil
    import tempfile

    short = Path(tempfile.mkdtemp(prefix="gp", dir="/tmp"))
    sock_path = short / "s"
    sock = socket.socket(socket.AF_UNIX)
    sock.bind(str(sock_path))
    try:
        for name, bad in (("a device", Path("/dev/null")), ("a socket", sock_path),
                          ("a directory", a_dir)):
            status, printed = run([*_argv(bad, pass_, registrations=regs), "--vehicle", "CAR-1",
                                   "--lane", "L1", "--direction", "exit",
                                   "--at", "2026-06-01T12:00:00-06:00"], capsys)
            assert status == EXIT_REFUSED_REQUEST, (name, status, printed)
            assert printed["refused"] == f.REFUSAL_DOCUMENT_UNREADABLE
            assert printed["field"] == "--garage"
            if name == "a socket":  # refused by the open itself, before any fstat
                assert "could not be read: " in printed["detail"], (name, printed["detail"])
                assert "not a regular file" not in printed["detail"], (name, printed["detail"])
            else:
                assert "not a regular file" in printed["detail"], (name, printed["detail"])
    finally:
        sock.close()
        shutil.rmtree(short, ignore_errors=True)
    status, printed = run([*_argv(garage, tmp_path / "nowhere.json", registrations=regs),
                           "--vehicle", "CAR-1", "--lane", "L1", "--direction", "exit",
                           "--at", "2026-06-01T12:00:00-06:00"], capsys)
    assert status == EXIT_REFUSED_REQUEST and "does not exist" in printed["detail"], printed
    # a path past NAME_MAX: os.open raises ENAMETOOLONG -- measured as 16 tracebacks of 432
    # when the guard stood outside the try; it is a refusal like the rest
    too_long = tmp_path / ("x" * 300 + ".json")
    status, printed = run([*_argv(garage, too_long, registrations=regs),
                           "--vehicle", "CAR-1", "--lane", "L1", "--direction", "exit",
                           "--at", "2026-06-01T12:00:00-06:00"], capsys)
    assert status == EXIT_REFUSED_REQUEST and printed["refused"] == f.REFUSAL_DOCUMENT_UNREADABLE


@pytest.mark.guarantee("G18")
@pytest.mark.parametrize("option", ["garage", "pass", "registrations", "visits"])
def test_a_device_that_never_stops_producing_bytes_is_refused_by_name_under_a_bound(
    tmp_path, option
):
    """THE FAIL-CONTROL FOR THE REGULAR-FILE CHECK ON THE DESCRIPTOR. With the
    boundary opening ``O_NONBLOCK`` and reading the descriptor, a pipe with no
    writer can no longer hang it even with the ``S_ISREG`` check gone -- the
    read returns EOF, the empty text is not JSON, the document is refused for
    the wrong reason and every test built on the pipe stays green. What the
    check now stands between the caller and is a device that PRODUCES bytes
    without end: ``/dev/zero`` read to EOF never returns. So this is the shape
    that goes red -- as a HANG under the bound, in the actual process -- when
    the ``S_ISREG`` check is planted away, on all four document arguments in
    both directions; with the check in place it is refused by name, the same
    code and the same sentence as a directory or a pipe.

    THE COST WHEN IT FIRES IS BOUNDED ON PURPOSE. A child reading ``/dev/zero``
    to EOF grows without limit for as long as it is allowed to run, and a Mac
    compresses the all-zero pages, so a generous bound is minutes of kernel
    teardown after the kill (measured: the 10 s bound stalled the runner). So
    this shape runs under a 2 s bound, the child's address space is capped
    where the system enforces a cap (Linux; a Mac accepts the limit and does
    not enforce it), and a child that did not return is killed and NOT waited
    for -- the failure is asserted, the teardown is the kernel's business."""
    garage, pass_ = _documents(tmp_path)
    docs = {"garage": garage, "pass": pass_,
            "registrations": _write(tmp_path, "r.json", [REGISTRATION]),
            "visits": _write(tmp_path, "v.json", [])}
    docs[option] = Path("/dev/zero")
    for direction in ("entry", "exit"):
        done = _process_capped(
            [*_argv(docs["garage"], docs["pass"], registrations=docs["registrations"],
                    visits=docs["visits"]), "--vehicle", "CAR-1", "--lane", "L1",
             "--direction", direction, "--at", "2026-06-01T12:00:00-06:00"],
            seconds=2.0, address_space=512 * 1024 * 1024,
        )
        assert done.returncode == EXIT_REFUSED_REQUEST and done.stderr == "", (
            option, direction, done.returncode, done.stderr[-300:]
        )
        printed = json.loads(done.stdout)
        assert printed["refused"] == f.REFUSAL_DOCUMENT_UNREADABLE
        assert printed["field"] == f"--{option}" and "not a regular file" in printed["detail"]


@pytest.mark.guarantee("G18")
@pytest.mark.parametrize("option", ["garage", "pass", "registrations", "visits"])
def test_the_bytes_decoded_come_from_the_descriptor_that_was_checked_never_from_the_name(
    tmp_path, capsys, monkeypatch, option
):
    """THE CHECK AND THE READ ARE THE SAME FILE -- proven deterministically, not
    by racing. Measured before this: the boundary asked ``Path(path).is_file()``
    and then called ``open(path)``: two resolutions of one name, and a writer
    swapping a regular file for a pipe between them put the command line back
    into the blocking ``open()`` -- 3 hangs in 620,000 racing calls. A race
    harness reading zero cannot tell fixed from lucky. This can: every
    NAME-based way of opening a file is made to raise for the duration of the
    call -- ``builtins.open`` / ``io.open`` handed a path, ``Path.open``,
    ``Path.read_text``, ``Path.read_bytes`` -- while an open handed a
    DESCRIPTOR (an ``int``) is let through. The documents must still read and
    the call must still answer covered on all four document arguments in both
    directions. Control in the same run: with the patch in place, a direct
    ``Path.read_text`` on the garage document raises -- the patch is live."""
    import builtins
    import io

    real_open = builtins.open

    def only_descriptors(file, *args, **kwargs):
        if isinstance(file, int):
            return real_open(file, *args, **kwargs)
        raise AssertionError(f"a NAME-based open on the document path: open({file!r})")

    def never(self, *args, **kwargs):
        raise AssertionError(f"a NAME-based read on the document path: {self!r}")

    garage, pass_ = _documents(tmp_path)
    regs = _write(tmp_path, "r.json", [REGISTRATION])
    visits = _write(tmp_path, "v.json", [])
    monkeypatch.setattr(builtins, "open", only_descriptors)
    monkeypatch.setattr(io, "open", only_descriptors)
    monkeypatch.setattr(Path, "open", never)
    monkeypatch.setattr(Path, "read_text", never)
    monkeypatch.setattr(Path, "read_bytes", never)
    with pytest.raises(AssertionError, match="NAME-based"):  # the control: the patch is live
        Path(garage).read_text()
    # the option under test is the one handed in LAST, so every option's read is exercised
    docs = {"garage": garage, "pass": pass_, "registrations": regs, "visits": visits}
    assert option in docs
    for direction in ("entry", "exit"):
        status, printed = run([*_argv(docs["garage"], docs["pass"],
                                      registrations=docs["registrations"], visits=docs["visits"]),
                               "--vehicle", "CAR-1", "--lane", "L1", "--direction", direction,
                               "--at", "2026-06-01T12:00:00-06:00"], capsys)
        assert status == 0 and printed["outcome"] == "covered", (option, direction, status, printed)


@pytest.mark.guarantee("G18")
def test_the_descriptor_is_closed_on_every_path_out_refusals_included(tmp_path, capsys):
    """A leaked descriptor is a defect of the same family as the hang, and the
    command line opens up to four documents per call. Every shape the boundary
    meets -- a regular file that reads, a directory, a device, a missing path,
    a file that is not JSON, a file that is not text -- is handed in as every
    document argument, and the number of open descriptors in this process is
    the same after as before. Control in the same run: one descriptor opened
    and deliberately not closed moves the count by one, so the count can see a
    leak of one."""
    import os

    def open_fds() -> int:
        return len(os.listdir("/dev/fd"))

    garage, pass_ = _documents(tmp_path)
    regs = _write(tmp_path, "r.json", [REGISTRATION])
    not_json = tmp_path / "not.json"
    not_json.write_text("{not json")
    not_text = tmp_path / "bytes.json"
    not_text.write_bytes(b"\xff\xfe\x00\x00")
    shapes = [garage, tmp_path, Path("/dev/null"), tmp_path / "nowhere.json", not_json, not_text]
    before = open_fds()
    for bad in shapes:
        for option in ("garage", "pass", "registrations", "visits"):
            docs = {"garage": garage, "pass": pass_, "registrations": regs,
                    "visits": _write(tmp_path, "v.json", [])}
            docs[option] = bad
            run([*_argv(docs["garage"], docs["pass"], registrations=docs["registrations"],
                        visits=docs["visits"]), "--vehicle", "CAR-1", "--lane", "L1",
                 "--direction", "exit", "--at", "2026-06-01T12:00:00-06:00"], capsys)
    assert open_fds() == before, (before, open_fds())
    leak = os.open(garage, os.O_RDONLY)  # the control: one descriptor left open is visible
    try:
        assert open_fds() == before + 1
    finally:
        os.close(leak)


@pytest.mark.guarantee("G18")
def test_an_empty_option_value_is_a_path_that_cannot_be_read_not_an_option_not_given(
    tmp_path, capsys
):
    """Measured before this: ``--visits ''`` and ``--registrations ''`` were read as
    "not given" -- ``if args.visits`` read the empty string as falsy and the
    document was never opened. Now the test is ``is None``: an empty string is a
    path (``.``, a directory) and is refused by name in both directions, on both
    list options; omitting the option still means "not given" and still answers.
    THE SHAPE OF THE REFUSAL ONLY -- what dropping the document unread does to
    the ANSWER is the next test's question, on its own, so that under a plant it
    is the assertion about the answer that reddens and not this one."""
    garage, pass_ = _documents(tmp_path)
    regs = _write(tmp_path, "r.json", [REGISTRATION])
    for option in ("registrations", "visits"):
        for direction in ("entry", "exit"):
            argv = [*_argv(garage, pass_, registrations=regs), f"--{option}", "",
                    "--vehicle", "CAR-1", "--lane", "L1", "--direction", direction,
                    "--at", "2026-06-01T12:00:00-06:00"]
            status, printed = run(argv, capsys)
            assert status == EXIT_REFUSED_REQUEST, (
                f"--{option} '' at {direction} was read as 'not given': exit {status}, {printed}"
            )
            assert printed["refused"] == f.REFUSAL_DOCUMENT_UNREADABLE
            assert printed["field"] == f"--{option}"
    move = ["--vehicle", "CAR-1", "--lane", "L1", "--direction", "entry",
            "--at", "2026-06-01T12:00:00-06:00"]
    status, printed = run([*_argv(garage, pass_, registrations=regs), *move], capsys)
    assert status == 0 and printed["outcome"] == "covered", ("omitted must still answer", printed)


#: The visits document that changes the answer at each door, and the reason it changes it to:
#: at an ENTRY the allowance (3 per window) spent by three entries today; at an EXIT an open
#: entry eleven hours before the exit against a maximum stay of ten. Both are read from the
#: visits; both vanish if the visits document is dropped unread.
_SPENT_ALLOWANCE = [
    {"pass_id": "pass-1", "garage_id": "garage-downtown", "vehicle_identity": "CAR-1",
     "entry_lane": "L1", "entered_at": f"2026-06-01T0{h}:00:00-06:00",
     "exited_at": f"2026-06-01T0{h}:30:00-06:00", "exit_lane": "L1"} for h in (7, 8, 9)
]
_OPEN_ENTRY_PAST_MAX_STAY = [
    {"pass_id": "pass-1", "garage_id": "garage-downtown", "vehicle_identity": "CAR-1",
     "entry_lane": "L1", "entered_at": "2026-06-01T01:00:00-06:00"},
]


@pytest.mark.guarantee("G18")
@pytest.mark.parametrize(
    "direction,visits,reason",
    [("entry", _SPENT_ALLOWANCE, "OUT_OF_VISITS"),
     ("exit", _OPEN_ENTRY_PAST_MAX_STAY, "OVER_MAX_STAY")],
    ids=["entry-spent-allowance", "exit-over-max-stay"],
)
def test_an_empty_visits_option_never_answers_covered_on_visits_it_did_not_read(
    tmp_path, capsys, direction, visits, reason
):
    """THE SILENT WRONG ANSWER, ON ITS OWN, AT BOTH DOORS. Visits are the evidence
    for the visit allowance and the maximum stay; a boundary that drops the visits
    document unread turns an over-allowance or an over-stay into COVERED -- which
    this project ranks above a traceback. Measured before this: ``--visits ''``
    answered covered with the visits silently unread. The control that proves the
    wrong-answer shape is gone: with the visits document handed in, the answer is
    not-covered for the reason the visits carry; the SAME case with ``--visits ''``
    must NOT read covered -- asserted FIRST, so that under a plant of the
    truthiness test this is the red, naming the covered answer -- and is refused
    naming the option. Measured before this round: the previous test carried this
    assertion after its refusal-shape loop, which any such plant reddens first, so
    the assertion about the answer could never be the one that fired."""
    garage, pass_ = _documents(tmp_path)
    regs = _write(tmp_path, "r.json", [REGISTRATION])
    visits_document = _write(tmp_path, "visits.json", visits)
    move = ["--vehicle", "CAR-1", "--lane", "L1", "--direction", direction,
            "--at", "2026-06-01T12:00:00-06:00"]
    status, printed = run([*_argv(garage, pass_, registrations=regs, visits=visits_document),
                           *move], capsys)
    assert status == 1 and printed["reason"] == getattr(f, reason), printed
    status, printed = run([*_argv(garage, pass_, registrations=regs), "--visits", "", *move],
                          capsys)
    assert printed.get("outcome") != "covered", (
        f"--visits '' at {direction} dropped the visits document unread and answered COVERED "
        f"where the visits say {reason}: {printed}"
    )
    assert status == EXIT_REFUSED_REQUEST and printed["field"] == "--visits", printed
