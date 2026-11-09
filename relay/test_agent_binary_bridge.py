from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import agent_binary_bridge as bridge
from agent_binary_bridge import BridgeError, safe_project_path


class AgentBinaryBridgePathTests(unittest.TestCase):
    def test_accepts_relative_posix_project_paths(self):
        self.assertEqual(safe_project_path("scenes/player.tscn"), "scenes/player.tscn")
        self.assertEqual(safe_project_path("assets/sprites/hero.png"), "assets/sprites/hero.png")


    def test_import_submits_one_atomic_zip_batch(self):
        payload = b"\x00Godot\xffbinary"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "bridge-inbox"
            inbox.mkdir()
            (inbox / "part.txt").write_text(base64.b64encode(payload).decode("ascii"), encoding="ascii")
            request = {
                "project_id": "project-uuid",
                "base_revision": 7,
                "files": [{
                    "path": "assets/hero.bin", "payload": "bridge-inbox/part.txt",
                    "byte_size": len(payload), "sha256": digest,
                    "base_sha256": None, "mime_type": "application/octet-stream",
                }],
                "deletes": [],
            }
            response = {
                "atomic": True, "head_revision": 8,
                "operations": [{"path": "assets/hero.bin", "sha256": digest, "revision": 8}],
            }
            with patch.object(bridge, "ROOT", root), patch.object(bridge, "INBOX", inbox), \
                 patch.object(bridge, "project_manifest", return_value={"head_revision": 7}), \
                 patch.object(bridge, "api_request", return_value=json.dumps(response).encode("utf-8")) as send:
                result = bridge.import_project(request, "temporary-token")

            self.assertTrue(result["atomic"])
            self.assertEqual(result["head_revision"], 8)
            self.assertEqual(send.call_count, 1)
            self.assertIn("/projects/project-uuid/batch", send.call_args.args[1])
            archive = zipfile.ZipFile(io.BytesIO(send.call_args.args[3]))
            self.assertEqual(archive.read("files/assets/hero.bin"), payload)
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["base_revision"], 7)
            self.assertEqual(manifest["files"][0]["sha256"], digest)

    def test_import_rejects_bad_payload_before_network_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "bridge-inbox"
            inbox.mkdir()
            (inbox / "part.txt").write_text("not-base64!", encoding="ascii")
            request = {
                "project_id": "project-uuid", "base_revision": 1,
                "files": [{"path": "assets/bad.bin", "payload": "bridge-inbox/part.txt",
                           "byte_size": 2, "sha256": "0" * 64}],
            }
            with patch.object(bridge, "ROOT", root), patch.object(bridge, "INBOX", inbox), \
                 patch.object(bridge, "project_manifest", return_value={"head_revision": 1}), \
                 patch.object(bridge, "api_request") as send:
                with self.assertRaises(BridgeError):
                    bridge.import_project(request, "temporary-token")
            send.assert_not_called()

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
