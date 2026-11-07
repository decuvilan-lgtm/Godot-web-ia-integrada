# Godot AI Bridge · sandbox client

This editor plugin is the first executable bridge component. It is loaded by the included sandbox project and connects outward to a trusted backend using **WSS**.

## Current scope

Protocol v1 is intentionally read-only:
- `ping`
- `project.get_state`
- `project.list_files`
- `scene.inspect`
- `script.read`

It does not create nodes, write scripts, delete files, execute shell commands, or run arbitrary code. Scene traversal and file reads have explicit limits.

## Connecting

1. Open the sandbox project in the Godot Web Editor.
2. Enable **Godot AI Bridge** in Project > Project Settings > Plugins if it is not already enabled.
3. In the AI Bridge dock, enter a backend URL beginning with `wss://`.
4. Paste the temporary session token and connect.

The token stays in the plugin's memory and is not written to `project.godot` or the project files.

## WebSocket messages

Client authentication:
```json
{"type":"auth","protocol":1,"token":"<temporary-session-token>"}
```

Server authentication success:
```json
{"type":"auth_ok","protocol":1}
```

Server request:
```json
{"type":"request","id":"req-001","action":"scene.inspect","args":{}}
```

Client response:
```json
{"type":"response","id":"req-001","ok":true,"data":{"scene_path":"res://scenes/main.tscn"},"error":""}
```

The backend must authenticate every connection, bind each token to one project/session, validate message size and rate, and never forward arbitrary shell commands. Use TLS and short-lived, revocable session tokens.

## Next integration stage

The server-side WebSocket gateway and project/session manager are not yet deployed. Write operations will be added only after the read-only round trip is tested and snapshots/diffs are in place.
