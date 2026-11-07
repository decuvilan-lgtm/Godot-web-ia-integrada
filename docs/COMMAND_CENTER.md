# Godot Command Center

## Roles

- **Godot Android**: the user's Android editor built through [Godot-engine4-v4.7.2-stable-difusion-modificado](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado). This repository maintains the reproducible patch/build workflow; it currently fetches upstream Godot 4.7.2-stable at build time rather than storing the full engine source tree.
- **Godot Web**: the agent's remote editor/workspace. Agent edits remain isolated until reviewed.
- **Neon Postgres**: durable state for workspaces, device registrations, sessions, command queue/results, revisions, snapshots, proposals and event history.
- **Neon Realtime**: notification channel for clients that need to react to persisted state changes. Postgres remains the source of truth; clients must reconnect and resume from a cursor.
- **GitHub**: source code and reviewed releases, not a transport for each editor command. The Android engine's persistent modifications live in its patch scripts/workflows.

## Database

Migrations: `database/migrations/001_command_center.sql`, `database/migrations/002_live_link_command_leases.sql`, and `database/migrations/003_require_command_idempotency_keys.sql`.

Schema `command_center` is installed in the Neon project's `neondb` database. It contains:
- `workspaces`: project identity and accepted revision.
- `devices`: Android editor, web editor and agent registrations. Only token hashes belong here.
- `pairing_codes`: short-lived, single-use enrollment codes scoped to a workspace; only SHA-256 hashes are stored.
- `commands` lease fields: `claimed_by_device`, `claim_expires_at` and `attempt_count` support safe recovery after a worker disconnects.
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

The schema, default workspace, workspace-scoped pairing codes, command lease fields and mandatory bounded idempotency keys exist in Neon. Neon Realtime is enabled for the Godot Web editor origin. This is not yet an operational API or a completed end-to-end bridge: no Neon Function has been deployed, no device has been enrolled, and the current Godot bridge remains read-only. Do not advertise Android/Web live synchronization until the API, enrollment, queue worker and reconnect tests are complete.

The Android-side integration is not yet in that repo's source patch. Its current GitHub import patch must be preserved; the next native changes should be layered as a separate, reproducible patch and validated against the exact upstream tag fetched by the build workflow.

## Next implementation steps

1. Deploy an authenticated API/worker that uses Neon Postgres as the source of truth.
2. Add one-time pairing codes and hashed device credentials.
3. Connect the web editor bridge to the durable command queue.
4. Add Android-side project identity, status reporting and safe project export/import to the modified editor build.
5. Implement proposal validation, approval, snapshot and rollback.
6. Test disconnect/reconnect, duplicate commands, stale revisions and Render sleep/restart.
