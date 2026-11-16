from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).parents[1] / "headless/native-editor/tools/native_command_agent.py"
SPEC = importlib.util.spec_from_file_location("native_command_agent", MODULE_PATH)
agent = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(agent)


class NativeCommandAgentPolicyTests(unittest.TestCase):
    def test_only_read_only_bridge_actions_are_exposed(self):
        self.assertEqual(
            set(agent.ACTIONS),
            {
                "ping",
                "editor.get_state",
                "scene.get_tree",
                "project.list_resources",
                "capture.editor_screenshot",
                "capture.desktop_screenshot",
            },
        )

    def test_unknown_action_is_rejected_before_process_launch(self):
        with self.assertRaises(agent.AgentError):
            agent.execute("shell.exec", {})

    def test_arguments_are_rejected(self):
        with self.assertRaises(agent.AgentError):
            agent.execute("ping", {"command": "anything"})

    def test_api_requires_https(self):
        agent.API = "http://localhost"
        agent.TOKEN = "test"
        with self.assertRaises(agent.AgentError):
            agent.request("GET", "/health")


if __name__ == "__main__":
    unittest.main()
