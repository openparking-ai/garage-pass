"""G16 -- no test module sits outside the guarantee registry.

**THE HOLE THIS CLOSES.** `conftest.py` fails a run when a REGISTERED GUARANTEE
did not run and pass. That is a set comparison over guarantee ids, so it is blind
to a test module that registers nothing at all: skip it, delete it, or let it
stop collecting, and every gate stays green because no id went missing.

In the sibling module this guard is copied from, two modules were in exactly
that position -- 16 tests carrying the anti-prose controls and the fixture
controls -- and a review skipped one at module level with the suite reporting
green. Another sibling shipped 21 tests outside both guards.

Registering those modules by hand fixes today. **This fixes tomorrow, and it is
DERIVED**: the module set comes off the filesystem and the marks come out of the
AST, so a file that arrives next round cannot arrive unnoticed.

**READ WITH THE AST, NEVER WITH A REGEX.** This file writes
`@pytest.mark.guarantee(...)` inside the string literal it plants below. A text
scan would count that as a mark on THIS module and report it guarded whatever its
real decorators said -- a check measuring the word instead of the shape, which is
the failure this project keeps cataloguing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from _guarantees import GUARANTEES
from store_harness import store_test

ROOT = Path(__file__).resolve().parent.parent

#: Modules deliberately contributing no guarantee. EMPTY, and an entry here is a
#: decision somebody writes down -- the same shape as ALLOW_ENV, for the same
#: reason. A module that PLANTS may not be listed: see the second rule below.
UNGUARANTEED_MODULES: frozenset[str] = frozenset()


def _declared_guarantee_ids(tree: ast.AST) -> set[str]:
    """The ids on real `@pytest.mark.guarantee(...)` DECORATORS in one module."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            if call is None or not isinstance(call.func, ast.Attribute):
                continue
            if call.func.attr != "guarantee":
                continue
            found |= {
                arg.value
                for arg in call.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            }
    return found


