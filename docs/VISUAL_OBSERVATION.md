# Visual Observation Protocol

## Purpose

The Godot Web instance is the **AI's remote editor workspace**. The user continues working in the separate Godot Android editor. The AI must be able to inspect actual rendered output, not only scene-tree metadata and source files.

Neon Command Center remains the command and metadata authority. Neon Object Storage holds the image bytes. Render transports authenticated requests and short-lived upload/download URLs; it must not retain screenshots on its local filesystem.

## Storage provisioned

The Neon production branch `br-dark-shadow-b567bp59` has Object Storage enabled in `us-east-2`. A private bucket named `godot-visual-captures` has been created.

- Bucket access: `private`.
- Image bytes are never placed in command JSONB results.
- Postgres stores capture metadata and private object keys only.
- Access is through short-lived presigned URLs issued by the authenticated relay.
- No public bucket URLs and no long-lived browser storage credentials.

Migration `004_visual_observations.sql` adds:
- `visual_sequences`: bounded groups of consecutive captures.
- `visual_assets`: metadata, dimensions, hash, sequence/frame index and private object key.

The migration file is in the Godot Web IA repository. It has **not yet been applied** to the production Neon branch.

## Observation modes

| Mode | What is captured | Capture mechanism |
|---|---|---|
| `editor_ui` | Full visible Godot Web editor interface, panels and current layout | Browser-level screenshot, outside the Godot plugin |
| `editor_2d` | Actual 2D scene viewport | Godot `EditorInterface.get_editor_viewport_2d()` |
| `editor_3d` | Actual 3D scene viewport | Godot `EditorInterface.get_editor_viewport_3d(index)` |
| `game_preview` | Running game output | Embedded preview/browser capture or an optional project-side capture hook, depending on how the Web editor runs the game |
| `zoom_detail` | Close-up around a requested world coordinate | Temporary viewport focus/zoom, then capture |

The Godot API exposes the editor's 2D and 3D SubViewports. A viewport image is captured after `RenderingServer.frame_post_draw` so the result is not an empty or stale first-frame texture. See the official [EditorInterface 4.7 API](https://docs.godotengine.org/en/4.7/classes/class_editorinterface.html) and [Viewport capture documentation](https://docs.godotengine.org/en/4.7/tutorials/rendering/viewports.html).

A Godot viewport capture is not the same as a full browser screenshot: editor chrome, docks and browser UI must be captured by the browser automation layer. The plugin must not pretend a scene viewport image is a screenshot of the whole editor.

## Coordinate zoom

A capture request may include a temporary focus:

```json
{
  "view": "editor_2d",
  "focus": {
    "coordinate_space": "world_2d",
    "position": [640.0, 360.0],
    "zoom": 3.0
  },
  "restore_view": true
}
```

For 3D:

```json
{
  "view": "editor_3d",
  "viewport_index": 0,
  "focus": {
    "coordinate_space": "world_3d",
    "position": [0.0, 1.5, 0.0],
    "distance": 4.0
  },
  "restore_view": true
}
```

Coordinates must explicitly identify their space: 2D world coordinates, 3D world coordinates, viewport pixels, or normalized viewport coordinates. No ambiguous bare `x/y` values.

Zoom/focus is an observation operation, not a project edit. The implementation must save the original editor view transform/camera state, apply the temporary focus, wait for a rendered frame, capture, and restore the original view even on failure. It must not move project nodes or modify scene files.

## Consecutive 3D captures instead of video

`visual.capture_sequence` requests a bounded sequence of still images:

```json
{
  "source": "game_preview",
  "frames": 12,
  "interval_ms": 200,
  "include_camera": true,
  "include_timestamps": true
}
```

Initial limits:
- 1–24 images per sequence.
- 50–5000 ms between captures.
- JPEG or WebP for normal captures; PNG for pixel-perfect/transparent content when supported.
- Per-image maximum 12 MiB.
- Each image is uploaded directly to private Neon Object Storage.
- Results contain asset IDs, dimensions, timestamps and optional frame/camera metadata, never base64 image blobs.

For animation/movement inspection, each frame carries:
- sequence ID and zero-based frame index;
- capture timestamp and elapsed time;
- viewport/source and resolution;
- active camera transform when available;
- optional target/world transform supplied by a project-side observer.

A contact sheet can be generated from the returned stills for quick comparison, while individual frames remain available for detailed inspection. This is a sequence of stills, not a video stream.

Two timing modes must be distinguished:
1. **Timed observation:** capture every N milliseconds while the game runs. This shows real motion but timing may vary with browser/render performance.
2. **Frame-stepped observation:** pause/advance a controlled simulation and capture after each rendered frame. This is more repeatable but requires a supported game-preview control hook. It must not be claimed until implemented and tested.

## Command contract

Visual commands are initially permitted only for the AI's `web_editor` device. The Android editor retains its original read-only command set until a separate need is approved.

- `visual.capture`: one viewport/browser observation.
- `visual.capture_sequence`: bounded consecutive still captures.
- `visual.zoom_to`: temporary focus/zoom observation; restore original view by default.

The relay must validate target role, command lease, allowed view, coordinate space, dimensions, frame count, interval and payload size. It must reject arbitrary filesystem paths, arbitrary URLs, shell commands, or requests to capture another device's private screen.

## Artifact transfer

1. Agent controller enqueues a visual command in Neon.
2. Godot Web claims it as `web_editor`.
3. The capture backend produces a compressed image.
4. The editor requests a short-lived presigned upload URL from the relay.
5. The editor uploads bytes directly to the private Neon bucket.
6. The editor calls the completion endpoint with the object key, dimensions, MIME type, size and SHA-256.
7. Relay verifies the object metadata and records `visual_assets` in Postgres.
8. The command result returns asset IDs and sequence metadata.
9. The agent controller requests a short-lived download URL and retrieves the image.
10. Neon retains the metadata and object; Render holds no screenshot files.

The upload and completion operations must be idempotent. An incomplete upload must not appear as a valid visual asset. Presigned URLs must be short-lived and must never be written to logs or persisted in the editor project.

## Implementation status

- [x] Confirmed Neon Object Storage is enabled on the existing `us-east-2` project.
- [x] Created private bucket `godot-visual-captures`.
- [x] Added migration file for visual sequence and asset metadata.
- [ ] Apply migration 004 to Neon production branch.
- [ ] Add relay endpoints for presigned upload, completion and authenticated download.
- [ ] Provision a narrowly scoped storage credential for the Render relay and configure it securely.
- [ ] Implement 2D/3D viewport capture in the Godot Web plugin.
- [ ] Implement temporary coordinate zoom with guaranteed restoration.
- [ ] Connect browser-level screenshot capture for full editor UI and game preview.
- [ ] Implement timed 3D frame sequences and camera metadata.
- [ ] Add optional deterministic frame stepping for game preview.
- [ ] Connect agent-side asset retrieval and visual inspection.
- [ ] Test real images end-to-end; CI parser checks alone are not sufficient.

## Safety and workspace boundary

Visual capture is read-only. It does not grant file write, shell, process execution, or permission to apply project changes. Capture requests target only the AI's isolated Godot Web workspace by default. No Android screen capture is requested by this phase.
