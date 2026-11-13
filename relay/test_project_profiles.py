from __future__ import annotations

import io
import unittest

import project_profiles as profiles

VERIFIED_SHA = "a" * 40


class ProjectProfileValidationTests(unittest.TestCase):
    def setUp(self):
        self.controls = profiles.validate_control_profile({
            "schema_version": 1,
            "verification": {"status": "verified", "commit_sha": VERIFIED_SHA},
            "controls": {
                "move_left": {"type": "key", "key": "A"},
                "start": {"type": "text", "text": "JUGAR"},
                "fire": {"type": "point", "x": 0.5, "y": 0.9},
            },
        })["controls"]

    def test_manifest_accepts_project_owned_paths_and_command_names(self):
        manifest = profiles.validate_manifest({
            "schema_version": 1,
            "project": {"name": "Sample", "project_path": "game"},
            "control_profile": "control-profile.json",
            "commands": [
                {"name": "smoke-test", "file": "commands/smoke-test.json", "description": "Basic UI check"}
            ],
        })
        self.assertEqual(manifest["project"]["project_path"], "game")
        self.assertEqual(manifest["commands"][0]["file"], "godot-lab/commands/smoke-test.json")

    def test_manifest_requires_an_explicit_project_path(self):
        with self.assertRaises(ValueError):
            profiles.validate_manifest({
                "schema_version": 1,
                "project": {"name": "Sample"},
                "commands": [{"name": "smoke-test", "file": "commands/smoke-test.json"}],
            })

    def test_manifest_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            profiles.validate_manifest({
                "schema_version": 1,
                "project": {"name": "Sample", "project_path": "game"},
                "control_profile": "../secrets.json",
                "commands": [{"name": "smoke-test", "file": "commands/smoke-test.json"}],
            })

    def test_control_profile_rejects_unapproved_keys_and_absolute_points(self):
        with self.assertRaises(ValueError):
            profiles.validate_control_profile({
                "schema_version": 1,
                "verification": {"status": "pending", "commit_sha": None},
                "controls": {"danger": {"type": "key", "key": "Control+Alt+Delete"}},
            })
        with self.assertRaises(ValueError):
            profiles.validate_control_profile({
                "schema_version": 1,
                "verification": {"status": "pending", "commit_sha": None},
                "controls": {"outside": {"type": "point", "x": 1.1, "y": 0.5}},
            })

    def test_command_accepts_only_safe_generic_browser_operations(self):
        command = profiles.validate_command({
            "schema_version": 1,
            "name": "smoke-test",
            "verification": {"status": "verified", "commit_sha": VERIFIED_SHA},
            "steps": [
                {"op": "wait", "ms": 500},
                {"op": "tap_control", "control": "start"},
                {"op": "hold_control", "control": "move_left", "duration_ms": 250},
                {"op": "assert_canvas"},
                {"op": "screenshot"},
            ],
        }, expected_name="smoke-test", controls=self.controls, expected_commit_sha=VERIFIED_SHA)
        self.assertEqual(len(command["steps"]), 5)

    def test_command_rejects_shell_script_or_unknown_operation(self):
        with self.assertRaises(ValueError):
            profiles.validate_command({
                "schema_version": 1,
                "name": "smoke-test",
                "verification": {"status": "verified", "commit_sha": VERIFIED_SHA},
                "steps": [{"op": "shell", "command": "echo unsafe"}],
            }, expected_name="smoke-test", controls=self.controls, expected_commit_sha=VERIFIED_SHA)

    def test_command_enforces_total_delay_budget(self):
        with self.assertRaises(ValueError):
            profiles.validate_command({
                "schema_version": 1,
                "name": "smoke-test",
                "verification": {"status": "verified", "commit_sha": VERIFIED_SHA},
                "steps": [
                    {"op": "wait", "ms": 5000},
                    {"op": "wait", "ms": 5000},
                    {"op": "wait", "ms": 5000},
                    {"op": "wait", "ms": 5000},
                    {"op": "wait", "ms": 5000},
                ],
            }, expected_name="smoke-test", controls=self.controls, expected_commit_sha=VERIFIED_SHA)

    def test_missing_verification_metadata_is_rejected(self):
        with self.assertRaises(ValueError):
            profiles.validate_control_profile({"schema_version": 1, "controls": {}})

    def test_verified_profile_from_another_commit_becomes_obsolete(self):
        result = profiles.validate_control_profile({
            "schema_version": 1,
            "verification": {"status": "verified", "commit_sha": VERIFIED_SHA},
            "controls": {},
        }, expected_commit_sha="b" * 40)
        self.assertEqual(result["verification"]["status"], "obsolete")

    def test_pending_command_cannot_become_verified_by_valid_json(self):
        result = profiles.validate_command({
            "schema_version": 1,
            "name": "smoke-test",
            "verification": {"status": "pending", "commit_sha": None},
            "steps": [{"op": "inspect"}],
        }, expected_name="smoke-test", controls={}, expected_commit_sha=VERIFIED_SHA)
        self.assertEqual(result["verification"]["status"], "pending")


class FakePage:
    url = "https://editor.example/"
    class Keyboard:
        async def press(self, key):
            self.last_key = key
        async def down(self, key):
            self.last_key = key
        async def up(self, key):
            self.last_key = key
    class Locator:
        async def inner_text(self, **kwargs):
            return "JUGAR Editor"
        async def count(self):
            return 1
        async def click(self, **kwargs):
            return None
    def __init__(self):
        self.keyboard = self.Keyboard()
    async def title(self):
        return "Godot Web"
    def locator(self, selector):
        return self.Locator()
    async def evaluate(self, script):
        return {"width": 800, "height": 600}
    async def screenshot(self, **kwargs):
        return b"fake-png"
    def get_by_text(self, text, exact=True):
        return type("First", (), {"first": self.Locator()})()
    class Mouse:
        async def click(self, x, y):
            return None
    @property
    def mouse(self):
        return self.Mouse()


class ProjectProfileExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_command_executes_and_stores_screenshot(self):
        controls = {"start": {"type": "text", "text": "JUGAR"}}
        profile = {
            "control_profile": {"verification": {"status": "verified", "commit_sha": VERIFIED_SHA}, "controls": controls},
            "commands": {
                "smoke-test": {
                    "name": "smoke-test",
                    "verification": {"status": "verified", "commit_sha": VERIFIED_SHA},
                    "steps": [
                        {"op": "tap_control", "control": "start"},
                        {"op": "screenshot"},
                    ],
                }
            },
        }
        artifacts = {}
        results = await profiles.execute_profile_command(FakePage(), profile, "smoke-test", artifacts)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(artifacts), 1)
        self.assertTrue(next(iter(artifacts)).endswith(".png"))


if __name__ == "__main__":
    unittest.main()
