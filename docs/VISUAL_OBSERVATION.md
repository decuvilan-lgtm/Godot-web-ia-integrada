# Visual Observation Architecture

## Purpose and workspace boundary

The Godot Web instance deployed on Render is the **AI's remote editor workspace**. The user continues working in the separate, modified Godot 4.7.2 Android editor on their phone. The web editor is not a replacement or mobile version of the user's editor.

Neon Command Center is the authoritative command and metadata store. Neon Object Storage holds image bytes. Render transports authenticated requests and short-lived upload/download URLs; it must not retain screenshots on its local filesystem.

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

Migration `004_visual_observations.sql` and migration `005_visual_ui_sequences.sql` were applied successfully to production after explicit user authorization. Verification confirmed:
- `command_center.visual_sequences` exists.
- `command_center.visual_assets` exists.
- The three planned visual asset indexes exist, along with primary/unique indexes.
- Both tables currently contain zero rows, as expected before the capture pipeline is implemented.

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

Uploads and completion must be idempotent. Sequence frames are unique by `(sequence_id, frame_index)`; standalone captures require one unique asset per command because PostgreSQL's ordinary UNIQUE constraint treats NULL sequence IDs as distinct. Migration `006_visual_asset_single_capture_idempotency.sql` adds that partial unique index. It is included in the draft branch but has **not** been applied to production. On a retry that creates a fresh object key for an already registered frame, the relay keeps the original asset and attempts to delete the unreferenced duplicate object. An incomplete upload must not appear as a valid visual asset. Signed URLs must be short-lived, private, never logged and never persisted in the editor project.

## Implementation status

- [x] Neon Object Storage enabled in the existing production project.
- [x] Private bucket `godot-visual-captures` created.
- [x] Migration 004 applied to production and verified.
- [x] Migration 005 applied to production and verified.
- [x] Canonical visual command contract documented in `VISUAL_COMMANDS.md`.
- [x] Add relay endpoints for presigned upload, upload completion and authenticated download (implemented on the draft branch; not deployed).
- [x] Make single-capture metadata registration idempotent in code and add duplicate-object cleanup on retries.
- [ ] Apply migration 006 (partial unique index for one standalone capture per command) to production after explicit authorization.
- [x] Apply migration 005 allowing `editor_ui` sequence sources; production verification completed.
- [ ] Provision a narrowly scoped storage credential for the Render relay and configure it securely.
- [x] Implement 2D/3D viewport capture in the Godot Web plugin (CI smoke-tested; live capture not yet demonstrated).
- [ ] Implement temporary coordinate zoom with guaranteed restoration.
- [ ] Connect browser-level screenshot capture for full editor UI and game preview.
- [x] Implement realtime timed still-image sequences and per-frame upload metadata (CI-tested; live storage transfer pending).
- [ ] Add deterministic frame stepping only after a tested preview control hook exists.
- [ ] Connect agent-side asset retrieval and visual inspection.
- [ ] Test real images end-to-end; CI parser checks alone are not sufficient.

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

## Private visual transfer API (implemented, not deployed)

The relay branch now contains `relay/visual_storage.py`, mounted under `/v1/command-center/visual`:

- `POST /uploads/presign`: requires a live command lease owned by the paired `web_editor`; issues a 180-second presigned PUT URL for the private bucket. The server creates the object key; the editor never receives S3 credentials.
- `POST /commands/{command_id}/heartbeat`: renews only an unexpired lease already owned by that editor, capped by the command's absolute expiry. The Godot capture client renews before each frame and before metadata registration so longer sequences do not silently lose ownership.
- `POST /uploads/complete`: rechecks the command lease and workspace, verifies object size and MIME type, downloads at most 12 MiB for SHA-256 and image-format/dimension verification, then inserts metadata in `visual_assets`. The signed object key binds the workspace, command and frame index; duplicate frame submissions are idempotent.
- Sequence results are finalized as `completed`, `partial` or `failed` when the editor submits its command result, based on the requested frame count and successfully registered assets.
- `GET /assets/{asset_id}/download`: workspace-scoped, authenticated controller/web-editor access; issues a short-lived private GET URL. The API returns metadata and URLs, not image bytes.
- S3 calls use path-style SigV4 against the branch endpoint and fail closed unless the four AWS-standard Neon storage environment variables are present.
- New dependencies are pinned in the relay requirements: boto3 and Pillow.

The API has not yet been configured in Render or exercised against production Object Storage. The visual command feature flag remains off. The Godot plugin contains 2D/3D viewport capture and realtime sequence upload code, but no live capture or storage transfer has yet been demonstrated. Browser-level full-UI/game-preview capture, safe zoom restoration and agent-side image inspection remain pending.

## Implementation order and acceptance gates

The visual pipeline stays disabled until each gate is demonstrated:

1. **Storage authorization:** issue a dedicated Neon credential with only `storage:read` and `storage:write`, scoped to the existing production branch. Configure it as Render secrets only after reviewing the exact service and environment target. Never place it in Git, the Godot project, browser JavaScript, command payloads, or logs.
2. **Relay transfer API:** implement short-lived presigned PUT/GET issuance, upload completion, server-generated object keys, lease/workspace checks, object HEAD verification, MIME/size/hash validation, idempotent metadata insertion, and workspace-scoped downloads.
3. **Godot viewport capture:** implement 2D and 3D SubViewport capture after `RenderingServer.frame_post_draw`. Compress and bound images before requesting an upload URL. Keep the device credential in memory and never expose storage credentials to Godot.
4. **Browser-only capture targets:** provide a separately authenticated browser capture agent for `editor_ui` and `game_preview`. Do not pretend a SubViewport image is a full editor screenshot. If this agent is unavailable, return `VISUAL_TARGET_UNAVAILABLE`.
5. **Zoom restoration:** capture and restore the original 2D editor transform or 3D editor camera state in a guaranteed cleanup path, including capture/upload failures.
6. **Sequences:** create one sequence record per command, upload each frame independently with its index and timestamp, preserve successful frames after a later failure, and mark the sequence `partial` when appropriate. Keep `frame_step` rejected until deterministic preview control is proven.
7. **Agent retrieval:** return asset IDs only to the controller, issue short-lived private download URLs after workspace authorization, and verify the controller can inspect the actual bytes.
8. **End-to-end gate:** test real 2D, 3D, full-UI, preview and sequence captures in the deployed Godot Web workspace. Only then enable the visual command feature flag.

The Android editor remains a separate user-owned workspace throughout these steps. No visual command in this phase may target the Android device or phone screen.


## Additional relay verification coverage

The draft relay test suite now exercises the private object verifier with generated PNG bytes and a fake S3 client. It checks successful SHA-256 calculation, strict reported-dimension matching, MIME/extension consistency, invalid image rejection and object-length mismatch. These are deterministic unit tests; they do not replace the pending presigned PUT/GET integration test against the actual private Neon bucket.
