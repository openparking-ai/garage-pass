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

**THE SECOND HALF READS WHAT IS RENDERED, NOT ONLY WHAT IS WRITTEN.** A sweep of
literals cannot see a sentence assembled at run time -- ``"is " + "stored" +
" with"``, ``"".join(...)``, ``%``, ``.format()``, an f-string whose route word
sits inside a placeholder, a ``.replace()`` on a true literal. Measured: six such
spellings of the exact falsehood the round before this removed rendered to the
operator and left this sweep green. So the test suite COLLECTS every detail the
module renders while it runs (``tests/conftest.py``: every ``Answer`` built, every
``Refused`` the command line prints -- what the operator reads is the definition)
and hands them to ``judge_rendered`` here: THE SAME templates, THE SAME key, THE
SAME judgements file, THE SAME fail-closed loader. **The file of a rendered
sentence is the file of the LITERAL it was rendered from, and that file must be
on the call stack that rendered it.** A rendered detail carrying a route word is
matched WHOLE, anchored at both ends, against every literal in the package as a
template -- literal segments escaped and in order, each ``{…}`` placeholder a
minimal wildcard that consumes exactly what the value rendered, and nothing
else: there is no character-level scrubber of ids, paths or instants, because a
scrubber is a second copy of the sentence's shape and this pass built four that
were each wrong the same way. A match to a template that stands in a file on the
rendering stack is covered by THAT literal's ``(text, file)`` judgements; a route
word that fell inside a wildcard is matched again, recursively, as its own text;
no match anywhere is UNJUDGED -- red, naming the rendered text and its call site.
**No judgement is ever written for a rendered-only text**: a route sentence the
module assembles at run time has one honest fix, which is to make it a literal so
the first half can see it, never a second judgement store. **The scope, said
plainly:** the sweep certifies the MODULE's sentences. A value rendered into a
detail is data the module was handed, and a green sweep does not say that no
false text can reach an operator through a value -- it says the module's own
sentences are judged and none is false.

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
import subprocess
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
# the rendered half: what the module renders, matched to the literal it came from
# ---------------------------------------------------------------------------

PLACEHOLDER = "{…}"
_SPLIT_PLACEHOLDERS = re.compile(r"(\{…\})")
_WILDCARD = "(?s:.*?)"


class Template:
    """One literal as a whole-text template. ``anywhere`` is True for a registry or
    guarantee VALUE (``by_import``): a published sentence is the module's wherever
    it is rendered -- the code reads it as data, so the file it stands in is
    never on the rendering stack -- and its judgement was made for that."""

    __slots__ = ("text", "file", "anywhere", "whole", "prefix", "route_keys", "literal_length")

    def __init__(self, text: str, file: str, anywhere: bool) -> None:
        self.text, self.file, self.anywhere = text, file, anywhere
        body = "".join(_WILDCARD if part == PLACEHOLDER else re.escape(part)
                       for part in _SPLIT_PLACEHOLDERS.split(text))
        self.whole = re.compile(body)
        self.prefix = re.compile(body + "(?=\\s|$)")
        self.route_keys = [keyed(s, file) for s in sentences(text) if ROUTE.search(s)]
        self.literal_length = sum(len(part) for part in _SPLIT_PLACEHOLDERS.split(text)
                                  if part != PLACEHOLDER)

    def spans(self, text: str, whole: bool) -> list[tuple[int, int]] | None:
        """The spans the wildcards consumed, and where the match ended -- by matching
        with each wildcard made a group. ``None`` when the template does not match."""
        grouped = re.compile((self.whole if whole else self.prefix).pattern.replace(
            _WILDCARD, f"({_WILDCARD})"))
        m = grouped.fullmatch(text) if whole else grouped.match(text)
        if not m:
            return None
        return [m.span(i) for i in range(1, grouped.groups + 1)] + [(m.end(), m.end())]


def templates(src: Path = ROOT / "src" / "garage_pass", root: Path = ROOT) -> list[Template]:
    """Every string literal in the package (by AST, ``{…}`` for a formatted part)
    and every registry and guarantee value (by import, usable from any stack), as
    templates; a literal with no placeholder matches only itself."""
    out: dict[tuple[str, str], Template] = {}
    for anywhere, rows in ((False, [(f, x) for _, f, x in strings_by_ast(src)]),
                           (True, [(f, x) for _, f, x in by_import(root)])):
        for file, text in rows:
            t = normalise(text)
            if not t:
                continue
            if (t, file) in out:  # a registry value is also a literal in its own file: the
                out[(t, file)].anywhere |= anywhere  # value's reach wins
                continue
            out[(t, file)] = Template(t, file, anywhere)
    return list(out.values())


