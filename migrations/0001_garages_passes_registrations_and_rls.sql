-- 0001 — tenants, the module's tables, and the row-level security foundation
-- every later migration inherits.
--
-- Run as the database OWNER. The application never connects as this role.
--
-- The shape of the tenant column, the policies, the composite garage key and
-- the app role is the one a sibling module in this project already ships,
-- copied rather than reinvented: two shapes would mean two sets of failure
-- modes, and the second one is always the one nobody tested.
--
-- ⛔ THERE IS NO COLUMN IN THIS SCHEMA THAT HOLDS MONEY, AND THERE NEVER WILL
-- BE. A pass does not know what anything costs. There is no reservation-shaped
-- column either: neither reservation system exists yet, and a field invented in
-- advance is a field nothing measures. A test reads the catalogue for both.

BEGIN;

-- Needed for the one-car-one-pass constraint below: an EXCLUDE over a uuid, a
-- text and a daterange needs btree operator classes inside a GiST index.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------------------
-- The application role.
--
-- NOSUPERUSER and NOBYPASSRLS are the whole point. A superuser bypasses
-- row-level security unconditionally -- FORCE ROW LEVEL SECURITY does not stop
-- one, it only closes the table-owner hole. If the application (or a test)
-- connects as a superuser, every policy below is inert and every isolation test
-- passes for the wrong reason.
--
-- Created NOLOGIN here so the schema carries the guarantee; scripts/ensure-app-role.py
-- adds LOGIN and a password from the environment.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'garage_pass_app') THEN
    CREATE ROLE garage_pass_app NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  ELSE
    ALTER ROLE garage_pass_app NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- Tenant context.
--
-- Unset resolves to NULL, and `tenant_id = NULL` is NULL, not true -- so a
-- connection that forgets to set the context sees nothing. Fail closed.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS uuid
  LANGUAGE sql STABLE
  AS $$ SELECT NULLIF(current_setting('garage_pass.tenant_id', true), '')::uuid $$;

