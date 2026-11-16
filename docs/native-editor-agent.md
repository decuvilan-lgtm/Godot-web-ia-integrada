# Native editor queue agent

## Scope

This is the first remote adapter for a persistent Godot Desktop editor. It is intentionally read-only. It does not start or stop the editor, save scenes, change resources, run arbitrary scripts, or expose a public listener.

The process runs on the same machine as the graphical editor and uses the existing localhost Headless Session Bridge. The Command Center connection is outbound HTTPS only.

## Current allowlist

- `ping`
- `editor.get_state`
- `scene.get_tree`
- `project.list_resources`
- `capture.editor_screenshot`
- `capture.desktop_screenshot`

The relay validates the target and action, and the agent independently checks the action again.

## Prerequisites

- A dedicated, trusted Linux desktop host with a supported Godot 4.x build and a real graphical session.
- The project opened in Godot with the Headless Session Bridge addon enabled.
- The bridge discovery record published by the open editor.
- Migration `008_native_editor_device.sql` applied to Neon.
- A dedicated Command Center pairing code for device kind `native_editor`.

Do not install a persistent runner or agent on a device without its owner's explicit permission. Do not use an untrusted pull-request checkout as the host workspace.

## Pairing

Use the existing authenticated admin endpoint to issue a short-lived pairing code with `device_kind=native_editor`. Exchange it at `POST /v1/command-center/pair` with a unique installation ID and label. The returned device credential is a secret: keep it in the host's process environment or a secret manager, never commit it, print it, or put it in the Godot project.

## Run

Set `COMMAND_CENTER_URL` (HTTPS relay base URL), `COMMAND_CENTER_DEVICE_TOKEN` (paired credential), `GODOT_PROJECT_PATH` (absolute isolated workspace path), and optionally `GODOT_BIN` (defaults to `godot`).

Run `python3 headless/native-editor/tools/native_command_agent.py` on the host. The agent polls every two seconds by default. It claims only `native_editor` commands and reports results to the queue. Ctrl+C stops the agent without closing the Godot editor.

## Current limitations

- The relay and agent code are committed to the development branch only.
- The SQL migration has not been applied to the connected Neon database.
- No host has been provisioned, paired, or tested end-to-end.
- Capture payload size and the native screenshot round-trip still require a real host test.
- The agent currently does not renew leases during long captures; execution is bounded to 25 seconds against the 45-second queue lease.
- Native editing/mutation is disabled until isolated snapshots, diffs, approval, validation, and rollback are implemented.

Passing the GitHub validation workflow proves Python syntax, policy tests, and the migration contract only. It does not prove a native Godot host is connected or that Vulkan works.