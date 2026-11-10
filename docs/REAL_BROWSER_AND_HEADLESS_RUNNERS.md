# Real browser and headless development runners

## Purpose

The project uses two complementary execution environments. They are not interchangeable:

1. **Godot headless** is the engineering runner. It imports the isolated Godot workspace, validates scripts/resources, inspects scenes, and can execute fixed scene-audit/capture tasks.
2. **Chromium + Playwright** is the browser observation runner. It opens the published Godot Web editor as an actual web page, waits for the editor canvas, and records real browser screenshots and runtime diagnostics.

The browser runner does not replace Godot headless. A browser screenshot cannot prove that a scene is structurally correct; a headless scene audit cannot prove that the deployed web UI loaded correctly.

## Current implementation

### Godot headless

The existing fixed profiles remain:

- `engine_smoke`: import the fixed `examples/bridge-sandbox` project with Godot 4.7.2 headless and reject script/parse errors.
- `scene_audit_3d`: inspect the fixed sandbox fixture, assert required 3D nodes/tracks, and render eight bounded viewpoints under Xvfb/software rendering at 1280×720.

These are repository fixtures. They are not evidence from an arbitrary user project or a live Android device.

### Real browser audit

The new fixed profile is `web_browser_audit`.

- Opens only `https://godot-web-ia-integrada-rt2l.onrender.com`; callers cannot supply a URL, path, shell command, browser arguments, or source code.
- Uses pinned Playwright 1.56.0 and its managed Chromium browser on an on-demand GitHub Actions runner.
- Waits for an actual HTML canvas before declaring that the editor page has loaded.
- Captures a 1440×900 desktop viewport and a 390×844 mobile-sized viewport.
- Records the page title, canvas count, elapsed time, page exceptions, HTTP 5xx responses, and console errors.
- Stores PNG evidence plus `web-browser-audit.json` as a GitHub Actions artifact for seven days.

The mobile-sized capture is **viewport emulation in Chromium**, not a physical Android device test. The browser audit is a smoke test of the published web editor. It does not prove device pairing, project import, Command Center connectivity, a running game preview, or private image retrieval.

## Dispatch and cost model

The existing task dispatcher accepts only fixed profiles. The browser profile is routed directly to GitHub Actions because the current CircleCI job is the Godot runner and does not install Playwright. Existing Godot profiles retain the CircleCI-first / GitHub Actions fallback behavior.

The profile can be dispatched on demand through the existing task workflow. A separate pull-request workflow also runs the browser audit when the runner or its workflow changes, so the real-browser smoke test is exercised during this PR. It does not create a persistent worker or upgrade Render resources. Browser installation and page loading consume the normal GitHub Actions job time.

## Security boundaries

- The task profile and request ID are allowlisted and validated.
- The browser target is a constant in the runner; no caller-provided URL is accepted, preventing the task interface from becoming an arbitrary URL fetcher.
- Workflow permissions remain `contents: read`.
- No Neon, Render, device, or storage credentials are passed to the browser job.
- Screenshots are uploaded as short-lived CI artifacts; they are not made public and may require GitHub repository access.
- The audit is read-only. It does not click editor controls, execute project scripts, change project files, or apply changes to the user's Android copy.

## How to run

Use the existing `godot_start_task` MCP tool with:

```json
{
  "task_profile": "web_browser_audit",
  "request_id": "browser-audit-0001"
}
```

The request ID must contain 8–80 letters, digits, underscores, or hyphens. Check the result with `godot_task_status` using provider `github_actions` and the same request ID. The resulting workflow artifact contains:

- `web-editor-desktop.png`
- `web-editor-mobile-viewport.png`
- `web-browser-audit.json`

A manual GitHub Actions run is also available through **Actions → Remote Godot task → Run workflow**.

## Next integration stages

These remain future work and must not be described as operational until implemented and tested:

1. **Visual asset return path:** retrieve authenticated private screenshot bytes from Neon into a model-inspectable result. CI artifacts alone are not an automatic ChatGPT image handoff.
2. **Live editor capture:** pair the isolated web editor and verify the existing Godot 2D/3D viewport capture round-trip. Browser screenshots and Godot viewport screenshots are distinct capture sources.
3. **Full editor UI / game preview / zoom:** connect browser-level capture and safe view restoration to the existing visual command contract. Reject unsupported targets until their backend is proven.
4. **Project-scoped headless work:** run import, validation, scene inspection and fixed tests against an immutable, hash-verified project revision from the isolated workspace. Keep the accepted Android project untouched until explicit approval.
5. **3D asset authoring:** evaluate an optional pinned Blender headless runner for procedural mesh/material/animation generation and export. Blender is not installed or wired into this phase.
6. **Evidence feedback loop:** deliver screenshots and structured reports to the agent, inspect them, propose corrections, and repeat the bounded test cycle.

The acceptance rule is evidence-based: each stage is marked complete only after a real end-to-end run, not merely a unit test or successful build.
