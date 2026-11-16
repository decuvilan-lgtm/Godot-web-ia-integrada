# Godot Web Controller Extension

Chromium Manifest V3 extension that relays semantic requests from the Actions worker to the native agent embedded in the Godot Web Editor.

## Separation

- This is not the Linux Headless runtime.
- It does not replace Chromium or Playwright in GitHub Actions.
- It does not start a second browser or editor.
- It does not install an EditorPlugin into an imported game project.
- It does not implement editor operations itself; the built-in Godot Web agent does.
- It does not expose shell, arbitrary scripts, filesystem access or general-purpose JavaScript execution.

## Current implementation

- MAIN-world page dispatcher with a strict allowlist.
- Isolated content-script relay between the Actions worker and the page adapter.
- Python request client in scripts/bridge/semantic_controller.py.
- The Actions worker loads the extension in its existing Chromium instance through a persistent Playwright context.
- The trusted issue command loop accepts semantic_command and routes it through the extension.
- The built-in editor adapter currently exposes read-only capability discovery, editor state and scene tree inspection.

The previous project-installed addon prototype was retired. Its history is documented in godot-addon/README.md; the plugin files were removed so they cannot accidentally be injected into game projects.

See ../docs/CHROMIUM_GODOT_CONTROLLER.md and ../docs/UNIFIED_EDITOR_CONTROL.md for the contract, security boundaries and acceptance tests.
