-- Shared project catalog and revisioned file manifest.
-- File bytes remain in the private Neon Object Storage bucket and are served only by Render.
CREATE TABLE IF NOT EXISTS command_center.projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES command_center.workspaces(id) ON DELETE CASCADE,
  slug text NOT NULL,
  display_name text NOT NULL,
  head_revision bigint NOT NULL DEFAULT 0 CHECK (head_revision >= 0),
  created_by_device uuid REFERENCES command_center.devices(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, slug)
);
CREATE INDEX IF NOT EXISTS projects_workspace_updated_idx
  ON command_center.projects(workspace_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS command_center.project_files (
  project_id uuid NOT NULL REFERENCES command_center.projects(id) ON DELETE CASCADE,
  path text NOT NULL,
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  byte_size bigint NOT NULL CHECK (byte_size > 0 AND byte_size <= 33554432),
  mime_type text NOT NULL,
  object_key text NOT NULL,
  revision bigint NOT NULL CHECK (revision > 0),
  updated_by_device uuid REFERENCES command_center.devices(id) ON DELETE SET NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  PRIMARY KEY(project_id, path)
);
CREATE INDEX IF NOT EXISTS project_files_manifest_idx
  ON command_center.project_files(project_id, path) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS command_center.project_changes (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id uuid NOT NULL REFERENCES command_center.projects(id) ON DELETE CASCADE,
  revision bigint NOT NULL CHECK (revision > 0),
  path text NOT NULL,
  operation text NOT NULL CHECK (operation IN ('add','modify','delete')),
  old_sha256 text,
  new_sha256 text,
  byte_size bigint,
  mime_type text,
  actor_device_id uuid REFERENCES command_center.devices(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(project_id, revision)
);
CREATE INDEX IF NOT EXISTS project_changes_cursor_idx
  ON command_center.project_changes(project_id, revision);
