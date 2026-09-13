#!/usr/bin/env python3
"""Generate docs/CONTRACT.md from the registries, and check it has not drifted.

    python scripts/generate_contract.py            # write the document
    python scripts/generate_contract.py --check    # fail if it would change

**EVERY MARKED BLOCK IS DERIVED.** The guarantees come from
``tests/_guarantees.py``; the refusals, the not-covered reasons, the barrier
meanings and the refused-to-answer fields from ``findings.py``; the answer
fields from the ``Answer`` dataclass; the states and transitions from
``states.py``; the document keys from ``documents.py``; and the worked example
by RUNNING the module over ``tests/documents`` and printing what it returned.
A number or a sentence edited by hand turns ``--check`` red.

**AND GENERATION IS NOT VERIFICATION.** Moving a sentence from a document into a
template does not stop it being hand-written -- everywhere except the holes it is
still prose nobody checks. A generated block asserts only what it DERIVES from
its values. So ``tests/test_contract_is_generated.py`` plants values that
contradict the prose and requires the prose to change; anything that survives
that plant is a fixed string, and a fixed string is marked as design
documentation rather than left looking measured.

``--check`` writes nothing: it renders in memory and compares.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _guarantees import GUARANTEES, guarantee_ids  # noqa: E402
from garage_pass import documents as docs  # noqa: E402
from garage_pass.access import Answer, Outcome, access  # noqa: E402
from garage_pass.findings import (  # noqa: E402
    BARRIER_MEANINGS,
    EXIT_IS_NEVER_REFUSED,
    NOT_COVERED_REASONS,
    REFUSALS,
    REFUSED_TO_ANSWER,
)
from garage_pass.enrolment import (  # noqa: E402
    EXPIRED_CREDENTIAL,
    PAYLOAD_PREFIX,
    CredentialState,
)
from garage_pass.garage import ENROLS_AT  # noqa: E402
from garage_pass.passes import EXPIRED, State  # noqa: E402
from garage_pass.states import ALLOWED_TRANSITIONS  # noqa: E402
from garage_pass.terms import Direction  # noqa: E402

DOC = ROOT / "docs" / "CONTRACT.md"
DOCUMENTS = ROOT / "tests" / "documents"
BEGIN = "<!-- GENERATED:{name} -->"
END = "<!-- END:{name} -->"


def block_guarantees() -> str:
    rows = ["| id | what is guaranteed |", "|---|---|"]
    for gid in guarantee_ids():
        rows.append(f"| **{gid}** | {GUARANTEES[gid]} |")
    rows.append("")
    rows.append(
        f"That is {len(GUARANTEES)} guarantees. Every one of them has a fail control "
        "that has been proven to fire, and the count above is derived from the "
        "registry rather than typed here."
    )
    return "\n".join(rows)


def block_refusals() -> str:
    rows = ["| code | when, and what to do about it |", "|---|---|"]
    for code, sentence in sorted(REFUSALS.items()):
        rows.append(f"| `{code}` | {sentence} |")
    rows.append("")
    rows.append(
        f"{len(REFUSALS)} refusals. Each is raised with the FIELD it is about, and none "
        "of them is raised by the access call about a term: a contradiction is refused "
        "when the pass is created."
    )
    return "\n".join(rows)


def block_not_covered() -> str:
    rows = ["| reason | what the lane is told |", "|---|---|"]
    for code, sentence in sorted(NOT_COVERED_REASONS.items()):
        rows.append(f"| `{code}` | {sentence} |")
    return "\n".join(rows)


def block_meanings() -> str:
    rows = ["| meaning | at the barrier |", "|---|---|"]
    for code, sentence in sorted(BARRIER_MEANINGS.items()):
        rows.append(f"| `{code}` | {sentence} |")
    rows.append("")
    rows.append(f"Every EXIT answer, whatever its outcome, carries: *{EXIT_IS_NEVER_REFUSED}*")
    return "\n".join(rows)


def block_refused_to_answer() -> str:
    rows = ["| missing | why the call will not guess |", "|---|---|"]
    for field, sentence in sorted(REFUSED_TO_ANSWER.items()):
        rows.append(f"| `{field}` | {sentence} |")
    return "\n".join(rows)


def block_answer_fields() -> str:
    rows = ["| field | type |", "|---|---|"]
    for name, spec in Answer.__dataclass_fields__.items():
        rows.append(f"| `{name}` | `{spec.type}` |")
    rows.append("")
    rows.append(
        f"That is the whole answer: {len(Answer.__dataclass_fields__)} fields, none of "
        "which is money, and none of which could express a decision about a barrier. "
        f"`outcome` is one of {', '.join('`' + o.value + '`' for o in Outcome)}."
    )
    return "\n".join(rows)


def block_states() -> str:
    typed = [s.value for s in State]
    rows = [f"Typed states: {', '.join('`' + s + '`' for s in typed)}. Derived: `{EXPIRED}`.", ""]
    rows += ["| from | may move to |", "|---|---|"]
    for state in State:
        to = sorted(s.value for s in ALLOWED_TRANSITIONS[state])
        cells = ", ".join("`" + s + "`" for s in to) or "— (terminal)"
        rows.append(f"| `{state.value}` | {cells} |")
    return "\n".join(rows)


def block_credential_states() -> str:
    """The one-time credentials' typed states and the derived one, and what a
    QR carries -- read from ``enrolment.py``, never typed here."""
    typed = ", ".join("`" + s.value + "`" for s in CredentialState)
    ends = " or ".join("`" + e + "`" for e in ENROLS_AT)
    return "\n".join([
        f"Typed credential states: {typed}. Derived: `{EXPIRED_CREDENTIAL}` -- from `starts_on` "
        "and `days_valid` against the garage's local day; nobody types it, and typing it is "
        "refused by its own code.",
        "",
        f"A QR carries `{PAYLOAD_PREFIX}<token>`; a lane may present the payload or the bare "
        f"token. A garage enrols at {ends}; a garage with no transient parking enrols at "
        f"`{ENROLS_AT[0]}`, derived, and need not state it.",
    ])


def block_document_keys() -> str:
    rows = ["| document | keys |", "|---|---|"]
    for name in ("GARAGE", "PASS", "HOLDER", "TERMS", "WINDOW", "ALLOWANCE", "REGISTRATION",
                 "VISIT"):
        keys = sorted(getattr(docs, f"{name}_KEYS"))
        rows.append(f"| {name.lower()} | {', '.join('`' + k + '`' for k in keys)} |")
    rows.append("")
    rows.append("A key not in its document's list is refused, never ignored.")
    return "\n".join(rows)


def _load(name: str):
    return json.loads((DOCUMENTS / name).read_text())


MOVEMENTS: tuple[tuple[str, str, str, str], ...] = (
    ("CAR-1", "L1", "entry", "2026-06-01T12:00:00-06:00"),
    ("CAR-1", "L1", "exit", "2026-06-01T12:00:00-06:00"),
    ("CAR-1", "L1", "entry", "2026-06-01T05:30:00-06:00"),
    ("CAR-1", "L9", "entry", "2026-06-01T12:00:00-06:00"),
    ("NOBODY", "L1", "entry", "2026-06-01T12:00:00-06:00"),
    ("NOBODY", "L1", "exit", "2026-06-01T12:00:00-06:00"),
)


def worked_answers() -> list[tuple[tuple[str, str, str, str], Answer]]:
    garage = docs.load_garage(_load("garage_downtown.json"))
    passes = [docs.load_pass(_load("pass_employee.json"))]
    registrations = [docs.load_registration(r) for r in _load("registrations.json")]
    visits = [docs.load_visit(v) for v in _load("visits.json")]
    out = []
    for identity, lane, direction, at in MOVEMENTS:
        answer = access(
            garage=garage, passes=passes, registrations=registrations, visits=visits,
            vehicle_identity=identity, lane=lane, direction=Direction(direction),
            at=datetime.fromisoformat(at),
        )
        out.append(((identity, lane, direction, at), answer))
    return out


def _outcome_sentence(answer: Answer) -> str:
    """ASSERTION about what the run returned: three renderings whose non-numeric
    text differs, each reachable, each driven by the answer's own outcome."""
    if answer.outcome is Outcome.COVERED:
        return f"**covered** by `{answer.pass_id}` ({answer.pass_label}): {answer.covering_term}"
    if answer.outcome is Outcome.NOT_COVERED:
        return f"**not covered** — `{answer.reason}`, meaning `{answer.means}`: {answer.detail}"
    return f"**refused to answer** — missing `{answer.missing}`: {answer.detail}"


