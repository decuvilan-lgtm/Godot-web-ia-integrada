# AI Bridge WebSocket Protocol v1

This document describes the protocol currently implemented by the Godot editor plugin. It is a client contract, not evidence that a remote relay server is already deployed.

## Transport and authentication

- Transport: secure WebSocket only (`wss://`).
- The URL is entered in the editor dock.
- The user supplies a temporary token. The plugin keeps it in memory only.
- After the socket opens, the plugin sends one authentication packet.

```json
{
  "type": "auth",
  "protocol": 1,
  "token": "temporary-session-token"
}
```

A compatible relay must answer with either:

```json
{ "type": "auth_ok" }
```

or:

```json
{ "type": "auth_error" }
```

The plugin does not process requests before receiving `auth_ok`.

## Request and response envelope

The relay sends a request packet:

```json
{
  "type": "request",
  "id": "request-unique-id",
  "action": "project.get_state",
  "args": {}
}
```

The plugin answers with the same request ID:

```json
{
  "type": "response",
  "id": "request-unique-id",
  "ok": true,
  "data": {},
  "error": ""
}
```

Unknown actions and malformed arguments are rejected. The server must not interpret an editor response as permission to execute arbitrary commands.

## Actions implemented in v1

| Action | Arguments | Result |
| --- | --- | --- |
| `ping` | `{}` | `pong`, protocol version |
| `project.get_state` | `{}` | Project name, currently open scene, capabilities |
| `project.list_files` | `{}` | Bounded list of project file paths |
| `scene.inspect` | `{}` | Current scene path and bounded node tree |
| `script.read` | `{"path":"res://scripts/example.gd"}` | Text content of an allowed project file |

## Limits

- At most 1000 file paths are listed.
- A scene tree is limited to 500 nodes and depth 32.
- A text file read is limited to 256 KiB.
- Only `res://` paths are accepted; paths containing `..` are rejected.
- Only a fixed allowlist of text extensions is readable.
- No write, shell, process-launch, or arbitrary filesystem action is exposed in v1.

## Relay requirements (not yet deployed)

A compatible relay still needs to:
- authenticate the editor and the agent/controller separately;
- create short-lived sessions and expire disconnected sessions;
- correlate request IDs and enforce timeouts;
- enforce message-size, rate, and origin limits;
- avoid logging tokens or project source contents;
- return clear unavailable/offline states when a free service has spun down.

Do not put long-lived credentials in the Godot project or commit them to Git. The current Render deployment is a static site and does not provide the relay endpoint yet.
