# Visual Command Contract

Version: 1.0  
Status: normative request contract; relay proxy deployed; live end-to-end transfer verification pending. The relay currently rejects all visual commands. The Godot plugin can capture only the 2D/3D editor SubViewports and supports JPEG/PNG; browser-level targets and zoom are not implemented.

For the operator pairing steps and controlled acceptance procedure, see [LIVE_VISUAL_TRANSFER_RUNBOOK.md](LIVE_VISUAL_TRANSFER_RUNBOOK.md).

This document is the canonical contract for visual observation commands sent through Neon Command Center. Human requests must be translated into one of these exact command objects before they enter the queue. The relay validates them; the web editor executes only the requested observation.

## 1. Non-negotiable rules

1. Every request names exactly one `target`. "Capture the editor" without a target is invalid.
2. A sequence names an exact positive frame count and an interval in milliseconds.
3. A zoom request names the coordinate space and the coordinate values. Bare `x/y` values are invalid.
4. Visual commands target only `web_editor` (the AI's Godot Web workspace). They never target the user's Android editor.
5. Captures are read-only. Temporary camera/focus changes must be restored even when capture fails.
6. No command may request arbitrary filesystem paths, arbitrary URLs, shell commands, or capture of another device's screen.
7. Image bytes travel from the authenticated Godot Web client to the Render relay, which writes them to the private Neon Object Storage bucket using server-side credentials. The client never receives Neon S3 credentials or a direct S3 URL. Command results contain asset IDs and metadata, never base64 image data.
8. Missing required fields, unknown fields, unsupported target/coordinate combinations, or out-of-range values are rejected before execution.

## 2. Persistent project and multiple queries

All visual requests in this phase operate on the already-open Godot Web AI project inside its existing Neon workspace. A visual request never creates a project, workspace, device pairing or session.

- The authenticated device identity supplies the workspace; callers cannot select a different workspace per query.
- Each request becomes a distinct durable command with its own command ID and idempotency key.
- Multiple commands may be queued against the same workspace/project. The web editor drains them sequentially, preserving a stable editor state and avoiding concurrent UI manipulation.
- Retries of the same logical request reuse the same idempotency key. A genuinely new query gets a new key, but keeps the same workspace/project.
- A capture sequence is one command with multiple frame assets; it is not a set of newly created projects or sessions.
- `sessions` represent device connection state only. They are not created per query.

A future multi-project mode must add explicit project registration/selection. It must never create a project implicitly for each query.

## 3. Target vocabulary

| target | Exact image content | Capture backend | Sequence allowed |
|---|---|---|---|
| `editor_ui` | Entire Godot Web page viewport, including editor docks and panels. | Browser-level page screenshot — not implemented | Not currently supported |
| `editor_2d` | Godot 2D editor viewport only; not the surrounding docks or browser UI. | Godot EditorInterface 2D SubViewport — implemented in plugin, not live-verified | Plugin supports it |
| `editor_3d` | Godot 3D editor viewport only; not the surrounding docks or browser UI. | Godot EditorInterface 3D SubViewport — implemented in plugin, not live-verified | Plugin supports it |
| `game_preview` | The running game's visible preview area only. | Browser/preview capture backend — not implemented | Not currently supported |

`zoom_detail` is not a target. It is an asset classification produced when a capture temporarily focuses a coordinate inside `editor_2d` or `editor_3d`.

A target must never be silently substituted. For example, a request for `editor_ui` must not return an `editor_2d` SubViewport and label it as the editor screenshot.

## 4. Command names

### 3.1 `visual.capture`

Exactly one still image.

Required:
- `target`: one of the four target values above.

Optional:
- `viewport_index`: integer 0–3; required only for `editor_3d` when the editor exposes more than one 3D viewport. Defaults to 0 when omitted.
- Contract formats: `jpeg`, `webp`, or `png`; default `webp`. Current Godot plugin implementation supports only `jpeg` and `png`; `webp` is not yet implemented there.
- `output.max_width`, `output.max_height`: each 320–8192; defaults 2560 and 1440.
- `output.quality`: integer 40–100; applies to JPEG/WebP in the contract. The current plugin applies quality only to JPEG; PNG ignores quality.
- `include_metadata`: boolean; default true.

Example — whole editor page (contract example only; current plugin rejects `editor_ui` until a browser-level capture backend exists):
```json
{
  "target": "editor_ui",
  "output": {
    "format": "webp",
    "max_width": 2560,
    "max_height": 1440,
    "quality": 88
  },
  "include_metadata": true
}
```

Example — 3D viewport only:
```json
{
  "target": "editor_3d",
  "viewport_index": 0,
  "output": {
    "format": "png",
    "max_width": 1920,
    "max_height": 1080
  },
  "include_metadata": true
}
```

### 3.2 `visual.capture_sequence`

A bounded series of still images, never a video.

Required:
- `target`: one of `editor_ui`, `editor_2d`, `editor_3d`, `game_preview`.
- `frames`: integer 2–24.
- `interval_ms`: integer 50–5000.

Optional:
- `viewport_index`: same rule as `visual.capture`.
- `timing_mode`: `realtime` only until deterministic preview stepping exists. Do not accept `frame_step` before its control hook is implemented and tested.
- `output`: same output object as `visual.capture`.
- `include_metadata`: boolean; default true.
- `include_contact_sheet`: boolean; default true. A contact sheet is supplementary; each original frame remains a separate asset.

Example — 12 consecutive screenshots of the 2D viewport:
```json
{
  "target": "editor_2d",
  "frames": 12,
  "interval_ms": 250,
  "timing_mode": "realtime",
  "output": {
    "format": "webp",
    "max_width": 1920,
    "max_height": 1080,
    "quality": 85
  },
  "include_metadata": true,
  "include_contact_sheet": true
}
```

Example — 8 consecutive images of the 3D viewport:
```json
{
  "target": "editor_3d",
  "viewport_index": 0,
  "frames": 8,
  "interval_ms": 150,
  "timing_mode": "realtime",
  "output": {
    "format": "png",
    "max_width": 1600,
    "max_height": 900
  },
  "include_metadata": true,
  "include_contact_sheet": true
}
```

Each frame records a zero-based `frame_index`, capture timestamp, elapsed time, target, dimensions and optional camera/viewport metadata. The sequence result records requested and completed frame counts and the final status (`completed`, `partial`, or `failed`).

### 3.3 `visual.zoom_to`

Temporarily focuses a coordinate in a supported viewport, captures one still, then restores the original view.

Required:
- `target`: `editor_2d` or `editor_3d`.
- `focus.coordinate_space`: exactly one of `world_2d`, `world_3d`, `viewport_pixels`, `viewport_normalized`.
- `focus.position`: 2 numbers for `world_2d`/pixel/normalized coordinates; 3 numbers for `world_3d`.
- `restore_view`: required and must be explicitly set to `true`; omission and `false` are rejected by the relay.

Additional coordinate rules:
- `world_2d`: target must be `editor_2d`; `position=[x,y]`; `zoom` between 0.25 and 16.
- `world_3d`: target must be `editor_3d`; `position=[x,y,z]`; `distance` between 0.1 and 1000.
- `viewport_pixels`: target must be `editor_2d` or `editor_3d`; position is pixel coordinates within that target viewport.
- `viewport_normalized`: target must be `editor_2d` or `editor_3d`; each coordinate is between 0 and 1.
- Pixel/normalized focus requires a supported capture backend to translate viewport focus safely; reject if unsupported rather than guessing.

Example — zoom into a 2D world point:
```json
{
  "target": "editor_2d",
  "focus": {
    "coordinate_space": "world_2d",
    "position": [640.0, 360.0],
    "zoom": 3.0
  },
  "restore_view": true,
  "output": {
    "format": "png",
    "max_width": 1600,
    "max_height": 900
  }
}
```

Example — focus a 3D world point:
```json
{
  "target": "editor_3d",
  "viewport_index": 0,
  "focus": {
    "coordinate_space": "world_3d",
    "position": [0.0, 1.5, 0.0],
    "distance": 4.0
  },
  "restore_view": true
}
```

## 5. Common output and storage limits

- Image dimensions: maximum 8192 × 8192.
- Maximum encoded size per image: 12 MiB.
- Formats: JPEG, WebP, PNG.
- Sequence size: 2–24 frames; interval: 50–5000 ms.
- Object keys are server-generated and scoped to workspace/command/asset IDs. Clients cannot choose arbitrary object keys.
- **Upload path:** the Godot Web client sends raw image bytes to `POST /v1/command-center/visual/uploads/proxy` with its Bearer credential and command headers. Render validates the active command lease and size limit, then writes to the private bucket. The client never talks to Neon S3.
- **Registration path:** after upload, the client calls `POST /v1/command-center/visual/uploads/complete`. The relay rechecks the lease, reads the stored object, verifies actual MIME, dimensions, byte size and SHA-256, then registers the asset in `command_center.visual_assets`.
- **Abandon path:** if the upload succeeded but the lease or metadata registration fails, the paired web editor calls `POST /v1/command-center/visual/uploads/abandon`. The relay verifies workspace, command ownership and that no asset references the key before deleting the unregistered object. Registered assets cannot be removed through this route.
- **Download path:** authorized clients retrieve bytes through `GET /v1/command-center/visual/assets/{asset_id}/content`. The relay checks device role and workspace ownership before reading from the private bucket.
- Legacy presigned upload/download routes remain in `visual_storage.py` for compatibility; they are not the client flow described here and must not be used by the browser/Godot Web client.
- The relay currently has `VISUAL_COMMANDS_ENABLED = False`; all visual commands are rejected before enqueueing. Do not change this to `True` for testing. A separately scoped, one-shot test authorization must be implemented and reviewed after the isolated editor is paired.
- Automated proxy tests mock the S3 client. They prove relay routing and validation behavior, not a real Neon round trip. Live upload/download verification remains pending.
- Results return asset IDs, dimensions, hashes, timestamps and sequence metadata only.

## 6. Sequence semantics

- `realtime`: capture every requested interval while the target is rendering. Actual elapsed intervals may vary with browser and render load; timestamps are authoritative.
- `frame_step`: reserved for a future deterministic preview controller. It must be rejected until the preview can pause, advance exactly one simulation frame, wait for rendering, and resume safely.
- A failed frame does not erase successful frames. Mark the sequence `partial` when at least one frame succeeded but not all did.
- The requested count is a maximum exact target, not a promise that a backend can capture unsupported targets. Unsupported backends fail explicitly.
- Never label a still-image sequence as a video.

## 7. Error codes

| code | Meaning |
|---|---|
| `VISUAL_TARGET_REQUIRED` | Target is missing or invalid. |
| `VISUAL_TARGET_UNAVAILABLE` | Requested capture backend is not implemented/available. |
| `VISUAL_SEQUENCE_LIMIT` | Frame count or interval is outside the allowed range. |
| `VISUAL_COORDINATE_SPACE_REQUIRED` | Focus lacks an explicit coordinate space. |
| `VISUAL_COORDINATE_MISMATCH` | Coordinate dimensions or target do not match. |
| `VISUAL_RESTORE_REQUIRED` | Request attempts to leave the editor view changed. |
| `VISUAL_CAPTURE_TIMEOUT` | Capture did not complete within its deadline. |
| `VISUAL_UPLOAD_INVALID` | Uploaded object failed metadata/hash validation. |

## 8. Examples of natural-language translation

| Human request | Valid command |
|---|---|
| "Show me the whole Godot Web editor." | `visual.capture`, target `editor_ui` |
| "Show me only the 2D canvas." | `visual.capture`, target `editor_2d` |
| "Give me 10 consecutive screenshots of the full editor, 300 ms apart." | `visual.capture_sequence`, target `editor_ui`, frames 10, interval_ms 300 |
| "Give me 15 consecutive images of the 3D viewport, 100 ms apart." | `visual.capture_sequence`, target `editor_3d`, frames 15, interval_ms 100 |
| "Zoom into world position (640, 360) in the 2D viewport." | `visual.zoom_to`, target `editor_2d`, coordinate_space `world_2d` |
| "Show the running game, not the editor." | `visual.capture`, target `game_preview` |

If a human request does not identify which target they mean, the agent must ask one concise clarification before enqueueing a command. It must not guess.

## 9. Workspace boundary

All visual commands in this phase are restricted to the AI's `web_editor` device and its isolated Godot Web workspace. They cannot inspect or capture the user's Android editor, phone screen, or unrelated browser tabs.
