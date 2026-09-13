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

**THE JUDGEMENT IS HUMAN, RECORDED, AND KEYED TO THE SENTENCE'S CONTENT AND THE
FILE IT STANDS IN.** Whether an English sentence is true is not mechanically
decidable, so each hit carries a verdict written by hand into
``docs/route_sentence_judgements.json`` -- and the key is the sentence itself
(whitespace collapsed, nothing else touched: not case, not a character the token
contains) TOGETHER WITH THE FILE, never a line. Keyed by line, editing a
judged-true sentence would silently inherit its old verdict, which is exactly how
the falsehood above survived. Keyed by content alone -- as this sweep was first
built -- the verdict travelled with the TEXT and not with the door: measured, a
sentence judged TRUE where it is rendered on a store write (``records.py``:
"pass … is stored unreadable", true of a row that IS stored) copied verbatim
into the document-door detail in ``access.py`` inherited TRUE, and the operator
read "is stored" from a document again -- the exact falsehood this instrument
exists to catch, re-entering through the instrument. And a docstring sentence
judged NOT-PUBLISHED, copied into README or into a rendered detail, stayed
NOT-PUBLISHED. So the same sentence in a NEW FILE is a NEW QUESTION and reads
UNJUDGED until someone answers it; any edit to the text does the same. The file
is what the sweep can know -- it cannot know the door, since one literal in
``access.py`` renders on both -- and it is what separates the store's own
sentences from the boundary's. CONTRACT's generated copies of a registry
sentence are the registry's, not CONTRACT's: the document is generated, not
authored, so a copy there is not a new question (an authored copy in README is).

**WHAT FAILS THE RUN:** a hit with no judgement (UNJUDGED); a hit judged FALSE; a
judgement for a sentence that no longer exists anywhere (STALE -- the file
carries no garbage). What does not: TRUE, VAGUE (true, could be read wrong) and
NOT-PUBLISHED (a docstring or comment-like string nobody outside reads) -- the
property certified is ZERO FALSE over every hit, not zero hits.

``--self-test`` plants a "stored"-style falsehood into a rendered detail that is
NOT the one this sweep was built for, in a COPY of the source, and requires the
run to go red naming that sentence; then edits one judged-true sentence by a
word and requires it to read UNJUDGED; then copies one judged-true sentence
VERBATIM into a file it does not stand in and requires THAT to read UNJUDGED
(the key carries the file); then requires the unmodified tree to read clean. A
sweep that only catches the line already known has not widened.
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


def keyed(sentence: str, file: str) -> tuple[str, str]:
    """The judgement key: the sentence's content AND the file it stands in."""
    return (sentence, file)


def strings_by_ast(src: Path) -> list[tuple[str, str, str]]:
    """Every string literal in the package: ``(where, file, text)``. An f-string's
    formatted parts read as ``{…}`` so the sentence around them is judged."""
    out: list[tuple[str, str, str]] = []
    for path in sorted(src.rglob("*.py")):
        file = str(path.relative_to(src.parent.parent))
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
            out.append((f"{file}:{node.lineno}", file, text))
    return out


def by_import(root: Path = ROOT) -> list[tuple[str, str, str]]:
    """The registries and the guarantees as VALUES, each attributed to the file
    that defines it -- read from the module, never typed."""
    import _guarantees
    from garage_pass import findings as f

    def home(module) -> str:
        # the module's file relative to the tree it was imported from -- this tree
        # (ROOT); a caller sweeping a COPY of the tree still imports from here
        file = Path(module.__file__).resolve()
        for base in (ROOT, Path(root).resolve()):
            if file.is_relative_to(base):
                return str(file.relative_to(base))
        raise SystemExit(f"{module.__name__} was imported from outside the tree: {file}")

    out: list[tuple[str, str, str]] = []
    for name, registry in (("REFUSALS", f.REFUSALS), ("NOT_COVERED_REASONS", f.NOT_COVERED_REASONS),
                           ("BARRIER_MEANINGS", f.BARRIER_MEANINGS),
                           ("REFUSED_TO_ANSWER", f.REFUSED_TO_ANSWER)):
        out += [(f"{name}[{code}]", home(f), text) for code, text in registry.items()]
    out += [(f"GUARANTEES[{gid}]", home(_guarantees), text)
            for gid, text in _guarantees.GUARANTEES.items()]
    return out


