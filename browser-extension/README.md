# Godot Controller Bridge (experimental)

Chromium Manifest V3 extension for semantic control of the Godot Web editor already open in the GitHub Actions browser session.

## Separation

- This is not the Godot engine Linux Headless runtime.
- It does not replace Chromium or Playwright in GitHub Actions.
- It does not start a second browser or editor.
- It does not use coordinates, mouse clicks, keyboard simulation, arbitrary JavaScript, shell commands, or filesystem access.
- Chromium in Actions remains responsible for screenshots, video, console output, and visual review.

## Current implementation

- MAIN-world page dispatcher with a strict semantic action allowlist.
- Isolated content-script relay between the Actions page and the editor adapter.
- Python request client in scripts/bridge/semantic_controller.py.
- The Actions worker loads this extension in its existing Chromium instance through a persistent Playwright context.
- The trusted issue command loop accepts semantic_command and routes it through the extension.

## Current limitation

Actual Godot editor operations require window.__godotEditorAgent in the Godot Web build. That editor-side adapter is not implemented yet. Requests therefore return GODOT_ADAPTER_UNAVAILABLE when the extension bridge is reached; they must never fall back to coordinate automation.

See ../docs/CHROMIUM_GODOT_CONTROLLER.md for the protocol, security boundaries, and acceptance tests.
