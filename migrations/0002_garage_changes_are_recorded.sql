-- 0002 — the garage repair is RECORDED: who, when, why, the old value and the
-- new, into an append-only history with the shape 0001 already ships for pass
-- state changes.
--
-- Run as the database OWNER, after 0001. 0001 is not edited; it is merged.
--
-- WHY. `set-garage-timezone` changes how every pass at the garage is read --
-- every window, every valid range, every local day -- and it left no record but
-- the row, in a module where every pass state change is written to
-- `pass_state_changes` and the application role cannot erase it. An operator
-- write that moves every clock in the building and cannot be traced afterwards
-- is inconsistent with the module's own discipline. Measured at the re-gate:
-- after the repair, `garages` carried `id, tenant_id, external_id, timezone,
-- transient_available, created_at` and nothing said who, when or why.
--
-- THE SHAPE IS COPIED, NOT INVENTED. Same composite tenant key to the parent
-- (a foreign-key check runs past row-level security, so a bare `garage_id`
-- would let a tenant-A row name tenant B's garage), same ENABLE + FORCE + policy,
-- same indexes, same grant: SELECT and INSERT to the application role and
-- nothing else. And the same consequence 0001 states for the pass history: the
-- application role holds no DELETE on any table whose deletion cascades into
-- this one (`garages`, `tenants`) -- the suite reads that set from the catalogue
-- and walks it, so a history cannot be erased by deleting what it belongs to.
--
-- `field` names the column that changed. Only `timezone` is repairable today;
-- the CHECK lists the repairable columns so a second repair is a migration and
-- not a free-text value. `old_value` is what the row held before -- which may
-- be a value the module refuses to read, since that is what a repair is for --
-- and `new_value` is what it holds now.
--
-- ⛔ THERE IS STILL NO COLUMN IN THIS SCHEMA THAT HOLDS MONEY, and no
-- reservation-shaped column. The catalogue test in G3 reads this table too.

BEGIN;

CREATE TABLE garage_changes (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  garage_id   uuid        NOT NULL,
  field       text        NOT NULL CHECK (field IN ('timezone')),
  old_value   text        NOT NULL,
  new_value   text        NOT NULL,
  changed_by  text        NOT NULL CHECK (length(btrim(changed_by)) > 0),
  changed_at  timestamptz NOT NULL,
  reason      text        NOT NULL CHECK (length(btrim(reason)) > 0),
  created_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT garage_changes_garage_in_tenant
    FOREIGN KEY (tenant_id, garage_id) REFERENCES garages (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX garage_changes_tenant_id_idx ON garage_changes (tenant_id);
CREATE INDEX garage_changes_garage_idx ON garage_changes (tenant_id, garage_id, changed_at);
ALTER TABLE garage_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE garage_changes FORCE  ROW LEVEL SECURITY;
CREATE POLICY garage_changes_tenant_isolation ON garage_changes
  USING      (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- Append-only: SELECT and INSERT, nothing else. No DELETE anywhere, as 0001.
GRANT SELECT, INSERT ON garage_changes TO garage_pass_app;

COMMIT;
