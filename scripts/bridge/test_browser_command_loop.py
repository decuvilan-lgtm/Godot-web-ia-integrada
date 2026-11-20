import unittest
from unittest.mock import patch
import browser_command_loop
from browser_command_loop import TRUSTED_ACTORS, _bounded_duration_seconds, _fetch_new_comments, _ordered_comments, _validate

SESSION="issue-test"

class BrowserCommandValidationTests(unittest.TestCase):
    def test_operator_workflow_bot_is_trusted_for_scoped_issue_commands(self):
        self.assertIn("github-actions[bot]", TRUSTED_ACTORS)

    def command(self, action, **fields):
        return {"protocol":1,"session_id":SESSION,"seq":1,"action":action,**fields}

    def test_normalized_canvas_click_is_accepted(self):
        self.assertEqual(_validate(self.command("canvas_click",x=0.5,y=1.0),SESSION,0),(1,"canvas_click"))

    def test_canvas_drag_accepts_bounded_path(self):
        cmd=self.command("canvas_drag",points=[[0.1,0.2],[0.5,0.6],[0.9,0.8]],duration_ms=600)
        self.assertEqual(_validate(cmd,SESSION,0),(1,"canvas_drag"))

    def test_screenshot_can_return_inline_canvas_preview(self):
        cmd=self.command("screenshot",include_image=True,scope="canvas")
        self.assertEqual(_validate(cmd,SESSION,0),(1,"screenshot"))

    def test_screenshot_rejects_invalid_inline_scope(self):
        cmd=self.command("screenshot",include_image=True,scope="window")
        with self.assertRaises(ValueError):
            _validate(cmd,SESSION,0)

    def test_screenshot_rejects_non_boolean_inline_flag(self):
        cmd=self.command("screenshot",include_image="yes",scope="page")
        with self.assertRaises(ValueError):
            _validate(cmd,SESSION,0)

    def test_game_preview_click_accepts_normalized_coordinates(self):
        self.assertEqual(_validate(self.command("game_click",x=0.5,y=0.5),SESSION,0),(1,"game_click"))

    def test_game_preview_input_accepts_bounded_key_hold(self):
        cmd=self.command("game_input",key="Space",duration_ms=350)
        self.assertEqual(_validate(cmd,SESSION,0),(1,"game_input"))

    def test_game_preview_input_accepts_interaction_key(self):
        cmd=self.command("game_input",key="e",duration_ms=150)
        self.assertEqual(_validate(cmd,SESSION,0),(1,"game_input"))

    def test_game_preview_input_rejects_unapproved_key(self):
        with self.assertRaises(ValueError):
            _validate(self.command("game_input",key="Alt+F4",duration_ms=350),SESSION,0)

    def test_game_preview_input_rejects_unbounded_hold(self):
        with self.assertRaises(ValueError):
            _validate(self.command("game_input",key="Space",duration_ms=6000),SESSION,0)

    def test_canvas_click_rejects_out_of_bounds_coordinates(self):
        with self.assertRaises(ValueError):
            _validate(self.command("canvas_click",x=1.01,y=0.5),SESSION,0)

    def test_canvas_click_rejects_extremely_large_coordinates(self):
        with self.assertRaises(ValueError):
            _validate(self.command("canvas_click",x=10**1000,y=0.5),SESSION,0)

    def test_canvas_drag_rejects_unbounded_path(self):
        points=[[0.5,0.5] for _ in range(65)]
        with self.assertRaises(ValueError):
            _validate(self.command("canvas_drag",points=points),SESSION,0)

    def test_canvas_drag_rejects_malformed_points(self):
        with self.assertRaises(ValueError):
            _validate(self.command("canvas_drag",points=[[0.5,0.5],[2,0.5]]),SESSION,0)

    def test_capture_editor_panel_accepts_output_and_debugger(self):
        for panel in ("Output", "Debugger"):
            cmd=self.command("capture_editor_panel",panel=panel)
            self.assertEqual(_validate(cmd,SESSION,0),(1,"capture_editor_panel"))

    def test_capture_editor_panel_rejects_unknown_panel(self):
        with self.assertRaises(ValueError):
            _validate(self.command("capture_editor_panel",panel="Inspector"),SESSION,0)

    def test_semantic_command_accepts_read_only_editor_action(self):
        cmd=self.command("semantic_command",editor_action="scene.get_tree",args={})
        self.assertEqual(_validate(cmd,SESSION,0),(1,"semantic_command"))

    def test_semantic_project_file_and_resource_actions_are_accepted(self):
        for editor_action, args in (
            ("project.list_files", {}),
            ("project.read_file", {"path": "res://scripts/player.gd"}),
            ("project.write_file", {"path": "res://scripts/player.gd", "content": "extends Node2D\\n"}),
            ("resource.inspect", {"path": "res://scenes/main.tscn"}),
            ("scene.save", {}),
        ):
            with self.subTest(editor_action=editor_action):
                cmd=self.command("semantic_command",editor_action=editor_action,args=args)
                self.assertEqual(_validate(cmd,SESSION,0),(1,"semantic_command"))

    def test_semantic_project_write_rejects_large_or_unsafe_content(self):
        for args in (
            {"path": "res://../outside.gd", "content": "x"},
            {"path": "res://assets/texture.png", "content": "x"},
            {"path": "res://scripts/player.gd", "content": "x" * 10001},
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                _validate(self.command("semantic_command",editor_action="project.write_file",args=args),SESSION,0)

    def test_semantic_select_node_rejects_unsafe_path(self):
        cmd=self.command("semantic_command",editor_action="scene.select_node",args={"path":"../Outside"})
        with self.assertRaises(ValueError):
            _validate(cmd,SESSION,0)

    def test_semantic_command_rejects_unknown_editor_action(self):
        cmd=self.command("semantic_command",editor_action="execute_script",args={"code":"print(1)"})
        with self.assertRaises(ValueError):
            _validate(cmd,SESSION,0)

    def test_semantic_command_rejects_too_many_arguments(self):
        cmd=self.command("semantic_command",editor_action="scene.get_tree",args={"a":1,"b":2,"c":3,"d":4,"e":5})
        with self.assertRaises(ValueError):
            _validate(cmd,SESSION,0)

    def test_semantic_inspect_node_accepts_relative_path(self):
        cmd=self.command("semantic_command",editor_action="scene.inspect_node",args={"path":"Player/AnimatedSprite2D"})
        self.assertEqual(_validate(cmd,SESSION,0),(1,"semantic_command"))

    def test_semantic_inspect_node_rejects_parent_traversal(self):
        cmd=self.command("semantic_command",editor_action="scene.inspect_node",args={"path":"Player/../../Outside"})
        with self.assertRaises(ValueError):
            _validate(cmd,SESSION,0)

    def test_semantic_set_property_accepts_vector_and_resource_reference(self):
        cmd=self.command("semantic_command",editor_action="scene.set_property",args={"path":"Player","property":"position","value":[42.0,84.0]})
        self.assertEqual(_validate(cmd,SESSION,0),(1,"semantic_command"))
        resource=self.command("semantic_command",editor_action="scene.set_property",args={"path":"Player/Sprite2D","property":"texture","value":{"resource_path":"res://assets/hero.png"}})
        self.assertEqual(_validate(resource,SESSION,0),(1,"semantic_command"))

    def test_semantic_set_property_rejects_script_attachment(self):
        cmd=self.command("semantic_command",editor_action="scene.set_property",args={"path":"Player","property":"script","value":{"resource_path":"res://main.gd"}})
        with self.assertRaises(ValueError):
            _validate(cmd,SESSION,0)

    def test_semantic_set_property_rejects_parent_traversal_and_unsafe_resource(self):
        bad_path=self.command("semantic_command",editor_action="scene.set_property",args={"path":"Player/../Outside","property":"position","value":[1,2]})
        with self.assertRaises(ValueError):
            _validate(bad_path,SESSION,0)
        bad_resource=self.command("semantic_command",editor_action="scene.set_property",args={"path":"Player","property":"texture","value":{"resource_path":"res://../outside.png"}})
        with self.assertRaises(ValueError):
            _validate(bad_resource,SESSION,0)

    def test_semantic_add_node_accepts_allowlisted_arguments(self):
        cmd=self.command("semantic_command",editor_action="scene.add_node",args={"node_type":"Node2D","node_name":"VisualRoot"})
        self.assertEqual(_validate(cmd,SESSION,0),(1,"semantic_command"))

    def test_semantic_add_node_rejects_untrusted_node_type(self):
        cmd=self.command("semantic_command",editor_action="scene.add_node",args={"node_type":"EditorPlugin","node_name":"Injected"})
        with self.assertRaises(ValueError):
            _validate(cmd,SESSION,0)

    def test_semantic_add_node_rejects_parent_traversal(self):
        cmd=self.command("semantic_command",editor_action="scene.add_node",args={"node_type":"Node2D","node_name":"Safe","parent_path":"Child/../Outside"})
        with self.assertRaises(ValueError):
            _validate(cmd,SESSION,0)

    def test_press_key_uses_allowlist(self):
        self.assertEqual(_validate(self.command("press_key",key="Escape"),SESSION,0),(1,"press_key"))
        with self.assertRaises(ValueError):
            _validate(self.command("press_key",key="Alt+F4"),SESSION,0)

    def test_type_text_is_bounded(self):
        self.assertEqual(_validate(self.command("type_text",text="BridgeSandbox"),SESSION,0),(1,"type_text"))
        with self.assertRaises(ValueError):
            _validate(self.command("type_text",text="x"*501),SESSION,0)

    def test_canvas_scroll_accepts_bounded_deltas(self):
        cmd=self.command("canvas_scroll",x=0.5,y=0.5,delta_y=-600)
        self.assertEqual(_validate(cmd,SESSION,0),(1,"canvas_scroll"))

    def test_canvas_scroll_rejects_excessive_deltas(self):
        cmd=self.command("canvas_scroll",x=0.5,y=0.5,delta_y=1201)
        with self.assertRaises(ValueError):
            _validate(cmd,SESSION,0)

    def test_unknown_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            _validate(self.command("canvas_click",x=0.5,y=0.5,script="alert(1)"),SESSION,0)

    def test_duration_is_clamped_to_requested_limit(self):
        self.assertEqual(_bounded_duration_seconds(180),180)
        self.assertEqual(_bounded_duration_seconds(600),600)
        self.assertEqual(_bounded_duration_seconds(900),900)
        self.assertEqual(_bounded_duration_seconds(3600),3600)
        self.assertEqual(_bounded_duration_seconds(4000),3600)
        self.assertEqual(_bounded_duration_seconds(-10),0)

    def test_duration_rejects_bool_and_non_integer_values(self):
        for value in (True, False, 1.5, "180", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _bounded_duration_seconds(value)

    def test_descending_api_comments_are_processed_oldest_first(self):
        comments = [{"id": 300}, {"id": 200}, {"id": 100}]
        self.assertEqual([item["id"] for item in _ordered_comments(comments)], [100,200,300])

    @patch("browser_command_loop._api")
    def test_comment_pagination_reads_all_new_pages_without_replaying_old(self, api):
        api.side_effect = [
            [{"id": value} for value in range(300, 200, -1)],
            [{"id": value} for value in range(200, 100, -1)],
        ]
        comments = _fetch_new_comments("https://api.invalid/comments?per_page=100", "token", 150)
        self.assertEqual([item["id"] for item in comments], list(range(151, 301)))
        self.assertEqual(api.call_count, 2)
        self.assertIn("page=2", api.call_args_list[1].args[0])

if __name__=="__main__":
    unittest.main()
