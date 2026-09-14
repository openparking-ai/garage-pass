"""A migrated database, an application connection, and the rows seeded --
shared by every store-backed test.

Not a test module (no ``test_`` prefix, so the guarantee guard does not ask it
for a mark) and not a conftest: it is imported by name, so a reader of any test
can see where the database came from. Migrations are applied as the OWNER from
``migrations/``, sorted, so the schema under test is the schema that ships; the
application connects as the NOSUPERUSER NOBYPASSRLS role.

**ONE DATABASE, ONE TENANT PER TEST, FRESH ROWS PER TEST.** The tenant policy
stops a test reading anything but its own rows, and G10 proves that.

**ONE MIGRATION AT A TIME IN THE CLUSTER.** The migration ``CREATE``s or
``ALTER``s the application ROLE, and a role is cluster-global: two databases
migrating at once in one cluster collide on it (``tuple concurrently
updated``). So ``migrate`` runs under a cluster-wide advisory lock, taken on
ONE shared database of the cluster (``postgres``, else ``template1``) through a
second connection held for the length of the migration -- an advisory lock is
per database, measured on the sibling module that this harness is copied from.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from garage_pass.garage import Garage
from garage_pass.passes import Pass
from garage_pass.store.postgres import connect, set_tenant, tenant
from garage_pass.store.records import as_uuid, create_pass, store_garage

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
DSN = os.environ.get("GARAGE_PASS_TEST_DSN")
APP_PASSWORD = "test-only-password"

#: One key, one meaning: "a migration of this module is running in this cluster".
MIGRATION_LOCK_KEY = 0x67617261676570  # 'garagep', as a bigint

CREATED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@contextmanager
def cluster_lock(dsn: str):
    import psycopg
    from psycopg import conninfo

    params = conninfo.conninfo_to_dict(dsn)
    holder = None
    for shared in ("postgres", "template1"):
        try:
            holder = connect(conninfo.make_conninfo(**{**params, "dbname": shared}))
            break
        except psycopg.OperationalError:
            continue
    if holder is None:
        print(
            "store_harness.cluster_lock: no shared database accepted the connection; the "
            "migration lock is taken on the target database and serialises that database "
            "only.",
            file=sys.stderr,
        )
        holder = connect(dsn)
    holder.autocommit = True
    with holder.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        try:
            yield
        finally:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))
    holder.close()


def migrate(dsn: str) -> Any:
    """Drop and rebuild the schema from ``migrations/`` as the owner -- one
    migration at a time in the cluster."""
    owner = connect(dsn)
    owner.autocommit = True
    with cluster_lock(dsn), owner.cursor() as cursor:
        cursor.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        for path in sorted(MIGRATIONS.glob("*.sql")):
            try:
                cursor.execute(path.read_text())
            except Exception:
                # A migration file opens its own BEGIN and never reaches its COMMIT
                # when it raises, so the connection is left inside an aborted
                # transaction. End it here, so the failure is the migration's
                # message and not "current transaction is aborted".
                cursor.execute("ROLLBACK")
                raise
        cursor.execute(f"ALTER ROLE garage_pass_app LOGIN PASSWORD '{APP_PASSWORD}'")
    return owner


def app_connection(dsn: str) -> Any:
    connection = connect(f"{dsn} user=garage_pass_app password={APP_PASSWORD}")
    connection.autocommit = False
    return connection


def new_tenant(owner: Any, slug: str | None = None) -> UUID:
    slug = slug or f"t-{uuid4().hex[:8]}"
    with owner.cursor() as cursor:
        cursor.execute(
            "INSERT INTO tenants (slug, name) VALUES (%s, %s) RETURNING id", (slug, slug)
        )
        (tenant_id,) = cursor.fetchone()
    return as_uuid(tenant_id)


def seed(app: Any, tenant_id: UUID, garage: Garage, passes: tuple[Pass, ...] = ()) -> UUID:
    """The garage and the passes, committed. Returns the garage's uuid."""
    with tenant(app, tenant_id) as cursor:
        garage_uuid = store_garage(cursor, tenant_id, garage)
        for pass_ in passes:
            create_pass(cursor, tenant_id, garage.id, pass_, by="seed", at=CREATED_AT)
    app.commit()
    return garage_uuid


def query(app: Any, tenant_id: Any, statement: str, parameters: tuple = ()) -> list[tuple]:
    """A read inside the tenant's context, rolled back afterwards."""
    with app.cursor() as cursor:
        set_tenant(cursor, tenant_id)
        cursor.execute(statement, parameters)
        rows = cursor.fetchall()
    app.rollback()
    return rows


#: The marks every store-backed test module carries. The fixtures that hand a
#: test its database live in conftest.py, so no module has to import them.
needs_postgres = [
    pytest.mark.needs_postgres,
    pytest.mark.skipif(not DSN, reason="GARAGE_PASS_TEST_DSN is not set"),
]


def store_test(function):
    """The same marks, for one test in a module that also runs without a database."""
    for mark in needs_postgres:
        function = mark(function)
    return function


def seed_full_graph(app: Any, tenant_id: UUID) -> None:
    """A row in EVERY table, as one tenant, through the module: a garage, a
    pass with a window and a lane (and its creation in the history), a
    registration, a recorded entry, a garage repair (and its row in the
    garage history), an enrolment and a holder link (0003). The isolation
    test's denominator."""
    from datetime import date

    from fixtures import TWO_HOURS_BEFORE, a_pass, everything_terms, transient_garage
    from garage_pass.store.enrolments import issue_enrolment, issue_holder_link
    from garage_pass.store.records import record_entry, register_vehicle, set_garage_timezone

    garage = transient_garage()
    pass_ = a_pass(garage_id=garage.id, terms=everything_terms())
    seed(app, tenant_id, garage, (pass_,))
    with tenant(app, tenant_id) as cursor:
        register_vehicle(cursor, tenant_id, garage.id, pass_.id, "CAR-1", date(2026, 1, 1))
        record_entry(cursor, tenant_id, garage.id, pass_.id, "CAR-1", "L1", TWO_HOURS_BEFORE)
        # the one operator write on a garage, and its history row (0002)
        set_garage_timezone(cursor, tenant_id, garage.id, garage.timezone, by="seed",
                            at=CREATED_AT, reason="seeded")
        # the two one-time credentials (0003)
        issue_enrolment(cursor, tenant_id, garage.id, pass_.id, "enrol-1", date(2026, 6, 1), 3,
                        by="seed", at=CREATED_AT)
        issue_holder_link(cursor, tenant_id, garage.id, pass_.id, "link-1", date(2026, 6, 1), 3,
                          by="seed", at=CREATED_AT)
    app.commit()
