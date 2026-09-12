"""Documents: the JSON shapes an integrator hands the command line.

Every key is known or refused. A key this module does not know is not ignored
-- a term silently dropped is a term the owner believes is in force and is not
-- and a reservation-shaped or money-shaped field invented in advance would be
exactly such a key. The known sets are the source the contract prints.

**THE KEYS AND THE CHECKS ARE DERIVED FROM THE DATACLASSES, NOT LISTED.**
Measured before this: the loaders checked a hand-written set of fields, so
twenty-odd malformed shapes were refused by name while a registration with no
``vehicle_identity``, a ``pass_id`` that was an object, ``allowed_lanes: 5`` and
an enormous ``max_stay_minutes`` were tracebacks at the command line -- and
``allowed_lanes: "L1"`` was read as the lane set ``{'1', 'L'}``, a silently wrong
pass. Now every document key is a field of the dataclass it loads into, every
value is checked against that field's declared type (``typed.py``, the same
source ``Registration`` and ``Visit`` check themselves against), and a field
added to a dataclass tomorrow is a document key with a type check the same day,
with nobody editing a list.

**A STRING IS NEVER REINTERPRETED AS A COLLECTION.** Where the field is a set or
a list the document must carry a JSON list; text there is refused by name.

**THE TWO DECLARED EXCEPTIONS**, as data the derivation reads, so a third one is
added at the same place and is visible there: ``DOCUMENT_KEY_OF`` (a field whose
document key spells its unit -- ``Terms.max_stay`` is ``max_stay_minutes``) and
``STORE_ONLY`` (a field the store's load path sets and a document never carries
-- ``unreadable`` on a pass and a garage). There are exactly two.

**Required, optional, absent.** A field with no default is required: absent or
``null`` is refused naming it. A field with a default may be absent, and ``null``
where the declared type admits it means what the dataclass says it means
(``Garage.transient_available``: unstated).
"""

from __future__ import annotations

import dataclasses
import json
import typing
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, NoReturn

from garage_pass.findings import (
    REFUSAL_FIELD_BLANK,
    REFUSAL_FIELD_WRONG_TYPE,
    REFUSAL_UNKNOWN_FIELD,
    Refused,
)
from garage_pass.garage import Garage
from garage_pass.localday import require_aware
from garage_pass.passes import Holder, Pass, Registration, State, Visit
from garage_pass.states import parse_state
from garage_pass.terms import Terms, VisitAllowance, Window
from garage_pass.typed import arms, describe, hints

#: A field whose DOCUMENT key differs from its name, because the key spells the
#: unit the document carries: ``(class, field) -> (document key, timedelta unit)``.
DOCUMENT_KEY_OF: dict[tuple[type, str], tuple[str, str]] = {
    (Terms, "max_stay"): ("max_stay_minutes", "minutes"),
}

#: A field the STORE's load path sets and a document never carries.
STORE_ONLY: dict[type, frozenset[str]] = {
    Pass: frozenset({"unreadable"}),
    Garage: frozenset({"unreadable"}),
}


@dataclasses.dataclass(frozen=True)
class DocumentField:
    """One field of a document-backed dataclass, as the loader sees it."""

    name: str
    key: str
    hint: Any
    required: bool
    unit: str | None


def document_fields(cls: type) -> tuple[DocumentField, ...]:
    """The fields a document for ``cls`` may carry -- derived from the
    dataclass, minus ``STORE_ONLY``, keys renamed per ``DOCUMENT_KEY_OF``."""
    out = []
    for f in dataclasses.fields(cls):
        if f.name in STORE_ONLY.get(cls, frozenset()):
            continue
        key, unit = DOCUMENT_KEY_OF.get((cls, f.name), (f.name, None))
        required = (
            f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        )
        out.append(DocumentField(f.name, key, hints(cls)[f.name], required, unit))
    return tuple(out)


def keys_of(cls: type) -> frozenset[str]:
    return frozenset(f.key for f in document_fields(cls))


#: The published key sets, by name -- read by the contract generator. Derived.
GARAGE_KEYS = keys_of(Garage)
PASS_KEYS = keys_of(Pass)
HOLDER_KEYS = keys_of(Holder)
TERMS_KEYS = keys_of(Terms)
WINDOW_KEYS = keys_of(Window)
ALLOWANCE_KEYS = keys_of(VisitAllowance)
REGISTRATION_KEYS = keys_of(Registration)
VISIT_KEYS = keys_of(Visit)


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


def _refuse_wrong_type(field: str, hint: Any, value: Any) -> NoReturn:
    raise Refused(
        REFUSAL_FIELD_WRONG_TYPE, field,
        f"{field} must be {describe(hint)}, not {value!r}.",
    )


