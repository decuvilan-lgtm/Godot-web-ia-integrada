# ChatGPT ↔ GitHub Bridge

This is a deliberately limited bridge for ChatGPT sessions that can use the connected
GitHub repository integration but cannot register this project's custom MCP endpoint.

## Flow

1. ChatGPT creates an issue titled `[CHATGPT-BRIDGE] <short description>`.
2. The issue body is a plain JSON task envelope.
3. The `ChatGPT GitHub Bridge` workflow accepts issues created by repository owner
   `decuvilan-lgtm` only, validates the envelope, and runs one allowlisted task.
4. The runner posts a machine-readable result as an issue comment.
5. ChatGPT fetches the issue and its comments through the GitHub connector.

This is asynchronous GitHub Actions execution, not a direct MCP connection, not a
persistent local agent, and not a live view of the Godot editor.

## Protocol v1

Example body:

```json
{
  "protocol": 1,
  "task_id": "bridge-ping-0001",
  "action": "ping"
}
```

Allowed actions:

- `ping`: return `pong` from the GitHub Actions runner.
- `engine_smoke`: run the existing fixed Godot headless smoke test against
  `examples/bridge-sandbox`.

The task envelope rejects unknown keys, unsupported versions, unsafe task IDs,
oversized bodies, and actions outside the allowlist. It does not accept shell
commands, arbitrary paths, code, secrets, or free-form execution instructions.

## Current limitations

- Only issues opened by `decuvilan-lgtm` with the exact title prefix are processed.
- Editing an existing issue does not re-run a task; create a new issue per request.
- GitHub Actions may queue or delay work; there is no real-time guarantee.
- Artifacts are retained for seven days and may require GitHub authentication.
- The current bridge proves ChatGPT-to-runner messaging and return comments. It does
  not yet retrieve binary screenshots into the ChatGPT conversation.
- Godot execution is isolated to the repository's fixed sandbox. It cannot inspect
  the user's Android editor or a separate desktop session.

## Security

The workflow grants only `contents: read` and `issues: write`. It does not receive
Render, Neon, S3, MCP, or device credentials. The runner checks out `main`, not
the task issue's branch. No issue content is evaluated as code or passed to a shell.
