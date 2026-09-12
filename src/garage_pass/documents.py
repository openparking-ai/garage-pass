"""Documents: the JSON shapes an integrator hands the command line.

Every key is known or refused. A key this module does not know is not ignored
-- a term silently dropped is a term the owner believes is in force and is not
-- and a reservation-shaped or money-shaped field invented in advance would be
exactly such a key. The known sets are the source the contract prints.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from garage_pass.findings import REFUSAL_FIELD_BLANK, REFUSAL_UNKNOWN_FIELD, Refused
from garage_pass.garage import Garage
from garage_pass.localday import require_aware
from garage_pass.passes import Holder, Pass, Registration, Visit
from garage_pass.states import parse_state
from garage_pass.terms import AllowancePeriod, Direction, Terms, VisitAllowance, Window

GARAGE_KEYS = frozenset({"id", "timezone", "transient_available"})
PASS_KEYS = frozenset({"id", "garage_id", "label", "holder", "terms", "state"})
HOLDER_KEYS = frozenset({"email", "name", "phone"})
TERMS_KEYS = frozenset(
    {
        "valid_from",
        "valid_to",
        "windows",
        "max_stay_minutes",
        "visit_allowance",
        "directions",
        "allowed_lanes",
    }
)
WINDOW_KEYS = frozenset({"days", "start_minute", "end_minute"})
ALLOWANCE_KEYS = frozenset({"count", "per"})
REGISTRATION_KEYS = frozenset({"pass_id", "vehicle_identity", "effective_day", "end_day"})
VISIT_KEYS = frozenset(
    {"pass_id", "vehicle_identity", "entry_lane", "entered_at", "exited_at", "exit_lane"}
)


def _only(document: Any, known: frozenset[str], what: str) -> dict:
    if not isinstance(document, dict):
        raise Refused(REFUSAL_FIELD_BLANK, what, f"{what} must be an object, not {document!r}.")
    unknown = sorted(set(document) - known)
    if unknown:
        raise Refused(
            REFUSAL_UNKNOWN_FIELD,
            f"{what}.{unknown[0]}",
            f"{what} carries unknown field(s) {unknown}; known: {sorted(known)}.",
        )
    return document


def _day(value: Any, field: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise Refused(
            REFUSAL_FIELD_BLANK, field, f"{field} must be YYYY-MM-DD, not {value!r}."
        ) from None


def _instant(value: Any, field: str) -> datetime:
    try:
        return require_aware(datetime.fromisoformat(value), field)
    except (TypeError, ValueError) as exc:
        raise Refused(
            REFUSAL_FIELD_BLANK, field, f"{field} must be an ISO instant with an offset: {exc}"
        ) from None


def load_garage(document: Any) -> Garage:
    d = _only(document, GARAGE_KEYS, "garage")
    return Garage(
        id=d.get("id"), timezone=d.get("timezone"), transient_available=d.get("transient_available")
    )


def load_terms(document: Any) -> Terms:
    d = _only(document, TERMS_KEYS, "terms")
    windows = []
    for index, w in enumerate(d.get("windows") or []):
        w = _only(w, WINDOW_KEYS, f"terms.windows[{index}]")
        windows.append(
            Window(
                days=frozenset(w.get("days") or []),
                start_minute=w.get("start_minute"),
                end_minute=w.get("end_minute"),
            )
        )
    allowance = None
    if d.get("visit_allowance") is not None:
        a = _only(d["visit_allowance"], ALLOWANCE_KEYS, "terms.visit_allowance")
        try:
            per = AllowancePeriod(a.get("per"))
        except ValueError:
            raise Refused(
                REFUSAL_FIELD_BLANK,
                "terms.visit_allowance.per",
                f"per must be one of {[p.value for p in AllowancePeriod]}, not {a.get('per')!r}.",
            ) from None
        allowance = VisitAllowance(count=a.get("count"), per=per)
    try:
        directions = frozenset(Direction(x) for x in (d.get("directions") or []))
    except ValueError:
        raise Refused(
            REFUSAL_FIELD_BLANK,
            "terms.directions",
            f"directions must be among {[x.value for x in Direction]}, "
            f"not {d.get('directions')!r}.",
        ) from None
    max_stay = d.get("max_stay_minutes")
    if max_stay is not None and (isinstance(max_stay, bool) or not isinstance(max_stay, int)):
        raise Refused(
            REFUSAL_FIELD_BLANK, "terms.max_stay_minutes", f"must be an integer, not {max_stay!r}."
        )
    lanes = d.get("allowed_lanes")
    return Terms(
        valid_from=_day(d.get("valid_from"), "terms.valid_from"),
        valid_to=_day(d.get("valid_to"), "terms.valid_to"),
        windows=tuple(windows),
        max_stay=timedelta(minutes=max_stay) if max_stay is not None else None,
        visit_allowance=allowance,
        directions=directions,
        allowed_lanes=frozenset(lanes) if lanes is not None else None,
    )


def load_pass(document: Any) -> Pass:
    d = _only(document, PASS_KEYS, "pass")
    h = _only(d.get("holder"), HOLDER_KEYS, "pass.holder")
    return Pass(
        id=d.get("id"),
        garage_id=d.get("garage_id"),
        label=d.get("label"),
        holder=Holder(email=h.get("email"), name=h.get("name"), phone=h.get("phone")),
        terms=load_terms(d.get("terms") or {}),
        state=parse_state(d.get("state", "draft")),
    )


def load_registration(document: Any) -> Registration:
    d = _only(document, REGISTRATION_KEYS, "registration")
    effective = _day(d.get("effective_day"), "registration.effective_day")
    if effective is None:
        raise Refused(REFUSAL_FIELD_BLANK, "registration.effective_day", "is required.")
    return Registration(
        pass_id=d.get("pass_id"),
        vehicle_identity=d.get("vehicle_identity"),
        effective_day=effective,
        end_day=_day(d.get("end_day"), "registration.end_day"),
    )


def load_visit(document: Any) -> Visit:
    d = _only(document, VISIT_KEYS, "visit")
    return Visit(
        pass_id=d.get("pass_id"),
        vehicle_identity=d.get("vehicle_identity"),
        entry_lane=d.get("entry_lane"),
        entered_at=_instant(d.get("entered_at"), "visit.entered_at"),
        exited_at=_instant(d["exited_at"], "visit.exited_at") if d.get("exited_at") else None,
        exit_lane=d.get("exit_lane"),
    )


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())
