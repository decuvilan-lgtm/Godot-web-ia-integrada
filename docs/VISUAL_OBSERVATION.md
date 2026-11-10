# Visual Observation Architecture

## Purpose and workspace boundary

The Godot Web instance deployed on Render is the **AI's remote editor workspace**. The user continues working in the separate, modified Godot 4.7.2 Android editor on their phone. The web editor is not a replacement or mobile version of the user's editor.

Neon Command Center is the authoritative command and metadata store. Neon Object Storage holds image bytes. Render transports authenticated image bytes through the relay proxy; it must not retain screenshots on its local filesystem or expose S3 credentials/URLs to the editor.

All visual commands in this phase target only the AI's `web_editor` device. They are read-only and cannot inspect the Android editor, the phone screen, unrelated browser tabs, project files outside the web workspace, or the operating system.

## Canonical command specification

The normative command names, exact target vocabulary, JSON shapes, validation limits, coordinate rules, sequence semantics and error codes live in [VISUAL_COMMANDS.md](VISUAL_COMMANDS.md).

Every command must identify exactly what is to be captured:

- `editor_ui`: the full Godot Web page viewport, including editor chrome, docks and panels; excludes browser tabs and OS chrome.
- `editor_2d`: only the Godot 2D editor viewport.
- `editor_3d`: only the Godot 3D editor viewport.
- `game_preview`: only the running game's visible preview area.
- `zoom_detail` is an asset classification, not a capture target. It is produced by temporarily focusing a coordinate in a supported 2D/3D viewport.

A viewport image must never be mislabeled as a full editor screenshot. If a requested capture backend is not implemented or available, the command must fail explicitly rather than silently returning another target.

## Capture mechanisms

| Target | Intended mechanism |
|---|---|
| `editor_ui` | Browser-level page screenshot; outside the Godot plugin |
| `editor_2d` | Godot `EditorInterface.get_editor_viewport_2d()` |
| `editor_3d` | Godot `EditorInterface.get_editor_viewport_3d(index)` |
| `game_preview` | Embedded preview/browser capture or a tested project-side capture hook |

Godot 4.7 exposes the editor's 2D and 3D SubViewports. A viewport image should be captured after `RenderingServer.frame_post_draw` so the result is not an empty or stale first-frame texture. See the official [EditorInterface 4.7 API](https://docs.godotengine.org/en/4.7/classes/class_editorinterface.html) and [Viewport capture documentation](https://docs.godotengine.org/en/4.7/tutorials/rendering/viewports.html).

Full editor chrome and embedded game preview require a browser-level capture mechanism or a tested preview hook. A Godot SubViewport capture alone cannot provide those targets.

## Coordinate focus and restoration

Coordinate focus is requested with `visual.zoom_to`, not by passing ambiguous coordinates to `visual.capture`.

Every focus must declare its coordinate space:
- `world_2d`: two coordinates and a bounded zoom factor; target `editor_2d`.
- `world_3d`: three coordinates and a bounded camera distance; target `editor_3d`.
- `viewport_pixels`: pixel coordinates relative to the named viewport.
- `viewport_normalized`: coordinates from 0 to 1 relative to the named viewport.

No bare `x/y` values are accepted. The implementation saves the original view/camera state, applies the temporary focus, waits for a rendered frame, captures, and restores the original state even on failure. It must not move project nodes or modify scene files. `restore_view` is mandatory and must be true.

## Consecutive still-image sequences

`visual.capture_sequence` creates a bounded sequence of still images, not a video. It requires an exact target, frame count and interval. The initial bounds are 2–24 frames and 50–5000 ms between captures.

Each frame records:
- sequence ID and zero-based frame index;
- capture timestamp and elapsed time;
- target and resolution;
- active camera transform when available;
- optional target/world transform from a tested project-side observer.

A contact sheet may be generated for quick comparison, while individual images remain separately stored for inspection.

Two timing modes are distinct:
1. `realtime`: capture at the requested interval while the target is rendering; actual timing can vary with browser/render performance.
2. `frame_step`: reserved for a future deterministic preview control hook. Reject it until pause/advance/render/wait behavior is implemented and tested.

A partial sequence preserves successful frames and is marked `partial`. Unsupported targets fail explicitly.

## Storage provisioned

Neon production branch `br-dark-shadow-b567bp59`, region `us-east-2`:
- Object Storage is enabled.
- Private bucket `godot-visual-captures` exists.
- No public bucket URLs are used.
- Postgres stores metadata and private object keys only.
- Image bytes never go into command JSONB results.

Migrations `004_visual_observations.sql`, `005_visual_ui_sequences.sql`, `006_visual_asset_single_capture_idempotency.sql` and `007_shared_project_sync.sql` are applied to the production branch. Verification confirmed:
- `command_center.visual_sequences` exists.
- `command_center.visual_assets` exists.
- The three planned visual asset indexes exist, along with primary/unique indexes.
- Both visual tables currently contain zero rows because no `web_editor` has been paired and no live capture command has run.

