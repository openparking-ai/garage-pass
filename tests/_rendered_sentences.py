"""THE RENDERED-SENTENCE COLLECTOR -- the second half of the route sweep, as a
pytest plugin (``conftest.py`` registers it and stays the guarantee guard).

What the operator reads is the definition: every ``Answer`` the module builds
(either door -- documents through the command line, rows through the store) and
every ``Refused`` the command line prints, with the package files on the stack
that rendered each. At the end of a FULL run the collected details are judged by
the SAME mechanism as the literal sweep (``scripts/sweep_route_sentences.py``:
same templates, same key, same judgements file, same fail-closed loader): a
route-asserting detail must be a literal that stands in a file on its own
rendering stack -- or a registry value, which is a published sentence wherever
it is rendered -- or the run is red. This is the half a sweep of literals cannot
do -- six run-time spellings of a removed falsehood rendered to the operator and
left the literal sweep green. Collection touches no product code: ``Answer``'s
generated ``__init__`` is wrapped here, and the command line's one
refusal-rendering seam (``cli._refusal``) is wrapped here. Tests that run the
command line as a SUBPROCESS render outside this process and are not collected;
that is a declared limit of the denominator, printed with it.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sweep_route_sentences as sweep  # noqa: E402

_rendered: list[tuple[str, frozenset[str]]] = []


def _package_file(filename: str) -> str | None:
    """``src/garage_pass/…`` for a frame inside the package -- by the path's own
    ``src/garage_pass`` components, so a COPY of the tree (the sweep's self-test
    renders from one) reads the same file names as the tree itself."""
    parts = Path(filename).parts
    for i in range(len(parts) - 2):
        if parts[i] == "src" and parts[i + 1] == "garage_pass":
            return "/".join(parts[i:])
    return None


def _stack_files() -> frozenset[str]:
    return frozenset(f for f in (_package_file(fr.filename)
                                 for fr in traceback.extract_stack()) if f)


def _traceback_files(exc: BaseException) -> frozenset[str]:
    return frozenset(f for f in (_package_file(fr.filename)
                                 for fr in traceback.extract_tb(exc.__traceback__)) if f)


def _install_collector() -> None:
    from garage_pass import cli
    from garage_pass.access import Answer

    original_init = Answer.__init__

    def collecting_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if self.detail:
            _rendered.append((self.detail, _stack_files()))

    Answer.__init__ = collecting_init  # type: ignore[method-assign]
    original_refusal = cli._refusal

    def collecting_refusal(refused):
        rendered = original_refusal(refused)
        # the refusal's own traceback carries the frames that raised it -- the
        # literal that spelled the detail stands in one of them; the render itself
        # happens in cli.py
        files = _traceback_files(refused) | frozenset({"src/garage_pass/cli.py"})
        _rendered.append((rendered["detail"], files))
        return rendered

    cli._refusal = collecting_refusal


def pytest_sessionstart(session):
    _install_collector()


def pytest_sessionfinish(session, exitstatus):
    """The rendered half of the route sweep, over everything this run rendered --
    on a FULL run only, like the guarantee guard: a developer running one file
    has rendered a handful of details, not the module's output."""
    from conftest import _is_a_full_run

    if not _is_a_full_run(session):
        return
    status, result = sweep.judge_rendered(list(_rendered))
    print("\n" + sweep.report_rendered(result)
          + "\n(subprocess runs of the command line render outside this process and are not "
          "in this denominator)")
    if status != 0:
        session.exitstatus = 1


def rendered_so_far() -> list[tuple[str, frozenset[str]]]:
    """The collector's list, for a test that judges a fixed denominator of its own."""
    return _rendered


def render_and_collect(argv: list[str]) -> list[tuple[str, frozenset[str]]]:
    """Run the command line in-process with the collector installed and return
    what it rendered -- for the sweep's own self-test, which renders from a COPY
    of the package in a subprocess with no database and no test session."""
    import contextlib
    import io

    from garage_pass.cli import main

    before = len(_rendered)
    _install_collector()
    with contextlib.redirect_stdout(io.StringIO()):
        main(argv)
    return _rendered[before:]