def block_worked_example() -> str:
    rows = [
        "Produced by running the module over `tests/documents/` -- the garage, the "
        "employee pass, one registration and two recorded visits -- for these movements:",
        "",
    ]
    for (identity, lane, direction, at), answer in worked_answers():
        rows.append(f"- `{identity}` at lane `{lane}`, **{direction}**, `{at}` → "
                    + _outcome_sentence(answer))
        if answer.exit_note:
            rows.append(f"  - exit note: *{answer.exit_note}*")
    return "\n".join(rows)


BLOCKS = {
    "guarantees": block_guarantees,
    "refusals": block_refusals,
    "not-covered": block_not_covered,
    "meanings": block_meanings,
    "refused-to-answer": block_refused_to_answer,
    "answer-fields": block_answer_fields,
    "states": block_states,
    "credential-states": block_credential_states,
    "document-keys": block_document_keys,
    "worked-example": block_worked_example,
}


def render(template: str) -> str:
    out = template
    for name, builder in BLOCKS.items():
        begin, end = BEGIN.format(name=name), END.format(name=name)
        if begin not in out or end not in out:
            raise SystemExit(f"docs/CONTRACT.md has no {begin} ... {end} block")
        head, rest = out.split(begin, 1)
        _stale, tail = rest.split(end, 1)
        out = f"{head}{begin}\n{builder()}\n{end}{tail}"
    return out


