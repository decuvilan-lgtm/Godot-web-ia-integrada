# A/B large-payload transport

Status: architecture specification; not yet wired into the live A/B runtime.

## Goal

Remove GitHub Issues comment-size limits from A/B communication. GitHub remains the source-control and CI system, not the message bus or file-transfer channel.

## Existing infrastructure verified

- Neon project: `Godot Command Center`, region `aws-us-east-2`, free plan.
- Branch: `br-dark-shadow-b567bp59`.
- Neon Functions are available in this region and support long-lived WebSocket connections.
- Neon Object Storage is enabled.
- Existing private bucket: `godot-visual-captures`.
- Existing tables: `command_center.workspaces`, `devices`, `sessions`, `commands`, `command_results`, `events`.
- `commands.args` and `command_results.result` are JSONB; command rows already have idempotency keys, claim leases, attempt counts and expiry.
- The default workspace is `default` / `Godot Android Workspace`.
- The existing bucket already contains historical session ZIP artifacts. Do not delete or rewrite them during migration.

## Two-plane protocol

### Control plane: WebSocket

A and B connect to a Neon Function WebSocket endpoint. It carries only bounded control envelopes:

- `hello`, `ready`, `heartbeat`, `resume`
- `command`, `accepted`, `started`, `completed`, `failed`
- `artifact_available`, `context_manifest`
- `cancel`, `ack`, `ping`, `pong`

Every envelope includes `protocol_version`, `session_id`, `message_id`, `sender_device_id`, `sent_at`, and a small payload. Commands use a stable idempotency key. Never put image base64, project archives, video, or huge scene dumps into a WebSocket frame.

The database remains the durable source of truth. A WebSocket notification is a wake-up signal, not the only copy of a command. After reconnect, a device resumes from its last acknowledged sequence and queries outstanding rows. Claim leases prevent two A workers from executing the same command simultaneously. A completed command is acknowledged only after its result is committed.

### Content plane: private Object Storage

Large content is transferred directly to/from the existing private bucket using short-lived presigned URLs. The WebSocket carries only an artifact manifest:

```json
{
  "artifact_id": "uuid",
  "session_id": "uuid",
  "object_key": "sessions/<session-id>/<artifact-id>.json.gz",
  "kind": "scene_tree",
  "content_type": "application/gzip",
  "encoding": "gzip",
  "size_bytes": 123456,
  "sha256": "<hex digest>",
  "created_at": "ISO-8601 timestamp"
}
```

Supported artifact kinds should include `context_bundle`, `scene_tree`, `inspector_dump`, `screenshot`, `video`, `project_archive`, `logs`, and `animation_frames`.

Upload flow:
1. A/B asks the authenticated Function for an upload URL and artifact ID.
2. Function validates the session, device, allowed artifact kind, declared size and content type.
3. Client uploads bytes directly to the private bucket using the presigned URL.
4. Client sends `artifact_available` with byte length and SHA-256.
5. Function verifies object metadata and records the artifact manifest in Postgres.
6. Recipient requests a short-lived download URL and verifies the hash after download.

Never place permanent S3 credentials in browser JavaScript, repository files, GitHub artifacts, or WebSocket messages. Never trust a client-supplied object key without validating its session-scoped prefix.

## Context packaging

Context is not one unlimited prompt. It is a versioned bundle with:
- a compact manifest and index;
- the current task and requested outcome;
- active project/scene identifiers;
- relevant scene tree and Inspector snapshots;
- selected scripts/resources only when needed;
- recent command history and outcomes;
- image/video references;
- checksums and truncation/omission notes.

Use gzip for text/JSON and preserve binary images/video as binary. Split large artifacts into bounded chunks only when direct object upload is impractical. Keep the context manifest small; fetch only the artifacts needed for the current task. This avoids repeatedly sending the entire project context for every command.

## Security and reliability

