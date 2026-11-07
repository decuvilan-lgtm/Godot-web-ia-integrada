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

Migration `004_visual_observations.sql` was applied successfully to production after explicit user authorization. Verification confirmed:
- `command_center.visual_sequences` exists.
- `command_center.visual_assets` exists.
- The three planned visual asset indexes exist, along with primary/unique indexes.
- Both tables currently contain zero rows, as expected before the capture pipeline is implemented.

The sequence source constraint currently lists `editor_2d`, `editor_3d` and `game_preview`. The canonical command contract also permits `editor_ui` sequences; a follow-up schema migration must expand that constraint before such sequences can be persisted. Do not claim this database detail is implemented until that migration is prepared, approved, applied and verified.

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

Uploads and completion must be idempotent. An incomplete upload must not appear as a valid visual asset. Signed URLs must be short-lived, private, never logged and never persisted in the editor project.

## Implementation status

- [x] Neon Object Storage enabled in the existing production project.
- [x] Private bucket `godot-visual-captures` created.
- [x] Migration 004 applied to production and verified.
- [x] Canonical visual command contract documented in `VISUAL_COMMANDS.md`.
- [ ] Add relay endpoints for presigned upload, upload completion and authenticated download.
- [ ] Prepare and approve a follow-up migration allowing `editor_ui` sequence sources.
- [ ] Provision a narrowly scoped storage credential for the Render relay and configure it securely.
- [ ] Implement 2D/3D viewport capture in the Godot Web plugin.
- [ ] Implement temporary coordinate zoom with guaranteed restoration.
- [ ] Connect browser-level screenshot capture for full editor UI and game preview.
- [ ] Implement timed sequences and camera metadata.
- [ ] Add deterministic frame stepping only after a tested preview control hook exists.
- [ ] Connect agent-side asset retrieval and visual inspection.
- [ ] Test real images end-to-end; CI parser checks alone are not sufficient.

## Security and safety

The relay validates device role, command lease, target, coordinate space, dimensions, frame count, interval and payload size. It rejects arbitrary filesystem paths, arbitrary URLs, shell commands and requests to capture another device's private screen. Visual capture does not grant file-write, shell, process-execution or project-apply permissions.
