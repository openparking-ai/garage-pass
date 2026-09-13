"""G15 -- the contract is DERIVED, and derivation is proven by plants, not by reading.

**GENERATION IS NOT VERIFICATION.** Moving a sentence from a document into a
template does not stop it being hand-written: everywhere except the holes it is
still prose nobody checks, and a template whose prose is fixed agrees with itself
perfectly for ever. A generated block asserts only what it DERIVES from its
values.

So each test below plants a value that CONTRADICTS the rendered prose and
requires the prose to change. Anything that survives such a plant is a fixed
string, and a fixed string is design documentation rather than a measurement --
which is fine, as long as nobody reads it as derived.

**AND THE CHECK IS AGAINST THE MEASUREMENT, NEVER AGAINST A SECOND COPY OF THE
CLAIM.** Comparing the document to another rendering of the same template would
agree happily while both carried the same error.

Controls: the guarantee count typed into the generator; the worked example's
outcome sentence made a fixed string; the transitions block reading a typed
list.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import generate_contract as gen  # noqa: E402


@pytest.mark.guarantee("G15")
def test_the_document_on_disk_is_the_generated_one():
    current = gen.DOC.read_text()
    assert current == gen.render(current), (
        "docs/CONTRACT.md does not match its generator. Run scripts/generate_contract.py."
    )


@pytest.mark.guarantee("G15")
def test_every_block_the_document_declares_is_actually_built():
    text = gen.DOC.read_text()
    for name in gen.BLOCKS:
        assert gen.BEGIN.format(name=name) in text
        assert gen.END.format(name=name) in text


@pytest.mark.guarantee("G15")
def test_a_new_guarantee_appears_and_the_count_moves():
    before = gen.block_guarantees()
    gen.GUARANTEES["G99"] = "A planted guarantee that must appear in the document."
    try:
        after = gen.block_guarantees()
    finally:
        del gen.GUARANTEES["G99"]
    assert "G99" not in before and "G99" in after
    assert f"That is {len(gen.GUARANTEES)} guarantees" in before
    assert f"That is {len(gen.GUARANTEES) + 1} guarantees" in after


@pytest.mark.guarantee("G15")
def test_a_new_refusal_a_new_reason_and_a_new_meaning_each_appear():
    for registry, builder, key in (
        (gen.REFUSALS, gen.block_refusals, "REFUSAL_PLANTED"),
        (gen.NOT_COVERED_REASONS, gen.block_not_covered, "PLANTED_REASON"),
        (gen.BARRIER_MEANINGS, gen.block_meanings, "PLANTED_MEANING"),
        (gen.REFUSED_TO_ANSWER, gen.block_refused_to_answer, "planted.field"),
    ):
        before = builder()
        registry[key] = "A planted sentence."
        try:
            after = builder()
        finally:
            del registry[key]
        assert key not in before and key in after and "A planted sentence." in after


@pytest.mark.guarantee("G15")
def test_a_new_answer_field_appears():
    from dataclasses import field, make_dataclass

    before = gen.block_answer_fields()
    Planted = make_dataclass("Planted", [("planted_field", str, field(default=""))],
                             bases=(gen.Answer,), frozen=True)
    original = gen.Answer
    gen.Answer = Planted
    try:
        after = gen.block_answer_fields()
    finally:
        gen.Answer = original
    assert "planted_field" not in before and "planted_field" in after
    assert f"{len(original.__dataclass_fields__) + 1} fields" in after


@pytest.mark.guarantee("G15")
def test_a_changed_transition_changes_the_states_block():
    from garage_pass.passes import State

    before = gen.block_states()
    original = gen.ALLOWED_TRANSITIONS[State.REVOKED]
    gen.ALLOWED_TRANSITIONS[State.REVOKED] = frozenset({State.ACTIVE})
    try:
        after = gen.block_states()
    finally:
        gen.ALLOWED_TRANSITIONS[State.REVOKED] = original
    assert "| `revoked` | — (terminal) |" in before
    assert "| `revoked` | `active` |" in after


@pytest.mark.guarantee("G15")
def test_a_new_document_key_appears():
    before = gen.block_document_keys()
    original = gen.docs.TERMS_KEYS
    gen.docs.TERMS_KEYS = original | {"planted_key"}
    try:
        after = gen.block_document_keys()
    finally:
        gen.docs.TERMS_KEYS = original
    assert "planted_key" not in before and "`planted_key`" in after


@pytest.mark.guarantee("G15")
def test_the_worked_example_is_produced_by_running_and_its_prose_follows_the_outcome():
    """Three renderings whose non-numeric text differs, all reachable from the
    documents as shipped, and a plant that changes a movement changes the
    sentence -- with the values masked, so a moved number does not count."""
    import re

    def masked(text: str) -> str:
        return re.sub(r"[0-9]", "#", text)

    before = gen.block_worked_example()
    assert "**covered** by" in before and "**not covered**" in before
    original = gen.MOVEMENTS
    gen.MOVEMENTS = (("CAR-1", "L1", "entry", "2026-06-01T12:00:00-06:00"),)
    try:
        one = gen.block_worked_example()
        gen.MOVEMENTS = (("", "L1", "entry", "2026-06-01T12:00:00-06:00"),)
        refused = gen.block_worked_example()
    finally:
        gen.MOVEMENTS = original
    assert "**covered** by" in one and "**not covered**" not in one
    assert "**refused to answer**" in refused and "**covered**" not in refused
    assert masked(one) != masked(refused)


@pytest.mark.guarantee("G15")
def test_the_render_refuses_a_document_missing_a_block():
    with pytest.raises(SystemExit, match="has no"):
        gen.render("no markers here")


@pytest.mark.guarantee("G15")
def test_a_code_published_but_produced_nowhere_fails_the_check():
    """An orphan refusal in the registry: before this, regenerating the
    contract silenced it and the suite stayed green (measured). Now the
    orphan scan names it; and, the control, the shipped registries have none."""
    assert gen.orphan_codes() == {}, gen.orphan_codes()
    gen.REFUSALS["REFUSAL_PLANTED_ORPHAN"] = "A planted sentence for a code nothing raises."
    try:
        assert gen.orphan_codes() == {"REFUSALS": ["REFUSAL_PLANTED_ORPHAN"]}
    finally:
        del gen.REFUSALS["REFUSAL_PLANTED_ORPHAN"]
    gen.NOT_COVERED_REASONS["PLANTED_REASON"] = "A planted reason nothing returns."
    try:
        assert gen.orphan_codes() == {"NOT_COVERED_REASONS": ["PLANTED_REASON"]}
    finally:
        del gen.NOT_COVERED_REASONS["PLANTED_REASON"]


# ---------------------------------------------------------------------------
# The route sweep: every published sentence that asserts a route, judged by content.
# ---------------------------------------------------------------------------

import subprocess  # noqa: E402

import sweep_route_sentences as sweep  # noqa: E402


@pytest.mark.guarantee("G15")
def test_every_route_asserting_sentence_is_judged_by_content_and_none_is_false():
    """A sentence true when written and false after a later round opened a new
    door survived one sweep because that sweep's denominator was the registries
    and the prose, never the DETAILS the operator reads in an answer. The shipped
    sweep derives its denominator (every string literal in the package by AST,
    the registries and guarantees by import, README and CONTRACT), flags every
    route-asserting sentence, and requires a recorded judgement KEYED BY THE
    SENTENCE'S CONTENT AND ITS FILE -- so an edit makes it unjudged, and so does
    the same sentence standing in a file it was not judged in (measured before
    this: keyed by content alone, a store-write sentence judged TRUE in
    ``records.py`` inherited TRUE when copied into the document door in
    ``access.py``, and the operator read "is stored" from a document again). An
    unjudged hit, a FALSE one, or a stale judgement fails this test. Zero FALSE
    is the property, not zero hits."""
    status, result = sweep.run(quiet=True)
    assert result["found"] >= 40, (
        f"the sweep found {result['found']} sentences: the instrument is broken"
    )
    assert result["unjudged"] == [], f"UNJUDGED route-asserting sentence(s): {result['unjudged']}"
    assert result["false"] == [], f"a published sentence judged FALSE: {result['false']}"
    assert result["stale"] == [], (
        f"stale judgement(s) for sentences that no longer exist: {result['stale']}"
    )
    assert status == 0


@pytest.mark.guarantee("G15")
def test_the_route_sweep_goes_red_on_a_falsehood_planted_where_it_was_not_looking():
    """The instrument proven able to fail, on a COPY of the source: a "stored"
    falsehood planted into the GARAGE_UNREADABLE detail -- not the PASS one the
    sweep was built for -- must be named UNJUDGED; a judged-true sentence edited
    by one word must read UNJUDGED (content-keyed, not line-keyed); a judged-true
    sentence copied VERBATIM into a file it does not stand in must read UNJUDGED
    there (file-keyed: the same sentence in a new file is a new question); the
    unmodified tree must read clean. A sweep that only catches the line already
    known has not widened."""
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "sweep_route_sentences.py"),
                           "--self-test"], capture_output=True, text=True, cwd=ROOT)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "named: 'garage {…} is stored with a value this module refuses to read" in done.stdout
    assert "edited by one word: exit 1, reads UNJUDGED: True" in done.stdout, done.stdout
    assert "the same sentence in a NEW file reads UNJUDGED: True" in done.stdout, done.stdout
    assert "the unmodified tree: exit 0" in done.stdout, done.stdout
