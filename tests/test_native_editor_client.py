import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.bridge.native_editor_client import (
    ALLOWED_COMMANDS,
    execute_native_command,
    load_registry,
    project_fingerprint,
    validate_command,
)


class NativeEditorClientTests(unittest.TestCase):
    def test_project_fingerprint_is_stable_for_resolved_path(self):
        with tempfile.TemporaryDirectory() as folder:
            expected = hashlib.sha256(str(Path(folder).resolve()).replace("\\", "/").encode()).hexdigest()
            self.assertEqual(project_fingerprint(folder), expected)

    def test_only_explicit_native_commands_are_accepted(self):
        self.assertIn("scene.add_node", ALLOWED_COMMANDS)
        self.assertEqual(validate_command("editor.get_state", None), {})
        for unsafe in ("page.click", "shell.exec", "script.eval", "filesystem.write"):
            with self.subTest(command=unsafe):
                with self.assertRaises(ValueError):
                    validate_command(unsafe, {})

    def test_arguments_must_be_bounded_json_object(self):
        with self.assertRaises(ValueError):
            validate_command("editor.get_state", [])
        with self.assertRaises(ValueError):
            validate_command("scene.add_node", {"blob": "x" * 70000})

    def test_registry_rejects_invalid_protocol_and_port(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.json"
            base = {"protocol": 1, "token": "t" * 64, "project_id": "a" * 64, "port": 48765}
            path.write_text(json.dumps({**base, "port": 0}), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                load_registry(path)
            path.write_text(json.dumps({**base, "protocol": 99}), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                load_registry(path)

    def test_native_command_uses_loopback_and_checks_project_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            registry_path = Path(folder) / "registry.json"
            project_path = Path(folder) / "project"
            project_path.mkdir()
            project_id = project_fingerprint(project_path)
            registry_path.write_text(json.dumps({
                "protocol": 1, "token": "t" * 64, "project_id": project_id, "port": 48765
            }), encoding="utf-8")
            response = {
                "ok": True, "command": "editor.get_state", "project_id": project_id,
                "result": {"adapter": "godot_native_editor"}
            }

            class FakeSocket:
                def __init__(self):
                    self.sent = b""
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    return False
                def settimeout(self, _timeout):
                    pass
                def sendall(self, data):
                    self.sent = data
                def recv(self, _size):
                    if self.sent:
                        self.sent = b""
                        return (json.dumps(response) + "\n").encode()
                    return b""

            fake = FakeSocket()
            with patch("scripts.bridge.native_editor_client.socket.create_connection", return_value=fake) as connect:
                result = execute_native_command(registry_path, project_path, "editor.get_state")
            connect.assert_called_once_with(("127.0.0.1", 48765), timeout=18.0)
            self.assertEqual(result["result"]["adapter"], "godot_native_editor")

    def test_mismatched_project_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as folder:
            registry_path = Path(folder) / "registry.json"
            project_path = Path(folder) / "project"
            project_path.mkdir()
            registry_path.write_text(json.dumps({
                "protocol": 1, "token": "t" * 64, "project_id": "f" * 64, "port": 48765
            }), encoding="utf-8")
            with patch("scripts.bridge.native_editor_client.socket.create_connection") as connect:
                with self.assertRaisesRegex(RuntimeError, "different project"):
                    execute_native_command(registry_path, project_path, "editor.get_state")
                connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