The sequence source constraint now lists `editor_ui`, `editor_2d`, `editor_3d` and `game_preview`, and was verified on the production branch.

## Artifact transfer

1. Agent controller enqueues a validated visual command in Neon.
2. Godot Web claims it as `web_editor`.
3. The target-specific capture backend produces a compressed image.
4. The editor requests a short-lived presigned upload URL from the relay.
5. The editor uploads bytes directly to the private Neon bucket.
6. The editor submits completion metadata: object key, dimensions, MIME type, size and SHA-256.
7. Relay verifies the object and records `visual_assets` metadata in Postgres.
8. Command result returns asset IDs and sequence metadata, never base64.
9. The authenticated agent controller requests a short-lived download URL and retrieves the image.
10. Neon retains metadata and bytes; Render does not persist screenshot files.

Uploads and completion must be idempotent. Sequence metadata is created transactionally when a command is queued (`pending`), transitions to `capturing` on the first frame, and is finalized as `completed`, `partial` or `failed` on result/expiry. Sequence frames are unique by `(sequence_id, frame_index)`; standalone captures require one unique asset per command because PostgreSQL's ordinary UNIQUE constraint treats NULL sequence IDs as distinct. Migration `006_visual_asset_single_capture_idempotency.sql` adds that partial unique index and is applied to production. On a retry that creates a fresh object key for an already registered frame, the relay keeps the original asset and attempts to delete the unreferenced duplicate object. An incomplete upload must not appear as a valid visual asset. The active proxy path never exposes S3 credentials or signed URLs to the editor.

## Implementation status

- [x] Neon Object Storage enabled in the existing production project.
- [x] Private bucket `godot-visual-captures` created.
- [x] Migration 004 applied to production and verified.
- [x] Migration 005 applied to production and verified.
- [x] Canonical visual command contract documented in `VISUAL_COMMANDS.md`.
- [x] Add authenticated relay-proxy upload, completion, and private content-download endpoints; browser/editor bytes never go directly to Neon S3.
- [x] Make single-capture metadata registration idempotent in code and add duplicate-object cleanup on retries.
- [x] Apply the partial unique index for one standalone capture per command to production.
- [x] Apply migration 005 allowing `editor_ui` sequence sources; production verification completed.
- [x] Provision a branch-scoped Neon credential with only `storage:read` and `storage:write`; configure it as Render secrets.
- [x] Add a manual, non-startup CORS setup utility with exact-origin validation and unit tests; no bucket CORS rules have been changed yet.
- [x] Use the authenticated relay proxy for visual uploads; bucket CORS is not required by this transfer path.
- [x] Implement 2D/3D viewport capture in the Godot Web plugin; CI headless smoke test passed.
- [ ] Implement temporary coordinate zoom with guaranteed restoration.
- [ ] Connect browser-level screenshot capture for full editor UI and game preview.
- [x] Implement realtime timed still-image sequences and per-frame upload metadata.
- [ ] Add deterministic frame stepping only after a tested preview control hook exists.
- [ ] Connect agent-side asset retrieval and visual inspection.
- [ ] Pair the isolated Godot Web editor and test a real image round-trip through Neon; CI tests are not a substitute.

## Security and safety

The relay validates device role, command lease, target, coordinate space, dimensions, frame count, interval and payload size. It rejects arbitrary filesystem paths, arbitrary URLs, shell commands and requests to capture another device's private screen. Visual capture does not grant file-write, shell, process-execution or project-apply permissions.


## Latest verification checkpoint

The Godot Web editor build workflow completed successfully on 2026-11-07:

- Pinned Godot source submodule verification: passed.
- Native Godot headless validation of the bridge sandbox: passed.
- Godot Web Editor build: passed.
- Published bundle verification: passed.
- Three-minute HTTP stability observation against the CI-served bundle: passed.
- Bundle-size report: completed.

This is build/CI evidence only. It does **not** establish that the Render production service stayed healthy for three minutes, that the deployed browser editor is paired, or that any visual capture backend works in the real browser.

## Browser upload CORS setup (utility added; not applied)

Neon Object Storage supports `GetBucketCors`, `PutBucketCors`, `DeleteBucketCors` and automatic OPTIONS preflight handling. The draft branch now includes:

- `relay/storage_cors.py`: explicit operator-run setup utility for the private `godot-visual-captures` bucket.
- It accepts only one exact HTTPS origin (no wildcard, credentials, path, query or fragment).
- It allows PUT/GET/HEAD, only the Content-Type request header, exposes ETag and caches preflight for 300 seconds.
- It writes the CORS rule and immediately reads it back to verify the provider accepted it.
- `tests/live_link/test_storage_cors.py` covers origin validation, least-privilege rule shape and provider read-back verification.
- It is never invoked at application startup and no production CORS configuration has been changed.