def match_rendered(detail: str, stack_files: frozenset[str], templates_: list[Template],
                   judged: dict[tuple[str, str], dict], depth: int = 0,
                   memo: dict | None = None) -> tuple[str, list]:
    """One rendered text against the templates on the stack that rendered it (and
    the registry values, usable from any stack). A text is ACCOUNTED FOR when it
    is one template whole, or a template as its PREFIX followed by text that is
    itself accounted for -- a detail is often two literals side by side (a
    registry sentence and the f-string beside it; describes joined by a
    separator that is itself a literal). Among the templates that match, **the
    most specific wins** -- the least text consumed by wildcards, then the most
    literal text -- because ``f"--{option}"`` also matches every refusal that
    begins with two dashes, and a permissive template must never be the one that
    accounts for a route word.

    **A ROUTE PHRASE IS ASSERTED BY WHOEVER SPELLED IT WHOLE.** Every route phrase
    in the text must lie entirely inside ONE literal segment of the template (then
    that literal's judged route sentence covers it), or entirely inside one
    captured value (then the value is matched again as its own text), or entirely
    in the rest after a prefix (matched again). A phrase that straddles a boundary
    -- ``is`` in the literal, ``stored`` in the value; ``stored`` as one literal
    and ``with`` in the next -- rejects the candidate: that is exactly how a
    sentence gets assembled at run time, and the assembly is the thing to catch.
    Text with no route phrase needs no accounting: the sweep judges the module's
    route sentences, not every character it prints.

    Returns ``("covered", keys)`` -- every judged ``(text, file)`` key of the route
    sentences that account for the route phrases -- or ``("unjudged", [])``."""
    text = normalise(detail)
    if memo is None:
        memo = {}
    phrases = [m.span() for m in ROUTE.finditer(text)]
    if not phrases:
        return "covered", []
    if depth > 8:
        return "unjudged", []
    key = (text, stack_files)
    if key in memo:
        return memo[key]
    memo[key] = ("unjudged", [])  # a cycle reads as unjudged
    usable = [tp for tp in templates_ if tp.anywhere or tp.file in stack_files]

    def inside(span: tuple[int, int], segment: tuple[int, int]) -> bool:
        return segment[0] <= span[0] and span[1] <= segment[1]

    for whole in (True, False):
        candidates = []
        for tp in usable:
            spans = tp.spans(text, whole)
            if spans is None:
                continue
            end = spans.pop()[0]
            if not whole and end == 0:
                continue
            consumed = sum(b - a for a, b in spans)
            candidates.append(((consumed, -end, -tp.literal_length), tp, spans, end))
        for _, tp, spans, end in sorted(candidates, key=lambda c: c[0]):
            # the literal segments: the gaps between the wildcards, up to the end
            cursor, literals = 0, []
            for a, b in spans:
                if a > cursor:
                    literals.append((cursor, a))
                cursor = b
            if end > cursor:
                literals.append((cursor, end))
            rest = (end, len(text))
            ok, keys = True, list(tp.route_keys)
            for phrase in phrases:
                if any(inside(phrase, seg) for seg in literals):
                    if not tp.route_keys:  # cannot happen: the phrase is in the template's text
                        ok = False
                elif not (any(inside(phrase, seg) for seg in spans) or inside(phrase, rest)):
                    ok = False  # the phrase straddles a boundary: assembled, not spelled
                if not ok:
                    break
            if not ok:
                continue
            for a, b in spans:  # a route phrase inside a value must itself be accounted for
                if any(inside(ph, (a, b)) for ph in phrases):
                    verdict, more = match_rendered(text[a:b], stack_files, templates_, judged,
                                                   depth + 1, memo)
                    if verdict == "unjudged":
                        ok = False
                        break
                    keys += more
            if ok and not whole and any(inside(ph, rest) for ph in phrases):
                verdict, more = match_rendered(text[end:].lstrip(), stack_files, templates_,
                                               judged, depth + 1, memo)
                if verdict == "unjudged":
                    ok = False
                keys += more
            if ok:
                memo[key] = ("covered", keys)
                return memo[key]
    return memo[key]


