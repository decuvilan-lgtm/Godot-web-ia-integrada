-- 005_visual_ui_sequences.sql
-- Allow full Godot Web page captures to be stored as a sequence source.
ALTER TABLE command_center.visual_sequences
  DROP CONSTRAINT visual_sequences_source_check;

ALTER TABLE command_center.visual_sequences
  ADD CONSTRAINT visual_sequences_source_check
  CHECK (source IN ('editor_ui','editor_2d','editor_3d','game_preview'));