def prose(root: Path) -> list[tuple[str, str, str]]:
    """README and CONTRACT by PARAGRAPH (a sentence wrapped over two lines is one
    sentence, and re-wrapping it is not an edit); a table row by CELL, wherever
    it stands -- the CONTRACT's generated tables sit against their markers with
    no blank line between. ``(where, file, text)``; a CONTRACT line inside a
    ``GENERATED`` block reads its file as ``GENERATED`` so ``hits`` can attribute a
    copy of a registry sentence to the registry's own file."""
    out: list[tuple[str, str, str]] = []

    def flush(name: str, file: str, start: int, block: list[str]) -> None:
        if block:
            out.append((f"{name}:{start}", file, " ".join(block)))
            block.clear()

    for name in ("README.md", "docs/CONTRACT.md"):
        start, block, generated = 1, [], False
        for i, line in enumerate((root / name).read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("<!-- GENERATED:"):
                flush(name, name, start, block)
                generated = True
                continue
            if stripped.startswith("<!-- END:"):
                flush(name, "GENERATED", start, block)
                generated = False
                continue
            file = "GENERATED" if generated else name
            if line.lstrip().startswith("|"):
                flush(name, file, start, block)
                out.extend((f"{name}:{i}", file, c) for c in line.split("|") if c.strip())
            elif stripped:
                if not block:
                    start = i
                block.append(line)
            else:
                flush(name, file, start, block)
        flush(name, name, start, block)
    return out


def hits(src: Path, root: Path) -> tuple[dict[tuple[str, str], list[str]], dict[str, int]]:
    """``{(sentence, file): [where, ...]}`` for every route-asserting sentence, and
    the denominator. A sentence inside one of CONTRACT's generated blocks that is
    a registry or guarantee sentence by import is the registry's, and is keyed to
    the registry's file; generated text that is not a copy of an imported value
    is keyed to CONTRACT itself."""
    found: dict[tuple[str, str], list[str]] = {}
    sources = strings_by_ast(src)
    imported = by_import(root)
    lines = prose(root)
    counts = {"string literals in src by AST": len(sources),
              "registry and guarantee sentences by import": len(imported),
              "README/CONTRACT lines and cells": len(lines), "sentences": 0}
    registry_home = {s: file for _, file, text in imported for s in sentences(text)}
    for where, file, text in sources + imported + lines:
        for s in sentences(text):
            counts["sentences"] += 1
            if ROUTE.search(s):
                if file == "GENERATED":
                    file = registry_home.get(s, "docs/CONTRACT.md")
                found.setdefault(keyed(s, file), []).append(where)
    return found, counts


def load_judgements(path: Path = JUDGEMENTS) -> dict[tuple[str, str], dict]:
    rows = json.loads(path.read_text())
    out: dict[tuple[str, str], dict] = {}
    for row in rows:
        if "file" not in row:
            raise SystemExit(f"a judgement with no file -- the key is the sentence AND its file: "
                             f"{row.get('sentence', '')[:80]!r}")
        key = keyed(normalise(row["sentence"]), row["file"])
        if row["verdict"] not in VERDICTS:
            raise SystemExit(f"a verdict that is not one of {VERDICTS}: {row}")
        if key in out:
            raise SystemExit(f"the same sentence judged twice in {row['file']}: {key[0][:80]!r}")
        out[key] = row
    return out


def run(src: Path = ROOT / "src" / "garage_pass", root: Path = ROOT,
        judgements: Path = JUDGEMENTS, quiet: bool = False) -> tuple[int, dict]:
    found, counts = hits(src, root)
    judged = load_judgements(judgements)
    tally = {v: 0 for v in VERDICTS}
    unjudged: list[tuple[tuple[str, str], list[str]]] = []
    false: list[tuple[tuple[str, str], list[str], str]] = []
    for key, where in found.items():
        row = judged.get(key)
        if row is None:
            unjudged.append((key, where))
        else:
            tally[row["verdict"]] += 1
            if row["verdict"] == "FALSE":
                false.append((key, where, row.get("why", "")))
    stale = [key for key in judged if key not in found]
    if not quiet:
        print("DENOMINATOR: " + "; ".join(f"{v} {k}" for k, v in counts.items()))
        print(f"ROUTE-ASSERTING SENTENCES (distinct, by content AND file): {len(found)}"
              f" ({len({s for s, _ in found})} distinct by content)")
        print("JUDGED: " + ", ".join(f"{v} {k}" for k, v in tally.items())
              + f"; UNJUDGED {len(unjudged)}; STALE judgements {len(stale)}")
        for (s, file), where in unjudged:
            print(f"\nUNJUDGED -- write a verdict for this sentence IN {file} in "
                  f"{judgements.relative_to(root)}:\n  {s}\n  at {', '.join(where[:4])}")
        for (s, file), where, why in false:
            print(f"\nFALSE -- {why}\n  {s}\n  in {file}, at {', '.join(where[:4])}")
        for s, file in stale:
            print(f"\nSTALE -- judged in {file}, but no such sentence stands there any more; "
                  f"remove it:\n  {s}")
    status = 1 if (unjudged or false or stale) else 0
    return status, {"found": len(found), "unjudged": [f"{file}: {s}" for (s, file), _ in unjudged],
                    "false": [f"{file}: {s}" for (s, file), _, _ in false],
                    "stale": [f"{file}: {s}" for s, file in stale], **tally}


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
                   and s.split(": ", 1)[1].startswith("garage")]
        print(f"self-test 1: a 'stored' falsehood planted into the GARAGE_UNREADABLE detail "
              f"(not the PASS one): exit {status}, unjudged {len(result['unjudged'])}, "
              f"named: {planted[0].split(': ', 1)[1][:70]!r}" if planted else
              f"self-test 1: the planted falsehood was NOT named (exit {status}, "
              f"unjudged {result['unjudged']})")
        if status != 1 or not planted:
            return 1
        # 2. a judged-true sentence edited by one word must read UNJUDGED (content-keyed)
        shutil.rmtree(copy)
        shutil.copytree(src, copy)
        judged = load_judgements()
        found, _ = hits(src, ROOT)
        # candidates are chosen by WHERE they stand (the AST location), never by the key's
        # file, so a key that lost its file cannot hide from the copy step below
        def standing_in_src(key: tuple[str, str]) -> str | None:
            return next((w.rsplit(":", 1)[0] for w in found[key] if w.startswith("src/")), None)

        candidates = [(key[0], standing_in_src(key)) for key in found
                      if judged.get(key, {}).get("verdict") == "TRUE"
                      and standing_in_src(key) and "{" not in key[0]]
        if not candidates:
            print("self-test 2: no judged-TRUE plain sentence in src to edit")
            return 1
        edited = False
        for sentence, file in candidates:
            raw_path = copy.parent.parent / file
            raw = raw_path.read_text()
            # the sentence may be spelled across concatenated literals; edit the first
            # distinctive run of words that appears verbatim in its own file
            for n in range(min(8, len(sentence.split())), 2, -1):
                piece = " ".join(sentence.split()[:n])
                if raw.count(piece) == 1:
                    raw_path.write_text(raw.replace(piece, piece + " (edited)"))
                    edited = True
                    break
            if edited:
                break
        if not edited:
            print("self-test 2: could not find any judged sentence's words in its own file")
            return 1
        status2, result2 = run(src=copy, quiet=True)
        moved = any(sentence.split()[:3] == s.split(": ", 1)[1].split()[:3]
                    for s in result2["unjudged"])
        print(f"self-test 2: a judged-TRUE sentence edited by one word: exit {status2}, "
              f"reads UNJUDGED: {moved}")
        if status2 != 1 or not moved:
            return 1
        # 3. a judged-true sentence copied VERBATIM into a file it does not stand in must read
        #    UNJUDGED there (the key carries the file) -- the shape measured before this: a
        #    store-write sentence copied into the document door inherited TRUE
        shutil.rmtree(copy)
        shutil.copytree(src, copy)
        plain = next(((key[0], standing_in_src(key)) for key in found
                      if judged.get(key, {}).get("verdict") == "TRUE"
                      and standing_in_src(key) and "{" not in key[0] and '"' not in key[0]), None)
        if plain is None:
            print("self-test 3: no judged-TRUE plain sentence in src to copy")
            return 1
        sentence3, file3 = plain
        other = next(p for p in sorted(copy.rglob("*.py"))
                     if str(p.relative_to(copy.parent.parent)) != file3 and p.name != "__init__.py")
        other.write_text(other.read_text() + f"\n\n_COPIED_VERBATIM = {sentence3!r}\n")
        status3, result3 = run(src=copy, quiet=True)
        other_file = str(other.relative_to(copy.parent.parent))
        copied = any(s == f"{other_file}: {sentence3}" for s in result3["unjudged"])
        print(f"self-test 3: a judged-TRUE sentence of {file3} copied verbatim into "
              f"{other_file}: exit {status3}, the same sentence in a NEW file reads UNJUDGED: "
              f"{copied}")
        if status3 != 1 or not copied:
            return 1
    status4, result4 = run(quiet=True)
    print(f"self-test 4: the unmodified tree: exit {status4} (FALSE {result4['FALSE']}, "
          f"UNJUDGED {len(result4['unjudged'])}, STALE {len(result4['stale'])})")
    return 0 if status4 == 0 else 1


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    status, _ = run()
    print("\nzero FALSE, every hit judged, no stale judgement" if status == 0 else "\nNOT CLEAN")
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