def judge_rendered(collected: list[tuple[str, frozenset[str]]],
                   src: Path = ROOT / "src" / "garage_pass",
                   judgements: Path = JUDGEMENTS) -> tuple[int, dict]:
    """The rendered half's verdict over ``collected`` -- ``(detail, files on the stack)``
    pairs, as the test suite collected them. Distinct pairs are judged once. The
    denominator is reported so a collector that collected nothing reads as
    UNMEASURED, never as clean."""
    judged = load_judgements(judgements)
    templates_ = templates(src)
    distinct = sorted(set(collected), key=lambda c: (c[0], sorted(c[1])))
    route = [(d, s) for d, s in distinct if ROUTE.search(normalise(d))]
    unjudged: list[tuple[str, frozenset[str]]] = []
    false: list[tuple[str, tuple[str, str], str]] = []
    covered = 0
    memo: dict = {}
    for detail, stack in route:
        verdict, keys = match_rendered(detail, stack, templates_, judged, memo=memo)
        if verdict == "unjudged":
            unjudged.append((detail, stack))
            continue
        rows = [judged.get(key) for key in keys]
        if any(row is None for row in rows):  # a literal the first half has not judged yet
            unjudged.append((detail, stack))
            continue
        covered += 1
        for key, row in zip(keys, rows, strict=True):
            if row["verdict"] == "FALSE":
                false.append((detail, key, row.get("why", "")))
    result = {"collected": len(collected), "distinct": len(distinct), "route_asserting": len(route),
              "covered": covered,
              "unjudged": [f"{sorted(s)}: {d}" for d, s in unjudged],
              "false": [f"{k[1]}: {d}" for d, k, _ in false]}
    status = 1 if (unjudged or false or not collected) else 0
    return status, result


def report_rendered(result: dict) -> str:
    lines = [f"RENDERED: {result['collected']} details collected, {result['distinct']} distinct "
             f"(detail, stack); {result['route_asserting']} route-asserting; "
             f"{result['covered']} accounted for by literals on the stack or registry "
             f"values; UNJUDGED {len(result['unjudged'])}; FALSE {len(result['false'])}"]
    if result["collected"] == 0:
        lines.append("UNMEASURED -- the collector saw no rendered detail at all; a zero from "
                     "an unproven collector is not a clean reading")
    for u in result["unjudged"]:
        lines.append("\nUNJUDGED RENDERED -- no literal on the rendering stack produces this "
                     f"text; if the module assembled it at run time, make it a literal:\n  {u}")
    for f_ in result["false"]:
        lines.append(f"\nFALSE RENDERED -- {f_}")
    return "\n".join(lines)


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
    if status4 != 0:
        return 1
    return rendered_self_test()


# the rendered half's self-test: a COPY of the package rendered in a subprocess with
# the suite's collector installed -- no database, no test session -- then judged here
_RENDER_ANCHOR = ('                f"refuses to read -- {pass_.unreadable.describe()}"\n'
                  '            )\n            if is_exit:')
#: the seventh spelling -- a .replace() on a TRUE literal, a shape the gate's six did not use
_RENDER_PLANT = ('                f"refuses to read -- {pass_.unreadable.describe()}"\n'
                 '            )\n'
                 '            what = what.replace("carries a value", "is stored with a value")\n'
                 '            if is_exit:')
_FOOL_ANCHOR = ('    return {"refused": refused.code, "field": refused.field, '
                '"detail": refused.detail}')
#: one word inserted beside a route phrase: the literal segments now differ from every template
_FOOL_PLANT = ('    return {"refused": refused.code, "field": refused.field,\n'
               '            "detail": refused.detail.replace("regular file (", '
               '"regular file indeed (")}')


