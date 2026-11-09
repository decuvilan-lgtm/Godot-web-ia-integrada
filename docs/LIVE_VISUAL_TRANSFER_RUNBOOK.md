# Live Visual Transfer Runbook

Status: 2D/3D capture commands enabled in main; branch-scoped Neon storage credential configured on Render; relay deployment and live capture round-trip still require verification with a paired `web_editor`.

## Safety boundaries

- Use only the isolated AI Godot Web workspace. Do not pair the user's Android editor for this test.
- Keep the Neon bucket `godot-visual-captures` private.
- Never paste the Render administrator secret, device credential, or one-time pairing code into source control, issues, screenshots, or chat.
- The pairing code is single-use and expires after 120 seconds.
- The feature flag is enabled only for `editor_2d` and `editor_3d`. Do not broaden it to `editor_ui`, `game_preview`, or `visual.zoom_to` before those capture backends are implemented and tested.
- The relay may sleep on Render's free plan. The first request can take time while it wakes; this does not mean the service was deleted.

## Pair the isolated Godot Web editor

1. Open the relay's HTTPS administrator page: `https://godot-web-ia-relay.onrender.com/command-center/admin`.
2. Retrieve the value of `COMMAND_CENTER_ADMIN_TOKEN` from the Render service's private environment settings. Do not send it to anyone or put it in the URL.
3. On the page, enter that administrator secret, leave workspace as `default`, and choose **Godot Web** (`web_editor`).
4. Generate a code and use it immediately. It expires in 120 seconds and is displayed once.
5. Open the official isolated Godot Web editor build. In the **Godot Command Center** dock, paste the code into **Código temporal de un solo uso** and press **Emparejar como Godot Web (IA)**.
6. After the dock confirms pairing, press **Iniciar recepción de órdenes**.
7. Do not pair an Android editor for this acceptance test. The web and Android workspaces must remain independent.

The admin page is same-origin, HTTPS-only, no-store, and does not save the administrator secret or pairing code in browser storage. Close it after pairing.

## Controlled acceptance sequence

The operator/maintainer should run these checks after the web editor is paired and polling:

1. Confirm Neon has exactly the expected active `web_editor` device for workspace `default`; confirm no Android device was added or modified.
2. Confirm the Render relay is live and its Neon connection is healthy.
3. Prepare one short-lived, explicitly targeted `visual.capture` command for `editor_2d` on that paired device only. Keep the visual command gate closed for all other commands.
4. Confirm the command is claimed, its lease heartbeat succeeds, and the image bytes are sent to `POST /v1/command-center/visual/uploads/proxy`.
5. Confirm the object appears in the private Neon bucket and registration records its MIME, dimensions, byte size, and SHA-256.
6. Retrieve the same asset through `GET /v1/command-center/visual/assets/{asset_id}/content` using an authorized controller credential. Compare exact bytes and SHA-256 with the registered metadata.
7. Repeat with a small `visual.capture_sequence` (2–3 frames). Verify unique frame indexes, expected count, and final sequence state.
8. Confirm browser/Godot Web requests never go directly to Neon S3 and never receive S3 credentials or presigned URLs.
9. Confirm a failed registration invokes the scoped abandon route and that a registered asset cannot be deleted through it.
10. Disable the temporary test gate again unless the full acceptance suite passes. Only then decide whether to enable the supported visual commands.

## Acceptance evidence to record

- Relay deployment ID and commit SHA.
- Paired device ID and workspace (never the credential).
- Command IDs and statuses.
- Asset IDs, frame indexes, MIME types, dimensions, byte sizes, and SHA-256 hashes.
- Downloaded byte-for-byte equality result.
- Confirmation that the Neon bucket remains private.
- Confirmation that Android pairing/workspace was untouched.

## Current known implementation limits

- The Godot plugin captures `editor_2d` and `editor_3d` SubViewports; only these targets are enabled.
- `editor_ui` and `game_preview` require a browser-level capture backend and are rejected by the API; they must not be substituted with a partial viewport image.
- `visual.zoom_to` remains unavailable until exact view restoration is implemented and tested.
- A still-image sequence is a sequence of images, not a video.
- Automated tests mock S3. They do not replace the live Neon round-trip acceptance test.