def _imports_the_plant_helper(tree: ast.AST) -> bool:
    """Does this module import `planted` -- i.e. does it break source on purpose?"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "plant":
            if any(alias.name == "planted" for alias in node.names):
                return True
    return False


def _test_modules() -> dict[str, ast.AST]:
    """Derived from the filesystem, so a new file is in the set the day it lands."""
    return {
        path.name: ast.parse(path.read_text())
        for path in sorted((ROOT / "tests").glob("test_*.py"))
    }


def unguarded_modules() -> dict[str, str]:
    """Every test module no registered guarantee names, and why that is wrong.

    1. A test module contributes at least one registered guarantee, or is named
       in UNGUARANTEED_MODULES.
    2. **A module that PLANTS a defect must contribute one, with no allowance.**
       Going to the trouble of breaking source on purpose means producing
       evidence, and evidence nothing names is evidence nothing protects.
    """
    problems: dict[str, str] = {}
    for name, tree in _test_modules().items():
        ids = _declared_guarantee_ids(tree)
        unknown = sorted(ids - set(GUARANTEES))
        if unknown:
            problems[name] = f"claims unregistered guarantee id(s): {', '.join(unknown)}"
        elif ids:
            continue
        elif _imports_the_plant_helper(tree):
            problems[name] = (
                "plants a defect but registers no guarantee, and a planting module "
                "may not be excused -- delete it and the suite stays green while a "
                "control silently stops existing"
            )
        elif name not in UNGUARANTEED_MODULES:
            problems[name] = (
                "carries no @pytest.mark.guarantee, so deleting or skipping it leaves "
                "the suite green and this guard silent"
            )
    return problems


@pytest.mark.guarantee("G16")
def test_the_module_scan_is_pointed_at_a_real_set():
    """The control on the denominator. An empty scan reports every module guarded."""
    modules = _test_modules()
    assert len(modules) >= 12, f"the scan found only {len(modules)} test modules"
    assert "test_g7_the_garages_local_day.py" in modules
    assert Path(__file__).name in modules, "this module is outside its own scan"


@pytest.mark.guarantee("G16")
def test_every_test_module_contributes_a_registered_guarantee():
    problems = unguarded_modules()
    assert not problems, "test modules outside both guards:\n  " + "\n  ".join(
        f"{name}: {why}" for name, why in sorted(problems.items())
    )


@pytest.mark.guarantee("G16")
def test_a_module_that_registers_nothing_is_REFUSED():
    """THE FAIL-CONTROL, and it plants a real file in the real `tests/` tree.

    Not a temp directory: the guard reads `tests/` off the filesystem, so a
    control pointed at a copy would prove the derivation works somewhere the
    derivation never runs. Restored in a `finally`, from the bytes written --
    never `git checkout`.
    """
    intruder = ROOT / "tests" / "test_zz_planted_intruder.py"
    assert not intruder.exists(), "the intruder path is already occupied"
    body = (
        '"""A module with no mark at all, which is what this control is."""\n\n\n'
        "def test_it_registers_no_guarantee():\n"
        "    assert True\n"
    )
    try:
        intruder.write_text(body)
        problems = unguarded_modules()
        assert intruder.name in problems, (
            "a module registering no guarantee was accepted, so the hole that hid "
            "16 tests here and 21 in a sibling repository is still open"
        )
        assert "no @pytest.mark.guarantee" in problems[intruder.name]
    finally:
        intruder.unlink(missing_ok=True)
    assert not intruder.exists(), "the planted intruder was not removed"


@pytest.mark.guarantee("G16")
def test_a_module_LEGITIMATELY_outside_the_set_is_not_flagged():
    """The other arm, without which this guard is a rule nobody can satisfy.

    A guard that flags every module whatever the allowance says is not deriving
    anything -- it is refusing unconditionally, and the first person to meet it
    widens it until it stops working. So: a non-planting module named in
    UNGUARANTEED_MODULES is accepted, and the SAME module is flagged the moment
    the allowance is taken away.
    """
    intruder = ROOT / "tests" / "test_zz_planted_allowed.py"
    assert not intruder.exists(), "the intruder path is already occupied"
    body = (
        '"""A module with no mark, named in the allowance."""\n\n\n'
        "def test_it_registers_no_guarantee():\n"
        "    assert True\n"
    )
    try:
        intruder.write_text(body)
        assert intruder.name in unguarded_modules(), (
            "the control is degenerate: this module is not flagged even unallowed"
        )

        import test_guarantee_guard as self_module

        original = self_module.UNGUARANTEED_MODULES
        try:
            self_module.UNGUARANTEED_MODULES = frozenset({intruder.name})
            assert intruder.name not in unguarded_modules(), (
                "a non-planting module named in UNGUARANTEED_MODULES was still "
                "flagged, so the allowance does not work and the guard is a rule "
                "nobody can satisfy"
            )
        finally:
            self_module.UNGUARANTEED_MODULES = original
    finally:
        intruder.unlink(missing_ok=True)
    assert not intruder.exists(), "the planted intruder was not removed"


@pytest.mark.guarantee("G16")
def test_a_module_that_PLANTS_and_registers_nothing_cannot_be_excused():
    """Rule 2 has no escape hatch, and the allowance may not buy one out."""
    intruder = ROOT / "tests" / "test_zz_planted_planter.py"
    assert not intruder.exists(), "the intruder path is already occupied"
    body = (
        "from plant import planted\n\n\n"
        "def test_it_plants_but_names_no_guarantee():\n"
        "    with planted('access.py', 'def access(', 'def access('):\n"
        "        pass\n"
    )
    try:
        intruder.write_text(body)
        assert "may not be excused" in unguarded_modules()[intruder.name]

        import test_guarantee_guard as self_module

        original = self_module.UNGUARANTEED_MODULES
        try:
            self_module.UNGUARANTEED_MODULES = frozenset({intruder.name})
            assert intruder.name in unguarded_modules(), (
                "naming a PLANTING module in UNGUARANTEED_MODULES excused it; the "
                "allowance must not reach rule 2"
            )
        finally:
            self_module.UNGUARANTEED_MODULES = original
    finally:
        intruder.unlink(missing_ok=True)
    assert not intruder.exists(), "the planted intruder was not removed"


@pytest.mark.guarantee("G16")
def test_a_mark_naming_an_unregistered_id_is_REFUSED():
    """The reverse direction: a module claiming a guarantee nobody registered.

    `conftest.py` catches this at collection for ids it can see; this catches it
    from the AST, so it holds for a module that never collects.
    """
    intruder = ROOT / "tests" / "test_zz_planted_unknown_id.py"
    assert not intruder.exists(), "the intruder path is already occupied"
    body = (
        "import pytest\n\n\n"
        '@pytest.mark.guarantee("NOT_IN_THE_REGISTRY")\n'
        "def test_it_claims_an_id_nobody_registered():\n"
        "    assert True\n"
    )
    try:
        intruder.write_text(body)
        assert "NOT_IN_THE_REGISTRY" in unguarded_modules()[intruder.name]
    finally:
        intruder.unlink(missing_ok=True)
    assert not intruder.exists(), "the planted intruder was not removed"


@pytest.mark.guarantee("G16")
def test_the_run_guard_fails_a_full_run_with_an_unrun_guarantee_unless_allowed(monkeypatch):
    """The other half of G16: a REGISTERED guarantee that did not run and pass
    fails the whole run, unless its id is named in the written-down allowance.
    Exercised against the hook itself with a stand-in session, so the plant
    that neuters the hook is caught without running the whole suite twice."""
    import conftest

    class Option:
        keyword = ""
        markexpr = ""

    class Config:
        option = Option()
        args = []

        @staticmethod
        def getini(name):
            return ["tests"]

    class Session:
        config = Config()
        exitstatus = 0

    missing = sorted(GUARANTEES)[-1]
    monkeypatch.setattr(conftest, "_ran", set(GUARANTEES) - {missing})
    monkeypatch.setattr(conftest, "_skipped", {})  # this run's real skips are not the subject
    monkeypatch.delenv(conftest.ALLOW_ENV, raising=False)
    session = Session()
    conftest.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 1, f"{missing} did not run and the run stayed green"

    allowed = Session()
    monkeypatch.setenv(conftest.ALLOW_ENV, missing)
    conftest.pytest_sessionfinish(allowed, 0)
    assert allowed.exitstatus == 0, "the written-down allowance did not work"

    complete = Session()
    monkeypatch.setattr(conftest, "_ran", set(GUARANTEES))
    monkeypatch.setattr(conftest, "_skipped", {})
    monkeypatch.delenv(conftest.ALLOW_ENV, raising=False)
    conftest.pytest_sessionfinish(complete, 0)
    assert complete.exitstatus == 0
    # THE SUMMARY NAMES THE FAILURE. A guard that only set the exit status
    # printed its block and watched "N passed" go by underneath: the run exited
    # 1 while its last line read green (measured at the L3 of the enrolment
    # round). The failed session carries what the summary must say; the clean
    # ones carry nothing; and the terminal summary hook writes it as a red
    # separator AND as its own counted kind in the count line.
    import _rendered_sentences as rendered

    assert not hasattr(complete, rendered.SUMMARY_FAILURES)
    assert not hasattr(allowed, rendered.SUMMARY_FAILURES)
    (key, block), = getattr(session, rendered.SUMMARY_FAILURES)
    assert key == "guarantee-guard failure" and missing in block

    class Reporter:
        _session = session
        stats: dict = {"passed": [object()] * 3}
        lines: list = []

        def write_sep(self, sep, title, **markup):
            self.lines.append((sep, title, markup))

        def write_line(self, line, **markup):
            self.lines.append(("", line, markup))

    reporter = Reporter()
    rendered.pytest_terminal_summary(reporter, 0, session.config)
    assert reporter.lines[0][1] == "GUARANTEE-GUARD FAILURE -- this run exits 1"
    assert reporter.lines[0][2].get("red") is True
    assert missing in reporter.lines[1][1]
    assert len(reporter.stats["guarantee-guard failure"]) == 1, "counted in the last line"
    assert reporter.stats["guarantee-guard failure"][0].count_towards_summary is True


@pytest.mark.guarantee("G16")
def test_the_run_guard_names_every_guarantee_that_did_not_run_in_full(monkeypatch, capsys):
    """A guarantee with SOME tests skipped ran and passed -- and is not
    covered. The report names it, with the count, beside the ones with no
    passing test. Measured before: with no database the report named two
    guarantees while five more had skipped tests, and a receipt copied the
    wrong list off it."""
    import conftest

    class Option:
        keyword = ""
        markexpr = ""

    class Config:
        option = Option()
        args = []

        @staticmethod
        def getini(name):
            return ["tests"]

    class Session:
        config = Config()
        exitstatus = 0

    ids = sorted(GUARANTEES, key=lambda g: int(g[1:]))
    none_ran, partly = ids[0], ids[1]
    monkeypatch.setattr(conftest, "_ran", set(GUARANTEES) - {none_ran})
    monkeypatch.setattr(conftest, "_skipped", {partly: 3, none_ran: 15})
    monkeypatch.setattr(conftest, "_collected", {partly: 10, none_ran: 15})
    monkeypatch.delenv(conftest.ALLOW_ENV, raising=False)
    session = Session()
    conftest.pytest_sessionfinish(session, 0)
    out = capsys.readouterr().out
    assert session.exitstatus == 1
    assert f"{none_ran}  no test ran and passed (15 of 15 skipped)" in out
    assert f"{partly}  3 of 10 tests skipped" in out
    for other in ids[2:]:
        assert f"    {other}  " not in out, f"{other} ran in full and was named"


@pytest.mark.guarantee("G16")
@store_test
def test_the_controls_runner_refuses_a_control_whose_only_reds_are_exceptions(tmp_path):
    """THE RULE THAT STOPS A THIRD ONE. Three times in this module a control
    reddened on something other than an assertion about its subject: a plant
    that dropped two SQL placeholders, a plant that dereferenced None on the
    next line, and a near-miss where one of six reds was a driver error. The
    runner now reads every red's REASON and refuses a control with no
    assertion red. Exercised against the runner itself: a crashing cut of the
    access call -- the local day planted to None, so every G9 test dies on a
    TypeError before any assertion -- is planted through it and must be
    reported EXCEPTION-ONLY; the shipped, quiet plant must be reported RED
    with assertion reds. The near-miss shape -- assertions plus one other --
    is allowed and reported as such.

    (The L3's own crashing cut -- `if False:` on the None check, the next
    line dereferencing None -- was the example here until the gate-fix round:
    G9's tests now assert `unmeasured is not None` on an entry later than the
    exit, and under that cut the stay is measured negative and that assertion
    reddens beside the AttributeErrors. The test set got better and the old
    cut stopped being exception-only, which is the point of the rule; the
    example moved to a cut that still is.)"""
    import io
    import sys
    from contextlib import redirect_stdout

    sys.path.insert(0, str(ROOT / "scripts"))
    import fail_controls

    crashing = (
        fail_controls.G9, "access.py",
        "    tz = zone(garage.timezone)\n    today = day_of(at, tz)\n",
        "    tz = zone(garage.timezone)\n"
        "    today = None  # PLANTED (a crashing cut): every comparison with the day dies\n",
        "a crashing cut: no test reaches an assertion",
    )
    fail_controls.CONTROLS["G9/crashing-cut"] = crashing
    try:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            fired = fail_controls.run_control("G9/crashing-cut")
        assert fired is False, "a control whose reds are all TypeError counted as fired"
        assert "EXCEPTION-ONLY" in buffer.getvalue() and "TypeError" in buffer.getvalue()
    finally:
        del fail_controls.CONTROLS["G9/crashing-cut"]
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        fired = fail_controls.run_control("G9/missing-entry")
    assert fired is True and "assertion red(s)" in buffer.getvalue(), buffer.getvalue()
    # the classifier itself, on the three shapes it must tell apart
    reasons = fail_controls.failure_reasons(
        "/x/tests/test_a.py:10: AssertionError: assert 1 == 2\n"
        "/x/tests/test_a.py:20: assert 'a' in 'b'\n"
        "/x/tests/test_a.py:30: Failed: DID NOT RAISE Refused\n"
        "/x/src/garage_pass/access.py:334: AttributeError: 'NoneType' object has no attribute 'x'\n"
        "/x/venv/psycopg/cursor.py:117: psycopg.errors.InFailedSqlTransaction: aborted\n"
        "FAILED tests/test_a.py::test_x - AssertionError\n"
    )
    assert [r[1] for r in reasons] == [
        "AssertionError", "assert", "Failed", "AttributeError",
        "psycopg.errors.InFailedSqlTransaction",
    ]
    assert len(fail_controls.assertion_reds(reasons)) == 3
