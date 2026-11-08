-- 004_visual_observations.sql
-- Metadata for private visual artifacts. Image bytes live in Neon Object Storage,
-- never in command_results JSONB or the Render relay filesystem.

CREATE TABLE IF NOT EXISTS command_center.visual_sequences (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES command_center.workspaces(id) ON DELETE CASCADE,
  command_id uuid NOT NULL UNIQUE REFERENCES command_center.commands(id) ON DELETE CASCADE,
  source text NOT NULL CHECK (source IN ('editor_2d','editor_3d','game_preview')),
  requested_frames integer NOT NULL CHECK (requested_frames BETWEEN 1 AND 24),
  interval_ms integer NOT NULL CHECK (interval_ms BETWEEN 50 AND 5000),
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','capturing','completed','partial','failed','cancelled')),
  started_at timestamptz,
  finished_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS command_center.visual_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES command_center.workspaces(id) ON DELETE CASCADE,
  command_id uuid NOT NULL REFERENCES command_center.commands(id) ON DELETE CASCADE,
  sequence_id uuid REFERENCES command_center.visual_sequences(id) ON DELETE CASCADE,
  frame_index integer CHECK (frame_index IS NULL OR frame_index BETWEEN 0 AND 23),
  capture_kind text NOT NULL CHECK (
    capture_kind IN ('editor_2d','editor_3d','game_preview','editor_ui','zoom_detail')
  ),
  object_key text NOT NULL UNIQUE,
  mime_type text NOT NULL CHECK (mime_type IN ('image/jpeg','image/png','image/webp')),
  width integer NOT NULL CHECK (width BETWEEN 1 AND 8192),
  height integer NOT NULL CHECK (height BETWEEN 1 AND 8192),
  byte_size bigint NOT NULL CHECK (byte_size BETWEEN 1 AND 12582912),
  sha256 text NOT NULL CHECK (length(sha256) = 64),
  captured_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(sequence_id, frame_index)
);

CREATE INDEX IF NOT EXISTS visual_assets_workspace_recent_idx
  ON command_center.visual_assets(workspace_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS visual_assets_command_idx
  ON command_center.visual_assets(command_id);
CREATE INDEX IF NOT EXISTS visual_assets_sequence_idx
  ON command_center.visual_assets(sequence_id, frame_index)
  WHERE sequence_id IS NOT NULL;

COMMENT ON TABLE command_center.visual_assets IS
  'Private visual capture metadata; bytes are stored in the private Neon Object Storage bucket godot-visual-captures.';
COMMENT ON COLUMN command_center.visual_assets.object_key IS
  'Private Neon Object Storage key. Never expose as a public URL; issue short-lived authenticated download URLs.';
