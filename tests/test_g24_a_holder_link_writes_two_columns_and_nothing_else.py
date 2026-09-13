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
