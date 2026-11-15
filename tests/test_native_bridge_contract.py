from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]


class NativeBridgeContractTests(unittest.TestCase):
    def test_worker_never_overlays_imported_project_archive(self):
        worker = (ROOT / "scripts" / "godot-browser-worker.py").read_text(encoding="utf-8")
        self.assertNotIn("apply_controller_overlay", worker)
        self.assertNotIn("overlay_project_archive", worker)
        self.assertNotIn("controller_project_overlay", worker)

    def test_extension_relays_to_native_dispatch_only(self):
        bridge = (ROOT / "browser-extension" / "page-bridge.js").read_text(encoding="utf-8")
        self.assertIn("adapter.dispatch", bridge)
        self.assertNotIn("adapter.execute", bridge)
        self.assertIn('"scene.get_tree"', bridge)

    def test_clean_build_smoke_rejects_temporary_instrumentation(self):
        smoke = (ROOT / "scripts" / "build" / "smoke_test_godot_web_agent.py").read_text(encoding="utf-8")
        self.assertIn('"WEB_DIAG_"', smoke)
        self.assertIn("Temporary WEB_DIAG instrumentation is present", smoke)

    def test_extension_pending_requests_are_bounded(self):
        relay = (ROOT / "browser-extension" / "content.js").read_text(encoding="utf-8")
        self.assertIn("MAX_PENDING=64", relay)
        self.assertIn("pending.size>=MAX_PENDING", relay)
        self.assertIn('"BRIDGE_BUSY"', relay)

    def test_python_controller_allowlist_matches_read_only_phase(self):
        controller = (ROOT / "scripts" / "bridge" / "semantic_controller.py").read_text(encoding="utf-8")
        self.assertIn('"editor.list_capabilities"', controller)
        self.assertIn('"editor.get_state"', controller)
        self.assertIn('"scene.get_tree"', controller)
        self.assertNotIn('"scene.open"', controller)
        self.assertNotIn('"editor.open_panel"', controller)

    def test_native_bridge_exposes_canonical_semantic_vocabulary(self):
        plugin = (ROOT / "headless" / "native-editor" / "addons" / "headless_session_bridge" / "plugin.gd").read_text(encoding="utf-8")
        probe = (ROOT / "headless" / "native-editor" / "tools" / "headless_bridge" / "bridge_probe.gd").read_text(encoding="utf-8")
        for command in (
            "editor.list_capabilities", "editor.get_state", "scene.get_tree",
            "scene.add_node", "scene.set_node_properties", "scene.configure_collision_shape",
            "scene.assign_visual_resource", "scene.create_sprite_frames",
            "editor.open_scene", "editor.focus_inspector", "editor.inspect_undo_history",
            "editor.undo", "editor.redo", "project.list_resources", "project.inspect_resource",
            "preview.get_status", "preview.start", "preview.stop", "capture.editor_screenshot",
            "capture.desktop_screenshot", "capture.start_editor_video", "capture.stop_editor_video", "capture.read_chunk",
        ):
            self.assertIn(command, plugin)
            self.assertIn(command, probe)
        self.assertIn('"mutations_require_explicit_commands": true', plugin)
        self.assertIn('"automatic_save": false', plugin)

    def test_native_bridge_does_not_expose_arbitrary_execution(self):
        plugin = (ROOT / "headless" / "native-editor" / "addons" / "headless_session_bridge" / "plugin.gd").read_text(encoding="utf-8")
        self.assertNotIn('"execute_script"', plugin)
        self.assertNotIn('"run_shell"', plugin)
        self.assertNotIn('"eval"', plugin)


    def test_advertised_native_capabilities_are_dispatched_and_probe_allowed(self):
        import re

        plugin = (ROOT / "headless" / "native-editor" / "addons" / "headless_session_bridge" / "plugin.gd").read_text(encoding="utf-8")
        probe = (ROOT / "headless" / "native-editor" / "tools" / "headless_bridge" / "bridge_probe.gd").read_text(encoding="utf-8")

        advertised_block = plugin.split('"commands": [', 1)[1].split('],', 1)[0]
        advertised = set(re.findall(r'"([a-z][a-z0-9_.]+)"', advertised_block))

        dispatch_block = plugin.split("\\tmatch command:", 1)[1]
        dispatched = set(re.findall(r'^\\s*"([^"]+)":', dispatch_block, re.MULTILINE))

        probe_block = probe.split("if not [", 1)[1].split("].has(action)", 1)[0]
        probe_allowed = set(re.findall(r'"([a-z][a-z0-9_.]+)"', probe_block))

        self.assertTrue(advertised, "The native adapter must advertise its capabilities.")
        self.assertEqual(advertised - dispatched, set(), "Every advertised command must have a dispatcher.")
        self.assertEqual(advertised - probe_allowed, set(), "Every advertised command must be callable by the native probe.")

if __name__ == "__main__":
    unittest.main()
