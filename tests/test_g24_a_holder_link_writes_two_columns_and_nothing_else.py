"""G24 -- a holder link writes ``holder_name`` and ``holder_phone`` on the pass,
and nothing else.

**THE WRITE IS NARROW AND PROVEN NARROW.** Every column of the pass row -- and
its windows and lanes -- is read before the redemption and after, and only the
two named columns may differ. A credential that arrives by email must not be
able to rewrite the terms of the pass it opens. The control plants a wider
UPDATE and the test names the column it should not have touched.

**ONE TRANSACTION, ONE USE.** Redeeming the link writes the two columns,
issues an enrolment for that pass with the link as the issuer -- the
enrolment's token returned once, here -- and spends the link; a blank name
refuses the whole and nothing is written. The owner-only path stands: an
owner issues an enrolment with no link ever used.

Controls: the UPDATE widened to the label; the enrolment's issuer planted to
'owner'; the link's spend planted away.
"""

from __future__ import annotations

from datetime import date

import pytest

from enrolment_harness import (
    HOLDER_LINK,
    NO_TRANSIENT,
    TRANSIENT_ENTRY,
    credential,
    enrolment_row,
    issue,
    issue_link,
    link_row,
    redeem,
    redeem_link,
    seeded,
)
from fixtures import at, everything_terms
from garage_pass import findings as f
from garage_pass.store.postgres import tenant
from store_harness import needs_postgres, query

pytestmark = needs_postgres

TWO = ("holder_name", "holder_phone")


def pass_row(app, tenant_id, pass_) -> dict:
    """Every column of the pass row by name, plus its windows and lanes."""
    with tenant(app, tenant_id) as cursor:
        cursor.execute("SELECT * FROM passes WHERE external_id = %s", (pass_.id,))
        names = [d.name for d in cursor.description]
        row = dict(zip(names, cursor.fetchone(), strict=True))
        cursor.execute(
            "SELECT days, start_minute, end_minute, position FROM pass_windows "
            "WHERE pass_id = %s ORDER BY position", (row["id"],),
        )
        row["_windows"] = cursor.fetchall()
        cursor.execute("SELECT lane FROM pass_lanes WHERE pass_id = %s ORDER BY lane", (row["id"],))
        row["_lanes"] = cursor.fetchall()
    app.rollback()
    return row


@pytest.mark.guarantee("G24")
def test_the_redemption_writes_the_two_columns_and_every_other_column_is_unchanged(app, tenant_id):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY, terms=everything_terms())
    link = issue_link(app, tenant_id, TRANSIENT_ENTRY, pass_)
    before = pass_row(app, tenant_id, pass_)
    assert before["holder_name"] == "A Holder" and before["holder_email"] == "holder@example.com"
    assert len(before) >= 20 and before["_windows"] and before["_lanes"], "a real row, fully termed"
    out = redeem_link(app, tenant_id, TRANSIENT_ENTRY, link["token"], name="Her Own Name",
                      phone="+1 555 0199", vehicle_description="silver Toyota")
    after = pass_row(app, tenant_id, pass_)
    assert after["holder_name"] == "Her Own Name" and after["holder_phone"] == "+1 555 0199"
    touched = sorted(k for k in before if before[k] != after[k])
    assert touched == sorted(TWO), f"the link wrote {touched}; only {TWO} may change"
    assert out["holder_name"] == "Her Own Name" and out["pass"] == pass_.id
    # the description went on the ENROLMENT, not the pass
    assert "vehicle_description" not in after
    assert out["enrolment"]["vehicle_description"] == "silver Toyota"
    assert credential(app, tenant_id, "qr-from-link").vehicle_description == "silver Toyota"


