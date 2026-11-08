-- 006_visual_asset_single_capture_idempotency.sql
-- PostgreSQL UNIQUE(sequence_id, frame_index) treats NULL sequence IDs as distinct.
-- A standalone capture has both fields NULL, so retries could create duplicate assets.
-- Enforce at most one standalone capture asset per command.
CREATE UNIQUE INDEX IF NOT EXISTS visual_assets_single_command_idx
  ON command_center.visual_assets(command_id)
  WHERE sequence_id IS NULL;
