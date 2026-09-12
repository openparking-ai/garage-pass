"""The command line: the access answer from documents, and the store's writes.

    garage-pass check-terms --pass pass.json
    garage-pass access --garage g.json --pass p.json [--pass ...] \
        [--registrations r.json] [--visits v.json] \
        --vehicle ID --lane L --direction entry|exit --at 2026-04-01T09:00:00-06:00

Exit status: 0 covered, 1 not covered, 2 refused to answer, 3 the request was
refused (a contradiction, a bad document, an unknown timezone, a malformed
instant or day). The answer is printed as JSON, and there is no money in it.

Against the store (``GARAGE_PASS_DSN``, ``--tenant``): ``create-garage``,
``set-garage-timezone`` (the repair for a garage stored with a timezone the
system does not carry -- the one write that takes an unreadable garage, and it
records who, when and why like a state change does),
``create-pass``, ``register-vehicle``, ``end-registration``, ``set-state``,
``record-entry``, ``record-exit`` and ``access-in-store``. A store command with
no ``GARAGE_PASS_DSN``, or one the database refuses to connect, prints a
sentence to stderr and exits 2.

**A REFUSAL IS RENDERED, NEVER A TRACEBACK.** Every ``Refused`` the module
raises -- and ``UnknownTimezone`` is one -- reaches this boundary and is printed
as ``{"refused": code, "field": ..., "detail": ...}`` with exit 3. What the
libraries this boundary calls can raise is mapped here too: a document that
cannot be read as JSON, an instant or a day that does not parse, a naive
instant, a registrations or visits document that is not a list. Measured
before this: ``create-garage`` with a mistyped zone printed sixty lines of
``zoneinfo`` stack. ``tests/test_g18_...`` enumerates every ``raise`` in the
package by AST and classifies each as rendered here or a programming error a
command cannot reach, so a new exception class fails that test until it is
classified. A value that starts with a dash (``--timezone -06:00``) reaches the
module and is refused by name rather than read by argparse as an option
(``_values_that_start_with_a_dash``). A machine with no timezone database at
all is a sentence on stderr and exit 2, like a DSN that does not connect: the
machine's configuration, not the request.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from garage_pass.access import Outcome, access
from garage_pass.documents import (
    load_garage,
    load_pass,
    load_registration,
    load_visit,
    read_json,
)
from garage_pass.findings import (
    REFUSAL_DOCUMENT_UNREADABLE,
    REFUSAL_FIELD_BLANK,
    Refused,
)
from garage_pass.localday import TimezoneDatabaseUnavailable
from garage_pass.states import parse_state
from garage_pass.terms import Direction

EXIT_BY_OUTCOME = {Outcome.COVERED: 0, Outcome.NOT_COVERED: 1, Outcome.REFUSED_TO_ANSWER: 2}
EXIT_REFUSED_REQUEST = 3


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {k: _plain(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_plain(v) for v in value]
    return value


def _print(value: Any) -> None:
    print(json.dumps(_plain(value), indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="garage-pass", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("check-terms", help="validate a pass document; refuse a contradiction")
    s.add_argument("--pass", dest="passes", action="append", required=True)

    s = sub.add_parser("access", help="the access answer, from documents")
    s.add_argument("--garage", required=True)
    s.add_argument("--pass", dest="passes", action="append", required=True)
    s.add_argument("--registrations", help="JSON list of registrations")
    s.add_argument("--visits", help="JSON list of recorded visits")
    _movement(s)

    s = sub.add_parser("create-garage", help="store a garage document")
    s.add_argument("--tenant", required=True, type=UUID, help="the tenant's uuid")
    s.add_argument("--garage", required=True, help="the garage document")
    s = sub.add_parser(
        "set-garage-timezone",
        help="repair a stored garage's timezone; the one write an unreadable garage takes",
    )
    s.add_argument("--tenant", required=True, type=UUID, help="the tenant's uuid")
    s.add_argument("--garage", required=True, help="the garage's external id")
    s.add_argument("--timezone", required=True, help="an IANA name such as America/Denver")
    s.add_argument("--by", required=True, help="who repaired it, for the garage's history")
    s.add_argument("--at", required=True, help="when, as an ISO instant with an offset")
    s.add_argument("--reason", required=True, help="why, for the garage's history")

    def store(name: str, help_: str) -> argparse.ArgumentParser:
        s = sub.add_parser(name, help=help_)
        s.add_argument("--tenant", required=True, type=UUID, help="the tenant's uuid")
        s.add_argument("--garage", required=True, help="the garage's external id")
        return s

    s = store("create-pass", "store a pass; refuse a contradiction")
    s.add_argument("--pass", dest="pass_", required=True)
    s.add_argument("--by", required=True, help="who created it, for the state history")
    s.add_argument("--at", required=True, help="when, as an ISO instant with an offset")
    s = store("register-vehicle", "bind a vehicle identity to a pass")
    s.add_argument("--pass-id", required=True)
    s.add_argument("--vehicle", required=True)
    s.add_argument("--effective-day", required=True)
    s.add_argument("--end-day")
    s = store("end-registration", "end a registration on a day; the identity is free from it")
    s.add_argument("--pass-id", required=True)
    s.add_argument("--vehicle", required=True)
    s.add_argument("--end-day", required=True)
    s = store("set-state", "move a pass to a typed state, recording who and why")
    s.add_argument("--pass-id", required=True)
    s.add_argument("--state", required=True)
    s.add_argument("--by", required=True)
    s.add_argument("--reason", required=True)
    s.add_argument("--at", required=True)
    s = store("record-entry", "the lane says the vehicle entered on this pass")
    s.add_argument("--pass-id", required=True)
    s.add_argument("--vehicle", required=True)
    s.add_argument("--lane", required=True)
    s.add_argument("--at", required=True)
    s = store("record-exit", "the lane says the vehicle left")
    s.add_argument("--pass-id", required=True)
    s.add_argument("--vehicle", required=True)
    s.add_argument("--lane", required=True)
    s.add_argument("--at", required=True)
    s = store("access-in-store", "the access answer, from the store")
    _movement(s)
    return p


def _movement(s: argparse.ArgumentParser) -> None:
    s.add_argument("--vehicle", required=True)
    s.add_argument("--lane", required=True)
    s.add_argument("--direction", required=True, choices=[d.value for d in Direction])
    s.add_argument("--at", required=True, help="ISO instant with an offset")


# ---- the boundary: what the libraries raise, rendered as refusals ----------


def _at(text: str, option: str = "--at") -> datetime:
    """An ISO instant WITH an offset, or a refusal naming the option and the
    value. A naive instant would be read as the running machine's local time,
    which is a property of the server and not of the garage."""
    from garage_pass.localday import require_aware

    try:
        return require_aware(datetime.fromisoformat(text), option)
    except (TypeError, ValueError) as exc:
        raise Refused(
            REFUSAL_FIELD_BLANK, option,
            f"{option} must be an ISO instant with an offset, such as "
            f"2026-06-01T09:00:00-06:00, not {text!r}: {exc}",
        ) from None


def _day(text: str, option: str) -> date:
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        raise Refused(
            REFUSAL_FIELD_BLANK, option, f"{option} must be YYYY-MM-DD, not {text!r}."
        ) from None


def _document(path: str, option: str) -> Any:
    """``read_json``, with a missing, unreadable or non-JSON file refused by
    name rather than raised as ``FileNotFoundError`` or ``JSONDecodeError``."""
    try:
        return read_json(path)
    except (OSError, ValueError) as exc:
        raise Refused(
            REFUSAL_DOCUMENT_UNREADABLE, option,
            f"{option} {path!r} could not be read: {exc}",
        ) from None


def _list(path: str, option: str) -> list:
    """A document that must be a JSON list -- registrations, visits."""
    document = _document(path, option)
    if not isinstance(document, list):
        raise Refused(
            REFUSAL_FIELD_BLANK, option,
            f"{option} {path!r} must be a JSON list, not {type(document).__name__}.",
        )
    return document


def _values_that_start_with_a_dash(parser: argparse.ArgumentParser, argv: list[str]) -> list[str]:
    """``--timezone -06:00`` reaches the MODULE, not argparse's usage error.

    argparse reads a token that starts with ``-`` as an option unless it looks
    like a negative number, so ``--timezone -06:00`` was "expected one
    argument", a usage message and exit 2 -- a third shape beside the JSON
    refusal and the traceback G18 forbids, found by an operator walking the
    product. The value belongs to the module, which refuses it by name
    (``-06:00`` is not an IANA name). So: where an option that takes one value
    is followed by a token that starts with ``-`` and is not itself an option
    of that command, the two are joined as ``--option=value``, which argparse
    always accepts. Every option string is read from the parser, not typed.
    """
    commands = {
        name: sub for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
        for name, sub in action.choices.items()
    }
    sub = commands.get(argv[0]) if argv else None
    if sub is None:
        return argv
    options = {opt for action in sub._actions for opt in action.option_strings}
    takes_one = {
        opt for action in sub._actions if action.nargs in (None, 1)
        and not isinstance(action, argparse._StoreConstAction)
        for opt in action.option_strings
    }
    joined: list[str] = []
    skip = False
    for i, token in enumerate(argv):
        if skip:
            skip = False
            continue
        following = argv[i + 1] if i + 1 < len(argv) else None
        if (
            token in takes_one and following is not None
            and following.startswith("-") and following not in options
        ):
            joined.append(f"{token}={following}")
            skip = True
        else:
            joined.append(token)
    return joined


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(_values_that_start_with_a_dash(parser, argv))
    try:
        return _run(args)
    except Refused as refused:
        print(json.dumps({"refused": refused.code, "field": refused.field,
                          "detail": refused.detail}, indent=2))
        return EXIT_REFUSED_REQUEST
    except TimezoneDatabaseUnavailable as missing:
        # The MACHINE's configuration, not a refusal of the request: one
        # sentence, exit 2, the shape of the unset DSN below. Not the JSON
        # refusal, which would name a field the operator can change.
        print(str(missing), file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    if args.command == "check-terms":
        for path in args.passes:
            pass_ = load_pass(_document(path, "--pass"))
            _print({"pass": pass_.id, "terms": pass_.terms.describe(), "contradictions": "none"})
        return 0

    if args.command == "access":
        answer = access(
            garage=load_garage(_document(args.garage, "--garage")),
            passes=[load_pass(_document(p, "--pass")) for p in args.passes],
            registrations=[load_registration(r)
                           for r in _list(args.registrations, "--registrations")]
            if args.registrations else [],
            visits=[load_visit(v) for v in _list(args.visits, "--visits")] if args.visits else [],
            vehicle_identity=args.vehicle,
            lane=args.lane,
            direction=Direction(args.direction),
            at=_at(args.at),
        )
        _print(answer)
        return EXIT_BY_OUTCOME[answer.outcome]

    # ---- the store --------------------------------------------------------
    from garage_pass.store import records
    from garage_pass.store.access import access_from_store
    from garage_pass.store.postgres import connect, tenant

    dsn = os.environ.get("GARAGE_PASS_DSN")
    if not dsn:
        print("GARAGE_PASS_DSN is not set.", file=sys.stderr)
        return 2
    import psycopg

    try:
        connection = connect(dsn)
    except psycopg.OperationalError as exc:
        # Configuration, not a refusal of the request: one sentence, exit 2,
        # like the unset DSN above. The DSN itself is not echoed.
        print(f"GARAGE_PASS_DSN did not connect: {exc}".strip(), file=sys.stderr)
        return 2
    connection.autocommit = False
    try:
        if args.command == "access-in-store":
            answer = access_from_store(
                connection, args.tenant, args.garage, args.vehicle, args.lane,
                Direction(args.direction), _at(args.at),
            )
            _print(answer)
            return EXIT_BY_OUTCOME[answer.outcome]
        with tenant(connection, args.tenant) as cursor:
            if args.command == "create-garage":
                garage = load_garage(_document(args.garage, "--garage"))
                records.store_garage(cursor, args.tenant, garage)
                out: Any = {"stored": garage.id, "transient_available": garage.transient_available}
            elif args.command == "set-garage-timezone":
                out = records.set_garage_timezone(
                    cursor, args.tenant, args.garage, args.timezone,
                    by=args.by, at=_at(args.at), reason=args.reason,
                )
            elif args.command == "create-pass":
                pass_ = load_pass(_document(args.pass_, "--pass"))
                records.create_pass(cursor, args.tenant, args.garage, pass_, by=args.by,
                                    at=_at(args.at))
                out = {"stored": pass_.id, "state": pass_.state.value}
            elif args.command == "register-vehicle":
                out = records.register_vehicle(
                    cursor, args.tenant, args.garage, args.pass_id, args.vehicle,
                    _day(args.effective_day, "--effective-day"),
                    _day(args.end_day, "--end-day") if args.end_day else None,
                )
            elif args.command == "end-registration":
                out = records.end_registration(
                    cursor, args.tenant, args.garage, args.pass_id, args.vehicle,
                    _day(args.end_day, "--end-day"),
                )
            elif args.command == "set-state":
                out = records.change_state(
                    cursor, args.tenant, args.garage, args.pass_id, parse_state(args.state),
                    by=args.by, at=_at(args.at), reason=args.reason,
                )
            elif args.command == "record-entry":
                out = records.record_entry(
                    cursor, args.tenant, args.garage, args.pass_id, args.vehicle, args.lane,
                    _at(args.at),
                )
            elif args.command == "record-exit":
                out = records.record_exit(
                    cursor, args.tenant, args.garage, args.pass_id, args.vehicle, args.lane,
                    _at(args.at),
                )
            else:  # pragma: no cover - argparse refuses unknown commands
                raise SystemExit(2)
        connection.commit()
        _print(out)
        return 0
    except Refused:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
