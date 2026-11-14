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

## Build and deployment changes required

The current lab deployment script downloads the precompiled official archive `Godot_v4.7.2-stable_web_editor.zip`. That archive cannot contain our custom adapter.

The build must therefore:
1. Check out the pinned official Godot source tag `4.7.2-stable`.
2. Apply a small, anchor-validated patch under `platform/web/editor/` (engine-owned source only).
3. Build the Web editor with Emscripten and SCons, using the editor target and web platform.
4. Package the resulting editor shell and binaries as a versioned artifact.
5. Deploy that artifact to the existing Godot Web static service.
6. Run a browser acceptance test proving that the built-in API is present, capabilities are returned, and a read-only state command reaches the live editor.

The existing prebuilt download path must remain available as a rollback until the custom artifact passes acceptance.

## Non-negotiable isolation checks

- Import a clean project archive and record its SHA-256 before import.
- Verify no controller add-on or bridge file appears in the imported project.
- Verify `project.godot` is byte-for-byte unchanged.
- Verify the browser bridge exists before and after project import.
- Keep the browser session alive while commands are exchanged.
- If the Actions session expires, create a new session and import the selected project again; do not inject controller files into it.

## Current status

The upstream hook and API surface have been verified against Godot 4.7.2-stable source. The anchor-validated engine patcher, initial read-only adapter, unit tests, and manual build workflow are now present on the feature branch. The Emscripten build, deployment, and live browser acceptance test are not yet verified. Do not describe the adapter as operational until those checks pass.
