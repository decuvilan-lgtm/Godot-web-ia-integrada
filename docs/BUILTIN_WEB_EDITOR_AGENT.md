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

The engine build workflow `.github/workflows/build-godot-web-agent-editor.yml` checks out Godot `4.7.2-stable`, applies anchor-validated changes to the Web Tools plugin and selected Web compatibility callsites, then builds the threaded Web Editor with Emscripten 4.0.0 and SCons. A temporary diagnostic-instrumentation pass also touches additional engine-owned callsites during investigation; it is not intended for the final production artifact. The workflow validates the exact changed-file set, ZIP contents, engine commit and SHA-256, then launches the built editor in Chromium.

Historical artifacts are not proof that the current branch is healthy. In particular, the cached artifact workflow previously reused an older editor build and reproduced a thread-lifecycle warning. The cached browser test has therefore been changed to require an explicitly selected build run ID; the authoritative acceptance test is the Chromium smoke test run against the freshly built artifact.

The wrapper builder `scripts/build-web.sh` supports:
- `GODOT_WEB_EDITOR_ARCHIVE`: local custom editor ZIP.
- `GODOT_WEB_EDITOR_URL`: HTTPS URL for a custom editor ZIP.
- `GODOT_WEB_EDITOR_SHA256`: required checksum for either custom source.
- Without custom inputs, it retains the pinned official archive and checksum as rollback.

The wrapper acceptance workflow also requires an explicitly selected build run ID and verifies the checksum entry for the exact editor ZIP. The versioned GitHub Release workflow is manual-only; a successful build does not automatically publish a release. The existing Render static service remains unchanged until a fresh wrapper acceptance test, explicit release review, and deployment authorization are completed.

## Non-negotiable isolation checks

- Import a clean project archive and record its SHA-256 before import.
- Verify no controller add-on or bridge file appears in the imported project.
- Verify `project.godot` is byte-for-byte unchanged.
- Verify the browser bridge exists before and after project import.
- Keep the browser session alive while commands are exchanged.
- If the Actions session expires, create a new session and import the selected project again; do not inject controller files into it.

## Current status

- **Implemented:** native C++ adapter, bounded native queue, protocol v1, browser extension relay, Python semantic client, anchor-validated patcher, and runtime diagnostic capture.
- **Verified before cleanup:** custom editor build and Chromium probes passed on run [43660833115](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/runs/43660833115); repository checks passed on [43660833184](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/runs/43660833184); official Web Editor verification passed on [43660833118](https://github.com/decuvilan-lgtgm/Godot-web-ia-integrada/actions/runs/43660833118). The custom artifact still contained temporary diagnostic markers, so it is investigation evidence, not clean acceptance.
- **Clean acceptance pending:** temporary engine instrumentation has been removed. A new build must verify that only the six engine files changed by the production patcher are modified and pass Chromium smoke without WEB_DIAG markers.
- **Hardening included:** actual bounded command-loop duration, paginated chronological GitHub comments, strict semantic argument validation, bounded extension pending requests, build-orchestrator error classification, rollback-safe wrapper assembly, and exact source-run validation for manual releases.
- **Project Manager limitation:** Web folder scanning currently falls back to a synchronous scan. Very large directory trees can block the editor; use ZIP import for large projects until bounded/incremental scanning is implemented.
- **Not deployed:** no Render deployment or versioned release has been performed. The release workflow remains manual and now verifies the exact successful build run, branch, and source SHA.
- **Not changed:** imported game repositories, Render services, and Neon storage.

Do not describe the current branch as production-ready until the latest clean custom build, Chromium acceptance, wrapper acceptance, and all repository checks pass. Deployment remains a separate, explicitly authorized action.
