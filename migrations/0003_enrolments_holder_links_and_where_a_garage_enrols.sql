-- 0003 — enrolment: the one-time credential a lane redeems to bind a car to a
-- pass (`enrolments`), the one-time link a holder redeems to write their own
-- name and phone and ask for that credential (`holder_links`), and WHERE a
-- garage enrols (`garages.enrols_at`) with its repair recorded.
--
-- Run as the database OWNER, after 0002. 0001 and 0002 are merged and are not
-- edited; what this migration changes on their tables it changes by ALTER.
--
-- ⛔ THE TOKEN IS NEVER STORED. Only its SHA-256 goes in the row. The plaintext
-- is returned exactly once, by the issue call, and by nothing else -- a
-- database read must not yield a working QR, because this is the credential
-- that opens a barrier. A test issues tokens and scans every column of every
-- table in the catalogue for the plaintext, with the hash as the positive
-- control that the scan reads the column it should.
--
-- THE SHAPE IS COPIED, NOT INVENTED. Composite tenant key to the parent (a
-- foreign-key check runs past row-level security, so a bare `pass_id` would
-- let a tenant-A row name tenant B's pass), ENABLE + FORCE + policy, the same
-- indexes, the same grant: SELECT, INSERT, UPDATE and NO DELETE. Neither table
-- carries `garage_id`: the garage is the pass's, read through the pass -- a copy
-- here would be a second place for one fact to drift, and the day the two
-- disagree is a bug with no constraint to catch it.
--
-- ONE QR PER CAR, his rule: a redeemed enrolment is TERMINAL and binds exactly
-- one vehicle identity. Several outstanding enrolments on one pass are allowed
-- and intended -- a pass may carry several vehicles -- and each redeems to one
-- car and dies. There is deliberately no one-outstanding-per-pass constraint
-- here, and nobody should add one: his pooling forbids it.
--
-- `expired` IS DERIVED from `starts_on` + `days_valid` against the garage's
-- local day, exactly as a pass's expiry is derived from `valid_to`; the CHECK on
-- `state` refuses it so nobody can type it. `days_valid` is STATED: NOT NULL
-- with NO DEFAULT. His product uses three days; that number is documented in
-- the command line's help and the README, never defaulted here.
--
-- ⛔ THERE IS STILL NO COLUMN IN THIS SCHEMA THAT HOLDS MONEY, no reservation-
-- shaped column, and no column added here carries `email` in its name: the
-- holder's email is the identity and it lives on the pass, where it already
-- is. The catalogue tests in G3 read these tables too.

BEGIN;

-- ---------------------------------------------------------------------------
-- garages.enrols_at — WHERE this garage enrols: at its entry lanes or its exit
-- lanes. NULL means UNSTATED, not a default -- the shape `transient_available`
-- already has. R1: a garage that sells no transient parking enrols at entry,
-- necessarily (an unregistered vehicle is not admitted there), so the module
-- DERIVES entry for it and it need not state this field; only a transient
-- garage has a choice, and unstated there makes a redemption refuse to answer
-- naming the field.
--
-- THE R1 CONTRADICTION -- no transient AND enrols at exit -- is refused by the
-- module by name where a garage is created and where this field is repaired;
-- the CHECK below is the backstop for a raw write, and it sits on `garages`
-- reading both columns, so it holds whichever column a raw write moves.
-- ---------------------------------------------------------------------------
ALTER TABLE garages
  ADD COLUMN enrols_at text CHECK (enrols_at IN ('entry', 'exit'));

ALTER TABLE garages
  ADD CONSTRAINT garages_no_transient_means_enrols_at_entry CHECK (
    NOT (transient_available = false AND enrols_at = 'exit')
  );

-- The repair path for the new field: `set-garage-enrols-at` records who, when
-- and why into `garage_changes`, exactly as the timezone repair does. 0002's
-- CHECK listed `timezone` as the only repairable field so that a second repair
-- is a migration and not a free-text value; this is that migration. The old
-- value may be NULL here (the field was unstated), so `old_value` loses its
-- NOT NULL -- the timezone repair's old value is never NULL, since
-- `garages.timezone` is not.
ALTER TABLE garage_changes DROP CONSTRAINT garage_changes_field_check;
ALTER TABLE garage_changes
  ADD CONSTRAINT garage_changes_field_check CHECK (field IN ('timezone', 'enrols_at'));
ALTER TABLE garage_changes ALTER COLUMN old_value DROP NOT NULL;

-- ---------------------------------------------------------------------------
-- enrolments — the QR. Issued by the owner (or by a holder through their link),
-- redeemed once at a lane with the vehicle identity the lane measured, or
-- cancelled with the pass's revocation. `vehicle_description` is the holder's
-- own statement of the car they will bring and DECIDES NOTHING: the identity
-- that binds is what the lane measured, and this module cannot compare an
-- opaque identity to free text and does not pretend to.
-- ---------------------------------------------------------------------------
CREATE TABLE enrolments (
  id                        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                 uuid        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  pass_id                   uuid        NOT NULL,
  external_id               text        NOT NULL CHECK (length(btrim(external_id)) > 0),
  token_sha256              text        NOT NULL CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
  starts_on                 date        NOT NULL,
  days_valid                integer     NOT NULL CHECK (days_valid > 0),
  vehicle_description       text        CHECK (vehicle_description IS NULL
                                               OR length(btrim(vehicle_description)) > 0),
  issued_by                 text        NOT NULL CHECK (length(btrim(issued_by)) > 0),
  issued_at                 timestamptz NOT NULL,
  state                     text        NOT NULL
                            CHECK (state IN ('issued', 'redeemed', 'cancelled')),
  redeemed_vehicle_identity text        CHECK (redeemed_vehicle_identity IS NULL
                                               OR length(btrim(redeemed_vehicle_identity)) > 0),
  redeemed_lane             text        CHECK (redeemed_lane IS NULL
                                               OR length(btrim(redeemed_lane)) > 0),
  redeemed_direction        text        CHECK (redeemed_direction IN ('entry', 'exit')),
  redeemed_at               timestamptz,
  cancelled_by              text        CHECK (cancelled_by IS NULL
                                               OR length(btrim(cancelled_by)) > 0),
  cancelled_at              timestamptz,
  cancelled_reason          text        CHECK (cancelled_reason IS NULL
                                               OR length(btrim(cancelled_reason)) > 0),
  created_at                timestamptz NOT NULL DEFAULT now(),

  -- redeemed: all four redemption columns, and only in that state
  CONSTRAINT enrolments_redemption_is_all_or_nothing CHECK (
    (redeemed_vehicle_identity IS NULL) = (redeemed_at IS NULL)
    AND (redeemed_lane IS NULL) = (redeemed_at IS NULL)
    AND (redeemed_direction IS NULL) = (redeemed_at IS NULL)
  ),
  CONSTRAINT enrolments_redeemed_iff_redeemed_at CHECK (
    (state = 'redeemed') = (redeemed_at IS NOT NULL)
  ),
  -- cancelled: all three cancellation columns, and only in that state
  CONSTRAINT enrolments_cancellation_is_all_or_nothing CHECK (
    (cancelled_by IS NULL) = (cancelled_at IS NULL)
    AND (cancelled_reason IS NULL) = (cancelled_at IS NULL)
  ),
  CONSTRAINT enrolments_cancelled_iff_cancelled_at CHECK (
    (state = 'cancelled') = (cancelled_at IS NOT NULL)
  ),
  CONSTRAINT enrolments_tenant_id_id_key UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, external_id),
  UNIQUE (tenant_id, token_sha256),
  CONSTRAINT enrolments_pass_in_tenant
    FOREIGN KEY (tenant_id, pass_id) REFERENCES passes (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX enrolments_tenant_id_idx ON enrolments (tenant_id);
CREATE INDEX enrolments_pass_idx ON enrolments (tenant_id, pass_id, state);
ALTER TABLE enrolments ENABLE ROW LEVEL SECURITY;
ALTER TABLE enrolments FORCE  ROW LEVEL SECURITY;
CREATE POLICY enrolments_tenant_isolation ON enrolments
  USING      (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- holder_links — the one-time link. The same primitive as the enrolment: a
-- hash stored, the plaintext returned once, a stated window, a single use,
-- cancelled with the pass's revocation. Scoped to ONE pass, whose holder email
-- is the identity -- so the link carries no email of its own. Redeeming it
-- writes the holder's name and phone onto the pass -- those two columns and
-- nothing else -- and issues an enrolment for that pass.
-- ---------------------------------------------------------------------------
CREATE TABLE holder_links (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  pass_id           uuid        NOT NULL,
  external_id       text        NOT NULL CHECK (length(btrim(external_id)) > 0),
  token_sha256      text        NOT NULL CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
  starts_on         date        NOT NULL,
  days_valid        integer     NOT NULL CHECK (days_valid > 0),
  issued_by         text        NOT NULL CHECK (length(btrim(issued_by)) > 0),
  issued_at         timestamptz NOT NULL,
  state             text        NOT NULL
                    CHECK (state IN ('issued', 'redeemed', 'cancelled')),
  redeemed_at       timestamptz,
  cancelled_by      text        CHECK (cancelled_by IS NULL OR length(btrim(cancelled_by)) > 0),
  cancelled_at      timestamptz,
  cancelled_reason  text        CHECK (cancelled_reason IS NULL
                                       OR length(btrim(cancelled_reason)) > 0),
  created_at        timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT holder_links_redeemed_iff_redeemed_at CHECK (
    (state = 'redeemed') = (redeemed_at IS NOT NULL)
  ),
  CONSTRAINT holder_links_cancellation_is_all_or_nothing CHECK (
    (cancelled_by IS NULL) = (cancelled_at IS NULL)
    AND (cancelled_reason IS NULL) = (cancelled_at IS NULL)
  ),
  CONSTRAINT holder_links_cancelled_iff_cancelled_at CHECK (
    (state = 'cancelled') = (cancelled_at IS NOT NULL)
  ),
  CONSTRAINT holder_links_tenant_id_id_key UNIQUE (tenant_id, id),
  UNIQUE (tenant_id, external_id),
  UNIQUE (tenant_id, token_sha256),
  CONSTRAINT holder_links_pass_in_tenant
    FOREIGN KEY (tenant_id, pass_id) REFERENCES passes (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX holder_links_tenant_id_idx ON holder_links (tenant_id);
CREATE INDEX holder_links_pass_idx ON holder_links (tenant_id, pass_id, state);
ALTER TABLE holder_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE holder_links FORCE  ROW LEVEL SECURITY;
CREATE POLICY holder_links_tenant_isolation ON holder_links
  USING      (tenant_id = current_tenant_id())
  WITH CHECK (tenant_id = current_tenant_id());

-- Grants: DML and nothing structural. NO DELETE ANYWHERE, as 0001 and 0002 --
-- and from this round the suite asserts that of EVERY table in the schema,
-- read from the catalogue, not of the tables that cascade into a history: the
-- module issues no DELETE on anything, and a leaf table nobody walked to is
-- exactly the one that would otherwise be missed.
GRANT SELECT, INSERT, UPDATE ON enrolments, holder_links TO garage_pass_app;

COMMIT;
