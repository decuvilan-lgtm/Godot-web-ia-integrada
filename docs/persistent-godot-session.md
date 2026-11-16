# Persistent Godot Web session

The Relay service owns one Playwright Chromium browser context and its real Godot Web editor page. The operator workflow is a short-lived client: it reconnects to the existing session, performs an operation, and exits without closing the editor.

## Workflows

- `.github/workflows/persistent-session-operator.yml`: opens, inspects, screenshots, starts/stops the editor preview, clicks visible text, or checkpoints an existing session.
- `.github/workflows/persistent-session-keeper.yml`: sends periodic heartbeats to reduce idle spin-down risk for the Relay service. It does not extend the editor session's fixed lifetime.
- `.github/workflows/persistent-session-validation.yml`: validates workflow YAML and embedded Python clients.

## Fixed ten-minute lifecycle

1. When the Relay creates a new editor session, its ten-minute wall-clock timer starts.
2. The session remains available to Workflow B for the full window, even if nobody interacts with it.
3. Operator actions, screenshots, task completion, and keeper heartbeats do not reset or extend the timer.
4. The Relay reaper checks every five seconds and closes the browser context once the ten-minute limit is reached. A command arriving after expiry receives HTTP 410.
5. Opening the same project while its session is still alive reuses that session and reports its original expiry; it does not silently restart the timer.
6. Once expired, a later `open` creates a new session and a new ten-minute window. A new session ID is returned.

The API reports `created_at`, `expires_at`, `max_duration_seconds`, and `remaining_seconds` so operators can see the actual remaining window.

## Authentication and deployment

The Relay validates GitHub OIDC claims against an explicit workflow allowlist and configured ref. The operator and keeper workflow paths must be included in `PERSISTENT_SESSION_OIDC_ADDITIONAL_WORKFLOWS` (or the code default) and run from the configured ref (currently `refs/heads/main`).

The workflow and Relay changes are currently being prepared on the development branch. They do not become active until reviewed and deployed to the Relay's configured branch. The current Render Blueprint still targets `main`; this work has not been deployed.

## Limits

- The host is Chromium running the deployed Godot Web editor, not a second editor or a native desktop process.
- Session state is held in Relay memory. A Render restart, redeploy, or process crash destroys the active browser context before its ten-minute timer finishes.
- The keeper reduces idle spin-down risk but cannot prevent provider restarts, deployment interruptions, or scheduled-workflow delays.
- The ten-minute guarantee is a fixed maximum lifetime measured by the Relay process clock; automatic closure can occur up to approximately five seconds after the deadline due to the reaper interval.