def _day(value: Any, field: str) -> date:
    if not isinstance(value, str):
        _refuse_wrong_type(field, date, value)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise Refused(
            REFUSAL_FIELD_BLANK, field, f"{field} must be YYYY-MM-DD, not {value!r}."
        ) from None


def _instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        _refuse_wrong_type(field, datetime, value)
    try:
        return require_aware(datetime.fromisoformat(value), field)
    except ValueError as exc:
        raise Refused(
            REFUSAL_FIELD_BLANK, field, f"{field} must be an ISO instant with an offset: {exc}"
        ) from None


def _duration(value: Any, field: str, unit: str) -> timedelta:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Refused(
            REFUSAL_FIELD_WRONG_TYPE, field,
            f"{field} must be a whole number of {unit}, not {value!r}.",
        )
    try:
        return timedelta(**{unit: value})
    except OverflowError:
        raise Refused(
            REFUSAL_FIELD_WRONG_TYPE, field,
            f"{field} is {value!r} {unit}, which is too large to be a duration.",
        ) from None


def _enum(value: Any, cls: type[Enum], field: str) -> Enum:
    if cls is State:
        return parse_state(value)  # 'expired' is refused by its own code
    if not isinstance(value, str):
        _refuse_wrong_type(field, cls, value)
    try:
        return cls(value)
    except ValueError:
        raise Refused(
            REFUSAL_FIELD_BLANK, field,
            f"{field} must be one of {[m.value for m in cls]}, not {value!r}.",
        ) from None


def _value(value: Any, hint: Any, field: str, unit: str | None = None) -> Any:
    """A JSON value converted to the field's declared type, or a refusal
    naming the field, the type and the value. ``None`` is handled by the
    caller (required or defaulted); here the value is present."""
    candidates = [a for a in arms(hint) if a is not type(None)]
    arm = candidates[0]
    origin = typing.get_origin(arm)
    if origin in (frozenset, set, tuple, list):
        # A STRING IS NEVER REINTERPRETED AS A COLLECTION: JSON lists only.
        if not isinstance(value, list):
            _refuse_wrong_type(field, hint, value)
        (inner,) = [a for a in typing.get_args(arm) if a is not Ellipsis] or [Any]
        items = [_value(v, inner, f"{field}[{i}]") for i, v in enumerate(value)]
        return origin(items) if origin is not list else items
    if arm is date:
        return _day(value, field)
    if arm is datetime:
        return _instant(value, field)
    if arm is timedelta:
        assert unit is not None, f"{field}: a duration field needs its unit in DOCUMENT_KEY_OF"
        return _duration(value, field, unit)
    if isinstance(arm, type) and issubclass(arm, Enum):
        return _enum(value, arm, field)
    if isinstance(arm, type) and dataclasses.is_dataclass(arm):
        return load(arm, value, field)
    if arm is bool:
        if not isinstance(value, bool):
            _refuse_wrong_type(field, hint, value)
        return value
    if arm is int:
        if isinstance(value, bool) or not isinstance(value, int):
            _refuse_wrong_type(field, hint, value)
        return value
    if arm is str:
        if not isinstance(value, str):
            _refuse_wrong_type(field, hint, value)
        return value
    if isinstance(arm, type) and isinstance(value, arm):  # pragma: no cover - no such field today
        return value
    _refuse_wrong_type(field, hint, value)  # pragma: no cover


def load(cls: type, document: Any, what: str) -> Any:
    """A document as an instance of ``cls`` -- every key known, every value of
    its declared type, then the dataclass's own validation (contradictions,
    an unknown zone, a blank identity) runs as it does for any caller."""
    d = _only(document, keys_of(cls), what)
    kwargs: dict[str, Any] = {}
    for f in document_fields(cls):
        value = d.get(f.key)
        field = f"{what}.{f.key}"
        if value is None:
            if f.required:
                raise Refused(REFUSAL_FIELD_BLANK, field, f"{field} is required.")
            if f.key in d and type(None) not in arms(f.hint):
                _refuse_wrong_type(field, f.hint, value)
            continue  # the dataclass's own default
        kwargs[f.name] = _value(value, f.hint, field, f.unit)
    return cls(**kwargs)


def load_garage(document: Any) -> Garage:
    return load(Garage, document, "garage")


def load_terms(document: Any) -> Terms:
    return load(Terms, document, "terms")


def load_pass(document: Any) -> Pass:
    return load(Pass, document, "pass")


def load_registration(document: Any) -> Registration:
    return load(Registration, document, "registration")


def load_visit(document: Any) -> Visit:
    return load(Visit, document, "visit")


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())