- Authenticate both devices; bind each device to the workspace and session.
- Use separate device credentials/scopes for A and B; support revocation.
- Validate message schema, payload limits, artifact type, session ownership and storage key prefix.
- Use server-generated UUIDs and idempotency keys.
- Keep command/result history durable in Postgres.
- Add heartbeats, reconnect with exponential backoff and jitter, lease expiry, and resume cursors.
- Treat duplicate messages as expected; process idempotently.
- Do not expose the private bucket publicly.
- Do not log bearer tokens, presigned URLs, or raw private context.
- Add quotas and TTL cleanup only after retention policy is defined; do not delete existing historical objects during rollout.

## Migration sequence

1. Keep the current Issues transport working as a fallback.
2. Implement and deploy a Neon Function WebSocket endpoint plus authenticated artifact URL endpoints.
3. Add an artifact manifest table and indexes using a reviewed, additive migration.
4. Add a transport adapter to A and B behind a feature flag.
5. Test large JSON bundles, screenshots, multi-megabyte files, disconnect/reconnect, duplicate delivery, stale leases and hash mismatch.
6. Run A/B parity tests: same real Chromium session, same semantic commands, same results.
7. Compare latency and transfer throughput against the Issues baseline.
8. Switch new sessions to WebSocket + Object Storage only after tests pass. Retain Issues fallback during soak period, then remove its command/result path in a separate reviewed change.

## Important distinction

Neon Realtime is useful for live database-query subscriptions, but it is not the large-file transport. WebSocket carries control messages; Object Storage carries bytes; Postgres stores durable command state and artifact metadata.


## First implementation slice

The repository now contains `scripts/bridge/artifacts.py`:

- `pack_json_artifact(payload, session_id=...)` creates deterministic UTF-8 JSON gzip bytes and a manifest with compressed and expanded SHA-256 hashes.
- `unpack_json_artifact(bytes, manifest)` verifies the protocol, kind, encoding, compressed size/hash, expanded size/hash, then decodes JSON.
- `upload_artifact(url, bytes)` and `download_artifact(url, manifest)` transfer through HTTPS presigned URLs. Redirects are refused so signed capabilities are not forwarded to another host.
- Current client-side bounds are 64 MiB compressed and 256 MiB expanded JSON. Artifact kinds are allowlisted.

Automated tests live in `tests/test_ab_artifacts.py`. Focused CI run: [A/B artifact transport validation](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/runs/44405952207) — passed after correcting the corruption test to mutate a byte without changing the payload length.

The additive manifest-table proposal is `sql/001_ab_artifacts.sql`. It references the existing workspace, session, and device records and enforces bounded sizes, allowed content types/kinds, and SHA-256 format. **It has not been applied to Neon.** The existing branch schema was inspected read-only; device records already contain a token hash and revocation timestamp.

## Not live yet

These primitives are not connected to the running A/B session yet. The next required pieces are the Neon Function that authenticates devices and issues scoped upload/download URLs, the manifest finalization endpoint that verifies object metadata, and the A/B adapters that exchange artifact IDs instead of inline payloads. GitHub Issues remains the active fallback until an end-to-end real-browser test passes.


## Client API contract (v1)

The Python client now exposes `upload_json_artifact(...)` and `download_json_artifact(...)`. They expect an authenticated control-plane API at the origin (HTTPS, no path/query) and use these routes:

- `POST /v1/artifacts/upload-url` with `{ "manifest": ... }` → `{ "artifact_id": "...", "upload_url": "https://..." }`.
- Client performs a direct `PUT` to the short-lived URL using the manifest content type.
- `POST /v1/artifacts/finalize` with `{ "artifact_id": "...", "sha256": "..." }` → `{ "artifact_id": "...", "status": "ready" }`.
- `POST /v1/artifacts/download-url` with `{ "artifact_id": "..." }` → `{ "artifact_id": "...", "download_url": "https://...", "manifest": ... }`.

Every control-plane request uses the device bearer token. The client never logs it, refuses non-HTTPS control/storage URLs and redirects, bounds response sizes, and validates the downloaded bytes and expanded JSON before returning a payload. The API must enforce device/session membership on every route; possession of an artifact UUID alone is not authorization.

