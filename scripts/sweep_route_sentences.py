#!/usr/bin/env python3
"""Every published sentence that asserts a ROUTE, found by derivation and judged by content.

    python scripts/sweep_route_sentences.py               # the tree: zero FALSE, or exit 1
    python scripts/sweep_route_sentences.py --self-test   # prove the sweep can go red first

**WHY THIS EXISTS.** A sentence can be true when it is written and false after a
later round opens a new door to the code it describes -- and nothing re-asks the
question. That is how ``PASS_UNREADABLE``'s registry sentence came to say a pass
"is stored with" a value on a route where nothing was stored, and how, after the
registry was corrected, the DETAIL the operator actually reads in the answer went
on saying it: the sweep that certified the registry never contained the rendered
details. A sweep that cannot see the operator's text cannot certify it.

**THE DENOMINATOR IS DERIVED, NEVER A HAND LIST.** Every string literal in
``src/garage_pass`` by AST (docstrings, f-string parts, the details rendered into
answers and refusals, argparse help), plus the four registries and the guarantees
BY IMPORT (the value, never the source that spells it), plus ``README.md`` and
``docs/CONTRACT.md`` in full. Every sentence in that set that carries a word
asserting where a code comes from or that nothing else reaches it (``ROUTE``) is
a hit.

**THE JUDGEMENT IS HUMAN, RECORDED, AND KEYED TO THE SENTENCE'S CONTENT.** Whether
an English sentence is true is not mechanically decidable, so each hit carries a
verdict written by hand into ``docs/route_sentence_judgements.json`` -- and the
key is the sentence itself (whitespace collapsed, nothing else touched: not
case, not a character the token contains), never a file and a line. Keyed by
location, editing a judged-true sentence would silently inherit its old verdict,
which is exactly how the falsehood above survived. Keyed by content, ANY edit
makes the sentence unjudged and the run fails until someone judges it again.

**WHAT FAILS THE RUN:** a hit with no judgement (UNJUDGED); a hit judged FALSE; a
judgement for a sentence that no longer exists anywhere (STALE -- the file
carries no garbage). What does not: TRUE, VAGUE (true, could be read wrong) and
NOT-PUBLISHED (a docstring or comment-like string nobody outside reads) -- the
property certified is ZERO FALSE over every hit, not zero hits.

``--self-test`` plants a "stored"-style falsehood into a rendered detail that is
NOT the one this sweep was built for, in a COPY of the source, and requires the
run to go red naming that sentence; then edits one judged-true sentence by a
word and requires it to read UNJUDGED; then requires the unmodified tree to read
clean. A sweep that only catches the line already known has not widened.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

JUDGEMENTS = ROOT / "docs" / "route_sentence_judgements.json"
VERDICTS = ("TRUE", "VAGUE", "NOT-PUBLISHED", "FALSE")

#: A word that says where a code comes from, or that nothing else reaches it.
ROUTE = re.compile(
    r"\b(raw write|raw insert|written raw|stored with|is stored|are stored|stored row|"
    r"stored unreadable|reached only|reached by|only by|only when|only at|only reached|"
    r"never reached|cannot produce|the store cannot|at creation|never discovered|"
    r"through the pure API|not JSON|nested deeper|handed to the command line|"
    r"regular file)\b",
    re.IGNORECASE,
)

_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'`*\[])")


def normalise(text: str) -> str:
    """Whitespace collapsed. Nothing else: not case, not a character the token contains."""
    return " ".join(text.split())


def sentences(text: str) -> list[str]:
    return [normalise(s) for s in _SPLIT.split(normalise(text)) if s.strip()]


def strings_by_ast(src: Path) -> list[tuple[str, str]]:
    """Every string literal in the package: ``(where, text)``. An f-string's
    formatted parts read as ``{…}`` so the sentence around them is judged."""
    out: list[tuple[str, str]] = []
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        # an f-string's literal pieces are Constants of their own under the
        # JoinedStr; the sentence is the whole, so the pieces are not re-read
        pieces = {id(v) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr)
                  for v in node.values}
        for node in ast.walk(tree):
            if id(node) in pieces:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
            elif isinstance(node, ast.JoinedStr):
                text = "".join(
                    v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{…}"
                    for v in node.values
                )
            else:
                continue
            out.append((f"{path.relative_to(src.parent.parent)}:{node.lineno}", text))
    return out


def by_import() -> list[tuple[str, str]]:
    from _guarantees import GUARANTEES
    from garage_pass import findings as f

    out: list[tuple[str, str]] = []
    for name, registry in (("REFUSALS", f.REFUSALS), ("NOT_COVERED_REASONS", f.NOT_COVERED_REASONS),
                           ("BARRIER_MEANINGS", f.BARRIER_MEANINGS),
                           ("REFUSED_TO_ANSWER", f.REFUSED_TO_ANSWER)):
        out += [(f"{name}[{code}]", text) for code, text in registry.items()]
    out += [(f"GUARANTEES[{gid}]", text) for gid, text in GUARANTEES.items()]
    return out


def prose(root: Path) -> list[tuple[str, str]]:
    """README and CONTRACT by PARAGRAPH (a sentence wrapped over two lines is one
    sentence, and re-wrapping it is not an edit); a table row by CELL, wherever
    it stands -- the CONTRACT's generated tables sit against their markers with
    no blank line between."""
    out: list[tuple[str, str]] = []

    def flush(name: str, start: int, block: list[str]) -> None:
        if block:
            out.append((f"{name}:{start}", " ".join(block)))
            block.clear()

    for name in ("README.md", "docs/CONTRACT.md"):
        start, block = 1, []
        for i, line in enumerate((root / name).read_text().splitlines(), 1):
            if line.lstrip().startswith("|"):
                flush(name, start, block)
                out.extend((f"{name}:{i}", c) for c in line.split("|") if c.strip())
            elif line.strip():
                if not block:
                    start = i
                block.append(line)
            else:
                flush(name, start, block)
        flush(name, start, block)
    return out


def hits(src: Path, root: Path) -> tuple[dict[str, list[str]], dict[str, int]]:
    """``{sentence: [where, ...]}`` for every route-asserting sentence, and the denominator."""
    found: dict[str, list[str]] = {}
    sources = strings_by_ast(src)
    imported = by_import()
    lines = prose(root)
    counts = {"string literals in src by AST": len(sources),
              "registry and guarantee sentences by import": len(imported),
              "README/CONTRACT lines and cells": len(lines), "sentences": 0}
    for where, text in sources + imported + lines:
        for s in sentences(text):
            counts["sentences"] += 1
            if ROUTE.search(s):
                found.setdefault(s, []).append(where)
    return found, counts


def load_judgements(path: Path = JUDGEMENTS) -> dict[str, dict]:
    rows = json.loads(path.read_text())
    out: dict[str, dict] = {}
    for row in rows:
        key = normalise(row["sentence"])
        if row["verdict"] not in VERDICTS:
            raise SystemExit(f"a verdict that is not one of {VERDICTS}: {row}")
        if key in out:
            raise SystemExit(f"the same sentence judged twice: {key[:80]!r}")
        out[key] = row
    return out


def run(src: Path = ROOT / "src" / "garage_pass", root: Path = ROOT,
        judgements: Path = JUDGEMENTS, quiet: bool = False) -> tuple[int, dict]:
    found, counts = hits(src, root)
    judged = load_judgements(judgements)
    tally = {v: 0 for v in VERDICTS}
    unjudged: list[tuple[str, list[str]]] = []
    false: list[tuple[str, list[str], str]] = []
    for s, where in found.items():
        row = judged.get(s)
        if row is None:
            unjudged.append((s, where))
        else:
            tally[row["verdict"]] += 1
            if row["verdict"] == "FALSE":
                false.append((s, where, row.get("why", "")))
    stale = [s for s in judged if s not in found]
    if not quiet:
        print("DENOMINATOR: " + "; ".join(f"{v} {k}" for k, v in counts.items()))
        print(f"ROUTE-ASSERTING SENTENCES (distinct, by content): {len(found)}")
        print("JUDGED: " + ", ".join(f"{v} {k}" for k, v in tally.items())
              + f"; UNJUDGED {len(unjudged)}; STALE judgements {len(stale)}")
        for s, where in unjudged:
            print(f"\nUNJUDGED -- write a verdict for this sentence in "
                  f"{judgements.relative_to(root)}:\n  {s}\n  at {', '.join(where[:4])}")
        for s, where, why in false:
            print(f"\nFALSE -- {why}\n  {s}\n  at {', '.join(where[:4])}")
        for s in stale:
            print(f"\nSTALE -- judged, but no such sentence exists any more; remove it:\n  {s}")
    status = 1 if (unjudged or false or stale) else 0
    return status, {"found": len(found), "unjudged": [s for s, _ in unjudged],
                    "false": [s for s, _, _ in false], "stale": stale, **tally}


# ---------------------------------------------------------------------------
# the self-test: the sweep proven able to go red, on a COPY of the source
# ---------------------------------------------------------------------------

PLANT_ANCHOR = 'what = f"garage {garage.id!r}: {garage.unreadable.describe()}"'
PLANT = ('what = f"garage {garage.id!r} is stored with a value this module refuses to read: '
         '{garage.unreadable.describe()}"')


def self_test() -> int:
    src = ROOT / "src" / "garage_pass"
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "src" / "garage_pass"
        shutil.copytree(src, copy)
        access = copy / "access.py"
        text = access.read_text()
        if text.count(PLANT_ANCHOR) != 1:
            print(f"self-test: the plant anchor appears {text.count(PLANT_ANCHOR)}x, not once")
            return 1
        access.write_text(text.replace(PLANT_ANCHOR, PLANT))
        status, result = run(src=copy, quiet=True)
        planted = [s for s in result["unjudged"] if "is stored with a value this module" in s
                   and s.startswith("garage")]
        print(f"self-test 1: a 'stored' falsehood planted into the GARAGE_UNREADABLE detail "
              f"(not the PASS one): exit {status}, unjudged {len(result['unjudged'])}, "
              f"named: {planted[0][:70]!r}" if planted else
              f"self-test 1: the planted falsehood was NOT named (exit {status}, "
              f"unjudged {result['unjudged']})")
        if status != 1 or not planted:
            return 1
        # 2. a judged-true sentence edited by one word must read UNJUDGED (content-keyed)
        shutil.rmtree(copy)
        shutil.copytree(src, copy)
        judged = load_judgements()
        found, _ = hits(src, ROOT)
        target = next((s for s in found if judged.get(s, {}).get("verdict") == "TRUE"
                       and any(w.startswith("src/") for w in found[s])), None)
        if target is None:
            print("self-test 2: no judged-TRUE sentence in src to edit")
            return 1
        edited = False
        for path in sorted(copy.rglob("*.py")):
            raw = path.read_text()
            # the sentence may be spelled across concatenated literals; edit the first
            # distinctive run of words that appears verbatim in the source
            for n in range(min(8, len(target.split())), 2, -1):
                piece = " ".join(target.split()[:n])
                if raw.count(piece) == 1:
                    path.write_text(raw.replace(piece, piece + " (edited)"))
                    edited = True
                    break
            if edited:
                break
        if not edited:
            print("self-test 2: could not find the judged sentence's words in the source copy")
            return 1
        status2, result2 = run(src=copy, quiet=True)
        moved = any(target.split()[:3] == s.split()[:3] for s in result2["unjudged"])
        print(f"self-test 2: a judged-TRUE sentence edited by one word: exit {status2}, "
              f"reads UNJUDGED: {moved}")
        if status2 != 1 or not moved:
            return 1
    status3, result3 = run(quiet=True)
    print(f"self-test 3: the unmodified tree: exit {status3} (FALSE {result3['FALSE']}, "
          f"UNJUDGED {len(result3['unjudged'])}, STALE {len(result3['stale'])})")
    return 0 if status3 == 0 else 1


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    status, _ = run()
    print("\nzero FALSE, every hit judged, no stale judgement" if status == 0 else "\nNOT CLEAN")
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
