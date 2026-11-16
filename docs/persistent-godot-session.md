# Persistent Godot Web session

The Relay service owns one Playwright Chromium browser context and its real Godot Web editor page. Workflow B is a short-lived operator client: it reconnects to the existing session, performs an operation, and exits without closing the editor.

## Workflows

- `.github/workflows/persistent-session-operator.yml`: opens, inspects, screenshots, starts/stops the editor preview, clicks visible text, or checkpoints an existing session.
- `.github/workflows/persistent-session-keeper.yml`: sends periodic heartbeats to reduce idle spin-down risk for the Relay service. It does not extend a session's fixed lifetime.
- `.github/workflows/persistent-session-validation.yml`: validates workflow YAML and embedded Python clients.

## Configurable session duration

- The default duration is **10 minutes (600 seconds)**.
- When starting a new session with the operator's `open` operation, change `duration_minutes` to any whole number from **1 to 1440 minutes** (24 hours).
- The chosen duration belongs to that session. It is not a global fixed limit.
- The timer starts after the Godot Web editor page finishes its initial navigation.
- The Relay closes the browser context automatically when the chosen duration expires, even if Workflow B is still connected or sending commands.
- Commands, screenshots, task completion, and keeper heartbeats do not reset or extend the session timer.
- Opening the same project while its session is still alive reuses that session and preserves its original expiry. It does not silently change the duration.
- After expiry, a later `open` creates a new session ID and starts a new timer using the newly selected duration.

The API reports `created_at`, `expires_at`, `max_duration_seconds`, and `remaining_seconds` so Workflow B can check the remaining time.

## Authentication and deployment

The Relay validates GitHub OIDC claims against an explicit workflow allowlist and configured ref. The operator and keeper workflow paths must be included in `PERSISTENT_SESSION_OIDC_ADDITIONAL_WORKFLOWS` (or the code default) and run from the configured ref (currently `refs/heads/main`).

The workflow and Relay changes are being prepared on the development branch. They do not become active until reviewed and deployed to the Relay's configured branch. The current Render Blueprint still targets `main`; this work has not been deployed.

## Limits

- The host is Chromium running the deployed Godot Web editor, not a second editor or a native desktop process.
- Session state is held in Relay memory. A Render restart, redeploy, or process crash destroys the active browser context before its configured timer finishes.
- The keeper reduces idle spin-down risk but cannot prevent provider restarts, deployment interruptions, or scheduled-workflow delays.
- The requested duration is a maximum wall-clock lifetime measured by the Relay process clock. Automatic closure can occur up to approximately five seconds after the deadline due to the reaper interval.
