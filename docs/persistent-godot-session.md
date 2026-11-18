# Persistent Godot Web session

Workflow A owns one real Chromium browser on a GitHub Actions runner. That browser opens a custom Godot Web editor built from a verified GitHub Actions artifact, imports the exact project revision, and remains alive for a bounded command window. Workflow B sends commands to that same page through a temporary GitHub issue comment channel. B never launches another editor or browser.

The Render Relay is not used by the A/B session workflow. Workflow A downloads the immutable project archive directly from the GitHub API using the workflow token, then injects generated assets locally. Browser screenshots and task evidence are retained as GitHub Actions artifacts; the workflow does not depend on Neon Object Storage.

## Workflow roles

- **Workflow A — `.github/workflows/persistent-session-host.yml`:** triggered by `.session-host-request.json`. It selects the latest successful custom-editor build (or a run ID explicitly supplied in the request), downloads and verifies its artifact, builds the mobile wrapper locally on the runner, serves that editor from the runner, imports the exact project revision through a same-origin local proxy that fetches the GitHub archive directly, checks the editor surface, publishes a ready marker, then keeps the same browser available for B.
- **Workflow B — `.github/workflows/persistent-session-operator.yml`:** triggered by `.session-operator-request.json`. It waits for A's ready marker, sends bounded commands to A's issue channel, and correlates each command with the browser's result. The B workflow supports `inspect` (status and screenshot), `interaction-smoke` (a diagnostic canvas click, Escape key, and screenshot), and `semantic-inspect` (coordinate-free state/capability/scene-tree queries) plus `semantic-edit` (currently only `scene.add_node`, with a fixed class allowlist, bounded identifiers and parent paths, and Godot Undo/Redo).
- **Command loop — `scripts/bridge/browser_command_loop.py`:** runs inside A's Chromium process. It polls the issue comments, accepts only the repository owner and the GitHub Actions bot, validates command shape and sequence numbers, and executes allowlisted browser actions.
- **B→A latency:** the current command transport is GitHub issue comments, not the Render Relay's Command Center queue. A polls for new commands every 4 seconds (bounded to 900 polls/hour at the maximum 60-minute session); B polls for correlated results every 1 second and reads the newest comments first. B records per-command round-trip time and poll count; A records command execution time separately. These measurements distinguish transport waiting from editor execution.
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

- `.session-host-request.json` supplies repository, branch, project path, session ID, and issue number to A. It may optionally include `editor_artifact_run_id`; if omitted, A selects the latest successful custom-editor build on the test branch.
- `.session-operator-request.json` supplies the same session ID and issue number to B.

The branch is restricted to `test/verdant-valley-development-benchmark`. The project archive is resolved to an immutable commit SHA before import. The request files do not change the project itself because the imported project path is `examples/verdant-valley`.

## Authentication and deployment

Workflow A uses its scoped GitHub Actions token to resolve the branch and download the immutable project archive from the GitHub API. The local same-origin proxy validates the requested repository and full commit SHA before fetching the archive, then injects generated assets. No OIDC token, Render endpoint, Relay wake-up, Render editor deployment, paid resource, legacy workspace, or change to `main` is required.

## Current verification scope

Workflow B supports coordinate-free inspection and one controlled scene mutation. The mutation creates a single allowlisted node inside the active scene, records the operation in Godot's Undo/Redo history, and leaves the scene unsaved for review. It does not accept arbitrary GDScript, shell commands, arbitrary class names, or external filesystem paths.

The adapter is compiled into the custom Godot Web editor binary by `.github/workflows/build-godot-web-agent-editor.yml`; it is not an addon installed into the game project. Workflow A now downloads the custom editor artifact, checks its SHA-256, compares the build's patcher and page-bridge hashes with the current branch, builds the wrapper locally, and serves it from the Actions runner. This removes the dependency on the Render editor service. A green CI run still does not prove that a particular A session imported the requested project; that requires the A/B live session evidence. A green Python/Relay validation alone does not prove the C++ agent was loaded by the active A session.

## Semantic edit request

A controlled node creation request uses `operation: "semantic-edit"`, `editor_action: "scene.add_node"`, and `args` such as:

```json
{
  "repository": "decuvilan-lgtm/Godot-web-ia-integrada",
  "branch": "test/verdant-valley-development-benchmark",
  "session_id": "the-active-A-session-id",
  "issue_number": 123,
  "operation": "semantic-edit",
  "editor_action": "scene.add_node",
  "args": {
    "node_type": "Node2D",
    "node_name": "VisualRoot",
    "parent_path": "."
  }
}
```

This is the only enabled Web mutation for now. It does not save the scene automatically; the resulting editor state must be inspected before saving or exporting.

A visible Godot scene editor confirms that the browser/editor opened; it does not by itself prove that the game runs correctly. Project resource errors and gameplay validation are reported separately.