The device token hash convention for the pending Function implementation is SHA-256 hex of the bearer token, compared against `command_center.devices.token_hash`; revoked devices must be rejected. The database already has `workspace_id`, `device_kind`, `installation_id`, `token_hash`, and `revoked_at` fields. No device currently exists on the inspected branch, so provisioning/pairing remains a prerequisite to a live test.


## Neon artifact control Function

An initial Function implementation is now in `neon/functions/abbridge/`:

- `index.mjs` implements `GET /health` and the three authenticated artifact routes defined above.
- `package.json` declares Node 24 dependencies for Neon Functions, Postgres, and the AWS S3-compatible SDK.
- Device authentication hashes the bearer token with SHA-256 and compares it to `devices.token_hash`; `revoked_at` devices are rejected.
- Session access is restricted to the device IDs attached to that active workspace session.
- Uploads create a pending manifest under a server-generated workspace/session object key, issue a five-minute presigned PUT, and only become downloadable after finalization checks the stored object's byte length and content type.
- Downloads require a ready artifact and a currently authorized session member. The signed GET URL expires after five minutes.
- Control request bodies are capped at 32 KiB; object bytes travel directly between the client and private object storage.

The SQL proposal now stores both compressed and expanded byte counts and SHA-256 digests, matching the client manifest. The Function has not been deployed, and the SQL has not been applied. The deployment still requires confirming the Neon Function environment receives the existing bucket's AWS-compatible variables, applying the reviewed schema, and provisioning two device identities (web editor and agent controller). There are no device rows on the inspected branch yet.


### Durable session endpoints

The Function now also exposes:
- `POST /v1/sessions` — a `web_editor` or `android_editor` device creates a one-hour session.
- `POST /v1/sessions/join` with `{ "session_id": "..." }` — an `agent_controller` or `android_editor` device joins an available session in the same workspace.
- `POST /v1/sessions/heartbeat` with `{ "session_id": "..." }` — a member refreshes activity and extends the session expiry.

The Python client has matching `create_transport_session`, `join_transport_session`, and `heartbeat_transport_session` helpers. Session IDs are database UUIDs; the existing GitHub/browser-run identifier remains a separate correlation ID until the A/B adapters are migrated.


### Durable command queue (GitHub Issues replacement path)

The Function now also implements a Postgres-backed command queue:
- `POST /v1/commands/enqueue` validates the session, target device role, action allowlist, arguments, idempotency key, priority, and TTL.
- `POST /v1/commands/claim` atomically claims one command for the authenticated device's role using `FOR UPDATE SKIP LOCKED`; claims have a 60-second lease and expired leases can be reclaimed.
- `POST /v1/commands/start` transitions a valid claim to running.
- `POST /v1/commands/lease` renews a running/claimed command lease.
- `POST /v1/commands/complete` atomically records success/failure and inserts its result row. Large outputs must be uploaded as artifacts and represented by an artifact ID in the result JSON.

The Python client has corresponding enqueue, claim, start, renew, and complete helpers. This provides a durable polling-based control path that does not have GitHub comment size limits; WebSocket notifications can be layered on later to reduce polling latency, while Postgres remains the source of truth. GitHub Issues is still the fallback until both A and B are wired to these helpers and a real session passes end-to-end.


The command queue uses the existing `command_center.commands` and `command_center.command_results` tables (no replacement queue schema):
- `POST /v1/commands/enqueue` — creates a queued command with workspace-scoped idempotency.
- `POST /v1/commands/claim` — one command per poll, matching the caller's device role.
- `POST /v1/commands/start`, `/lease`, and `/complete` — claim lifecycle and result persistence.

Command bodies/results are capped by the 32 KiB control-request limit. Put screenshots, scene dumps, and large context in object storage, then pass only `artifact_id` and manifest references in `args` or `result`. Claim leases expire after 60 seconds and can be reclaimed, so clients must keep operations idempotent and renew while executing.
