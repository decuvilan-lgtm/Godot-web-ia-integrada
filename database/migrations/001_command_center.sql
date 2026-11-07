-- 001_command_center.sql
-- Godot Command Center: persistent coordination layer.
-- Safe to re-run; secrets are never stored in plaintext.

CREATE SCHEMA IF NOT EXISTS command_center;

CREATE TABLE IF NOT EXISTS command_center.workspaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text NOT NULL UNIQUE,
  display_name text NOT NULL,
  owner_subject text,
  accepted_revision bigint NOT NULL DEFAULT 0 CHECK (accepted_revision >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS command_center.devices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES command_center.workspaces(id) ON DELETE CASCADE,
  device_kind text NOT NULL CHECK (device_kind IN ('web_editor','android_editor','agent_controller')),
  label text NOT NULL DEFAULT '',
  installation_id text NOT NULL,
  token_hash text NOT NULL,
  last_seen_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, installation_id)
);

CREATE TABLE IF NOT EXISTS command_center.sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES command_center.workspaces(id) ON DELETE CASCADE,
  web_device_id uuid REFERENCES command_center.devices(id) ON DELETE SET NULL,
  android_device_id uuid REFERENCES command_center.devices(id) ON DELETE SET NULL,
  agent_device_id uuid REFERENCES command_center.devices(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'waiting'
    CHECK (status IN ('waiting','connected','paused','closed','expired')),
  protocol_version integer NOT NULL DEFAULT 1,
  expires_at timestamptz NOT NULL,
  last_activity_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS command_center.commands (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES command_center.workspaces(id) ON DELETE CASCADE,
  session_id uuid REFERENCES command_center.sessions(id) ON DELETE SET NULL,
  origin_device_id uuid REFERENCES command_center.devices(id) ON DELETE SET NULL,
  target text NOT NULL CHECK (target IN ('web_editor','android_editor','agent_controller')),
  action text NOT NULL,
  args jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued','claimed','running','succeeded','failed','cancelled','expired')),
  priority smallint NOT NULL DEFAULT 0,
  idempotency_key text,
  created_at timestamptz NOT NULL DEFAULT now(),
  claimed_at timestamptz,
  finished_at timestamptz,
  expires_at timestamptz,
  error_code text,
  error_message text,
  UNIQUE(workspace_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS commands_dispatch_idx
  ON command_center.commands(target,status,priority DESC,created_at);
CREATE INDEX IF NOT EXISTS commands_workspace_recent_idx
  ON command_center.commands(workspace_id,created_at DESC);

CREATE TABLE IF NOT EXISTS command_center.command_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  command_id uuid NOT NULL UNIQUE REFERENCES command_center.commands(id) ON DELETE CASCADE,
  ok boolean NOT NULL,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_code text,
  error_message text,
  duration_ms integer CHECK (duration_ms IS NULL OR duration_ms >= 0),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS command_center.revisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES command_center.workspaces(id) ON DELETE CASCADE,
  revision bigint NOT NULL CHECK (revision >= 0),
  parent_revision bigint,
  source text NOT NULL CHECK (source IN ('android','agent','web','import')),
  manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_device uuid REFERENCES command_center.devices(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id,revision)
);

CREATE TABLE IF NOT EXISTS command_center.snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES command_center.workspaces(id) ON DELETE CASCADE,
  revision bigint NOT NULL,
  snapshot_kind text NOT NULL
    CHECK (snapshot_kind IN ('accepted','agent_checkpoint','pre_apply','rollback')),
  manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  storage_key text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS command_center.proposals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES command_center.workspaces(id) ON DELETE CASCADE,
  base_revision bigint NOT NULL,
  proposed_revision bigint,
  status text NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','validating','ready','approved','rejected','applied','conflicted','failed')),
  title text NOT NULL,
  summary text NOT NULL DEFAULT '',
  diff_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_device uuid REFERENCES command_center.devices(id) ON DELETE SET NULL,
  reviewed_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  reviewed_at timestamptz,
  applied_at timestamptz
);
CREATE INDEX IF NOT EXISTS proposals_workspace_recent_idx
  ON command_center.proposals(workspace_id,created_at DESC);

CREATE TABLE IF NOT EXISTS command_center.proposal_files (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  proposal_id uuid NOT NULL REFERENCES command_center.proposals(id) ON DELETE CASCADE,
  path text NOT NULL,
  operation text NOT NULL CHECK (operation IN ('add','modify','delete','rename')),
  old_hash text,
  new_hash text,
  patch text,
  content_storage_key text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(proposal_id,path)
);

CREATE TABLE IF NOT EXISTS command_center.events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES command_center.workspaces(id) ON DELETE CASCADE,
  session_id uuid REFERENCES command_center.sessions(id) ON DELETE SET NULL,
  actor_device_id uuid REFERENCES command_center.devices(id) ON DELETE SET NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS events_workspace_cursor_idx
  ON command_center.events(workspace_id,id);

INSERT INTO command_center.workspaces (slug,display_name)
VALUES ('default','Godot Android Workspace')
ON CONFLICT (slug) DO NOTHING;
