from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from project_assets import inject_generated_project_assets


class ProjectAssetOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name) / "verdant-valley"
        (self.project / "assets" / "backgrounds").mkdir(parents=True)
        (self.project / "assets" / "characters").mkdir(parents=True)
        (self.project / "assets" / "backgrounds" / "sky.png").write_bytes(b"sky-png")
        (self.project / "assets" / "characters" / "hero.png").write_bytes(b"hero-png")

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, entries):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return stream.getvalue()

    def assert_overlay(self, archive_bytes, expected_prefix):
        result = inject_generated_project_assets(
            archive_bytes, "examples/verdant-valley", self.project
        )
        with zipfile.ZipFile(io.BytesIO(result)) as archive:
            names = set(archive.namelist())
            self.assertIn(expected_prefix + "assets/", names)
            self.assertIn(expected_prefix + "assets/backgrounds/", names)
            self.assertIn(expected_prefix + "assets/characters/", names)
            self.assertEqual(archive.read(expected_prefix + "assets/backgrounds/sky.png"), b"sky-png")
            self.assertEqual(archive.read(expected_prefix + "assets/characters/hero.png"), b"hero-png")

    def test_selected_project_archive_without_repository_root(self):
        source = self.archive({
            "project.godot": b"[application]\n",
            "scenes/main.tscn": b"[gd_scene format=3]\n",
        })
        self.assert_overlay(source, "")

    def test_full_repository_archive_with_nested_project_root(self):
        prefix = "repo-abc/examples/verdant-valley/"
        source = self.archive({
            "repo-abc/README.md": b"repo",
            prefix + "project.godot": b"[application]\n",
            prefix + "scenes/main.tscn": b"[gd_scene format=3]\n",
        })
        self.assert_overlay(source, prefix)

    def test_archive_with_assets_is_not_duplicated(self):
        source = self.archive({
            "project.godot": b"[application]\n",
            "assets/backgrounds/sky.png": b"existing",
        })
        result = inject_generated_project_assets(
            source, "examples/verdant-valley", self.project
        )
        with zipfile.ZipFile(io.BytesIO(result)) as archive:
            self.assertEqual(archive.read("assets/backgrounds/sky.png"), b"existing")
            self.assertIn("assets/characters/hero.png", archive.namelist())


if __name__ == "__main__":
    unittest.main()
