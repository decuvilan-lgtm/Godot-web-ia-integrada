# Chromium Godot Controller

## Purpose

Add a small semantic control channel from ChatGPT's Actions worker to the Godot Web editor already open in the Actions-owned Chromium session. The controller removes routine coordinate-based clicking from editor operations.

This component is deliberately distinct from the Linux Godot Headless runtime:

| Component | Role |
|---|---|
| Godot Linux Headless | Full engine runtime used for local development, imports and technical tests |
| Chromium controller bridge | Lightweight command transport and dispatch layer; not an engine and not a second editor |
| Chromium in GitHub Actions | Existing browser session that hosts the editor and remains the visual inspection station |
| Godot editor adapter | Editor-specific implementation that translates semantic commands into supported Godot EditorInterface operations |

The extension is loaded into the existing Actions Chromium session. It must not launch a separate browser or replace screenshots, video, console collection, or existing visual evidence.

## Session lifecycle — one Actions browser, renewed when needed

The controller is part of this repository and runs inside the existing GitHub Actions browser worker. It is not a separate repository, hosted website, or second Chromium instance.

- Opening a trusted `[CHATGPT-BROWSER]` issue starts one Actions workflow, which opens one Godot Web editor tab in one Chromium process.
- While that workflow is alive, the same page and editor stay open. Semantic commands are posted as JSON issue comments and consumed by the worker's command loop; visual inspection uses that same page.
- The current interactive command window is bounded to 600 seconds, and the workflow itself has a 25-minute job limit. A session ending means the hosted job ended; it is not a persistent browser daemon.
- If the window or job expires, start a new `[CHATGPT-BROWSER]` issue. The worker opens a fresh Actions Chromium session, imports the requested exact project SHA, and continues there. No separate web service or repository is needed.
- The next session must re-import the project snapshot. Unsaved in-browser changes from an expired session are not assumed to survive; save/export and verify project changes before renewal.

The existing Actions Chromium remains the visual station. The semantic controller only sends structured editor operations; it does not replace screenshots, video, console collection, or visual review.

## Why an extension alone is not enough

Godot Web renders much of its editor UI inside the engine canvas/WebAssembly application. Those controls are not ordinary HTML buttons with accessible DOM names. A generic extension cannot reliably infer "open scene", "select node", or "save scene" from canvas pixels without returning to coordinate automation.

Therefore the architecture has two parts:

1. A Chromium extension that provides a narrow, authenticated-by-session message bridge and rejects unsupported commands.
2. A small adapter exposed by the Godot Web editor build as window.__godotEditorAgent. The adapter must call supported Godot editor APIs internally and return structured results.

Until the editor-side adapter exists, the extension must return GODOT_ADAPTER_UNAVAILABLE. It must never silently fall back to coordinates, clicks, keyboard simulation, arbitrary JavaScript, or OCR guesses.

## Command contract (v1)

Commands are JSON objects with a protocol version, request ID, action name and bounded arguments. Initial semantic action allowlist:

- editor.get_state
- editor.list_capabilities
- editor.open_panel (Godot main-screen tabs: 2D, 3D, Script, AssetLib)
- scene.open
- scene.select_node
- node.get_inspector

The editor-side prototype is supplied as a Godot EditorPlugin under `browser-extension/godot-addon/`. The Actions worker overlays these files into the ZIP response in memory and enables the plugin in the temporary browser import. The selected GitHub archive and game repository remain unchanged. The plugin uses Godot's documented `JavaScriptBridge` to publish `window.__godotEditorAgent` and `EditorInterface` for scene and selection operations. The adapter must validate every field and return a structured object:

- ok: boolean
- action: action name
- state/result: bounded structured data when successful
- error: stable machine-readable code when unsuccessful
- message: short diagnostic safe for logs

The first milestone is read-only state/capability inspection plus scene navigation and node selection. Mutating operations such as saving are deliberately excluded until explicit idempotency, dirty-state handling, and recovery tests exist. No arbitrary file writes, shell, process execution, arbitrary scripts, arbitrary URLs, or unrestricted editor commands.

## No-coordinate rule

The semantic command API contains no x/y fields, screen positions, viewport ratios, CSS selectors supplied by the caller, or mouse paths. Coordinates may remain in the existing visual observation subsystem only where that subsystem explicitly requires a visual focus operation; they are not part of this controller.

If the adapter cannot identify a target by stable editor identity (scene path, node path, resource ID, panel enum), it returns TARGET_NOT_FOUND or CAPABILITY_UNAVAILABLE. It does not guess.

## Actions integration plan

