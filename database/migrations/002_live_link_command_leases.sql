-- 002_live_link_command_leases.sql
-- Additive adapter fields required by the Live Link relay's durable command queue.
-- Safe to re-run; does not drop or rewrite existing project data.

ALTER TABLE command_center.pairing_codes
  ADD COLUMN IF NOT EXISTS workspace_id uuid;

UPDATE command_center.pairing_codes
SET workspace_id = (SELECT id FROM command_center.workspaces WHERE slug='default')
WHERE workspace_id IS NULL;

ALTER TABLE command_center.pairing_codes
  ALTER COLUMN workspace_id SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname='pairing_codes_workspace_id_fkey'
      AND conrelid='command_center.pairing_codes'::regclass
  ) THEN
    ALTER TABLE command_center.pairing_codes
      ADD CONSTRAINT pairing_codes_workspace_id_fkey
      FOREIGN KEY (workspace_id) REFERENCES command_center.workspaces(id) ON DELETE CASCADE;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS pairing_codes_workspace_expiry_idx
  ON command_center.pairing_codes(workspace_id, expires_at)
  WHERE consumed_at IS NULL;

ALTER TABLE command_center.commands
  ADD COLUMN IF NOT EXISTS claimed_by_device uuid,
  ADD COLUMN IF NOT EXISTS claim_expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS attempt_count integer NOT NULL DEFAULT 0;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname='commands_claimed_by_device_fkey'
      AND conrelid='command_center.commands'::regclass
  ) THEN
    ALTER TABLE command_center.commands
      ADD CONSTRAINT commands_claimed_by_device_fkey
      FOREIGN KEY (claimed_by_device) REFERENCES command_center.devices(id) ON DELETE SET NULL;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname='commands_attempt_count_nonnegative'
      AND conrelid='command_center.commands'::regclass
  ) THEN
    ALTER TABLE command_center.commands
      ADD CONSTRAINT commands_attempt_count_nonnegative CHECK (attempt_count >= 0);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS commands_claim_lease_idx
  ON command_center.commands(workspace_id, target, status, priority DESC, created_at)
  WHERE status IN ('queued','claimed');
