"""The command line: the access answer from documents, and the store's writes.

    garage-pass check-terms --pass pass.json
    garage-pass access --garage g.json --pass p.json [--pass ...] \
        [--registrations r.json] [--visits v.json] \
        --vehicle ID --lane L --direction entry|exit --at 2026-04-01T09:00:00-06:00

Exit status: 0 covered, 1 not covered, 2 refused to answer OR the machine's
configuration (a sentence on stderr: no DSN, a database that does not connect
or is not migrated, a role without its grants, no timezone database), 3 the
request was refused (a contradiction, a bad document, a field of the wrong
type, an unknown timezone, a malformed instant or day). The answer is printed
as JSON, and there is no money in it.

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
instant, a registrations or visits document that is not a list, a field of the
wrong type (every document value is checked against the type its dataclass
declares, in ``documents.py``, before anything is built from it). Measured
before this: ``create-garage`` with a mistyped zone printed sixty lines of
``zoneinfo`` stack; a registration document with no ``vehicle_identity`` was an
``AttributeError`` at an exit.

**WHAT THE DATABASE DRIVER RAISES AND THE MODULE DID NOT NAME IS THE MACHINE'S
CONFIGURATION**: one sentence on stderr naming the SQLSTATE, exit 2, the shape
of a DSN that does not connect -- an unmigrated database, a role without its
grants, a DSN that is not one. It is the LAST resort, after every named
refusal has had its chance: the module turns the SQLSTATEs it knows -- a unique
violation, the one-car-one-pass exclusion, a deadlock -- into named refusals
INSIDE the store, so the generic mapping here sees only what nothing named.
Measured before this: those were tracebacks, four of them in the L3's census.

``tests/test_g18_...`` enumerates every ``raise`` in the
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


#: What a SQLSTATE class says about WHOSE problem it is, in the operator's
#: words. Derived from the class digits the standard defines, not from a list
#: of the errors somebody has met; every class not named here is the last line.
_SQLSTATE_CLASSES = {
    "08": "the connection to the database failed",
    "28": "the database refused the login",
    "3D": "the database named does not exist",
    "40": "the database rolled this command back to break a deadlock or a serialization "
          "failure; nothing was written -- run it again",
    "42": "the database is not set up for this command (a missing table or function, or a "
          "role without its grants): the machine's configuration, not the request",
    "53": "the database is out of a resource (connections, disk, memory)",
    "57": "the database is shutting down or cancelled the command",
}


def _driver_sentence(exc: Exception) -> str:
    """One line for a database error the store did not name: what class of
    problem it is, the driver's class and SQLSTATE, the first line of its
    message. The DSN is never in it."""
    state = getattr(exc, "sqlstate", None) or "?"
    what = _SQLSTATE_CLASSES.get(state[:2], "the database could not run this command")
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else repr(exc)
    return f"{what}: {type(exc).__name__} (SQLSTATE {state}): {message}"


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
    except psycopg.Error as exc:
        # Configuration, not a refusal of the request: one sentence, exit 2,
        # like the unset DSN above. The DSN itself is not echoed. A DSN that
        # is not a conninfo string at all (ProgrammingError) is the same shape.
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
    except psycopg.Error as exc:
        # THE LAST RESORT, deliberately after Refused: a driver error the store
        # did not turn into a named refusal is one sentence with its SQLSTATE,
        # exit 2, never a traceback -- and never a refusal of the request's
        # content, because nothing about the content was judged. Nothing the
        # store names by SQLSTATE reaches here: those are Refused above.
        connection.rollback()
        print(_driver_sentence(exc), file=sys.stderr)
        return 2
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
