-- 0007 -- THE ONE NORMAL FORM READS O AS 0 AND I AS 1. A plate reader's
-- alphabet has no letter I and no letter O, so it prints the digit for either:
-- a plate typed GO4IT is read G041T. From this migration the module's one
-- normal form (``plate_key``) reads O as 0 and I as 1 on every side -- what the
-- desk types, what a lane reads, what a registration and a visit hold -- so the
-- two are one car. Rows written before it are re-keyed here, in the same
-- transaction, so a stored GO4IT meets a lane's G041T.
--
-- Run as the database OWNER, after 0006. 0001 to 0006 are not edited.
--
-- WHAT IT CHANGES, and nothing else:
--   * `vehicle_registrations.vehicle_identity`, `visits.vehicle_identity` and
--     `enrolments.plate` -- the three columns that hold the normal form -- have
--     O replaced by 0 and I by 1. The plate as the desk typed it
--     (`enrolments.plate_typed`) and the identity a QR's first use recorded
--     (`enrolments.redeemed_vehicle_identity`) are kept as they were: they are
--     what was typed or read, not the normal form.
--   * The floor a raw write must clear on those three columns (0005, 0006)
--     gains O and I: a raw write of GO4IT would otherwise be a second spelling
--     of a car the module holds as G041T, invisible to its lookups and to the
--     one-car-one-pass EXCLUDE.
--
-- IT REFUSES BY NAME RATHER THAN PICK A WINNER. Two rows that differ only by
-- O/0 or I/1 become one car. Where that makes two registrations of one car at
-- one garage on overlapping days, or two open visits of one car on one pass at
-- one garage, the database's own constraints forbid the result: this
-- migration names the rows and stops, and nothing moves.
--
-- `row_security` is off for this transaction: every table here FORCEs row-level
-- security, and a re-key that RLS filtered down to no rows would report success
-- and change nothing. With it off, a role RLS applies to fails loudly instead.
--
-- FORCE binds the tables' OWNER too, and the owner this is run as need not be a
-- superuser or BYPASSRLS: with FORCE on, such an owner is a role RLS applies to,
-- and the first read below would stop it. So for this transaction only, FORCE
-- is lifted on each of the five tables it reads and writes that has it, and put
-- back on exactly those before COMMIT -- the catalogue ends as it began. ALTER
-- TABLE holds each table's ACCESS EXCLUSIVE lock to the end of the transaction,
-- so no other session ever sees FORCE lifted, and a failure anywhere rolls the
-- lift back with everything else. ENABLE and the tenant policies are not
-- touched.

BEGIN;

SET LOCAL row_security = off;

DO $$
DECLARE
  forced text[];
  t text;
BEGIN
  SELECT coalesce(array_agg(name ORDER BY name), '{}') INTO forced
    FROM unnest(ARRAY['enrolments', 'garages', 'passes', 'vehicle_registrations',
                      'visits']) AS name
    JOIN pg_class c ON c.oid = to_regclass(name)
   WHERE c.relforcerowsecurity;
  FOREACH t IN ARRAY forced LOOP
    EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', t);
  END LOOP;
  PERFORM set_config('garage_pass.migration_0007_forced', array_to_string(forced, ','), true);
END
$$;

DO $$
DECLARE
  clash text;
BEGIN
  SELECT format('%s and %s at garage %s (passes %s and %s, from %s and %s)',
                a.vehicle_identity, b.vehicle_identity, g.external_id, pa.external_id,
                pb.external_id, a.effective_day, b.effective_day)
    INTO clash
    FROM vehicle_registrations a
    JOIN vehicle_registrations b
      ON b.tenant_id = a.tenant_id AND b.garage_id = a.garage_id
     AND b.vehicle_identity > a.vehicle_identity
     AND translate(b.vehicle_identity, 'OI', '01') = translate(a.vehicle_identity, 'OI', '01')
     AND daterange(b.effective_day, b.end_day, '[)') && daterange(a.effective_day, a.end_day, '[)')
    JOIN garages g ON g.tenant_id = a.tenant_id AND g.id = a.garage_id
    JOIN passes pa ON pa.tenant_id = a.tenant_id AND pa.id = a.pass_id
    JOIN passes pb ON pb.tenant_id = b.tenant_id AND pb.id = b.pass_id
   ORDER BY 1
   LIMIT 1;
  IF clash IS NOT NULL THEN
    RAISE EXCEPTION 'migration 0007 refuses to run: two registrations become one car once O '
                    'reads as 0 and I as 1, on overlapping days: %. Nothing was chosen for '
                    'you; end one of them first.', clash;
  END IF;

  SELECT format('%s and %s at garage %s on pass %s (entered %s and %s)',
                a.vehicle_identity, b.vehicle_identity, g.external_id, p.external_id,
                a.entered_at, b.entered_at)
    INTO clash
    FROM visits a
    JOIN visits b
      ON b.tenant_id = a.tenant_id AND b.pass_id = a.pass_id AND b.garage_id = a.garage_id
     AND b.vehicle_identity > a.vehicle_identity
     AND translate(b.vehicle_identity, 'OI', '01') = translate(a.vehicle_identity, 'OI', '01')
     AND a.exited_at IS NULL AND b.exited_at IS NULL
    JOIN garages g ON g.tenant_id = a.tenant_id AND g.id = a.garage_id
    JOIN passes p ON p.tenant_id = a.tenant_id AND p.id = a.pass_id
   ORDER BY 1
   LIMIT 1;
  IF clash IS NOT NULL THEN
    RAISE EXCEPTION 'migration 0007 refuses to run: two open visits become one car once O '
                    'reads as 0 and I as 1: %. Nothing was chosen for you; record the exit '
                    'of one of them first.', clash;
  END IF;
END
$$;

ALTER TABLE vehicle_registrations DROP CONSTRAINT vehicle_registrations_identity_in_normal_form;
ALTER TABLE visits DROP CONSTRAINT visits_identity_in_normal_form;
ALTER TABLE enrolments DROP CONSTRAINT enrolments_plate_check;

UPDATE vehicle_registrations SET vehicle_identity = translate(vehicle_identity, 'OI', '01')
 WHERE vehicle_identity ~ '[OI]';
UPDATE visits SET vehicle_identity = translate(vehicle_identity, 'OI', '01')
 WHERE vehicle_identity ~ '[OI]';
UPDATE enrolments SET plate = translate(plate, 'OI', '01')
 WHERE plate ~ '[OI]';

ALTER TABLE vehicle_registrations
  ADD CONSTRAINT vehicle_registrations_identity_in_normal_form CHECK (
    vehicle_identity = upper(vehicle_identity) AND vehicle_identity !~ '[[:space:].OI-]'
  );

ALTER TABLE visits
  ADD CONSTRAINT visits_identity_in_normal_form CHECK (
    vehicle_identity = upper(vehicle_identity) AND vehicle_identity !~ '[[:space:].OI-]'
  );

ALTER TABLE enrolments
  ADD CONSTRAINT enrolments_plate_check CHECK (
    plate IS NULL OR (length(plate) > 0 AND plate = upper(plate)
                      AND plate !~ '[[:space:].OI-]')
  );

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY string_to_array(current_setting('garage_pass.migration_0007_forced'), ',')
  LOOP
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
  END LOOP;
END
$$;

COMMIT;
