# Remote native Godot operator

This is a separate transport for the native editor addon. It does not use the
Chromium/Web editor session and does not expose the editor's TCP listener.

## Trust model

- Godot addon listens on `127.0.0.1:48765` only.
- The local agent makes outbound HTTPS requests to the Relay.
- The controller authenticates with `NATIVE_REMOTE_CONTROL_TOKEN`.
- Enrollment issues a separate, random agent token for one editor session.
- The agent token can only poll and submit results for its own session.
- Controller commands are allowlisted; arbitrary shell, script evaluation,
  filesystem writes, and browser input are not part of this protocol.
- The queue and sessions are in-memory. Restarting the Relay invalidates all
  active native remote sessions; restart the agent to enroll again.
- Use a dedicated high-entropy secret. Do not reuse the persistent-session or
  admin token.

## Relay configuration

Set `NATIVE_REMOTE_CONTROL_TOKEN` on the **test Relay service only** to a
random secret of at least 32 bytes. Keep the value private. Do not put it in
Git, a workflow file, a URL, or a project file. The API intentionally returns
503 until this variable is configured. Keep the existing legacy bridge disabled.

## Local setup

1. Open the project in the graphical Godot editor and enable
   `addons/headless_session_bridge` in Project Settings > Plugins.
2. Install the Python dependencies for the local agent: `python -m pip install httpx`.
3. Locate the addon's `user://headless_bridge.json` registry file in the
   Godot user data directory for this editor/project.
4. Start the agent on the same machine as Godot:

```sh
python scripts/bridge/native_remote_agent.py \
  --project /absolute/path/to/project \
  --registry /absolute/path/to/headless_bridge.json \
  --relay https://godot-web-ia-relay-test.onrender.com \
  --control-token "$NATIVE_REMOTE_CONTROL_TOKEN"
```

The agent refuses plain HTTP. Keep it running while the editor is available.
Ctrl+C closes its relay session. It never launches or drives the editor UI.

## Controller API

List connected sessions:

```sh
curl -H "Authorization: Bearer $NATIVE_REMOTE_CONTROL_TOKEN" \
  https://godot-web-ia-relay-test.onrender.com/v1/native-remote/sessions
```

Send a semantic read-only request (replace the session ID):

```sh
curl -X POST \
  -H "Authorization: Bearer $NATIVE_REMOTE_CONTROL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command":"editor.get_state","args":{},"timeout_seconds":20}' \
  https://godot-web-ia-relay-test.onrender.com/v1/native-remote/sessions/SESSION_ID/commands
```

The response is returned after the local agent executes the request against the
already-open editor. Mutations should be explicit, reviewed, and saved by the
user; the native addon does not auto-save. This API is not yet wired into the
GitHub Actions B issue-comment command vocabulary, and the test Relay must be
configured before remote end-to-end operation is possible.
