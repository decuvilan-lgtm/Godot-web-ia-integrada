#!/usr/bin/env python3
from pathlib import Path
import runpy
import unittest

PATCHER = Path(__file__).with_name("patch-web-shell.py")
PATCHER_NAMESPACE = runpy.run_path(str(PATCHER))
patch_html = PATCHER_NAMESPACE["patch_html"]

FIXTURE = """<!doctype html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Godot</title></head>
<body>
<div id="tabs-buttons"></div>
<input id="zip-file" type="file">
<button id="startButton">Start</button>
<script>function startEditor(zip) { const args = ['--project-manager', '--single-window']; }</script>
</body></html>
"""


class WebShellPatchTests(unittest.TestCase):
    def test_installs_project_manager_and_github_connector(self):
        result = patch_html(FIXTURE)
        self.assertIn("viewport-fit=cover", result)
        self.assertIn('id="godot-github-connector" data-version="commit-pinned-v3"', result)
        self.assertIn('button.id = "godot-connect-github"', result)
        self.assertIn("/v1/github/", result)
        self.assertIn('const relay = "https://godot-web-ia-relay-test.onrender.com";', result)
        self.assertIn('const readyStartButton = await waitForElement("#startButton", element => !element.disabled, 240000);', result)
        self.assertIn('readyStartButton.click();', result)
        self.assertIn('new Event("input", { bubbles: true })', result)
        self.assertIn('phase: "failed"', result)
        self.assertIn('startButtonDisabled', result)
        self.assertIn("credentials:", result)
        self.assertIn('target.searchParams.set("repo", repo)', result)
        self.assertIn('target.searchParams.set("branch", branch)', result)
        self.assertIn('target.searchParams.set("path", projectPath)', result)
        self.assertIn('target.searchParams.set("sha", commitSha)', result)
        self.assertIn('archiveUrl.searchParams.set("sha", commitSha)', result)
        self.assertIn("validCommitSha", result)
        self.assertIn("X-GitHub-Commit-SHA", result)
        self.assertIn('archiveUrl.searchParams.set("branch", branch)', result)
        self.assertIn('archiveUrl.searchParams.set("path", projectPath)', result)
        self.assertIn("validProjectPath", result)
        self.assertIn("readyStartButton.click()", result)
        self.assertIn('get("manual") === "1"', result)
        self.assertIn("async function waitForElement(selector, predicate, timeoutMs)", result)
        self.assertIn('await waitForElement("#startButton", element => !element.disabled, 240000)', result)
        self.assertIn('document.readyState === "loading"', result)
        self.assertIn('window.__godotGithubConnectorStatus', result)
        self.assertNotIn('if (!startButton || startButton.disabled) return;', result)
        self.assertNotIn("Compartir proyectos", result)

    def test_can_use_same_origin_archive_proxy_for_runner_hosted_editor(self):
        previous = PATCHER_NAMESPACE["RELAY_URL"]
        try:
            PATCHER_NAMESPACE["RELAY_URL"] = ""
            result = PATCHER_NAMESPACE["patch_html"](FIXTURE)
            self.assertIn('const relay = "";', result)
            self.assertIn("window.location.href", result)
        finally:
            PATCHER_NAMESPACE["RELAY_URL"] = previous

    def test_patch_is_idempotent(self):
        once = patch_html(FIXTURE)
        twice = patch_html(once)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count('id="godot-github-connector"'), 1)

    def test_accepts_changed_upstream_godot_internal_markup(self):
        changed = FIXTURE.replace('id="startButton"', 'id="new-start-control"')
        changed = changed.replace('id="zip-file"', 'id="new-zip-control"')
        self.assertIn('id="godot-github-connector"', patch_html(changed))

    def test_rejects_incomplete_html_document(self):
        for broken in ("", "<html><head></head></html>", "<html><body></body></html>"):
            with self.subTest(broken=broken):
                with self.assertRaises(SystemExit):
                    patch_html(broken)


if __name__ == "__main__":
    unittest.main()