CREATE TABLE tenants (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  slug        text        NOT NULL UNIQUE,
  name        text        NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE  ROW LEVEL SECURITY;

CREATE POLICY tenants_self_only ON tenants
  USING      (id = current_tenant_id())
  WITH CHECK (id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- garages — the clock, and whether transient parking is available.
--
-- `transient_available` is NULLABLE ON PURPOSE, and NULL means UNSTATED -- not
-- false. The access call refuses to answer an entry at a garage that has not
-- stated it, naming the field. A NOT NULL with a default here would be the
-- guessed default the module exists to refuse.
--
-- (tenant_id, id) is UNIQUE so that every garage reference below can be half
-- of a COMPOSITE TENANT KEY: a foreign-key check runs past row-level security,
-- so a bare `garage_id REFERENCES garages(id)` would let a tenant-A row name
-- tenant B's garage by a raw insert. A composite key does not.
-- ---------------------------------------------------------------------------
CREATE TABLE garages (
  id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  external_id          text        NOT NULL CHECK (length(btrim(external_id)) > 0),
  timezone             text        NOT NULL CHECK (length(btrim(timezone)) > 0),
  transient_available  boolean,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, external_id),
  CONSTRAINT garages_tenant_id_id_key UNIQUE (tenant_id, id)
);

CREATE INDEX garages_tenant_id_idx ON garages (tenant_id);
ALTER TABLE garages ENABLE ROW LEVEL SECURITY;
ALTER TABLE garages FORCE  ROW LEVEL SECURITY;
CREATE POLICY garages_tenant_isolation ON garages
  USING      (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- passes — one garage, an owner-typed label, a holder, the terms, the state.
--
-- THERE IS NO TYPE COLUMN. "Monthly", "employee", "vendor" are labels the
-- owner types into `label`, and no behaviour keys off it.
--
-- `state` holds the TYPED states only. `expired` is derived from `valid_to`
-- by the module and is refused by the CHECK here, so nobody can type it.
--
-- The CHECKs are the database half of "a contradiction is refused at
-- creation": the module refuses first, naming the field; these are the
-- backstop for a raw write.
-- ---------------------------------------------------------------------------
CREATE TABLE passes (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  garage_id         uuid        NOT NULL,
  external_id       text        NOT NULL CHECK (length(btrim(external_id)) > 0),
  label             text        NOT NULL CHECK (length(btrim(label)) > 0),
  holder_email      text        NOT NULL CHECK (position('@' in holder_email) > 1),
  holder_name       text,
  holder_phone      text,
  valid_from        date,
  valid_to          date,
  max_stay_minutes  integer     CHECK (max_stay_minutes > 0),
  allowance_count   integer     CHECK (allowance_count > 0),
  allowance_per     text        CHECK (allowance_per IN ('life', 'window')),
  entry_allowed     boolean     NOT NULL,
  exit_allowed      boolean     NOT NULL,
  -- true: the rows in pass_lanes are the allowed set. false: every lane.
  lanes_stated      boolean     NOT NULL,
  state             text        NOT NULL
                    CHECK (state IN ('draft', 'awaiting_enrolment', 'active',
                                     'suspended', 'revoked')),
  created_at        timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT passes_valid_range_is_ordered CHECK (
    valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from
  ),
  CONSTRAINT passes_allowance_is_both_or_neither CHECK (
    (allowance_count IS NULL) = (allowance_per IS NULL)
  ),
  CONSTRAINT passes_state_a_direction CHECK (entry_allowed OR exit_allowed),
  CONSTRAINT passes_tenant_id_id_key UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, garage_id, external_id),
  CONSTRAINT passes_garage_in_tenant
    FOREIGN KEY (tenant_id, garage_id) REFERENCES garages (tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX passes_tenant_id_idx ON passes (tenant_id);
ALTER TABLE passes ENABLE ROW LEVEL SECURITY;
ALTER TABLE passes FORCE  ROW LEVEL SECURITY;
CREATE POLICY passes_tenant_isolation ON passes
  USING      (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- pass_windows — recurring: ISO weekdays and minutes of the garage's local day,
-- half-open [start, end). 1440 is the end of the day.
-- ---------------------------------------------------------------------------
CREATE TABLE pass_windows (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  pass_id       uuid        NOT NULL,
  days          smallint[]  NOT NULL CHECK (cardinality(days) > 0 AND days <@ ARRAY[1,2,3,4,5,6,7]::smallint[]),
  start_minute  smallint    NOT NULL CHECK (start_minute BETWEEN 0 AND 1440),
  end_minute    smallint    NOT NULL CHECK (end_minute BETWEEN 0 AND 1440),
  position      smallint    NOT NULL CHECK (position >= 0),
  CONSTRAINT pass_windows_are_not_empty CHECK (end_minute > start_minute),
  UNIQUE (tenant_id, pass_id, position),
  CONSTRAINT pass_windows_pass_in_tenant
    FOREIGN KEY (tenant_id, pass_id) REFERENCES passes (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX pass_windows_tenant_id_idx ON pass_windows (tenant_id);
ALTER TABLE pass_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE pass_windows FORCE  ROW LEVEL SECURITY;
CREATE POLICY pass_windows_tenant_isolation ON pass_windows
  USING      (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- pass_lanes — the named set, read only when passes.lanes_stated.
-- ---------------------------------------------------------------------------
CREATE TABLE pass_lanes (
  tenant_id  uuid  NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  pass_id    uuid  NOT NULL,
  lane       text  NOT NULL CHECK (length(btrim(lane)) > 0),
  PRIMARY KEY (tenant_id, pass_id, lane),
  CONSTRAINT pass_lanes_pass_in_tenant
    FOREIGN KEY (tenant_id, pass_id) REFERENCES passes (tenant_id, id) ON DELETE CASCADE
);

ALTER TABLE pass_lanes ENABLE ROW LEVEL SECURITY;
ALTER TABLE pass_lanes FORCE  ROW LEVEL SECURITY;
CREATE POLICY pass_lanes_tenant_isolation ON pass_lanes
  USING      (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- pass_state_changes — who, when and why. APPEND-ONLY: the application role is
-- granted SELECT and INSERT on this table and nothing else, below, and a test
-- reads that grant from the catalogue and tries the UPDATE.
--
-- `from_state` is NULL for the row that records the pass's creation.
-- ---------------------------------------------------------------------------
CREATE TABLE pass_state_changes (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  pass_id     uuid        NOT NULL,
  from_state  text        CHECK (from_state IN ('draft', 'awaiting_enrolment', 'active',
                                                'suspended', 'revoked')),
  to_state    text        NOT NULL CHECK (to_state IN ('draft', 'awaiting_enrolment', 'active',
                                                       'suspended', 'revoked')),
  changed_by  text        NOT NULL CHECK (length(btrim(changed_by)) > 0),
  changed_at  timestamptz NOT NULL,
  reason      text        NOT NULL CHECK (length(btrim(reason)) > 0),
  created_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pass_state_changes_pass_in_tenant
    FOREIGN KEY (tenant_id, pass_id) REFERENCES passes (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX pass_state_changes_tenant_id_idx ON pass_state_changes (tenant_id);
CREATE INDEX pass_state_changes_pass_idx ON pass_state_changes (tenant_id, pass_id, changed_at);
ALTER TABLE pass_state_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE pass_state_changes FORCE  ROW LEVEL SECURITY;
CREATE POLICY pass_state_changes_tenant_isolation ON pass_state_changes
  USING      (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- vehicle_registrations — ONE CAR, ONE PASS PER GARAGE. His ruling.
--
-- A registration binds a vehicle identity to a pass for the half-open range of
-- local days [effective_day, end_day). The identity is free FROM end_day. An
-- end_day equal to effective_day is an empty range that covers nothing and
-- overlaps nothing: it is what revoking a pass writes onto a registration that
-- had not yet taken effect.
--
-- The module refuses a second registration BY NAME before this constraint has
-- to (REFUSAL_VEHICLE_ON_ANOTHER_PASS, naming the surviving pass and the day
-- it ends); the EXCLUDE is the backstop for a raw insert and for two
-- registrations racing. A refusal writes nothing.
--
-- `end_day` NULL means the registration has no end day of its own; the module
-- bounds it by the pass's valid_to when it reads it, and ends it there when the
-- vehicle is next registered elsewhere.
-- ---------------------------------------------------------------------------
CREATE TABLE vehicle_registrations (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  garage_id         uuid        NOT NULL,
  pass_id           uuid        NOT NULL,
  vehicle_identity  text        NOT NULL CHECK (length(btrim(vehicle_identity)) > 0),
  effective_day     date        NOT NULL,
  end_day           date,
  ended_reason      text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT vehicle_registrations_end_is_not_before_start CHECK (
    end_day IS NULL OR end_day >= effective_day
  ),
  CONSTRAINT vehicle_registrations_ended_reason_iff_ended CHECK (
    (end_day IS NULL) = (ended_reason IS NULL)
  ),
  CONSTRAINT vehicle_registrations_one_pass_per_garage EXCLUDE USING gist (
    tenant_id WITH =,
    garage_id WITH =,
    vehicle_identity WITH =,
    daterange(effective_day, end_day, '[)') WITH &&
  ),
  CONSTRAINT vehicle_registrations_garage_in_tenant
    FOREIGN KEY (tenant_id, garage_id) REFERENCES garages (tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT vehicle_registrations_pass_in_tenant
    FOREIGN KEY (tenant_id, pass_id) REFERENCES passes (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX vehicle_registrations_tenant_id_idx ON vehicle_registrations (tenant_id);
CREATE INDEX vehicle_registrations_lookup_idx
  ON vehicle_registrations (tenant_id, garage_id, vehicle_identity);
ALTER TABLE vehicle_registrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE vehicle_registrations FORCE  ROW LEVEL SECURITY;
CREATE POLICY vehicle_registrations_tenant_isolation ON vehicle_registrations
  USING      (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- visits — the LEDGER of what the lane told this module: an entry on a pass,
-- and its exit once recorded. A visit allowance and a maximum stay are computed
-- from these rows and from nothing else.
--
-- This is not a count of who is inside, and nothing in this module answers
-- that question. One open visit per vehicle per pass: a second entry before
-- the exit is refused by name, and the partial unique index is the backstop.
-- ---------------------------------------------------------------------------
CREATE TABLE visits (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  garage_id         uuid        NOT NULL,
  pass_id           uuid        NOT NULL,
  vehicle_identity  text        NOT NULL CHECK (length(btrim(vehicle_identity)) > 0),
  entry_lane        text        NOT NULL CHECK (length(btrim(entry_lane)) > 0),
  entered_at        timestamptz NOT NULL,
  exited_at         timestamptz,
  exit_lane         text        CHECK (exit_lane IS NULL OR length(btrim(exit_lane)) > 0),
  created_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT visits_exit_is_not_before_entry CHECK (exited_at IS NULL OR exited_at >= entered_at),
  CONSTRAINT visits_exit_lane_iff_exited CHECK ((exited_at IS NULL) = (exit_lane IS NULL)),
  CONSTRAINT visits_garage_in_tenant
    FOREIGN KEY (tenant_id, garage_id) REFERENCES garages (tenant_id, id) ON DELETE RESTRICT,
  CONSTRAINT visits_pass_in_tenant
    FOREIGN KEY (tenant_id, pass_id) REFERENCES passes (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX visits_tenant_id_idx ON visits (tenant_id);
CREATE INDEX visits_pass_idx ON visits (tenant_id, pass_id, entered_at);
CREATE UNIQUE INDEX visits_one_open_per_vehicle_per_pass
  ON visits (tenant_id, pass_id, vehicle_identity) WHERE exited_at IS NULL;
ALTER TABLE visits ENABLE ROW LEVEL SECURITY;
ALTER TABLE visits FORCE  ROW LEVEL SECURITY;
CREATE POLICY visits_tenant_isolation ON visits
  USING      (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- Grants. The app role gets DML and nothing structural -- and on the state
-- history it gets SELECT and INSERT only, which is what "append-only" means
-- here: a grant the catalogue can be asked about, not a promise.
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO garage_pass_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
  tenants, garages, passes, pass_windows, pass_lanes
TO garage_pass_app;
GRANT SELECT, INSERT, UPDATE ON vehicle_registrations, visits TO garage_pass_app;
GRANT SELECT, INSERT ON pass_state_changes TO garage_pass_app;
GRANT EXECUTE ON FUNCTION current_tenant_id() TO garage_pass_app;

COMMIT;
