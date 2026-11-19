-- Additive metadata table for large A/B artifacts stored in the existing private bucket.
-- Apply only to a non-production Neon branch.
CREATE TABLE IF NOT EXISTS command_center.artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES command_center.workspaces(id) ON DELETE CASCADE,
    session_id uuid REFERENCES command_center.sessions(id) ON DELETE CASCADE,
    owner_device_id uuid NOT NULL REFERENCES command_center.devices(id) ON DELETE RESTRICT,
    kind text NOT NULL CHECK (kind IN (
        'context_bundle', 'scene_tree', 'inspector_dump', 'screenshot',
        'video', 'project_archive', 'logs', 'animation_frames', 'command_result'
    )),
    object_key text NOT NULL UNIQUE,
    content_type text NOT NULL CHECK (content_type IN (
        'application/gzip', 'application/zip', 'application/json',
        'image/jpeg', 'image/png', 'video/mp4', 'application/octet-stream'
    )),
    encoding text NOT NULL DEFAULT 'identity' CHECK (encoding IN ('identity', 'gzip')),
    size_bytes bigint NOT NULL CHECK (size_bytes BETWEEN 1 AND 67108864),
    uncompressed_size_bytes bigint NOT NULL CHECK (uncompressed_size_bytes BETWEEN 1 AND 268435456),
    sha256 text NOT NULL CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    uncompressed_sha256 text NOT NULL CHECK (uncompressed_sha256 ~ '^[a-f0-9]{64}$'),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'ready', 'rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '15 minutes'),
    finalized_at timestamptz,
    CHECK ((status = 'ready' AND finalized_at IS NOT NULL) OR status <> 'ready')
);

CREATE INDEX IF NOT EXISTS artifacts_workspace_session_created_idx
    ON command_center.artifacts (workspace_id, session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS artifacts_pending_expiry_idx
    ON command_center.artifacts (expires_at)
    WHERE status = 'pending';
