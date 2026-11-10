import json
import tempfile
import unittest
from pathlib import Path

from prepare_issue import prepare


class PrepareIssueTests(unittest.TestCase):
    def run_task(self, body, title="[CHATGPT-BRIDGE] test"):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        event = root / "event.json"
        output = root / "output.txt"
        result = root / "result.json"
        event.write_text(json.dumps({
            "issue": {"title": title, "body": body, "number": 12}
        }), encoding="utf-8")
        return temp, event, output, result

    def test_accepts_ping(self):
        temp, event, output, result = self.run_task(json.dumps({
            "protocol": 1, "task_id": "bridge-ping-0001", "action": "ping"
        }))
        with temp:
            self.assertTrue(prepare(event, output, result)["accepted"])
            self.assertIn("action=ping", output.read_text())

    def test_rejects_shell_or_unknown_action(self):
        temp, event, output, result = self.run_task(json.dumps({
            "protocol": 1, "task_id": "bridge-ping-0001",
            "action": "shell", "command": "echo unsafe"
        }))
        with temp:
            with self.assertRaises(ValueError):
                prepare(event, output, result)

    def test_rejects_bad_task_id(self):
        temp, event, output, result = self.run_task(json.dumps({
            "protocol": 1, "task_id": "../../unsafe", "action": "ping"
        }))
        with temp:
            with self.assertRaises(ValueError):
                prepare(event, output, result)

    def test_rejects_wrong_title(self):
        temp, event, output, result = self.run_task(
            json.dumps({"protocol": 1, "task_id": "bridge-ping-0001", "action": "ping"}),
            title="ordinary issue"
        )
        with temp:
            with self.assertRaises(ValueError):
                prepare(event, output, result)


if __name__ == "__main__":
    unittest.main()
