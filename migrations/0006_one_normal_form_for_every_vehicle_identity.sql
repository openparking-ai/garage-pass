-- 0006 -- ONE NORMAL FORM FOR EVERY VEHICLE IDENTITY. From this migration the
-- module writes a vehicle identity -- on a registration and on a visit -- in the
-- one normal form a plate is compared in (``plate_key``: capitals, no space, no
-- invisible character, no dash and no dot), and looks every read up in that
-- form, so "xyz 789" read finds "XYZ789" registered, and "abc-123" on one pass
-- and "ABC 123" on another are one car, met by the one-car-one-pass EXCLUDE.
--
-- Run as the database OWNER, after 0005. 0001 to 0005 are not edited.
--
-- WHAT IT ADDS: the schema's backstop for a row written past the module -- a raw
-- write of "car-1" would otherwise be a second spelling of a car the module
-- holds as "CAR1", invisible to its lookups and to the EXCLUDE. The same rule
-- 0005 put on `enrolments.plate`: no lower case, no ASCII space, dash or dot.
-- (The module's normal form takes out more -- every Unicode space and dash and
-- the invisible characters -- and is the one implementation of it; this is the
-- floor a raw write must clear, not a second normal form.)
--
-- Existing rows: garage-pass is installed nowhere (no stored registration or
-- visit exists outside the test suites, which rebuild the schema every run), so
-- the constraints are added VALID.

BEGIN;

ALTER TABLE vehicle_registrations
  ADD CONSTRAINT vehicle_registrations_identity_in_normal_form CHECK (
    vehicle_identity = upper(vehicle_identity) AND vehicle_identity !~ '[[:space:].-]'
  );

ALTER TABLE visits
  ADD CONSTRAINT visits_identity_in_normal_form CHECK (
    vehicle_identity = upper(vehicle_identity) AND vehicle_identity !~ '[[:space:].-]'
  );

COMMIT;
