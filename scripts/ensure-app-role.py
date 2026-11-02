#!/usr/bin/env python3
"""Give the application role a login and a password from the environment.

Migration 0001 creates `garage_pass_app` NOLOGIN NOSUPERUSER NOBYPASSRLS, so
the SCHEMA carries the guarantee that the application cannot bypass row-level
security. This adds the login, and it deliberately does NOT touch the three
attributes that matter: a script that could hand the app role BYPASSRLS would be
a script that could make every isolation test pass for the wrong reason.

    GARAGE_PASS_OWNER_DSN=... GARAGE_PASS_APP_PASSWORD=... python scripts/ensure-app-role.py

Run as the database owner. The password is read from the environment and never
from an argument, because arguments are visible in `ps` to every user on the box.
The owner's DSN is read from the environment for the same reason: it carries
the owner's password. A DSN on the command line is still taken when it carries
NO password -- libpq then reads the password from ``PGPASSFILE`` (or
``~/.pgpass``) -- and one that carries a password is refused, unprinted, before
anything connects.
It never reaches the server either: the script computes the SCRAM-SHA-256
verifier PostgreSQL stores (``scram_verifier``) and sends that, so no statement
-- and no server log that keeps statements -- carries the password itself.
The verifier is put into the statement by ``psycopg.sql`` composition -- quoted
as a literal, never interpolated as a string -- because ``ALTER ROLE`` is a
utility statement and PostgreSQL binds no parameters into those: the first cut
passed the password as a bind parameter and the README's second install step
died on ``syntax error at or near "$1"``, and nothing in the tree had ever run
the script. A test now runs it against the test cluster (``tests/test_g10_...``),
and it prints nothing that contains the password.
"""

from __future__ import annotations

import os
import sys

#: The role this script gives a login to.
ROLE = "garage_pass_app"


def scram_verifier(connection, password: str, role: str = ROLE) -> str:
    """The password as PostgreSQL stores it: a salted, iterated SCRAM-SHA-256
    verifier, computed on THIS machine by libpq's own ``PQencryptPasswordConn``
    (the password's SASLprep included), so the statement that sets it carries
    the verifier and never the password. PostgreSQL stores a verifier it is
    handed as it is. Anything but a SCRAM-SHA-256 verifier is refused here,
    before a statement is sent."""
    verifier = connection.pgconn.encrypt_password(
        password.encode("utf-8"), role.encode("utf-8"), b"scram-sha-256"
    ).decode("ascii")
    if not verifier.startswith("SCRAM-SHA-256$"):
        raise RuntimeError("libpq did not compute a SCRAM-SHA-256 verifier; nothing was sent.")
    return verifier


#: Where the owner's DSN is read from. Never an argument that carries a password.
OWNER_DSN = "GARAGE_PASS_OWNER_DSN"


def owner_dsn(argv: list[str]) -> str | None:
    """The owner's DSN: ``GARAGE_PASS_OWNER_DSN``, or a DSN on the command line
    that carries no password. A sentence and None otherwise; the DSN is never
    printed."""
    from psycopg import conninfo

    from_env = os.environ.get(OWNER_DSN)
    if len(argv) > 1 or (argv and from_env):
        print(f"Give the owner's DSN once: in {OWNER_DSN}, or as the one argument.")
        return None
    dsn = argv[0] if argv else from_env
    if not dsn:
        print(f"{OWNER_DSN} is not set. The owner's DSN is read from the environment, "
              "because arguments are visible in `ps` to every user on the machine.")
        return None
    if argv:
        try:
            carries_password = bool(conninfo.conninfo_to_dict(dsn).get("password"))
        except Exception:  # noqa: BLE001 -- the parser's message may quote the DSN
            print("The DSN on the command line is not a connection string. It was not "
                  "printed.")
            return None
        if carries_password:
            print(f"The DSN on the command line carries a password, which `ps` shows to "
                  f"every user on the machine. Put the DSN in {OWNER_DSN}, or leave the "
                  "password out and let libpq read it from PGPASSFILE. Nothing was sent.")
            return None
    return dsn


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 2
    dsn = owner_dsn(argv)
    if dsn is None:
        return 2
    password = os.environ.get("GARAGE_PASS_APP_PASSWORD")
    if not password:
        print(
            "GARAGE_PASS_APP_PASSWORD is not set. It is read from the "
            "environment rather than from an argument, because arguments are "
            "visible in `ps` to every user on the machine."
        )
        return 2

    import psycopg
    from psycopg import sql

    with psycopg.connect(dsn) as connection:
        connection.autocommit = True
        verifier = scram_verifier(connection, password)
        with connection.cursor() as cursor:
            # ALTER, never CREATE: the role's attributes are the migration's, and
            # this script may not be a route to changing them. A quoted LITERAL,
            # not a bind parameter: utility statements take none.
            cursor.execute(
                sql.SQL("ALTER ROLE garage_pass_app LOGIN PASSWORD {}").format(
                    sql.Literal(verifier)
                )
            )
            cursor.execute(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = "
                "'garage_pass_app'"
            )
            is_super, bypasses = cursor.fetchone()

    if is_super or bypasses:
        print(
            "garage_pass_app can bypass row-level security. Something has "
            "granted it SUPERUSER or BYPASSRLS since migration 0001 ran, and "
            "every isolation policy is inert for it."
        )
        return 1
    print("garage_pass_app can log in, and still cannot bypass row-level security.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
