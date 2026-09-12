"""The command line: the access answer from documents, and the store's writes.

    garage-pass check-terms --pass pass.json
    garage-pass access --garage g.json --pass p.json [--pass ...] \
        [--registrations r.json] [--visits v.json] \
        --vehicle ID --lane L --direction entry|exit --at 2026-04-01T09:00:00-06:00

Exit status: 0 covered, 1 not covered, 2 refused to answer, 3 the request was
refused (a contradiction, a bad document). The answer is printed as JSON, and
there is no money in it.

Against the store (``GARAGE_PASS_DSN``, ``--tenant``): ``create-garage``, ``create-pass``,
``register-vehicle``, ``end-registration``, ``set-state``, ``record-entry``,
``record-exit`` and ``access-in-store``.
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
from garage_pass.findings import Refused
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


def _at(text: str) -> datetime:
    from garage_pass.localday import require_aware

    return require_aware(datetime.fromisoformat(text), "--at")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except Refused as refused:
        print(json.dumps({"refused": refused.code, "field": refused.field,
                          "detail": refused.detail}, indent=2))
        return EXIT_REFUSED_REQUEST


def _run(args: argparse.Namespace) -> int:
    if args.command == "check-terms":
        for path in args.passes:
            pass_ = load_pass(read_json(path))
            _print({"pass": pass_.id, "terms": pass_.terms.describe(), "contradictions": "none"})
        return 0

    if args.command == "access":
        answer = access(
            garage=load_garage(read_json(args.garage)),
            passes=[load_pass(read_json(p)) for p in args.passes],
            registrations=[load_registration(r) for r in read_json(args.registrations)]
            if args.registrations else [],
            visits=[load_visit(v) for v in read_json(args.visits)] if args.visits else [],
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
    connection = connect(dsn)
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
                garage = load_garage(read_json(args.garage))
                records.store_garage(cursor, args.tenant, garage)
                out: Any = {"stored": garage.id, "transient_available": garage.transient_available}
            elif args.command == "create-pass":
                pass_ = load_pass(read_json(args.pass_))
                records.create_pass(cursor, args.tenant, args.garage, pass_, by=args.by,
                                    at=_at(args.at))
                out = {"stored": pass_.id, "state": pass_.state.value}
            elif args.command == "register-vehicle":
                out = records.register_vehicle(
                    cursor, args.tenant, args.garage, args.pass_id, args.vehicle,
                    date.fromisoformat(args.effective_day),
                    date.fromisoformat(args.end_day) if args.end_day else None,
                )
            elif args.command == "end-registration":
                out = records.end_registration(
                    cursor, args.tenant, args.garage, args.pass_id, args.vehicle,
                    date.fromisoformat(args.end_day),
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
