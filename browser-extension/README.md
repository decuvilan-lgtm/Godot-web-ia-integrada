# Godot Controller Bridge (experimental)

Chromium Manifest V3 extension scaffold for semantic control of the Godot Web editor opened by the GitHub Actions browser worker.

## Separation

- This is **not** the Godot engine Linux Headless runtime.
- It does not replace Chromium or Playwright in GitHub Actions.
- It does not start a second editor or browser.
- It does not use coordinates, mouse clicks, keyboard simulation, arbitrary JavaScript, shell commands, or filesystem access.
- Chromium in Actions remains responsible for screenshots, video, console output, and visual review.

## Current status

The extension provides a restricted message bridge and allowlisted semantic command dispatcher. Actual Godot editor operations require the matching window.__godotEditorAgent adapter in the Godot Web build. That editor-side adapter is not implemented by this scaffold, so commands currently fail explicitly with GODOT_ADAPTER_UNAVAILABLE rather than falling back to coordinate automation.

See ../docs/CHROMIUM_GODOT_CONTROLLER.md.

The Actions worker integration is intentionally not enabled yet. First validate extension loading in the pinned Playwright/Chromium version and implement the editor-side adapter. Do not remove the existing browser command loop until semantic commands pass end-to-end tests.
