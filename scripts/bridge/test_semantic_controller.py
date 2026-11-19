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

    def test_project_file_operations_accept_safe_paths(self):
        from semantic_controller import _validate
        _validate("project.list_files", {})
        _validate("project.read_file", {"path": "res://scripts/player.gd"})
        _validate("project.write_file", {"path": "res://scripts/player.gd", "content": "extends Node2D\\n"})
        _validate("resource.inspect", {"path": "res://scenes/main.tscn"})
        _validate("scene.save", {})

    def test_project_file_operations_reject_traversal_and_binary_writes(self):
        from semantic_controller import _validate
        for action, args in (
            ("project.read_file", {"path": "res://../outside.gd"}),
            ("project.write_file", {"path": "res://assets/image.png", "content": "x"}),
            ("project.write_file", {"path": "res://scripts/a.gd", "content": "x" * 10001}),
            ("resource.inspect", {"path": "res://folder\\\\secret.tres"}),
        ):
            with self.subTest(action=action, args=args), self.assertRaises(ValueError):
                _validate(action, args)

    def test_scene_inspect_node_accepts_bounded_relative_path(self):
        from semantic_controller import _validate
        _validate("scene.inspect_node", {"path": "Player/AnimatedSprite2D"})

    def test_scene_inspect_node_rejects_parent_traversal(self):
        from semantic_controller import _validate
        with self.assertRaises(ValueError):
            _validate("scene.inspect_node", {"path": "Player/../../Outside"})

    def test_scene_set_property_accepts_vector_and_resource_values(self):
        from semantic_controller import _validate
        _validate("scene.set_property", {"path": "Player", "property": "position", "value": [42.0, 84.0]})
        _validate("scene.set_property", {"path": "Player/Sprite2D", "property": "texture", "value": {"resource_path": "res://assets/hero.png"}})

    def test_scene_set_property_rejects_parent_traversal(self):
        from semantic_controller import _validate
        with self.assertRaises(ValueError):
            _validate("scene.set_property", {"path": "Player/../Outside", "property": "position", "value": [1, 2]})

    def test_scene_set_property_rejects_script_attachment(self):
        from semantic_controller import _validate
        with self.assertRaises(ValueError):
            _validate("scene.set_property", {"path": "Player", "property": "script", "value": {"resource_path": "res://main.gd"}})

    def test_scene_set_property_rejects_unsafe_resource_path(self):
        from semantic_controller import _validate
        with self.assertRaises(ValueError):
            _validate("scene.set_property", {"path": "Player", "property": "texture", "value": {"resource_path": "res://../outside.png"}})

    def test_scene_set_property_rejects_unbounded_or_nested_values(self):
        from semantic_controller import _validate
        for value in ([1, 2, 3, 4, 5], {"resource_path": "res://x", "extra": 1}, float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _validate("scene.set_property", {"path": "Player", "property": "position", "value": value})

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
