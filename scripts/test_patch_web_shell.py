#!/usr/bin/env python3
from pathlib import Path
import runpy
import unittest

PATCHER = Path(__file__).with_name("patch-web-shell.py")
patch_html = runpy.run_path(str(PATCHER))["patch_html"]

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
        self.assertIn('id="godot-github-connector"', result)
        self.assertIn('button.id = "godot-connect-github"', result)
        self.assertIn("/v1/github/", result)
        self.assertIn("credentials:", result)
        self.assertIn("target.searchParams.set", result)
        self.assertIn("startButton.click()", result)
        self.assertNotIn("Compartir proyectos", result)

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