@pytest.mark.guarantee("G24")
def test_the_enrolment_the_link_issues_names_the_link_as_its_issuer_and_the_link_is_spent(
    app, tenant_id
):
    pass_ = seeded(app, tenant_id, NO_TRANSIENT)
    link = issue_link(app, tenant_id, NO_TRANSIENT, pass_, "link-7")
    when = at(date(2026, 6, 2), 9)
    out = redeem_link(app, tenant_id, NO_TRANSIENT, link["payload"], at=when)
    issued = out["enrolment"]
    assert issued["issued_by"] == "link-7" and issued["issued_at"] == when
    assert query(app, tenant_id, "SELECT issued_by FROM enrolments") == [("link-7",)]
    assert link_row(app, tenant_id, "link-7") == ("redeemed", when, None, None, None)
    assert credential(app, tenant_id, "link-7", HOLDER_LINK).redeemed_at == when
    # the QR it issued works, once, like any other
    assert redeem(app, tenant_id, NO_TRANSIENT, issued["token"], "CAR-1", at=when).redeemed
    assert enrolment_row(app, tenant_id, "qr-from-link")[1] == "CAR-1"


@pytest.mark.guarantee("G24")
@pytest.mark.parametrize("name,phone,field", [("  ", "1", "holder.name"), ("A", "", "holder.phone"),
                                              (None, "1", "holder.name")])
def test_a_blank_name_or_phone_refuses_the_whole_and_writes_nothing(
    app, tenant_id, name, phone, field
):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    link = issue_link(app, tenant_id, TRANSIENT_ENTRY, pass_)
    before = pass_row(app, tenant_id, pass_)
    with pytest.raises(f.Refused) as refused:
        redeem_link(app, tenant_id, TRANSIENT_ENTRY, link["token"], name=name, phone=phone)
    app.rollback()
    assert refused.value.code == f.REFUSAL_FIELD_BLANK and refused.value.field == field
    assert pass_row(app, tenant_id, pass_) == before
    assert link_row(app, tenant_id)[0] == "issued"
    assert query(app, tenant_id, "SELECT count(*) FROM enrolments") == [(0,)]


