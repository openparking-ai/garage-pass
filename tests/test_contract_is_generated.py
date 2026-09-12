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
