import unittest
import uuid

from scripts.bridge.bridge_request import validate_request


REPOSITORY = "decuvilan-lgtm/Godot-web-ia-integrada"
BRANCH = "test/verdant-valley-development-benchmark"


def valid_request():
    return {
        "repository": REPOSITORY,
        "branch": BRANCH,
        "request_id": "chatgpt-request-0001",
        "transport_session_id": str(uuid.uuid4()),
        "command": {"action": "status", "args": {}},
        "timeout_seconds": 240,
    }


class BridgeRequestValidationTests(unittest.TestCase):
    def test_accepts_exact_operator_command(self):
        request = valid_request()
        request_id, session_id, action, args, timeout = validate_request(request, REPOSITORY, BRANCH)
        self.assertEqual(request_id, request["request_id"])
        self.assertEqual(session_id, request["transport_session_id"])
        self.assertEqual(action, "status")
        self.assertEqual(args, {})
        self.assertEqual(timeout, 240)

    def test_preserves_operator_arguments_without_reinterpretation(self):
        request = valid_request()
        request["command"] = {"action": "semantic_command", "args": {
            "editor_action": "scene.inspect_node", "args": {"path": "Root/Hero"}
        }}
        _, _, action, args, _ = validate_request(request, REPOSITORY, BRANCH)
        self.assertEqual(action, "semantic_command")
        self.assertEqual(args, request["command"]["args"])

    def test_rejects_repository_mismatch(self):
        with self.assertRaisesRegex(ValueError, "repository mismatch"):
            validate_request(valid_request(), "other/repo", BRANCH)

    def test_rejects_non_test_branch(self):
        with self.assertRaisesRegex(ValueError, "authorized test branch"):
            validate_request(valid_request(), REPOSITORY, "main")

    def test_rejects_invalid_session_uuid(self):
        request = valid_request()
        request["transport_session_id"] = "not-a-uuid"
        with self.assertRaisesRegex(ValueError, "UUID"):
            validate_request(request, REPOSITORY, BRANCH)

    def test_rejects_unknown_command_envelope_fields(self):
        request = valid_request()
        request["command"]["operation"] = "latency-benchmark"
        with self.assertRaisesRegex(ValueError, "only action and args"):
            validate_request(request, REPOSITORY, BRANCH)

    def test_rejects_invalid_action_identifier(self):
        request = valid_request()
        request["command"]["action"] = "Run arbitrary workflow"
        with self.assertRaisesRegex(ValueError, "action identifier"):
            validate_request(request, REPOSITORY, BRANCH)

    def test_rejects_oversized_arguments(self):
        request = valid_request()
        request["command"]["args"] = {"payload": "x" * (64 * 1024)}
        with self.assertRaisesRegex(ValueError, "bounded JSON object"):
            validate_request(request, REPOSITORY, BRANCH)

    def test_rejects_boolean_timeout(self):
        request = valid_request()
        request["timeout_seconds"] = True
        with self.assertRaisesRegex(ValueError, "between 15 and 900"):
            validate_request(request, REPOSITORY, BRANCH)

    def test_rejects_task_level_operation_selector(self):
        request = valid_request()
        request["operation"] = "latency-benchmark"
        # Top-level unknown metadata is ignored; only command is the transport payload.
        _, _, action, _, _ = validate_request(request, REPOSITORY, BRANCH)
        self.assertEqual(action, "status")


if __name__ == "__main__":
    unittest.main()
