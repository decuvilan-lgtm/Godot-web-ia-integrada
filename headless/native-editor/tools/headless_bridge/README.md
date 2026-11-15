# Headless Session Bridge

This addon lets a separate Godot headless process discover and send a small,
authenticated set of commands to the already-running graphical editor for this
project. The headless process never starts, replaces, or captures a second
editor instance.

## Enablement

The addon is enabled in `project.godot` under `[editor_plugins]`.

When the graphical editor opens, the addon:

1. Starts a TCP listener bound only to `127.0.0.1`.
2. Creates a per-editor random token and writes a discovery record to
   `user://headless_bridge.json`.
3. Publishes the project fingerprint, protocol version, port and editor PID.
4. Removes its own discovery record when the plugin exits.

The record is intentionally local to the machine. It is not a network
rendezvous service; remote machines require a separately designed secure
transport and explicit network policy.

## One-shot operator

From the project directory:

```sh
godot --headless --path . --script res://tools/headless_bridge/bridge_probe.gd -- ping
godot --headless --path . --script res://tools/headless_bridge/bridge_probe.gd -- show_test_marker
godot --headless --path . --script res://tools/headless_bridge/bridge_probe.gd -- clear_test_marker
```

Commands are explicitly allowlisted: `ping`, `show_test_marker`,
`clear_test_marker`, `open_scene`, `inspect_scene`, `list_project_resources`,
`add_node`, `set_node_properties` and `configure_collision_shape`. `open_scene` accepts a JSON object such as
`{"path":"res://scenes/loading.tscn"}` and only permits `.tscn` files beneath
`res://scenes/`. The inspection commands return a bounded scene-tree snapshot
(maximum 200 nodes, depth 8) and a bounded project-resource inventory (maximum
300 entries). Scene-node `path` values are relative to the edited scene root
(the root is `.`); `runtime_path` is included separately for diagnostics and
must never be used as a scene-edit target. Each node also reports its groups and
a deliberately limited set of typed properties. For 2D nodes this includes
transforms and visibility; for collision objects it includes collision layers,
masks and pickability; `Area2D` adds monitoring flags; and `CollisionShape2D`
reports whether a shape is assigned, its resource type, common dimensions and
its disabled/one-way flags. This makes collision-related structure discoverable
without exposing arbitrary editor/Object properties. `open_scene` does not report success merely because the request was accepted:
it waits until the editor's active edited-scene root reports the requested path,
or returns a timeout error if that confirmation never arrives. Pending scene
opens are exempt from the ordinary five-second idle-peer cleanup so the full
ten-second scene confirmation window remains available; the one-shot probe
waits up to fifteen seconds for the definitive response. `add_node`
accepts only a fixed set of common 2D/UI/physics node classes, adds the node to the
currently edited scene through the editor undo manager, and does not save the
scene automatically. `set_node_properties` applies a bounded typed allowlist to
scene-relative node paths (2D transforms, collision layers/masks, Area2D flags,
CharacterBody2D movement configuration, ray/shape-cast settings, and collision
shape flags). `configure_collision_shape` creates only Circle, Rectangle, Capsule,
or Segment shape resources with validated dimensions and assigns them through
one undoable editor action. Values are validated before any edit is committed;
changes are recorded in the editor undo history. Arbitrary properties, object
references, scripts, and unrestricted resource mutation are not accepted. The user can inspect and undo
changes in the editor. Requests are JSON lines containing the protocol version,
project fingerprint and random session token. No arbitrary GDScript, shell
commands, file writes, or eval payloads are accepted.

## Persistent discovery and reconnect

Run a separate process:

```sh
godot --headless --path . --script res://tools/headless_bridge/session_watcher.gd
```

The watcher polls the project's discovery record, authenticates with the
current editor session, sends a heartbeat every second, and returns to
discovery when the editor disappears or stops responding. If the editor is
reopened, it reads the new session token and reconnects. Stop the watcher with
Ctrl+C or by terminating its process.

The editor accepts multiple simultaneous TCP peers on localhost. The
persistent watcher keeps its authenticated heartbeat connection open while
one-shot command clients connect, send an allowlisted request, receive their
response and disconnect. Each peer has an independent input buffer and idle
timeout, so a command client cannot consume or corrupt the watcher's heartbeat
response. This also allows independent operator processes to issue commands
without taking over the persistent discovery/reconnect session.

The current concurrency model is deliberately simple: each peer is processed
on the editor's main thread, requests are handled sequentially, and the server
does not promise parallel execution of editor mutations. The watcher remains
the persistent liveness/reconnect process; probes are short-lived command
clients.

## Boundaries

- Localhost only; no public listener.
- Project fingerprint and random token are both checked.
- Protocol is newline-delimited JSON with a version field.
- No arbitrary code execution.
- Idle peer connections are closed after five seconds without traffic; the timeout and receive buffer are tracked independently per peer.\n- Multiple localhost peers may coexist; the persistent watcher and one-shot command clients do not compete for a socket.
- Incoming buffered JSON lines are limited to 64 KiB; oversized requests are
  disconnected.
- Command-level failures are propagated through the top-level `ok` response.
- Scene mutations are limited to the current edited scene, fixed node/property
  allowlists, strict value validation, and the editor undo history.
- Scene/resource inspection is bounded to prevent unbounded responses.
- No command saves a scene or overwrites project assets automatically.
- The bridge is an experimental QA/operator interface, not a production
  remote-control or multi-user service.
