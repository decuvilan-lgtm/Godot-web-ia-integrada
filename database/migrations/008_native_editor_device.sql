-- 008_native_editor_device.sql
-- Add a dedicated native desktop editor role and queue target.
-- Native editor commands remain read-only until snapshot/diff/approval is implemented.

ALTER TABLE command_center.devices
  DROP CONSTRAINT IF EXISTS devices_device_kind_check;
ALTER TABLE command_center.devices
  ADD CONSTRAINT devices_device_kind_check
  CHECK (device_kind IN ('web_editor','android_editor','native_editor','agent_controller'));

ALTER TABLE command_center.commands
  DROP CONSTRAINT IF EXISTS commands_target_check;
ALTER TABLE command_center.commands
  ADD CONSTRAINT commands_target_check
  CHECK (target IN ('web_editor','android_editor','native_editor','agent_controller'));

CREATE INDEX IF NOT EXISTS commands_native_editor_dispatch_idx
  ON command_center.commands(workspace_id, priority DESC, created_at)
  WHERE target='native_editor' AND status IN ('queued','claimed');
