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

The extension must attach to the existing Actions Chromium session. It must not launch a separate browser or replace screenshots, video, console collection, or existing visual evidence.

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
- editor.open_panel
- scene.open
- scene.select_node
- node.get_inspector

The adapter must validate every field and return a structured object:

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

The example is a capability probe only. Until the Godot-side adapter is installed, the expected structured response is GODOT_ADAPTER_UNAVAILABLE if the extension bridge itself loaded successfully.

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

- Manifest V3 extension directory with a MAIN-world page adapter dispatcher and an isolated content-script relay, scoped to the Godot Web origin.
- Page-world bridge with an explicit semantic allowlist and explicit failure when the editor-side adapter is missing.
- Python client in scripts/bridge/semantic_controller.py that sends bounded semantic requests through the extension without mouse or coordinate operations.
- The Actions worker now loads the extension in the same Chromium instance using a persistent Playwright context and the chromium channel.
- The existing issue command loop accepts semantic_command and routes it through the extension; the older coordinate actions remain isolated for legacy workflows.
- Unit tests for command and argument validation in tests/test_semantic_controller.py.
- Documentation separating this controller from Godot Linux Headless and from the visual Chromium station.

### Not yet implemented or verified

- Editor-side window.__godotEditorAgent adapter in the Godot Web build.
- Successful extension load and message round-trip in an actual GitHub Actions run using the pinned Playwright 1.52.0 environment.
- Real editor command tests and structured state read-back.
- Evidence manifest integration for semantic command logs.

The worker has been updated to load the extension in the same Actions Chromium instance and to probe the bridge. This integration has not yet been exercised in a new Actions run, and the missing editor adapter means actual Godot editor operations remain unavailable. Treat the extension as an integrated prototype, not a verified controller.

## Acceptance gates

1. Actions starts one Chromium session and opens the same Godot Web editor as before.
2. The extension loads in that exact browser session; no second browser is created.
3. editor.list_capabilities returns the adapter version and supported command list.
4. editor.get_state returns the active project, scene, selection and dirty state when available.
5. scene.open and scene.select_node operate by stable scene/node identity, without coordinates.
6. An unknown command is rejected with COMMAND_NOT_ALLOWED.
7. An unsupported editor operation returns CAPABILITY_UNAVAILABLE.
8. A missing adapter returns GODOT_ADAPTER_UNAVAILABLE.
9. Chromium screenshots, video, console logs and existing evidence persistence continue to work unchanged.
10. The command log records requested action, result, duration, request ID and exact project SHA.