@pytest.mark.guarantee("G24")
def test_days_valid_absent_at_the_link_redemption_refuses_the_whole(app, tenant_id):
    """The enrolment half refuses by name; the link is not spent and the
    holder's details are not written: one transaction."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    link = issue_link(app, tenant_id, TRANSIENT_ENTRY, pass_)
    before = pass_row(app, tenant_id, pass_)
    with pytest.raises(f.Refused) as refused:
        redeem_link(app, tenant_id, TRANSIENT_ENTRY, link["token"], name="Her", phone="1",
                    days_valid=None)
    app.rollback()
    assert refused.value.code == f.REFUSAL_DAYS_VALID_NOT_STATED
    assert pass_row(app, tenant_id, pass_) == before
    assert link_row(app, tenant_id)[0] == "issued"


@pytest.mark.guarantee("G24")
def test_the_owner_only_path_stands_no_link_is_needed_to_enrol(app, tenant_id):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    out = issue(app, tenant_id, TRANSIENT_ENTRY, pass_)
    assert out["issued_by"] == "owner"
    assert query(app, tenant_id, "SELECT count(*) FROM holder_links") == [(0,)]
    assert redeem(app, tenant_id, TRANSIENT_ENTRY, out["token"], "CAR-1").redeemed


# ---------------------------------------------------------------------------
# CONTROL CHARACTERS IN THE HOLDER'S TEXT -- the fix round. Measured at the
# L3: a NUL in holder_name reached the driver and came back as the generic
# configuration-class sentence, not a refusal. The module's ONE text validator,
# require_text, now refuses a control character by name wherever it is used --
# and, held in the same run so the fix cannot quietly become an ASCII rule, a
# name with accented letters and names in non-Latin scripts are ACCEPTED.
# ---------------------------------------------------------------------------

CONTROL = [
    ("NUL", "A\x00B", "U+0000"),
    ("a line break inside", "A\nB", "U+000A"),
    ("a tab inside", "A\tB", "U+0009"),
    ("a C1 control (U+0085)", "A\x85B", "U+0085"),
    ("NUL alone, which no strip removes", "\x00", "U+0000"),
]

LETTERS_IN_ANY_SCRIPT = ["José Müller-Løvstad", "山田 太郎", "Ольга Іванівна", "أحمد بن علي",
                         "Ελένη Παπαδοπούλου", "Nguyễn Thị Hoa", "Zoë O'Brien"]


@pytest.mark.guarantee("G24")
@pytest.mark.parametrize("label,name,code_point", CONTROL, ids=[c[0] for c in CONTROL])
def test_a_control_character_in_the_holders_name_is_refused_by_name_and_writes_nothing(
    app, tenant_id, label, name, code_point
):
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    link = issue_link(app, tenant_id, TRANSIENT_ENTRY, pass_)
    before = pass_row(app, tenant_id, pass_)
    with pytest.raises(f.Refused) as refused:
        redeem_link(app, tenant_id, TRANSIENT_ENTRY, link["token"], name=name, phone="1")
    app.rollback()
    expected = f.REFUSAL_FIELD_BLANK if not name.strip() else f.REFUSAL_TEXT_HAS_CONTROL_CHARACTERS
    assert refused.value.code == expected and refused.value.field == "holder.name", label
    if expected == f.REFUSAL_TEXT_HAS_CONTROL_CHARACTERS:
        assert code_point in refused.value.detail, "the refusal names the character"
    assert pass_row(app, tenant_id, pass_) == before
    assert link_row(app, tenant_id)[0] == "issued"
    # the phone, by the same validator
    with pytest.raises(f.Refused) as refused:
        redeem_link(app, tenant_id, TRANSIENT_ENTRY, link["token"], name="A Holder", phone=name)
    app.rollback()
    assert refused.value.field == "holder.phone"


@pytest.mark.guarantee("G24")
@pytest.mark.parametrize("name", LETTERS_IN_ANY_SCRIPT)
def test_letters_in_any_script_are_a_name_and_are_accepted(app, tenant_id, name):
    """THE CONTROL THAT STOPS THE FIX BECOMING AN ASCII RULE: this module is
    for garages anywhere, and a validator that refuses a real person's name
    is a worse defect than the one being fixed. Accented Latin, CJK,
    Cyrillic, Arabic, Greek, Vietnamese, an apostrophe and a diaeresis --
    written, read back, and the enrolment issued."""
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY)
    link = issue_link(app, tenant_id, TRANSIENT_ENTRY, pass_)
    try:
        out = redeem_link(app, tenant_id, TRANSIENT_ENTRY, link["token"], name=name)
    except f.Refused as refused:  # judged as an assertion, so a fail control reads it as one
        app.rollback()
        pytest.fail(f"a real person's name was refused: {refused}")
    assert out["holder_name"] == name
    assert query(app, tenant_id, "SELECT holder_name FROM passes") == [(name,)]
    assert link_row(app, tenant_id)[0] == "redeemed"
    assert enrolment_row(app, tenant_id, "qr-from-link")[0] == "issued"


#: What ``str.strip()`` removes at the edges, among the Cc code points: the ten
#: Python counts as whitespace. Written out so the census below is an assertion
#: about a named set, not a discovery.
EDGE_STRIPPED = frozenset("\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f\x85")


@pytest.mark.guarantee("G24")
def test_every_cc_code_point_is_refused_inside_and_the_ten_whitespace_ones_stripped_at_the_edge():
    """THE CENSUS THE MERGE GATE RAN, kept as a test: every Unicode Cc code
    point, placed INSIDE text and at its EDGE, against the one validator.
    Inside, all 65 are refused by name. At the edge, exactly the ten that
    Python's ``str.isspace`` counts as whitespace are stripped -- the text is
    accepted without them, as a scanner's trailing line break is -- and the
    other 55 are refused; NUL is refused in every position. The registry
    sentence for the refusal is measured by the SAME instrument: it must name
    the inside rule, the edge rule and the ten, so the published sentence and
    the behaviour cannot drift apart unnoticed."""
    import unicodedata

    from garage_pass.garage import require_text

    cc = [chr(i) for i in range(0x110000) if unicodedata.category(chr(i)) == "Cc"]
    assert len(cc) == 65, "the Unicode Cc block, as this interpreter's unicodedata knows it"
    assert EDGE_STRIPPED == {ch for ch in cc if ch.isspace()}, "the ten, by Python's own rule"

    def outcome(value: str) -> str:
        try:
            return "accepted:" + require_text(value, "holder.name")
        except f.Refused as refused:
            return "refused:" + refused.code

    inside = {ch: outcome("a" + ch + "b") for ch in cc}
    edge = {ch: outcome("ab" + ch) for ch in cc}
    refused_inside = {ch for ch, out in inside.items()
                      if out == "refused:" + f.REFUSAL_TEXT_HAS_CONTROL_CHARACTERS}
    stripped_at_edge = {ch for ch, out in edge.items() if out == "accepted:ab"}
    refused_at_edge = {ch for ch, out in edge.items() if out.startswith("refused:")}
    assert refused_inside == set(cc), f"inside: {len(refused_inside)}/65 refused by name"
    assert stripped_at_edge == EDGE_STRIPPED, sorted(f"U+{ord(c):04X}" for c in stripped_at_edge)
    assert refused_at_edge == set(cc) - EDGE_STRIPPED, "the other 55 are refused at the edge"
    assert outcome("ab\x00") == outcome("\x00ab") == outcome("\x00") == (
        "refused:" + f.REFUSAL_TEXT_HAS_CONTROL_CHARACTERS
    ), "NUL is never whitespace and never stripped"
    ten = ", ".join(f"U+{ord(c):04X}" for c in sorted(EDGE_STRIPPED))
    print(f"Cc census: inside refused {len(refused_inside)}/65; edge stripped "
          f"{len(stripped_at_edge)}/65 ({ten}); edge refused {len(refused_at_edge)}/65")
    # the published sentence, against the same measurement
    sentence = f.REFUSALS[f.REFUSAL_TEXT_HAS_CONTROL_CHARACTERS]
    assert "INSIDE it" in sentence, "the sentence must say the check is on the inside"
    assert "either edge" in sentence and "stripped" in sentence, "edge whitespace is stripped"
    assert "ten Cc code points" in sentence, "and how many are stripped"
    for named in ("TAB", "LF", "VT", "FF", "CR", "U+001C to U+001F", "U+0085"):
        assert named in sentence, f"the sentence must name {named}"
    assert "NUL is never whitespace and never stripped" in sentence
    assert "wherever the module reads text" in sentence


@pytest.mark.guarantee("G24")
def test_the_one_validator_refuses_a_control_character_wherever_text_is_read():
    """One validator, one behaviour: ids, lanes, labels, the actor, the
    description, a token -- the same refusal by name from require_text, and
    whitespace AROUND the text is not part of it (a scanner's trailing line
    break after a QR payload is the measured case): stripped, not refused."""
    from garage_pass.garage import require_text

    for field in ("enrolment.id", "lane", "pass.label", "issued_by", "vehicle_description",
                  "token"):
        with pytest.raises(f.Refused) as refused:
            require_text("x\x00y", field)
        assert refused.value.code == f.REFUSAL_TEXT_HAS_CONTROL_CHARACTERS
        assert refused.value.field == field
    assert require_text("  payload \n", "token") == "payload"
    assert require_text("\tL1\r\n", "lane") == "L1"
    for name in LETTERS_IN_ANY_SCRIPT:
        try:
            assert require_text(name, "holder.name") == name
        except f.Refused as refused:
            pytest.fail(f"a real person's name was refused: {refused}")