1. Keep the existing Godot Browser Worker, Actions session lifecycle, issue dispatch, evidence capture and Neon/Artifact persistence.
2. Package this extension in the lab repository and load it into the same Actions-owned Chromium process.
3. Playwright's documented extension path uses a persistent context and the chromium channel for extension-capable headless mode. The worker now uses launch_persistent_context(channel=\"chromium\") with the extension loaded in that same browser process.
4. A Python client sends semantic commands through the extension bridge and awaits structured responses. The existing issue command loop now accepts the semantic_command action.
5. Keep visual screenshots/video and browser console collection in the same page/context.
6. Keep the old coordinate-oriented actions isolated as legacy visual fallbacks. New editor operations must use semantic_command; do not remove the legacy path until visual and canvas-specific workflows have a separate verified replacement.

## Example issue command

The existing trusted issue-comment command loop can now receive a semantic command. The session ID must match the active worker session, and sequence numbers must increase across all commands:

```json
{
  "protocol": 1,
  "session_id": "issue-123",
  "seq": 1,
  "action": "semantic_command",
  "editor_action": "editor.list_capabilities",
  "args": {}
}
```

The example is a capability probe only. The worker supplies the add-on in the temporary imported ZIP; it is not committed to the selected game repository.

## Security boundaries

- Only the Godot Web origin is matched by the extension.
- Only allowlisted semantic action names are accepted.
- Arguments are schema-validated and bounded by the editor adapter.
- No general-purpose execute-JavaScript or arbitrary code channel is exposed to ChatGPT.
- No filesystem, shell, process, arbitrary URL, or credential access is granted.
- The extension does not store tokens or secrets.
- Every request has a unique ID and bounded timeout.
- The Actions worker remains the trusted command origin; page-origin messages are not treated as proof of authorization on their own.
- Results and failures are logged with request IDs, not secret values.

## Implementation status

### Implemented scaffold

- Godot-side EditorPlugin prototype at `browser-extension/godot-addon/addons/godot_controller_bridge/`, exposing a narrow API through JavaScriptBridge and EditorInterface.

- Manifest V3 extension directory with a MAIN-world page adapter dispatcher and an isolated content-script relay, scoped to the Godot Web origin.
- Page-world bridge with an explicit semantic allowlist and explicit failure when the editor-side adapter is missing.
- Python client in scripts/bridge/semantic_controller.py that sends bounded semantic requests through the extension without mouse or coordinate operations.
- The Actions worker now loads the extension in the same Chromium instance using a persistent Playwright context and the chromium channel.
- The existing issue command loop accepts semantic_command and routes it through the extension; the older coordinate actions remain isolated for legacy workflows.
- Unit tests for command and argument validation in tests/test_semantic_controller.py.
- Documentation separating this controller from Godot Linux Headless and from the visual Chromium station.

### Implemented scaffold; runtime verification pending

- Temporary ZIP overlay in `scripts/bridge/project_overlay.py`: adds the lab-owned EditorPlugin and enables it in the project copy consumed by Godot Web. It does not write to the source repository or local project archive.
- The worker intercepts only the GitHub archive request in the existing Actions page and fails closed if the overlay cannot be applied.
- The bridge sandbox source no longer contains the controller add-on; the current Actions test is intended to verify that the temporary overlay makes it available.
- Unit tests for ZIP layout, plugin activation, idempotency, unsafe paths and conflict handling are now part of the browser workflow.
- Successful Actions import with the overlay, real editor state read-back, scene navigation and node inspection are still pending confirmation.

The worker loads the extension in the same Actions Chromium instance and temporarily injects the editor adapter into the ZIP before Godot imports it. The test in issue #50 is the first end-to-end validation of this no-project-modification path. Until it completes, treat the overlay as implemented but not yet runtime-verified.

## Acceptance gates

1. Actions starts one Chromium session and opens the same Godot Web editor as before.
2. The extension loads in that exact browser session; no second browser is created.
3. editor.list_capabilities returns the adapter version and supported command list.
4. editor.get_state returns the active project, scene, selection and dirty state when available.
5. scene.open and scene.select_node operate by stable scene/node identity, without coordinates.
6. An unknown command is rejected with COMMAND_NOT_ALLOWED.
7. An unsupported editor operation returns CAPABILITY_UNAVAILABLE.
8. A missing or disabled add-on returns GODOT_ADAPTER_UNAVAILABLE.
9. Chromium screenshots, video, console logs and existing evidence persistence continue to work unchanged.
10. The command log records requested action, result, duration, request ID and exact project SHA.
