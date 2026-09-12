"""G13 -- the label is only a label. No behaviour keys off it.

Two passes identical in everything but ``label`` answer identically across the
whole matrix -- every state, both directions, every terms configuration -- and
the source reads ``label`` nowhere but to report it. The second half is read
from the AST rather than by grep: a comparison against the label anywhere in
the package is a branch on it, whatever it is spelled like.

Control: a special case for one label planted into the access call.
"""

from __future__ import annotations

import ast
import pkgutil
from dataclasses import replace
from pathlib import Path

import pytest

from fixtures import (
    NOON_MONDAY,
    TERMS_CONFIGURATIONS,
    TWO_HOURS_BEFORE,
    a_pass,
    no_transient_garage,
    registered,
    transient_garage,
)
from garage_pass.access import access
from garage_pass.passes import State, Visit
from garage_pass.terms import Direction

LABELS = ("Employee", "Monthly", "Vendor", "Reservation", "VIP", "anything the owner types")


@pytest.mark.guarantee("G13")
@pytest.mark.parametrize("state", list(State), ids=[s.value for s in State])
@pytest.mark.parametrize("direction", list(Direction), ids=[d.value for d in Direction])
@pytest.mark.parametrize("name", list(TERMS_CONFIGURATIONS))
def test_passes_differing_only_in_label_answer_identically(name, direction, state):
    answers = []
    for garage in (transient_garage(), no_transient_garage()):
        for label in LABELS:
            pass_ = a_pass(garage_id=garage.id, label=label, terms=TERMS_CONFIGURATIONS[name],
                           state=state)
            answer = access(
                garage=garage, passes=[pass_], registrations=[registered(pass_)],
                visits=[Visit(pass_id=pass_.id, vehicle_identity="CAR-1", entry_lane="L1",
                              entered_at=TWO_HOURS_BEFORE)],
                vehicle_identity="CAR-1", lane="L1", direction=direction, at=NOON_MONDAY,
            )
            # The label is REPORTED, and that is the only place it may differ.
            assert answer.pass_label == (label if answer.pass_id else None)
            detail = answer.detail.replace(label, "")
            answers.append(replace(answer, pass_label=None, detail=detail))
        first, rest = answers[0], answers[1:]
        assert all(a == first for a in rest), [a for a in rest if a != first]
        answers.clear()


def _label_comparisons() -> list[str]:
    """Every place in the package where ``.label`` sits inside a comparison,
    a match, an ``in`` test or a call to a string predicate."""
    import garage_pass

    hits = []
    for info in pkgutil.walk_packages(garage_pass.__path__, "garage_pass."):
        path = Path(info.module_finder.path) / (info.name.rsplit(".", 1)[-1] + ".py")
        if not path.exists():
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                for side in [node.left, *node.comparators]:
                    if isinstance(side, ast.Attribute) and side.attr == "label":
                        hits.append(f"{info.name}:{node.lineno}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                target = node.func.value
                if isinstance(target, ast.Attribute) and target.attr == "label":
                    if node.func.attr in {"startswith", "endswith", "lower", "upper", "casefold"}:
                        hits.append(f"{info.name}:{node.lineno}")
            if isinstance(node, ast.Match) and isinstance(node.subject, ast.Attribute):
                if node.subject.attr == "label":
                    hits.append(f"{info.name}:{node.lineno}")
    return hits


@pytest.mark.guarantee("G13")
def test_the_source_compares_the_label_nowhere():
    assert _label_comparisons() == []


@pytest.mark.guarantee("G13")
def test_the_ast_scan_can_see_a_comparison():
    """The control on the scan: the shape it looks for, parsed from a string,
    is found -- so an empty result above is an absence and not blindness."""
    tree = ast.parse('if pass_.label == "employee":\n    pass\n')
    compares = [n for n in ast.walk(tree) if isinstance(n, ast.Compare)]
    assert compares and any(
        isinstance(s, ast.Attribute) and s.attr == "label" for s in [compares[0].left]
    )