def _render_from(copy_src: Path, argv: list[str]) -> list[tuple[str, frozenset[str]]]:
    """The command line of the package at ``copy_src`` run in a fresh interpreter
    with the suite's collector installed; what it rendered, with the stack files."""
    code = (
        "import json, sys\n"
        f"sys.path[:0] = [{str(copy_src.parent)!r}, {str(ROOT / 'tests')!r}, "
        f"{str(ROOT / 'scripts')!r}]\n"
        # the COPY's package first: importing the collector imports this sweep, which
        # puts the tree's own src at the front of sys.path
        "import garage_pass.cli\n"
        f"assert garage_pass.cli.__file__.startswith({str(copy_src)!r}), "
        "garage_pass.cli.__file__\n"
        "import _rendered_sentences as r\n"
        f"out = r.render_and_collect({argv!r})\n"
        "print(json.dumps([[d, sorted(s)] for d, s in out]))\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"the rendering subprocess failed:\n{done.stderr[-1500:]}")
    return [(d, frozenset(s)) for d, s in json.loads(done.stdout)]


def rendered_self_test() -> int:
    docs = ROOT / "tests" / "documents"
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "src" / "garage_pass"
        shutil.copytree(ROOT / "src" / "garage_pass", copy)
        bad = Path(tmp) / "bad_pass.json"
        document = json.loads((docs / "pass_employee.json").read_text())
        document["terms"]["allowed_lanes"] = []
        bad.write_text(json.dumps(document))
        exit_ = ["access", "--garage", str(docs / "garage_downtown.json"), "--pass", str(bad),
                 "--registrations", str(docs / "registrations.json"), "--vehicle", "CAR-1",
                 "--lane", "L1", "--direction", "exit", "--at", "2026-03-02T09:00:00-07:00"]
        # 5. the collector is not vacuous: the unplanted copy renders a route-asserting refusal
        #    (a directory as the garage document) and it is COVERED by cli.py's literal
        directory = ["access", "--garage", tmp, "--pass", str(docs / "pass_employee.json"),
                     "--vehicle", "CAR-1", "--lane", "L1", "--direction", "exit",
                     "--at", "2026-03-02T09:00:00-07:00"]
        collected = _render_from(copy, directory)
        status5, result5 = judge_rendered(collected, src=copy)
        print(f"self-test 5: the unplanted copy, a directory as --garage: {result5['collected']} "
              f"detail(s) collected, {result5['route_asserting']} route-asserting, "
              f"{result5['covered']} covered, exit {status5}")
        if status5 != 0 or result5["route_asserting"] < 1 or result5["covered"] < 1:
            return 1
        # 6. the seventh spelling: a .replace() on a true literal renders "is stored with" and
        #    no literal on the stack produces it -- UNJUDGED
        access = copy / "access.py"
        text = access.read_text()
        if text.count(_RENDER_ANCHOR) != 1:
            print(f"self-test 6: the render anchor appears {text.count(_RENDER_ANCHOR)}x, not once")
            return 1
        access.write_text(text.replace(_RENDER_ANCHOR, _RENDER_PLANT))
        collected = _render_from(copy, exit_)
        status6, result6 = judge_rendered(collected, src=copy)
        named = [u for u in result6["unjudged"] if "is stored with a value" in u]
        print(f"self-test 6: a run-time spelling (.replace on a true literal) rendered from the "
              f"copy: exit {status6}, the rendered falsehood reads UNJUDGED: {bool(named)}")
        if status6 != 1 or not named:
            return 1
        access.write_text(text)
        # 7. the match is not foolable: one word inserted beside a route phrase makes the
        #    rendered text differ from every template by a literal segment -- UNJUDGED, even
        #    though the generic {…} {…} could not be read: {…} template matches the whole
        cli = copy / "cli.py"
        text = cli.read_text()
        if text.count(_FOOL_ANCHOR) != 1:
            print(f"self-test 7: the fool anchor appears {text.count(_FOOL_ANCHOR)}x, not once")
            return 1
        cli.write_text(text.replace(_FOOL_ANCHOR, _FOOL_PLANT))
        collected = _render_from(copy, directory)
        status7, result7 = judge_rendered(collected, src=copy)
        named = [u for u in result7["unjudged"] if "regular file indeed" in u]
        print(f"self-test 7: one word inserted beside 'regular file' in the rendered refusal: "
              f"exit {status7}, matches no template and reads UNJUDGED: {bool(named)}")
        if status7 != 1 or not named:
            return 1
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    status, _ = run()
    print("\nzero FALSE, every hit judged, no stale judgement" if status == 0 else "\nNOT CLEAN")
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
