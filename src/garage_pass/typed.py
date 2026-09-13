"""A value is checked against the type its dataclass DECLARES -- derived from
the annotation, never from a hand-written list.

Two doors let a value into this module: a caller constructing a dataclass
(``Registration(...)``), and a document loaded by ``documents.py``. Both are
checked here against the same source, ``typing.get_type_hints`` of the
dataclass, so a field added tomorrow is covered the day it is added and there
is no list that can fall behind the class.

Measured before this: ``Registration`` validated nothing at all and ``Visit``
only its instants, so a registration whose ``vehicle_identity`` was ``None`` --
a document key left out -- was an ``AttributeError`` at an EXIT lane, and a
registration whose ``effective_day`` was the JSON string ``"2026-01-01"`` was a
``TypeError`` there. Every other dataclass refused a wrong type where it was
built; these two let it through to the answer.

**What is a wrong type, precisely.** ``bool`` is not an ``int`` here although
Python says it is (``True`` where a count belongs is a mistake, not a count);
``datetime`` is not a ``date`` here although Python says it is (an instant
where a day belongs would silently be read as its midnight). A union accepts a
value any of its arms accepts; ``None`` only where the annotation says so.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from datetime import date, datetime
from enum import Enum
from functools import cache
from typing import Any


@cache
def hints(cls: type) -> dict[str, Any]:
    """Every field's declared type, resolved (the package uses postponed
    annotations, so ``__annotations__`` alone holds strings)."""
    return typing.get_type_hints(cls)


def arms(hint: Any) -> tuple[Any, ...]:
    """The alternatives of a union, or the hint itself."""
    if isinstance(hint, types.UnionType) or typing.get_origin(hint) is typing.Union:
        return typing.get_args(hint)
    return (hint,)


def conforms(value: Any, hint: Any) -> bool:
    """Does ``value`` have the declared type -- element types included?"""
    for arm in arms(hint):
        if arm is type(None) or arm is None:
            if value is None:
                return True
            continue
        origin = typing.get_origin(arm)
        if origin is not None:
            args = typing.get_args(arm)
            if origin in (frozenset, set, list):
                if isinstance(value, origin) and (
                    not args or all(conforms(v, args[0]) for v in value)
                ):
                    return True
            elif origin is tuple:
                if isinstance(value, tuple):
                    if len(args) == 2 and args[1] is Ellipsis:
                        if all(conforms(v, args[0]) for v in value):
                            return True
                    elif not args or (
                        len(args) == len(value)
                        and all(conforms(v, a) for v, a in zip(value, args, strict=True))
                    ):
                        return True
            elif isinstance(value, origin):
                return True
            continue
        if arm is bool:
            if isinstance(value, bool):
                return True
        elif arm is int:
            if isinstance(value, int) and not isinstance(value, bool):
                return True
        elif arm is date:
            if isinstance(value, date) and not isinstance(value, datetime):
                return True
        elif arm is Any:
            return True
        elif isinstance(arm, type) and isinstance(value, arm):
            return True
    return False


def describe(hint: Any) -> str:
    """The declared type in words an operator can act on."""
    parts = []
    for arm in arms(hint):
        if arm is type(None):
            parts.append("absent")
            continue
        origin = typing.get_origin(arm)
        if origin in (frozenset, set, list, tuple):
            args = typing.get_args(arm)
            inner = describe(args[0]) if args and args[0] is not Ellipsis else "values"
            parts.append(f"a list of {inner}")
        elif arm is str:
            parts.append("text")
        elif arm is bool:
            parts.append("true or false")
        elif arm is int:
            parts.append("a whole number")
        elif arm is date:
            parts.append("a day")
        elif arm is datetime:
            parts.append("an instant")
        elif isinstance(arm, type) and issubclass(arm, Enum):
            parts.append("one of " + ", ".join(repr(m.value) for m in arm))
        elif isinstance(arm, type) and dataclasses.is_dataclass(arm):
            parts.append(f"a {arm.__name__.lower()} object")
        elif isinstance(arm, type):
            parts.append(f"a {arm.__name__}")
        else:
            parts.append(str(arm))
    return " or ".join(parts)


def require_typed(instance: Any) -> None:
    """Every field of a dataclass instance has its declared type, or a
    ``TypeError`` naming the field, the type and the value -- raised where the
    value is built, before any answer could be computed from it. A
    caller-contract error, the same family as a ``direction`` that is not a
    ``Direction``."""
    cls = type(instance)
    for field_ in dataclasses.fields(cls):
        value = getattr(instance, field_.name)
        hint = hints(cls)[field_.name]
        if not conforms(value, hint):
            raise TypeError(
                f"{cls.__name__}.{field_.name} must be {describe(hint)}, not {value!r}"
            )
