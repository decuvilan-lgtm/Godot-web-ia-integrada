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

    def test_python_controller_allowlist_matches_read_only_phase(self):
        controller = (ROOT / "scripts" / "bridge" / "semantic_controller.py").read_text(encoding="utf-8")
        self.assertIn('"editor.list_capabilities"', controller)
        self.assertIn('"editor.get_state"', controller)
        self.assertIn('"scene.get_tree"', controller)
        self.assertNotIn('"scene.open"', controller)
        self.assertNotIn('"editor.open_panel"', controller)


if __name__ == "__main__":
    unittest.main()
