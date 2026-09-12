"""G10 -- every table carries a tenant column, ENABLE, FORCE and a policy, and
every garage and pass reference is half of a composite tenant key.

**READ FROM THE CATALOGUE, NEVER FROM A LIST OF TABLE NAMES.** A check that
walked a list somebody typed cannot notice a table added without protection,
which is the entire failure it exists to catch.

**AND THE SUPERUSER TRAP IS CHECKED BEFORE ANYTHING ELSE.** A Postgres superuser
bypasses row-level security unconditionally; `FORCE` does not stop one, it only
closes the table-owner hole. So `assert_role_cannot_bypass_rls` runs first: the
test proves it is connected as a role that COULD be stopped, before it proves it
was stopped.

**THE ONE ALLOWANCE IN THE SUITE IS HERE.** There is no way to read a database
catalogue without a database, so these skip when `GARAGE_PASS_TEST_DSN` is
unset. CI always sets it, so CI never skips them -- and `GARAGE_PASS_ALLOW_UNRUN`
is empty in CI, so a run where these did not execute FAILS rather than passing
quietly.

Controls: FORCE removed from one table in the migration; a composite key
removed from one table in the migration; the policy's WITH CHECK removed.
"""

from __future__ import annotations

import psycopg
import pytest

from fixtures import transient_garage
from garage_pass.store.postgres import (
    assert_role_cannot_bypass_rls,
    references_without_a_composite_key,
    tables_without_rls,
    tables_without_tenant_column,
    tenant,
)
from garage_pass.store.records import store_garage
from store_harness import needs_postgres, new_tenant

pytestmark = needs_postgres


@pytest.mark.guarantee("G10")
def test_the_connection_could_actually_be_stopped(app):
    """THE CONTROL ON EVERY ISOLATION ASSERTION BELOW."""
    assert_role_cannot_bypass_rls(app)


@pytest.mark.guarantee("G10")
def test_the_owner_connection_would_have_failed_that_check(owner):
    """The positive control for the check itself."""
    with pytest.raises(AssertionError, match="inert"):
        assert_role_cannot_bypass_rls(owner)


@pytest.mark.guarantee("G10")
def test_no_table_ships_without_row_level_security(app):
    assert tables_without_rls(app) == []


@pytest.mark.guarantee("G10")
def test_every_table_but_tenants_carries_a_tenant_column(app):
    assert tables_without_tenant_column(app) == []


@pytest.mark.guarantee("G10")
def test_every_garage_and_pass_reference_is_a_composite_tenant_key(app):
    assert references_without_a_composite_key(app, "garage_id", "garages") == []
    assert references_without_a_composite_key(app, "pass_id", "passes") == []


@pytest.mark.guarantee("G10")
def test_the_composite_key_scan_can_see_a_bare_reference(owner):
    """The control on the scan above: a scratch table with a bare uuid column
    named garage_id and no composite key is reported, then dropped."""
    with owner.cursor() as cursor:
        cursor.execute("CREATE TABLE _bare_ref (tenant_id uuid, garage_id uuid)")
        try:
            assert references_without_a_composite_key(owner, "garage_id", "garages") == [
                "_bare_ref"
            ]
        finally:
            cursor.execute("DROP TABLE _bare_ref")


@pytest.mark.guarantee("G10")
def test_the_coverage_check_is_not_measuring_an_empty_schema(app):
    with app.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'"
        )
        (count,) = cursor.fetchone()
    assert count >= 8, f"only {count} tables found; the migration did not run"


@pytest.mark.guarantee("G10")
def test_one_tenant_cannot_read_another_tenants_rows(app, owner):
    assert_role_cannot_bypass_rls(app)
    alpha, beta = new_tenant(owner, "alpha"), new_tenant(owner, "beta")
    for tid, external in ((alpha, "g-alpha"), (beta, "g-beta")):
        with tenant(app, tid) as cursor:
            store_garage(cursor, tid, transient_garage().__class__(
                id=external, timezone="UTC", transient_available=True))
        app.commit()
    with tenant(app, alpha) as cursor:
        cursor.execute("SELECT external_id FROM garages")
        visible = sorted(row[0] for row in cursor.fetchall())
    app.rollback()
    assert visible == ["g-alpha"], f"tenant alpha saw {visible}"


@pytest.mark.guarantee("G10")
def test_a_connection_with_no_tenant_context_sees_nothing(app):
    """Fail closed. `tenant_id = NULL` is NULL, not true."""
    assert_role_cannot_bypass_rls(app)
    with app.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM garages")
        (count,) = cursor.fetchone()
    app.rollback()
    assert count == 0


@pytest.mark.guarantee("G10")
def test_a_tenant_cannot_write_a_row_attributed_to_another(app, owner):
    """WITH CHECK, not just USING."""
    alpha, beta = new_tenant(owner), new_tenant(owner)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant(app, alpha) as cursor:
            cursor.execute(
                "INSERT INTO garages (tenant_id, external_id, timezone) VALUES (%s, 'x', 'UTC')",
                (beta,),
            )
    app.rollback()


@pytest.mark.guarantee("G10")
def test_a_tenant_cannot_name_another_tenants_garage_even_by_a_raw_insert(app, owner):
    """The composite key: the foreign-key check runs past the policy, and the
    pair (tenant_id, garage_id) does not exist for tenant alpha."""
    alpha, beta = new_tenant(owner), new_tenant(owner)
    with tenant(app, beta) as cursor:
        garage_uuid = store_garage(cursor, beta, transient_garage())
    app.commit()
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with tenant(app, alpha) as cursor:
            cursor.execute(
                "INSERT INTO passes (tenant_id, garage_id, external_id, label, holder_email, "
                "entry_allowed, exit_allowed, lanes_stated, state) VALUES (%s, %s, 'p', 'l', "
                "'h@example.com', true, true, false, 'draft')",
                (alpha, garage_uuid),
            )
    app.rollback()
