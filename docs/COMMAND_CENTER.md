# Godot Command Center

## Roles

- **Godot Android**: the user's editor on the phone, built from the Godot source pinned in `engine/godot` (4.7.2-stable). It is the authoritative workspace for accepted user work.
- **Godot Web**: the agent's remote editor/workspace. Agent edits remain isolated until reviewed.
- **Neon Postgres**: durable state for workspaces, device registrations, sessions, command queue/results, revisions, snapshots, proposals and event history.
- **Neon Realtime**: notification channel for clients that need to react to persisted state changes. Postgres remains the source of truth; clients must reconnect and resume from a cursor.
- **GitHub**: source code and reviewed releases, not a transport for each editor command.

## Database

Migration: `database/migrations/001_command_center.sql`.

Schema `command_center` is installed in the Neon project's `neondb` database. It contains:
- `workspaces`: project identity and accepted revision.
- `devices`: Android editor, web editor and agent registrations. Only token hashes belong here.
- `pairing_codes`: short-lived, single-use enrollment codes; only SHA-256 hashes are stored.
- `sessions`: paired editor/controller lifetimes and expiry.
- `commands` / `command_results`: durable, idempotent command queue and results.
- `revisions` / `snapshots`: version lineage and recovery checkpoints.
- `proposals` / `proposal_files`: isolated changes awaiting review.
- `events`: append-only event cursor for reconnect and audit.

The default workspace is seeded as `default` / `Godot Android Workspace`.

## Safety and consistency invariants

1. Android's accepted revision is never overwritten by an agent workspace.
2. Agent work is represented as a proposal against a specific base revision.
3. A proposal can be applied only after validation and explicit approval.
4. Applying a proposal must verify the current accepted revision still equals its base revision; otherwise it becomes `conflicted`.
5. Every mutating operation must be idempotent and create an event.
6. Store only hashes of device tokens. Never commit credentials or place long-lived secrets in a Godot project.
7. The command queue is durable in Postgres. Realtime notifications are hints; clients must query pending work and resume using event IDs after reconnect.
8. The free Render relay may sleep. No authoritative project state or pending command may exist only in its process memory.

## Current implementation boundary

The schema, default workspace and single-use pairing-code table exist in Neon. Neon Realtime is enabled for the Godot Web editor origin. This is not yet an operational API or a completed end-to-end bridge: no Neon Function has been deployed, no device has been enrolled, and the current Godot bridge remains read-only. Do not advertise Android/Web live synchronization until the API, enrollment, queue worker and reconnect tests are complete.

## Next implementation steps

1. Deploy an authenticated API/worker that uses Neon Postgres as the source of truth.
2. Add one-time pairing codes and hashed device credentials.
3. Connect the web editor bridge to the durable command queue.
4. Add Android-side project export/import and revision reporting without overwriting local files.
5. Implement proposal validation, approval, snapshot and rollback.
6. Test disconnect/reconnect, duplicate commands, stale revisions and Render sleep/restart.
