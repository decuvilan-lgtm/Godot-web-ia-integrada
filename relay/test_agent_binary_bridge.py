from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from agent_binary_bridge import BridgeError, safe_project_path


class AgentBinaryBridgePathTests(unittest.TestCase):
    def test_accepts_relative_posix_project_paths(self):
        self.assertEqual(safe_project_path("scenes/player.tscn"), "scenes/player.tscn")
        self.assertEqual(safe_project_path("assets/sprites/hero.png"), "assets/sprites/hero.png")

    def test_rejects_absolute_windows_and_traversal_paths(self):
        invalid = [
            "",
            "/etc/passwd",
            "../outside.txt",
            "scenes/../../outside.txt",
            r"scenes\player.tscn",
            "C:/project/file.txt",
            "scenes//player.tscn",
            ".git/config",
            ".godot/editor_layout.cfg",
        ]
        for path in invalid:
            with self.subTest(path=path):
                with self.assertRaises(BridgeError):
                    safe_project_path(path)


if __name__ == "__main__":
    unittest.main()
