# Godot Controller Bridge — editor-side add-on

This is the Godot-side adapter for the Chromium extension. It is a **project editor add-on**, not a second browser, not the Linux Headless engine, and not a replacement for the Actions Chromium session.

## What it exposes

When enabled in a Godot Web editor project, the add-on registers `window.__godotEditorAgent.execute(command)` using Godot's Web-only `JavaScriptBridge` and Godot's `EditorInterface` APIs.

Initial read/navigation actions:

- `editor.list_capabilities`
- `editor.get_state` (active scene, selected nodes, bounded scene tree and unsaved scenes)
- `editor.open_panel` (main screen tabs: 2D, 3D, Script, AssetLib)
- `scene.open` (project-local `res://*.tscn`)
- `scene.select_node` (node path in active scene)
- `node.get_inspector` (bounded property snapshot)

No save, arbitrary GDScript execution, shell, external URL, or unrestricted filesystem command is exposed.

## Install into a test project

Copy `addons/godot_controller_bridge` into the test project's `addons/` directory and enable the plugin in Project Settings > Plugins, or add this to `project.godot`:

```ini
[editor_plugins]
enabled=PackedStringArray("res://addons/godot_controller_bridge/plugin.cfg")
```

The plugin intentionally activates only when `OS.has_feature("web")`. It is not intended to be enabled in native desktop or Android editor sessions.

## Important bootstrap limitation

The Godot Web editor loads the selected project into its browser-backed filesystem. This add-on must be present and enabled in that project before the page bridge can control the editor. The Actions worker currently imports the exact project revision and does not yet inject temporary add-on files into the editor's IndexedDB filesystem. Do not edit or commit the user's selected game repository to install this add-on.

The next integration step is a temporary, reversible bootstrap into the Actions editor's in-browser project filesystem, followed by plugin enablement and a verified bridge handshake. If the editor build does not expose the web JavaScriptBridge to editor plugins, this approach must fail closed and move to an engine-level adapter patch.

## Verification status

The add-on is a first implementation, not yet validated by a Godot 4.7.2 Web editor runtime. Its API calls are based on the documented Godot EditorInterface and JavaScriptBridge interfaces. End-to-end acceptance is still required.