SOURCE = ROOT / "src" / "garage_pass"


def orphan_codes() -> dict[str, list[str]]:
    """Every registered refusal, not-covered reason, barrier meaning and
    refused-to-answer field that NOTHING in the package uses -- a sentence
    published for a code nothing raises or returns. Read from the package's
    source outside ``findings.py`` by the constant's NAME; a code used only by
    its string value is reported too, because the raise site would then be a
    typo away from an unregistered code.

    Measured before this existed: an orphan refusal planted into the registry
    and the contract regenerated -- the whole suite stayed green and the
    document said "34 refusals". ``--check`` now fails on it.
    """
    sources = "\n".join(
        path.read_text() for path in sorted(SOURCE.rglob("*.py")) if path.name != "findings.py"
    )
    import garage_pass.findings as findings_module

    names_by_value = {}
    for name, value in vars(findings_module).items():
        if isinstance(value, str) and name.isupper() and not name.startswith("_"):
            names_by_value.setdefault(value, []).append(name)
    orphans: dict[str, list[str]] = {}
    for registry_name, registry in (
        ("REFUSALS", REFUSALS),
        ("NOT_COVERED_REASONS", NOT_COVERED_REASONS),
        ("BARRIER_MEANINGS", BARRIER_MEANINGS),
        ("REFUSED_TO_ANSWER", REFUSED_TO_ANSWER),
    ):
        for code in registry:
            names = names_by_value.get(code, [])
            if not any(re.search(rf"\b{re.escape(name)}\b", sources) for name in names):
                orphans.setdefault(registry_name, []).append(code)
    return orphans


def main(argv: list[str]) -> int:
    current = DOC.read_text()
    generated = render(current)
    if "--check" in argv:
        orphans = orphan_codes()
        if orphans:
            for registry_name, codes in orphans.items():
                print(
                    f"{registry_name} publishes {', '.join(codes)}, which nothing in "
                    "src/garage_pass raises or returns. A sentence published for a code "
                    "nothing produces is a promise nothing keeps: remove it, or use it."
                )
            return 1
        if current != generated:
            print(
                "docs/CONTRACT.md does not match its generator. A number or a "
                "sentence inside a generated block was edited by hand, or the "
                "registry it comes from moved. Run this script with no arguments."
            )
            return 1
        print("docs/CONTRACT.md is the generated one.")
        return 0
    DOC.write_text(generated)
    print(f"wrote {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
