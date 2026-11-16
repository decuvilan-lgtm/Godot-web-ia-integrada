import unittest

from semantic_controller import execute_semantic_command


class FakePage:
    def __init__(self):
        self.called = False

    def evaluate(self, script, payload):
        self.called = True
        return {"ok": True, "action": payload["command"]["action"]}


class SemanticControllerValidationTests(unittest.TestCase):
    def test_read_only_queries_accept_empty_arguments(self):
        from semantic_controller import _validate
        for action in ("editor.get_state", "editor.list_capabilities", "scene.get_tree"):
            with self.subTest(action=action):
                _validate(action, {})

    def test_scene_add_node_accepts_safe_request(self):
        from semantic_controller import _validate
        _validate("scene.add_node", {"node_type": "Node2D", "node_name": "VisualRoot", "parent_path": "."})

    def test_scene_add_node_rejects_unknown_class(self):
        from semantic_controller import _validate
        with self.assertRaises(ValueError):
            _validate("scene.add_node", {"node_type": "EditorPlugin", "node_name": "Bad"})

    def test_scene_add_node_rejects_parent_traversal(self):
        from semantic_controller import _validate
        with self.assertRaises(ValueError):
            _validate("scene.add_node", {"node_type": "Node2D", "node_name": "Safe", "parent_path": "Child/../Outside"})

    def test_none_arguments_are_normalized_to_empty_object(self):
        page = FakePage()
        result = execute_semantic_command(page, "editor.get_state", None)
        self.assertTrue(page.called)
        self.assertTrue(result["ok"])

    def test_falsy_non_object_arguments_are_rejected_before_page_evaluate(self):
        for invalid in ([], "", 0, False):
            with self.subTest(invalid=invalid):
                page = FakePage()
                with self.assertRaises(ValueError):
                    execute_semantic_command(page, "editor.get_state", invalid)
                self.assertFalse(page.called)


if __name__ == "__main__":
    unittest.main()
