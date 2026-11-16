# Persistent Godot Web session

Workflow A owns one real Chromium browser on a GitHub Actions runner. That browser opens the deployed Godot Web editor, imports the exact project revision, and remains alive for a bounded command window. Workflow B sends commands to that same page through a temporary GitHub issue comment channel. B never launches another editor or browser.

The Render Relay is not the browser host in this design. It supplies the project archive endpoint and validates the GitHub OIDC identity. Browser screenshots and task evidence are retained as GitHub Actions artifacts; the workflow does not depend on Neon Object Storage.

## Workflow roles

- **Workflow A — `.github/workflows/persistent-session-host.yml`:** triggered by `.session-host-request.json`. It starts Chromium on the GitHub runner, downloads and imports the exact branch revision, checks that the Godot scene editor and canvas are visible, publishes a ready marker to the issue channel, then keeps the same browser available for B.
- **Workflow B — `.github/workflows/persistent-session-operator.yml`:** triggered by `.session-operator-request.json`. It waits for A's ready marker, sends bounded commands to A's issue channel, and correlates each command with the browser's result. The current verification operation performs status, screenshot, and a second status check.
- **Command loop — `scripts/bridge/browser_command_loop.py`:** runs inside A's Chromium process. It polls the issue comments, accepts only the repository owner and the GitHub Actions bot, validates command shape and sequence numbers, and executes allowlisted browser actions.
- **Validation — `.github/workflows/persistent-session-validation.yml`:** validates workflow YAML, embedded Python, Relay session tests, editor patcher tests, and the A/B handoff configuration.

## Lifetime and handoff

- The current command window is **10 minutes (600 seconds)**, configured by `BROWSER_COMMAND_WINDOW_SECONDS` in Workflow A.
- The timer begins after the exact project SHA has been imported and the Godot scene editor surface has been detected.
- A remains active while B runs. B can finish early without closing Chromium, navigating away, or cancelling A.
- B checks the page title, URL, and visible canvas before and after its commands. Its result includes `session_kept_open: true` only when those checks pass.
- When A's bounded command window ends, its GitHub Actions job closes the temporary issue channel and uploads its evidence artifact.
- A new A run creates a new browser session ID. It does not claim to reconnect to a browser from an earlier completed or failed runner job.

## Request files

Both request files are temporary control inputs on the test branch:

- `.session-host-request.json` supplies repository, branch, project path, session ID, and issue number to A.
- `.session-operator-request.json` supplies the same session ID and issue number to B.

The branch is restricted to `test/verdant-valley-development-benchmark`. The project archive is resolved to an immutable commit SHA before import. The request files do not change the project itself because the imported project path is `examples/verdant-valley`.

## Authentication and deployment

The runner uses GitHub's OIDC token to authenticate with the test Relay. The Relay checks the repository, test branch, and explicit workflow allowlist. The editor and Relay endpoints are:

- Editor: `https://godot-web-ia-editor-test.onrender.com/`
- Relay: `https://godot-web-ia-relay-test.onrender.com`

Do not use the legacy Render workspace or service. No paid Render plan or deployment to `main` is required.

## Current verification scope

Workflow B currently verifies read-only control of the existing editor page: status, screenshot capture, and a second status check. The lower-level command loop already validates additional bounded actions such as visible-text clicks, typing, allowlisted keys, canvas clicks/drags/scrolls, and semantic commands, but those are not yet exposed by the current B request workflow.

A visible Godot scene editor confirms that the browser/editor opened; it does not by itself prove that the game runs correctly. Project resource errors and gameplay validation are reported separately.
