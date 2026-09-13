"""G22 -- the typed vehicle description decides nothing.

**THE MATRIX IS THE GUARANTEE**, in the shape G13 uses for the label. For every
identity a lane might measure -- one that spells the description exactly, one
that spells it in another case, one it contains, one unrelated -- enrolments
that differ only in ``vehicle_description`` redeem IDENTICALLY: the same
outcome, the same refusal code, the same answer; and in the two refusal
situations that carry an identity (on another pass; already used) the same
again. The description is reported on the enrolment and that is the only
place it may differ.

Its power is measured: five spellings of a description-keyed branch are
planted as its controls -- an equality, a containment, a case-folded equality,
a prefix, a length -- and each must redden the matrix.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from enrolment_harness import GARAGES, credential, issue, redeem, seeded
from fixtures import NOON_MONDAY, a_pass, at
from garage_pass.passes import State
from garage_pass.store.postgres import tenant
from garage_pass.store.records import create_pass, register_vehicle
from store_harness import needs_postgres

pytestmark = needs_postgres

#: The description is free text. The last spells an identity a lane measures.
DESCRIPTIONS = (None, "silver Toyota, dented rear bumper", "CAR-1", "car-1",
                "the one with CAR-1 on it")
#: What a lane measures: opaque values, some of which happen to look like a description.
IDENTITIES = ("CAR-1", "car-1", "CAR-2", "silver Toyota, dented rear bumper")


def outcome(redemption) -> tuple:
    """Everything a redemption returned, minus what may legitimately differ
    (the enrolment's own id): the outcome the description must not move."""
    refusal = redemption.refusal
    return (
        redemption.redeemed,
        (refusal.code, refusal.field) if refusal else None,
        replace(redemption.answer, detail=""),
        redemption.registration and redemption.registration["vehicle_identity"],
        redemption.pass_state_change and redemption.pass_state_change["to"],
    )


SITUATIONS = ("fresh", "identity on another pass", "already used")


def situated(app, tenant_id, garage, situation: str, identity: str) -> None:
    """The same situation at every garage, before the QR is presented."""
    if situation == "identity on another pass":
        holder = a_pass(id="pass-holding", garage_id=garage.id, state=State.ACTIVE)
        with tenant(app, tenant_id) as cursor:
            create_pass(cursor, tenant_id, garage.id, holder, by="seed", at=NOON_MONDAY)
            register_vehicle(cursor, tenant_id, garage.id, holder.id, identity, date(2026, 1, 1))
        app.commit()


@pytest.mark.guarantee("G22")
@pytest.mark.parametrize("situation", SITUATIONS)
@pytest.mark.parametrize("identity", IDENTITIES)
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
def test_enrolments_differing_only_in_description_redeem_identically(
    app, tenant_id, garage, identity, situation
):
    """One garage of the same shape per description -- one car, one pass is
    per garage, so each redemption meets the same situation -- and the same
    identity presented to each. Every outcome must be the same."""
    outcomes = []
    for i, description in enumerate(DESCRIPTIONS):
        here = replace(garage, id=f"{garage.id}-{i}")
        pass_ = seeded(app, tenant_id, here)
        situated(app, tenant_id, here, situation, identity)
        token = issue(app, tenant_id, here, pass_, f"qr-{i}", vehicle_description=description)[
            "token"
        ]
        if situation == "already used":
            assert redeem(app, tenant_id, here, token, "CAR-9", "L1").redeemed
        out = redeem(app, tenant_id, here, token, identity, "L1", at=at(date(2026, 6, 2), 9))
        # The description is REPORTED, and that is the only place it may differ.
        assert credential(app, tenant_id, f"qr-{i}").vehicle_description == description
        outcomes.append(outcome(out))
    first, rest = outcomes[0], outcomes[1:]
    assert all(o == first for o in rest), [o for o in rest if o != first]
    expected = {"fresh": None, "identity on another pass": ("REFUSAL_VEHICLE_ON_ANOTHER_PASS",
                                                            "vehicle_identity"),
                "already used": ("REFUSAL_CREDENTIAL_ALREADY_USED", "enrolment")}[situation]
    assert first[1] == expected, "the situation, not the description, decided"
    assert first[0] is (situation == "fresh")


@pytest.mark.guarantee("G22")
def test_a_mismatch_between_the_description_and_the_identity_is_not_a_refusal(app, tenant_id):
    """The car the holder said they would bring, and a different car measured
    at the lane: bound, covered, the description untouched."""
    pass_ = seeded(app, tenant_id, GARAGES[0])
    token = issue(app, tenant_id, GARAGES[0], pass_, vehicle_description="silver Toyota")["token"]
    out = redeem(app, tenant_id, GARAGES[0], token, "BLACK-VAN-7")
    assert out.redeemed and out.registration["vehicle_identity"] == "BLACK-VAN-7"
    assert out.answer.vehicle_identity == "BLACK-VAN-7"
    read = credential(app, tenant_id, "qr-1")
    assert read.vehicle_description == "silver Toyota"


@pytest.mark.guarantee("G22")
def test_the_description_is_stated_or_absent_and_blank_is_refused(app, tenant_id):
    from garage_pass import findings as f

    pass_ = seeded(app, tenant_id, GARAGES[1], state=State.ACTIVE)
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, GARAGES[1].id, pass_.id, "CAR-0", date(2026, 1, 1))
    app.commit()
    with pytest.raises(f.Refused) as refused:
        issue(app, tenant_id, GARAGES[1], pass_, vehicle_description="   ")
    app.rollback()
    assert refused.value.code == f.REFUSAL_FIELD_BLANK
    assert refused.value.field == "vehicle_description"
    assert issue(app, tenant_id, GARAGES[1], pass_)["vehicle_description"] is None
