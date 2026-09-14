-- 0004 — A PASS SPANS MANY GARAGES. The key change: a pass names a SET of
-- garages (`pass_garages`), the lanes it states are stated PER GARAGE
-- (`pass_lanes.garage_id`), and a pass's external id is unique per TENANT,
-- not per tenant and garage -- a pass that spans garages cannot be identified
-- by one of them.
--
-- Run as the database OWNER, after 0003. 0001, 0002 and 0003 are merged and
-- are not edited; what this migration changes on their tables it changes by
-- ALTER, and it BACKFILLS: a migration that is only correct against an empty
-- database is a trap for the first environment that is not one.
--
-- WHY. His decision, 2026-09-14: a company or a city holds one account, many
-- garages sit under it, and a monthly may be good at more than one of that
-- account's garages. A pass belonged to exactly one garage -- the foreign
-- key, the uniqueness key and the one-car-one-pass EXCLUDE all named it.
--
-- WHAT DOES NOT MOVE, said plainly:
--   * `vehicle_registrations` and `visits` STAY KEYED PER GARAGE, and the
--     one-car-one-pass EXCLUDE is unchanged: one enrolment writes one
--     registration row per garage of the pass, in one transaction, all or
--     none, and a collision at any one of them refuses the whole enrolment by
--     name. The database's backstop keeps its exact meaning.
--   * The credentials (`enrolments`, `holder_links`) carry no garage of their
--     own; they derive it from the pass, and now the pass's garage is a set.
--   * The terms stay ON THE PASS: one set, evaluated at whichever garage the
--     car is at. A 20-visit allowance is 20 on the pass, not 20 per garage.
--
-- THE ORDER INSIDE THIS FILE IS NOT NEGOTIABLE: at the moment it runs
-- `passes.garage_id` still exists, so every existing pass keeps exactly the one
-- garage it had, and every existing lane row is stamped with its own pass's
-- garage, BEFORE the column that says which garage that was is dropped.
--
-- TWO LOUD FAILURES, by design: a `pass_lanes` row whose pass cannot be found
-- (a shape the product cannot make; a raw write with the constraint triggers
-- off) makes this migration FAIL naming the count rather than dropping the row
-- -- a migration that silently discards a row it cannot place is the
-- wrong-silently failure this module exists to refuse. And the new
-- `UNIQUE (tenant_id, external_id)` is a TIGHTENING: two garages of one tenant
-- may each hold a pass called EMP-1 today, and this migration FAILS BY NAME
-- naming the colliding ids rather than picking a winner.
--
-- THE SHAPE IS COPIED, NOT INVENTED: composite tenant keys to both parents (a
-- foreign-key check runs past row-level security, so a bare key would let a
-- tenant-A row name tenant B's garage), ENABLE + FORCE + policy, the same
-- grant: SELECT, INSERT, UPDATE and NO DELETE. The garage side of the new
-- table is `ON DELETE RESTRICT`, exactly as `passes_garage_in_tenant` was; the
-- pass side cascades, as every child of `passes` does.
--
-- ⛔ THERE IS STILL NO COLUMN IN THIS SCHEMA THAT HOLDS MONEY, no reservation-
-- shaped column, and nothing added here carries `email` in its name.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. pass_garages — the set. One row per (pass, garage). A pass with no row
--    here names no garage and answers nowhere; the module refuses to create
--    one, and the load path reads the set through this table.
-- ---------------------------------------------------------------------------
CREATE TABLE pass_garages (
  tenant_id  uuid  NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  pass_id    uuid  NOT NULL,
  garage_id  uuid  NOT NULL,
  PRIMARY KEY (tenant_id, pass_id, garage_id),
  CONSTRAINT pass_garages_pass_in_tenant
    FOREIGN KEY (tenant_id, pass_id) REFERENCES passes (tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT pass_garages_garage_in_tenant
    FOREIGN KEY (tenant_id, garage_id) REFERENCES garages (tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX pass_garages_tenant_id_idx ON pass_garages (tenant_id);
CREATE INDEX pass_garages_garage_idx ON pass_garages (tenant_id, garage_id);
ALTER TABLE pass_garages ENABLE ROW LEVEL SECURITY;
ALTER TABLE pass_garages FORCE  ROW LEVEL SECURITY;
CREATE POLICY pass_garages_tenant_isolation ON pass_garages
  USING      (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- 2. BACKFILL: every existing pass keeps exactly the one garage it had.
-- ---------------------------------------------------------------------------
INSERT INTO pass_garages (tenant_id, pass_id, garage_id)
SELECT tenant_id, id, garage_id FROM passes;

-- ---------------------------------------------------------------------------
-- 3. pass_lanes gains its garage -- NULLABLE for the length of the backfill.
-- 4. BACKFILL: every lane row carries its own pass's garage.
-- ---------------------------------------------------------------------------
ALTER TABLE pass_lanes ADD COLUMN garage_id uuid;

UPDATE pass_lanes l
   SET garage_id = p.garage_id
  FROM passes p
 WHERE p.tenant_id = l.tenant_id AND p.id = l.pass_id;

-- THE LOUD FAILURE: a lane row this migration cannot place is a row whose
-- pass does not exist. It is not dropped; the migration stops, naming the
-- count. (0001's foreign key makes the shape unreachable through the
-- product; a raw write with the constraint's triggers disabled can make it,
-- and that is exactly the row nobody would look for afterwards.)
DO $$
DECLARE
  orphans integer;
BEGIN
  SELECT count(*) INTO orphans FROM pass_lanes WHERE garage_id IS NULL;
  IF orphans > 0 THEN
    RAISE EXCEPTION 'migration 0004 refuses to run: % pass_lanes row(s) name a pass that '
                    'does not exist, so no garage can be assigned to them. They are not '
                    'dropped; repair them first.', orphans;
  END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 5. Now the column is NOT NULL, a lane cannot name a garage the pass does not
--    hold (the database says it, not only Python), every garage reference is
--    a composite tenant key as everywhere else, and the primary key carries
--    the garage: lane `A1` at two garages is two different barriers.
-- ---------------------------------------------------------------------------
ALTER TABLE pass_lanes ALTER COLUMN garage_id SET NOT NULL;
ALTER TABLE pass_lanes
  ADD CONSTRAINT pass_lanes_garage_of_pass
    FOREIGN KEY (tenant_id, pass_id, garage_id)
    REFERENCES pass_garages (tenant_id, pass_id, garage_id) ON DELETE CASCADE;
ALTER TABLE pass_lanes
  ADD CONSTRAINT pass_lanes_garage_in_tenant
    FOREIGN KEY (tenant_id, garage_id) REFERENCES garages (tenant_id, id) ON DELETE RESTRICT;
ALTER TABLE pass_lanes DROP CONSTRAINT pass_lanes_pkey;
ALTER TABLE pass_lanes ADD PRIMARY KEY (tenant_id, pass_id, garage_id, lane);

-- The two tables that stay keyed per garage now say, in the database, that
-- the garage they name is one the pass holds: a registration or a visit at a
-- garage the pass does not name is a shape the module refuses, and a raw
-- write can no longer make it. Existing rows satisfy this by construction
-- (step 2 gave every pass its one garage, and every row named that garage).
ALTER TABLE vehicle_registrations
  ADD CONSTRAINT vehicle_registrations_garage_of_pass
    FOREIGN KEY (tenant_id, pass_id, garage_id)
    REFERENCES pass_garages (tenant_id, pass_id, garage_id) ON DELETE CASCADE;
ALTER TABLE visits
  ADD CONSTRAINT visits_garage_of_pass
    FOREIGN KEY (tenant_id, pass_id, garage_id)
    REFERENCES pass_garages (tenant_id, pass_id, garage_id) ON DELETE CASCADE;

-- ---------------------------------------------------------------------------
-- 6. ONLY NOW: the pass's external id is unique per tenant, and the column
--    that keyed a pass to one garage goes.
-- ---------------------------------------------------------------------------
-- THE TIGHTENING FAILS BY NAME. Two garages of one tenant may each hold a
-- pass with the same external id today; the migration names them and stops.
-- It never picks a winner: silent data loss is the failure mode if this is
-- got wrong, and nothing is deployed, so this is where it is cheap to say.
DO $$
DECLARE
  colliding text;
BEGIN
  SELECT string_agg(format('%s (%s passes)', external_id, n), ', ' ORDER BY external_id)
    INTO colliding
    FROM (SELECT tenant_id, external_id, count(*) AS n
            FROM passes GROUP BY tenant_id, external_id HAVING count(*) > 1) AS dup;
  IF colliding IS NOT NULL THEN
    RAISE EXCEPTION 'migration 0004 refuses to run: a pass''s external id becomes unique per '
                    'tenant, and these ids are held by more than one pass of one tenant: %. '
                    'Nothing was chosen for you; rename them first.', colliding;
  END IF;
END
$$;

ALTER TABLE passes DROP CONSTRAINT passes_garage_in_tenant;
ALTER TABLE passes DROP CONSTRAINT passes_tenant_id_garage_id_external_id_key;
ALTER TABLE passes DROP COLUMN garage_id;
ALTER TABLE passes ADD CONSTRAINT passes_tenant_id_external_id_key UNIQUE (tenant_id, external_id);

-- ---------------------------------------------------------------------------
-- Grants: DML and nothing structural. NO DELETE ANYWHERE, as 0001-0003.
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE ON pass_garages TO garage_pass_app;

COMMIT;
