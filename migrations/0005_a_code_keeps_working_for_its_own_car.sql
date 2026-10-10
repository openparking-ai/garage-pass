-- 0005 — A CODE KEEPS WORKING FOR ITS OWN CAR. Until now an enrolment was
-- spent on first use: the same car showing its own QR again was refused, so the
-- code could not be a backup once the car was recognised. From this migration
-- an enrolment BINDS on first use and then stays bound: shown again by the car
-- it is bound to, it answers for that car, in and out, for as long as the pass
-- covers it; shown by a different car, it is refused by name (wrong car).
--
-- Run as the database OWNER, after 0004. 0001 to 0004 are merged and are not
-- edited; what this migration changes on their tables it changes by ALTER.
--
-- WHAT IT ADDS, on `enrolments` only:
--   * EXIT ONLY -- `exit_only_at`, `exit_only_by`, `exit_only_reason`: the car
--     this code is bound to has been replaced on the pass. The code (and the
--     car) no longer enters; it still LEAVES, covered, so a car that broke down
--     inside can go. All three or none, and only on a code that was bound: an
--     unbound code that is replaced is cancelled instead, there being no car to
--     let out.
--   * THE PLATE, FROM ISSUE -- `plate_typed` (as the desk typed it, for display)
--     and `plate` (the one normal form a plate is compared in: capitals, no
--     space, dash or dot). A code is made for a car's plate and is BOUND to it
--     from issue: the issue registers the plate on the pass in the same
--     transaction, and first use binds nothing new. Both or neither: a code
--     stored before plates were required has neither, and binds on first use
--     exactly as it always did.
--   * PICTURE MATCHES -- `matches`: a bound code shown where the lane read no
--     identity opens nothing on its own; the lane matches the car's picture to
--     the bound car's earlier ones and answers (`confirm-match`). EACH answer
--     is kept on the code's own row, in order, with its instant, whether it
--     matched, what identity was read if any, who decided (the OPA ID or
--     the outside picture check) and the outcome -- so a car that keeps
--     needing a match is visible on its code. A JSON array, appended to by the
--     module and never rewritten by it.
--   * A BOUND CODE CAN BE CANCELLED. 0003 tied `state = 'redeemed'` to
--     `redeemed_at` both ways, so a cancelled row could not carry a bind. The
--     rule becomes one-way: a redeemed row has its bind, an issued row has none,
--     and a cancelled row keeps whatever it had -- the record of which car the
--     code was bound to is not erased by cancelling it.
--
-- WHAT DOES NOT MOVE: the token is still never stored (only its SHA-256), no
-- money-shaped or reservation-shaped column, no DELETE grant. The replacement
-- code is an ordinary enrolment on the same pass; which code replaced which is
-- in `exit_only_reason`, written by the module, not a second key.

BEGIN;

ALTER TABLE enrolments
  ADD COLUMN exit_only_at     timestamptz,
  ADD COLUMN exit_only_by     text CHECK (exit_only_by IS NULL OR length(btrim(exit_only_by)) > 0),
  ADD COLUMN exit_only_reason text CHECK (exit_only_reason IS NULL
                                          OR length(btrim(exit_only_reason)) > 0),
  ADD COLUMN matches          jsonb NOT NULL DEFAULT '[]'::jsonb
                              CHECK (jsonb_typeof(matches) = 'array'),
  ADD COLUMN plate_typed      text CHECK (plate_typed IS NULL OR length(btrim(plate_typed)) > 0),
  ADD COLUMN plate            text CHECK (plate IS NULL OR (length(plate) > 0
                                          AND plate = upper(plate)
                                          AND plate !~ '[[:space:].-]'));

ALTER TABLE enrolments
  ADD CONSTRAINT enrolments_exit_only_is_all_or_nothing CHECK (
    (exit_only_by IS NULL) = (exit_only_at IS NULL)
    AND (exit_only_reason IS NULL) = (exit_only_at IS NULL)
  ),
  ADD CONSTRAINT enrolments_exit_only_needs_a_bind CHECK (
    exit_only_at IS NULL OR redeemed_at IS NOT NULL OR plate IS NOT NULL
  ),
  ADD CONSTRAINT enrolments_plate_is_both_or_neither CHECK (
    (plate IS NULL) = (plate_typed IS NULL)
  );

-- one-way now: redeemed has its bind, issued has none, cancelled keeps either
ALTER TABLE enrolments DROP CONSTRAINT enrolments_redeemed_iff_redeemed_at;
ALTER TABLE enrolments
  ADD CONSTRAINT enrolments_redeemed_has_its_bind CHECK (
    (state <> 'redeemed' OR redeemed_at IS NOT NULL)
    AND (state <> 'issued' OR redeemed_at IS NULL)
  );

-- the lookup of the codes bound to a car on a pass: by first use, or by plate
CREATE INDEX enrolments_bound_identity_idx
  ON enrolments (tenant_id, pass_id, redeemed_vehicle_identity)
  WHERE redeemed_vehicle_identity IS NOT NULL;
CREATE INDEX enrolments_plate_idx
  ON enrolments (tenant_id, pass_id, plate)
  WHERE plate IS NOT NULL;

COMMIT;
