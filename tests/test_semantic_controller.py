import unittest

from scripts.bridge.semantic_controller import _validate


class SemanticControllerValidationTests(unittest.TestCase):
    def test_read_only_commands_accept_no_arguments(self):
        for action in ("editor.get_state", "editor.list_capabilities", "scene.save"):
            with self.subTest(action=action):
                _validate(action, {})

    def test_unknown_action_is_rejected(self):
        with self.assertRaises(ValueError):
            _validate("page.click", {})

    def test_unknown_argument_is_rejected(self):
        with self.assertRaises(ValueError):
            _validate("scene.open", {"scene_path": "res://main.tscn", "x": 0.5})

    def test_scene_path_is_bounded_string(self):
        _validate("scene.open", {"scene_path": "res://main.tscn"})
        with self.assertRaises(ValueError):
            _validate("scene.open", {"scene_path": "x" * 501})

    def test_panel_names_are_allowlisted(self):
        _validate("editor.open_panel", {"panel": "inspector"})
        with self.assertRaises(ValueError):
            _validate("editor.open_panel", {"panel": "terminal"})


if __name__ == "__main__":
    unittest.main()
