# Persistent Godot session: operator/host split

The persistent browser/editor host is the Relay service, not a GitHub Actions runner.
The Relay owns the Playwright browser context and its editor page in `persistent_sessions.py`.
A completed operator job does not close that context. The operator workflow is disposable and reconnects to the Relay by session ID.

## Workflows

- `.github/workflows/persistent-session-operator.yml`: manually opens, inspects, screenshots, starts/stops the editor preview, clicks visible text, or checkpoints an existing session.
- `.github/workflows/persistent-session-keeper.yml`: scheduled heartbeat every ten minutes. It refreshes active session idle leases and sends traffic to keep a free Render instance warm.
- `.github/workflows/persistent-session-smoke.yml`: existing browser-worker smoke/import workflow. It is not the persistent host and should not be used as the operator.

## Session lifecycle

1. Run the operator with `operation=open` once. Record the returned `session_id`.
2. Run later operator jobs with that same ID (or omit it to resolve the unique matching repository/branch/project).
3. Use `inspect` to inspect the current page, `run_game` to send F5, `stop_game` to send Escape, and `screenshot` or `complete` to persist evidence.
4. Task completion writes an evidence ZIP to Neon Object Storage and explicitly returns `session_kept_open=true`.
5. Close the session only by calling the existing DELETE endpoint; the operator workflow intentionally has no close action.

## Authentication and deployment

The Relay validates GitHub OIDC claims against an explicit workflow allowlist and the configured ref. The two new workflow paths must be included in `PERSISTENT_SESSION_OIDC_ADDITIONAL_WORKFLOWS` (or the code default) and must run from the configured ref (currently `refs/heads/main`). The workflow files and Relay code are committed to the development branch first; they do not become active until the changes are reviewed and deployed to the Relay's configured branch.

## Limits and honest guarantees

- The host is a Relay-owned Chromium browser session for the deployed Godot Web editor. It is not a native desktop Godot process or a native Vulkan runtime.
- Session state is in-memory in the Relay process; screenshots and task bundles are persisted in Neon Object Storage.
- Render Free may sleep or restart, and deploys/restarts destroy in-memory browser contexts. The keeper workflow reduces idle spin-down risk but cannot prevent provider restarts, scheduled-workflow delays, or deployments.
- The Relay's idle TTL is configurable. Keep the heartbeat cadence comfortably shorter than that TTL.
- Native Godot gameplay benchmarking remains a separate workflow until a dedicated persistent native runtime host is provisioned and tested.
