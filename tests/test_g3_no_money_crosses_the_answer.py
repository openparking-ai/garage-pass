"""G3 -- no fee, no amount, no balance and no barrier command crosses the call.

The answer's fields are enumerated from the dataclass and none is money-shaped
or gate-shaped; the schema's columns are read from the catalogue and none is
money-shaped or reservation-shaped; a document carrying such a field is
refused rather than ignored; the command line's JSON carries no such key.

The word lists are the instrument, so each has a positive control: a name
built from the list must be caught, or an empty result is blindness.

Controls: a monetary field planted onto Answer; a money column planted into
the migration; the unknown-key refusal planted away in documents.py.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from fixtures import NOON_MONDAY, a_pass, pass_document, registered, transient_garage
from garage_pass import findings as f
from garage_pass.access import Answer, access
from garage_pass.documents import load_garage, load_pass
from garage_pass.terms import Direction
from store_harness import store_test

#: What a money field or a barrier command would be called. A name containing
#: one of these is refused; the control below proves the list catches.
MONEY_WORDS = ("amount", "fee", "price", "balance", "currency", "minor", "cost", "charge",
               "invoice", "paid", "pay")
GATE_WORDS = ("open", "close", "gate", "admit", "barrier", "allow_exit", "refuse_exit")
RESERVATION_WORDS = ("reservation", "booking")

FIELDS = tuple(Answer.__dataclass_fields__)


def offending(names, words) -> list[str]:
    return [n for n in names if any(w in n.lower() for w in words)]


@pytest.mark.guarantee("G3")
def test_the_answer_carries_no_money_and_no_barrier_command():
    assert offending(FIELDS, MONEY_WORDS) == []
    assert offending(FIELDS, GATE_WORDS) == []
    assert offending(FIELDS, RESERVATION_WORDS) == []
    assert len(FIELDS) >= 10, "the scan is pointed at a real set of fields"


@pytest.mark.guarantee("G3")
def test_the_word_lists_catch_what_they_are_for():
    """The positive control: names a defect would use are caught."""
    assert offending(("amount_minor", "fee_due", "balance"), MONEY_WORDS) == [
        "amount_minor", "fee_due", "balance"
    ]
    assert offending(("open_gate", "admit"), GATE_WORDS) == ["open_gate", "admit"]
    assert offending(("reservation_id",), RESERVATION_WORDS) == ["reservation_id"]
    assert offending(FIELDS, ("outcome",)) == ["outcome"], "and the scan sees real fields"


@pytest.mark.guarantee("G3")
def test_no_answer_value_is_a_number_that_could_be_read_as_one():
    """Beyond names: no field of any answer is numeric. A count of visits is
    in the sentence, deliberately, where nothing can add it up."""
    garage = transient_garage()
    pass_ = a_pass()
    for direction in Direction:
        answer = access(
            garage=garage, passes=[pass_], registrations=[registered(pass_)], visits=[],
            vehicle_identity="CAR-1", lane="L1", direction=direction, at=NOON_MONDAY,
        )
        for field in dataclasses.fields(answer):
            value = getattr(answer, field.name)
            assert not isinstance(value, int | float) or isinstance(value, bool), field.name


@pytest.mark.guarantee("G3")
@pytest.mark.parametrize(
    "where,key",
    [("terms", "price_minor"), ("terms", "reservation_id"), ("pass", "amount"),
     ("garage", "fee"), ("holder", "balance")],
)
def test_a_document_with_a_field_this_module_does_not_know_is_refused(where, key):
    document = pass_document()
    if where == "garage":
        with pytest.raises(f.Refused) as refused:
            load_garage({"id": "g", "timezone": "UTC", "transient_available": True, key: 1})
    else:
        target = document if where == "pass" else document[where]
        target[key] = 1
        with pytest.raises(f.Refused) as refused:
            load_pass(document)
    assert refused.value.code == f.REFUSAL_UNKNOWN_FIELD
    assert refused.value.field.endswith(f".{key}")


@pytest.mark.guarantee("G3")
def test_the_command_line_answer_carries_no_such_key(tmp_path, capsys):
    from garage_pass.cli import main

    garage = tmp_path / "g.json"
    garage.write_text(json.dumps({"id": "garage-downtown", "timezone": "America/Denver",
                                  "transient_available": True}))
    pass_ = tmp_path / "p.json"
    pass_.write_text(json.dumps(pass_document()))
    regs = tmp_path / "r.json"
    regs.write_text(json.dumps([{"pass_id": "pass-1", "vehicle_identity": "CAR-1",
                                 "effective_day": "2026-01-01"}]))
    status = main(["access", "--garage", str(garage), "--pass", str(pass_),
                   "--registrations", str(regs), "--vehicle", "CAR-1", "--lane", "L1",
                   "--direction", "entry", "--at", "2026-06-01T12:00:00-06:00"])
    printed = json.loads(capsys.readouterr().out)
    assert status == 0 and printed["outcome"] == "covered", printed
    assert offending(printed, MONEY_WORDS + GATE_WORDS + RESERVATION_WORDS) == []


@pytest.mark.guarantee("G3")
@store_test
def test_the_schema_has_no_money_shaped_or_reservation_shaped_column(app):
    from garage_pass.store.postgres import columns_named_like

    assert columns_named_like(app, MONEY_WORDS) == []
    assert columns_named_like(app, RESERVATION_WORDS) == []
    assert columns_named_like(app, GATE_WORDS) == []
    assert columns_named_like(app, ("email",)) == ["passes.holder_email"], (
        "the control: the same query finds a column that IS there"
    )