This utility is not part of the active capture path: Godot sends image bytes to the authenticated Render relay, which stores them in the private bucket. Do not configure bucket CORS unless a future design intentionally changes to direct browser-to-S3 uploads.

```bash
cd relay
python -m storage_cors
```

The optional CORS utility requires `AWS_ENDPOINT_URL_S3`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `COMMAND_CENTER_STORAGE_CORS_ORIGIN`. It is not part of the active proxy-transfer path and has not been applied to the bucket. No browser-to-S3 CORS rule is needed for the current design.

## Private visual transfer API (deployed; live round-trip pending)

The relay branch now contains `relay/visual_storage.py`, mounted under `/v1/command-center/visual`:

- `POST /uploads/proxy`: requires a live command lease owned by the paired `web_editor`; accepts bounded image bytes and writes them to the private bucket through the relay. The editor never receives S3 credentials or presigned URLs.
- `POST /commands/{command_id}/heartbeat`: renews only an unexpired lease already owned by that editor, capped by the command's absolute expiry. The Godot capture client renews before each frame and before metadata registration so longer sequences do not silently lose ownership.
- `POST /uploads/complete`: rechecks the command lease and workspace, verifies object size and MIME type, downloads at most 12 MiB for SHA-256 and image-format/dimension verification, then inserts metadata in `visual_assets`. The signed object key binds the workspace, command and frame index; duplicate frame submissions are idempotent.
- Sequence results are finalized as `completed`, `partial` or `failed` when the editor submits its command result, based on the requested frame count and successfully registered assets.
- `GET /assets/{asset_id}/content`: workspace-scoped, authenticated controller/web-editor access; streams the verified image bytes through the relay.
- S3 calls use path-style SigV4 against the branch endpoint and fail closed unless the four AWS-standard Neon storage environment variables are present.
- New dependencies are pinned in the relay requirements: boto3 and Pillow.

Render now has the Neon storage endpoint and a branch-scoped read/write credential. The API feature flag is enabled only for `editor_2d` and `editor_3d`; the plugin uploads through the authenticated relay proxy. Live image capture and retrieval remain unverified until the isolated editor is paired and a command is executed. Browser-level full-UI/game-preview capture, safe zoom restoration and agent-side image inspection remain pending.

## Implementation order and acceptance gates

The deployed API accepts only the implemented 2D/3D viewport capture targets. End-to-end readiness remains provisional until each gate is demonstrated:

1. **Storage authorization:** a dedicated Neon credential with only `storage:read` and `storage:write` is already scoped to the production branch and configured as Render secrets. Never place it in Git, the Godot project, browser JavaScript, command payloads, or logs.
2. **Relay transfer API:** deployed proxy upload, completion, abandonment, object verification, SHA-256 metadata registration and workspace-scoped content download are implemented. Validate them against the live private bucket.
3. **Godot viewport capture:** the plugin implements 2D and 3D SubViewport capture after `RenderingServer.frame_post_draw`, bounded JPEG/PNG compression, and relay-proxy upload. Validate it in the deployed browser editor.
4. **Browser-only capture targets:** provide a separately authenticated browser capture agent for `editor_ui` and `game_preview`. Do not pretend a SubViewport image is a full editor screenshot. If this agent is unavailable, return `VISUAL_TARGET_UNAVAILABLE`.
5. **Zoom restoration:** capture and restore the original 2D editor transform or 3D editor camera state in a guaranteed cleanup path, including capture/upload failures.
6. **Sequences:** realtime still-image sequences and per-frame metadata are implemented. Verify a short live sequence, partial-failure handling and cleanup. Keep deterministic `frame_step` rejected until preview control is proven.
7. **Agent retrieval:** asset IDs are returned to the controller; authenticated content download is implemented. Verify byte-for-byte retrieval and connect a usable agent-side runtime that can inspect the image.
8. **End-to-end gate:** test real 2D and 3D captures plus a sequence in the deployed Godot Web workspace. Keep full-UI, game-preview and zoom targets disabled until their separate backends/restoration are implemented.

The Android editor remains a separate user-owned workspace throughout these steps. No visual command in this phase may target the Android device or phone screen.


## Additional relay verification coverage

The relay test suite exercises the private object verifier with generated PNG bytes and a fake S3 client. It checks successful SHA-256 calculation, strict reported-dimension matching, MIME/extension consistency, invalid image rejection and object-length mismatch. These are deterministic unit tests; they do not replace the pending live relay-proxy upload, metadata-registration and authenticated-download test against the actual private Neon bucket.
