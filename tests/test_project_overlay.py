from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
import zipfile

from bridge.project_overlay import apply_controller_overlay, PLUGIN_RES_PATH


class ProjectOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addon = self.root / "addon"
        self.addon.mkdir()
        (self.addon / "plugin.cfg").write_text('[plugin]\nscript="plugin.gd"\n', encoding="utf-8")
        (self.addon / "plugin.gd").write_text("@tool\nextends EditorPlugin\n", encoding="utf-8")

    def make_zip(self, entries):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        return buffer.getvalue()

    def inspect_zip(self, payload):
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            return {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}

    def test_injects_addon_and_enables_it_without_touching_source(self):
        original = self.make_zip({
            "project.godot": '[application]\nconfig/name="Test"\n',
            "main.tscn": '[gd_scene format=3]\n',
        })
        result, report = apply_controller_overlay(original, self.addon)
        files = self.inspect_zip(result)
        project = files["project.godot"].decode()
        self.assertIn(PLUGIN_RES_PATH, project)
        self.assertIn("addons/godot_controller_bridge/plugin.gd", files)
        self.assertEqual(report["source_repository_modified"], False)
        self.assertEqual(report["source_archive_sha256"], __import__("hashlib").sha256(original).hexdigest())
        self.assertNotIn("addons/godot_controller_bridge/plugin.gd", self.inspect_zip(original))

    def test_supports_root_folder_archives_and_existing_plugin_section(self):
        original = self.make_zip({
            "repo/project.godot": '[editor_plugins]\nenabled=PackedStringArray("res://addons/other/plugin.cfg")\n',
            "repo/scenes/main.tscn": "scene",
        })
        result, _ = apply_controller_overlay(original, self.addon)
        files = self.inspect_zip(result)
        self.assertIn("repo/addons/godot_controller_bridge/plugin.cfg", files)
        self.assertIn(PLUGIN_RES_PATH, files["repo/project.godot"].decode())
        self.assertIn("res://addons/other/plugin.cfg", files["repo/project.godot"].decode())

    def test_is_idempotent_for_same_controller_version(self):
        original = self.make_zip({"project.godot": '[editor_plugins]\nenabled=PackedStringArray()\n'})
        once, _ = apply_controller_overlay(original, self.addon)
        twice, report = apply_controller_overlay(once, self.addon)
        self.assertEqual(self.inspect_zip(once), self.inspect_zip(twice))
        self.assertEqual(report["added_files"], [])

    def test_rejects_missing_project_and_unsafe_paths(self):
        with self.assertRaises(ValueError):
            apply_controller_overlay(self.make_zip({"readme.txt": "no project"}), self.addon)
        with self.assertRaises(ValueError):
            apply_controller_overlay(self.make_zip({"../project.godot": "[application]\n"}), self.addon)

    def test_refuses_to_overwrite_different_project_addon(self):
        original = self.make_zip({
            "project.godot": "[application]\n",
            "addons/godot_controller_bridge/plugin.gd": "different code",
        })
        with self.assertRaises(ValueError):
            apply_controller_overlay(original, self.addon)


if __name__ == "__main__":
    unittest.main()
