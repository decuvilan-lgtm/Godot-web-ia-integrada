# Persistent Godot Web session

The Relay service owns one Playwright Chromium browser context and its real Godot Web editor page. Workflow A hosts that session for a chosen duration. Workflow B is a separate short-lived operator that reconnects to the same page and performs actions without closing it.

## Workflow roles

- **Workflow A — `.github/workflows/persistent-session-host.yml`:** starts or reuses the Godot Web session, remains running for the selected duration, sends periodic heartbeats, and requests closure at the deadline.
- **Workflow B — `.github/workflows/persistent-session-operator.yml`:** connects to the session ID (or resolves the unique active project session), inspects the editor, takes screenshots, sends keyboard/click commands, runs the game, and stores task evidence. Ending B does not close the editor or stop A.
- **Keeper — `.github/workflows/persistent-session-keeper.yml`:** optional periodic Relay warm-up. Heartbeats never extend a session's selected lifetime.
- **Validation — `.github/workflows/persistent-session-validation.yml`:** validates workflow YAML, embedded Python clients, and duration configuration.

## Configurable session duration

- The default is **10 minutes (600 seconds)**. This is only the starting default, not a permanent fixed duration.
- When manually starting Workflow A, change `duration_minutes` to any whole number from **1 to 350 minutes**.
- The selected duration is stored on that individual session. A session created for 20 minutes expires after 20 minutes, not after the default 10.
- Before starting the timer, the Relay waits up to 8 minutes for the connector to confirm the exact imported commit SHA and at least one editor canvas. The chosen duration starts only after that readiness check passes.
- Workflow A stays running during the selected window and sends a heartbeat every 30 seconds. Heartbeats keep the Relay service warm but do not reset or extend the deadline.
- Workflow B can operate on the same `session_id` during the window. B may finish early; A and the editor session remain active until the chosen deadline.
- When the deadline is reached, A requests closure. Independently, the Relay reaper enforces the same per-session deadline and closes the browser context automatically, even if A was cancelled or lost.
- Reopening the same project while its session is still alive reuses that session and preserves its original expiry. It does not silently restart or change the timer.
- After expiry, a later A run creates a new session ID and starts a fresh timer with the newly selected duration.

The API reports `created_at`, `expires_at`, `max_duration_seconds`, and `remaining_seconds` so Workflow B can check how much time remains.

## Authentication and deployment

The Relay validates GitHub OIDC claims against an explicit workflow allowlist and configured ref. Workflow A, Workflow B, and the keeper must be included in the allowlist and run from the configured ref (currently `refs/heads/main`).

The workflow and Relay changes are being prepared on the development branch. They do not become active until reviewed and deployed to the Relay's configured branch. The current Render Blueprint still targets `main`; this work has not been deployed.

## Limits

- The host is Chromium running the deployed Godot Web editor, not a second editor or a native desktop process.
- Session state is held in Relay memory. A Render restart, redeploy, or process crash destroys the active browser context before its configured timer finishes.
- Workflow A's heartbeat reduces idle spin-down risk but cannot prevent provider restarts, deployment interruptions, or runner cancellation.
- The requested duration is a maximum wall-clock lifetime measured by the Relay process clock. Automatic closure can occur up to approximately five seconds after the deadline due to the reaper interval.
