# Built-in Godot Web Agent Adapter

## Decision

The controller is part of the Godot Web editor binary, not an add-on installed in an imported game. Imported projects must never receive controller files, project.godot edits, or ZIP overlays.

## Verified upstream integration point

Godot 4.7.2-stable initializes `WebToolsEditorPlugin` from `platform/web/web_main.cpp` inside `godot_web_main()`, guarded by `TOOLS_ENABLED`:

```cpp
#ifdef TOOLS_ENABLED
WebToolsEditorPlugin::initialize();
#endif
```

The implementation is in:
- `platform/web/editor/web_tools_editor_plugin.h`
- `platform/web/editor/web_tools_editor_plugin.cpp`

Its current purpose is to register the browser editor's built-in “Download Project Source” tool. The callback is registered through `EditorNode::add_init_callback`, then the plugin is added to the running editor. This is the correct engine-owned lifecycle hook for the agent adapter.

The editor already exposes a substantial native API through `EditorInterface`, including current/open scenes, edited scene root, selection, inspector, panel switching, scene open/save, and play/stop operations. The adapter should call those native APIs from the editor side.

## Browser-to-editor boundary

A browser extension cannot directly call C++ or GDScript editor APIs merely because it shares the Chromium tab. A build-owned bridge must be registered by the web editor runtime.

Target contract:

- Page-world API: `window.__godotEditorAgent`
- Protocol version: `1`
- Discovery: `getCapabilities()`
- Commands: `dispatch({id, command, args})`
- Results: correlated by `id`, with structured `ok/error` responses.
- The extension relays messages; it does not implement editor operations itself.
- The Actions worker communicates with the extension through the existing browser command loop.

The bridge must queue commands and execute editor operations on the Godot main/editor thread. It must not call editor internals from an arbitrary browser callback or Web Worker thread.

## Initial allowlisted command scope

Read-only first implementation (implemented by the patcher):
- `editor.list_capabilities`
- `editor.get_state`
- `scene.get_tree` (bounded to 256 nodes and 16 levels)

Next read-only additions, after compile and browser acceptance:
- `scene.get_selection`
- `node.get_inspector`

Bounded editor actions next:
- `editor.open_panel` for known panels only
- `scene.open` for validated `res://` scene paths
- `scene.select_node` for paths in the active scene

No arbitrary GDScript evaluation, shell, external URL access, unrestricted filesystem access, or project mutation APIs are exposed.

## Build, wrapper, release, and deployment

The engine build workflow `.github/workflows/build-godot-web-agent-editor.yml` checks out Godot `4.7.2-stable`, applies the anchor-validated patch only to the two engine-owned files, and builds the threaded Web Editor with Emscripten 4.0.0 and SCons. It validates the ZIP contents, records the engine commit and SHA-256, and runs the browser acceptance probe before uploading the artifact.

The custom build artifact from run `43561299883` passed the three read-only probes in real Chromium:
- `editor.list_capabilities`
- `editor.get_state`
- `scene.get_tree`

The fixture project remained byte-for-byte unchanged, and the editor reported no pending native requests after the probes.

The wrapper builder `scripts/build-web.sh` now supports:
- `GODOT_WEB_EDITOR_ARCHIVE`: local custom editor ZIP.
- `GODOT_WEB_EDITOR_URL`: HTTPS URL for a custom editor ZIP.
- `GODOT_WEB_EDITOR_SHA256`: required checksum for either custom source.
- Without custom inputs, it retains the pinned official archive and checksum as rollback.

The wrapper-only build using the custom ZIP passed in run `43564943158`. A second acceptance workflow now launches the patched wrapper itself in Chromium and exercises the same native-agent contract; that test must pass before deployment.

A release workflow is configured to publish a versioned GitHub Release only after a successful custom editor build and native-agent smoke test. The existing Render static service remains unchanged until the wrapper browser acceptance test and release asset verification both pass. Preserve the COOP/COEP headers required for threaded WebAssembly.

## Non-negotiable isolation checks

- Import a clean project archive and record its SHA-256 before import.
- Verify no controller add-on or bridge file appears in the imported project.
- Verify `project.godot` is byte-for-byte unchanged.
- Verify the browser bridge exists before and after project import.
- Keep the browser session alive while commands are exchanged.
- If the Actions session expires, create a new session and import the selected project again; do not inject controller files into it.

## Current status

- **Implemented:** native C++ adapter, bounded queue, protocol v1, browser extension relay, Python semantic client, anchor-validated patcher, and tests.
- **Proven:** Godot 4.7.2 Web Editor compiled successfully; the native adapter answered all three read-only commands in Chromium; `editor_available=true`; pending queue returned to zero; the fixture project hash remained unchanged.
- **Proven:** the custom editor ZIP was consumed by `scripts/build-web.sh`, and the patched wrapper files were produced successfully.
- **Proven:** the patched wrapper's own `index.html` launched in Chromium and repeated all three native-agent probes successfully in run `43565341712`. The scene was `NestedRelayFixture`, the queue drained to zero, the source fixture hash remained unchanged, `crossOriginIsolated` was true, `SharedArrayBuffer` was available, and there were no page errors, request failures, or HTTP errors.
- **Runtime warnings to classify:** Godot logs a wait on a thread that was never started and a TCP server creation error in the browser runtime. They did not block editor use or the adapter probes, but should be understood before deployment.
- **Implemented, not yet executed:** `.github/workflows/release-godot-web-agent.yml` publishes a versioned GitHub Release only after verifying the selected build artifact's metadata, no-overlay marker, and SHA-256. It must be run from the default branch after the PR is integrated.
- **Pending:** execute and verify the versioned release, then deploy to the existing Render static service with rollback.
- **Not changed:** Render services, Neon storage, and any imported game repository.

Do not describe the Render deployment as operational until the wrapper browser acceptance test and deployed-site verification pass.
