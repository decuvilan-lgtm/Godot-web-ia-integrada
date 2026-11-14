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

## Temporary editor adapter

The lab-owned Godot EditorPlugin lives under godot-addon/. The Actions worker injects it into the GitHub ZIP response in memory and enables it only in the temporary Godot Web import. The selected project repository and its source ZIP are not changed. The sandbox project intentionally does not ship this add-on.

The archive overlay and its unit tests are implemented; the first Actions end-to-end test is pending. Until the editor responds successfully, unsupported operations must return an explicit error and must never fall back to coordinate automation.

See ../docs/CHROMIUM_GODOT_CONTROLLER.md for the protocol, security boundaries, and acceptance tests.
