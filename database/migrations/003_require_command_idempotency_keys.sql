-- 003_require_command_idempotency_keys.sql
-- Every queued command must have a bounded, non-empty idempotency key.
-- Verified before application: command_center.commands contained zero rows.

ALTER TABLE command_center.commands
  ALTER COLUMN idempotency_key SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'commands_idempotency_key_length_check'
      AND conrelid = 'command_center.commands'::regclass
  ) THEN
    ALTER TABLE command_center.commands
      ADD CONSTRAINT commands_idempotency_key_length_check
      CHECK (length(idempotency_key) BETWEEN 1 AND 128);
  END IF;
END $$;
