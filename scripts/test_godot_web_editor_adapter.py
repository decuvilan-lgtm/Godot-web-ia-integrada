#!/usr/bin/env python3
"""Static contract tests for the Godot Web EditorPlugin semantic adapter."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "examples" / "verdant-valley"
PLUGIN = PROJECT / "addons" / "godot_controller_bridge" / "plugin.gd"
CONFIG = PROJECT / "addons" / "godot_controller_bridge" / "plugin.cfg"
PROJECT_CONFIG = PROJECT / "project.godot"


class GodotWebEditorAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PLUGIN.read_text(encoding="utf-8")
        cls.project = PROJECT_CONFIG.read_text(encoding="utf-8")
        cls.config = CONFIG.read_text(encoding="utf-8")

    def test_plugin_is_enabled_in_the_project_loaded_by_workflow_a(self):
        self.assertIn('res://addons/godot_controller_bridge/plugin.cfg', self.project)
        self.assertIn('script="plugin.gd"', self.config)

    def test_adapter_is_registered_from_the_real_editor_plugin(self):
        self.assertIn("extends EditorPlugin", self.source)
        self.assertIn("JavaScriptBridge.create_callback(_dispatch)", self.source)
        self.assertIn('window.set("__godotEditorAgent", _adapter)', self.source)
        self.assertIn('_adapter.set("dispatch", _dispatch_callback)', self.source)

    def test_only_read_only_inspection_actions_are_exposed(self):
        for action in ("editor.get_state", "editor.list_capabilities", "scene.get_tree"):
            self.assertIn(f'"{action}"', self.source)
        self.assertIn('"COMMAND_NOT_ALLOWED"', self.source)
        self.assertIn('"INVALID_ARGUMENTS"', self.source)
        self.assertIn("if not args.is_empty():", self.source)

    def test_scene_tree_has_depth_and_node_limits(self):
        self.assertIn("MAX_TREE_NODES := 1000", self.source)
        self.assertIn("MAX_TREE_DEPTH := 12", self.source)
        self.assertIn('item["truncated"] = true', self.source)

    def test_plugin_cleans_up_browser_global_and_keeps_callback_refs(self):
        self.assertIn('_window.set("__godotEditorAgent", null)', self.source)
        self.assertIn("var _dispatch_callback: JavaScriptObject", self.source)
        self.assertIn("var _capabilities_callback: JavaScriptObject", self.source)

    def test_no_shell_or_arbitrary_script_execution_surface(self):
        forbidden = ("OS.execute(", "JavaScriptBridge.eval(", "FileAccess.open(", "DirAccess.")
        for fragment in forbidden:
            self.assertNotIn(fragment, self.source)


if __name__ == "__main__":
    unittest.main()
