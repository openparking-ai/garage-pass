"""G20 -- the enrolment opens nothing on its own, and where a garage enrols
follows from whether it sells transient parking (R1).

**ONE ANSWER, ONE PATH.** The redemption's answer is what
``store.access.answer_in_transaction`` returned for that movement on the rows
as written; after the commit, ``access_from_store`` with the same inputs
returns the identical value. Two layers deciding one concept is the trap this
estate keeps re-learning, so the control plants a divergence -- a detail the
enrolment path spells for itself -- and the equality must go red.

**R1, AS DERIVATION.** A garage with no transient parking does not admit an
unregistered vehicle, so it enrols at entry and need state nothing:
``where_enrolment_happens`` derives it from the stated ``transient_available``.
A transient garage has a choice; unstated, the redemption refuses to answer
naming ``garage.enrols_at`` -- and ``garage.transient_available`` first, when
that is what is unstated, since it is the field that decides. No transient
AND enrols at exit is a contradiction: refused by name where the garage is
built, where the field is repaired (G12's file), and by the CHECK for a raw
write. A QR at the wrong end is refused naming the end this garage enrols at.

Controls: a divergence planted into the redemption's answer; the unstated
enrols_at defaulted to entry; the derived entry planted to exit; the
contradiction check planted away; the CHECK removed from the migration; the
wrong-end refusal planted away.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from enrolment_harness import (
    GARAGES,
    NO_TRANSIENT,
    TRANSIENT_ENTRY,
    TRANSIENT_EXIT,
    TRANSIENT_UNSTATED,
    issue,
    other_end,
    pass_state,
    redeem,
    registrations,
    seeded,
)
from fixtures import NOON_MONDAY, SHIFTING_ZONE, at, unstated_garage
from garage_pass import findings as f
from garage_pass.access import Outcome
from garage_pass.documents import GARAGE_KEYS, load_garage
from garage_pass.enrolment import where_enrolment_happens
from garage_pass.garage import Garage
from garage_pass.store.access import access_from_store
from garage_pass.terms import Direction
from store_harness import needs_postgres, seed


@pytest.mark.guarantee("G20")
def test_a_no_transient_garage_derives_entry_and_a_transient_one_states_it():
    assert NO_TRANSIENT.enrols_at is None, "it need not state it"
    assert where_enrolment_happens(NO_TRANSIENT) == "entry"
    assert where_enrolment_happens(TRANSIENT_ENTRY) == "entry"
    assert where_enrolment_happens(TRANSIENT_EXIT) == "exit"
    stated_anyway = Garage(id="g", timezone=SHIFTING_ZONE, transient_available=False,
                           enrols_at="entry")
    assert where_enrolment_happens(stated_anyway) == "entry"


@pytest.mark.guarantee("G20")
def test_unstated_refuses_to_answer_naming_the_field_that_decides_transient_first():
    with pytest.raises(f.Refused) as refused:
        where_enrolment_happens(TRANSIENT_UNSTATED)
    assert refused.value.code == f.REFUSAL_WHERE_TO_ENROL_UNSTATED
    assert refused.value.field == "garage.enrols_at"
    with pytest.raises(f.Refused) as refused:
        where_enrolment_happens(unstated_garage())  # transient unstated, enrols_at unstated
    assert refused.value.code == f.REFUSAL_WHERE_TO_ENROL_UNSTATED
    assert refused.value.field == "garage.transient_available", "the field that decides, first"
    both_stated_but_transient_unknown = Garage(id="g", timezone=SHIFTING_ZONE,
                                               transient_available=None, enrols_at="exit")
    with pytest.raises(f.Refused) as refused:
        where_enrolment_happens(both_stated_but_transient_unknown)
    assert refused.value.field == "garage.transient_available"


@pytest.mark.guarantee("G20")
def test_no_transient_and_enrols_at_exit_is_refused_where_the_garage_is_built():
    with pytest.raises(f.Refused) as refused:
        Garage(id="g", timezone=SHIFTING_ZONE, transient_available=False, enrols_at="exit")
    assert refused.value.code == f.REFUSAL_ENROLS_AT_CONTRADICTS_TRANSIENT
    assert refused.value.field == "garage.enrols_at"
    with pytest.raises(f.Refused) as refused:
        Garage(id="g", timezone=SHIFTING_ZONE, transient_available=True, enrols_at="middle")
    assert refused.value.code == f.REFUSAL_FIELD_BLANK
    assert refused.value.field == "garage.enrols_at"
    # the document door: the key is derived from the dataclass, and the same refusal
    assert "enrols_at" in GARAGE_KEYS
    assert load_garage({"id": "g", "timezone": SHIFTING_ZONE, "transient_available": True,
                        "enrols_at": "exit"}).enrols_at == "exit"
    with pytest.raises(f.Refused) as refused:
        load_garage({"id": "g", "timezone": SHIFTING_ZONE, "transient_available": False,
                     "enrols_at": "exit"})
    assert refused.value.code == f.REFUSAL_ENROLS_AT_CONTRADICTS_TRANSIENT


@pytest.mark.guarantee("G20")
@needs_postgres[0]
@needs_postgres[1]
def test_the_check_is_the_backstop_for_a_raw_write(owner, tenant_id):
    """Both columns on one table, so the CHECK holds whichever a raw write
    moves; and the control that the same raw write with the other value lands."""
    for transient, end, lands in ((False, "exit", False), (True, "exit", True),
                                  (False, "entry", True), (None, "exit", True)):
        with owner.cursor() as cursor:  # the owner connection is autocommit
            try:
                cursor.execute(
                    "INSERT INTO garages (tenant_id, external_id, timezone, transient_available, "
                    "enrols_at) VALUES (%s, %s, 'UTC', %s, %s)",
                    (tenant_id, f"raw-{transient}-{end}", transient, end),
                )
                landed = True
            except psycopg.errors.CheckViolation as violation:
                landed = False
                assert violation.diag.constraint_name == (
                    "garages_no_transient_means_enrols_at_entry"
                )
        assert landed is lands, (transient, end)
    with owner.cursor() as cursor:
        # and moving the OTHER column into the contradiction is caught too
        with pytest.raises(psycopg.errors.CheckViolation):
            cursor.execute(
                "UPDATE garages SET transient_available = false WHERE tenant_id = %s "
                "AND external_id = 'raw-True-exit'", (tenant_id,),
            )


@pytest.mark.guarantee("G20")
@needs_postgres[0]
@needs_postgres[1]
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
def test_the_redemptions_answer_is_the_access_calls_answer_for_the_same_movement(
    app, tenant_id, garage
):
    """Identical to calling access with the same inputs after the bind -- and,
    when the bind is refused, identical to calling it as things stood."""
    pass_ = seeded(app, tenant_id, garage)
    token = issue(app, tenant_id, garage, pass_)["token"]
    end = Direction(where_enrolment_happens(garage))
    when = at(date(2026, 6, 2), 9)
    out = redeem(app, tenant_id, garage, token, "CAR-1", "L1", at=when)
    assert out.redeemed
    same = access_from_store(app, tenant_id, garage.id, "CAR-1", "L1", end, when)
    assert out.answer == same
    assert out.answer.outcome is Outcome.COVERED and out.answer.means == f.MEANS_COVERED
    again = redeem(app, tenant_id, garage, token, "CAR-2", "L1", at=when)
    assert not again.redeemed
    assert again.answer == access_from_store(app, tenant_id, garage.id, "CAR-2", "L1", end, when)


@pytest.mark.guarantee("G20")
@needs_postgres[0]
@needs_postgres[1]
def test_the_answer_is_the_access_calls_even_when_it_does_not_cover(app, tenant_id):
    """The bind lands; the pass's terms do not cover this movement (a Mon-Fri
    window, presented on a Sunday); the lane is told exactly that. The
    enrolment opened nothing: whatever the terms say is what the lane hears.
    The instance is TEMPORAL on purpose: an employee enrolling at the weekend
    is the ordinary case and must bind. (It was the exit-only pass at an
    entry-enrolling garage until the fix round refused that STRUCTURAL case
    by name -- G19 holds the distinction.)"""
    from fixtures import WEEKDAYS, simple_terms
    from garage_pass.terms import Window

    weekdays = Window(days=WEEKDAYS, start_minute=0, end_minute=1440)
    pass_ = seeded(app, tenant_id, TRANSIENT_ENTRY, terms=simple_terms(windows=(weekdays,)))
    sunday = at(date(2026, 6, 7), 12)
    token = issue(app, tenant_id, TRANSIENT_ENTRY, pass_, starts_on=date(2026, 6, 7))["token"]
    out = redeem(app, tenant_id, TRANSIENT_ENTRY, token, "CAR-1", at=sunday)
    assert out.redeemed and pass_state(app, tenant_id, pass_) == "active"
    assert out.answer.outcome is Outcome.NOT_COVERED
    assert out.answer.reason == f.OUTSIDE_WINDOW
    assert out.answer.means == f.MEANS_TRANSIENT_STAY
    assert out.answer == access_from_store(app, tenant_id, TRANSIENT_ENTRY.id, "CAR-1", "L1",
                                           Direction.ENTRY, sunday)


@pytest.mark.guarantee("G20")
@needs_postgres[0]
@needs_postgres[1]
@pytest.mark.parametrize("garage", GARAGES, ids=[g.id for g in GARAGES])
def test_a_qr_at_the_wrong_end_is_refused_naming_the_end_and_writes_nothing(
    app, tenant_id, garage
):
    pass_ = seeded(app, tenant_id, garage)
    token = issue(app, tenant_id, garage, pass_)["token"]
    end = Direction(where_enrolment_happens(garage))
    out = redeem(app, tenant_id, garage, token, "CAR-1", "L1", direction=other_end(end))
    assert not out.redeemed and out.refusal.code == f.REFUSAL_ENROLMENT_AT_WRONG_END
    assert out.refusal.field == "garage.enrols_at"
    assert f"enrols at {end.value}" in out.refusal.detail
    assert registrations(app, tenant_id) == [] and pass_state(app, tenant_id, pass_) == "draft"
    assert out.answer.direction is other_end(end)
    # and at the right end the same QR is redeemed
    assert redeem(app, tenant_id, garage, token, "CAR-1", "L1").redeemed


@pytest.mark.guarantee("G20")
@needs_postgres[0]
@needs_postgres[1]
def test_a_redemption_at_an_unstated_transient_garage_refuses_to_answer_naming_enrols_at(
    app, tenant_id
):
    pass_ = seeded(app, tenant_id, TRANSIENT_UNSTATED)
    token = issue(app, tenant_id, TRANSIENT_UNSTATED, pass_)["token"]
    for direction in Direction:
        out = redeem(app, tenant_id, TRANSIENT_UNSTATED, token, "CAR-1", "L1",
                     direction=direction)
        assert not out.redeemed and out.refusal.code == f.REFUSAL_WHERE_TO_ENROL_UNSTATED
        assert out.refusal.field == "garage.enrols_at"
        assert out.answer.outcome is Outcome.NOT_COVERED and out.answer.reason == f.NO_PASS
    assert registrations(app, tenant_id) == []
    # stated (the repair), and the same QR is redeemed
    from garage_pass.store.postgres import tenant
    from garage_pass.store.records import set_garage_enrols_at

    with tenant(app, tenant_id) as cursor:
        set_garage_enrols_at(cursor, tenant_id, TRANSIENT_UNSTATED.id, "entry", by="owner",
                             at=NOON_MONDAY, reason="stated")
    app.commit()
    assert redeem(app, tenant_id, TRANSIENT_UNSTATED, token, "CAR-1", "L1",
                  direction=Direction.ENTRY).redeemed


@pytest.mark.guarantee("G20")
@needs_postgres[0]
@needs_postgres[1]
def test_the_stored_enrols_at_round_trips_through_the_store(app, tenant_id):
    from garage_pass.store.postgres import tenant
    from garage_pass.store.records import load_garage as load_stored

    for garage in GARAGES:
        seed(app, tenant_id, garage, ())
        with tenant(app, tenant_id) as cursor:
            _uuid, loaded = load_stored(cursor, tenant_id, garage.id)
        app.rollback()
        assert loaded == garage
