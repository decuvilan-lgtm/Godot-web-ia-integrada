import asyncio
import unittest

from mcp import Client
from fastapi import HTTPException

from command_center import ALLOWED_ACTIONS
from mcp_server import mcp_server, validate_agent_command


class MCPCommandPolicyTests(unittest.TestCase):
    def test_mcp_protocol_exposes_only_the_intended_controller_tools(self):
        async def list_names():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                return {tool.name for tool in result.tools}

        names = asyncio.run(list_names())
        self.assertEqual(
            names,
            {
                "godot_workspace_status",
                "godot_enqueue_command",
                "godot_command_status",
                "godot_list_recent_commands",
                "godot_execution_providers",
                "godot_start_task",
                "godot_task_status",
            },
        )

        async def list_schemas():
            async with Client(mcp_server) as client:
                result = await client.list_tools()
                return {tool.name: tool.input_schema for tool in result.tools}

        schemas = asyncio.run(list_schemas())
        self.assertEqual(
            set(schemas["godot_task_status"]["properties"]),
            {"provider", "request_id", "execution_id"},
        )

    def test_all_read_only_actions_are_available(self):
        for action in ("ping", "project.get_state", "project.list_files", "scene.inspect", "script.read"):
            self.assertEqual(validate_agent_command(action, {}, "test-" + action), "test-" + action)
        self.assertTrue(set(("ping", "project.get_state", "project.list_files", "scene.inspect", "script.read")).issubset(ALLOWED_ACTIONS))

    def test_mutating_and_unknown_actions_are_rejected(self):
        for action in ("script.write", "filesystem.delete", "shell.execute", "unknown"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate_agent_command(action, {}, "test-key")

    def test_visual_capture_uses_the_shared_contract(self):
        self.assertEqual(
            validate_agent_command("visual.capture", {"target": "editor_2d"}, "capture-1"),
            "capture-1",
        )
        self.assertEqual(
            validate_agent_command(
                "visual.capture_sequence",
                {"target": "editor_3d", "frames": 3, "interval_ms": 250},
                "sequence-1",
            ),
            "sequence-1",
        )

    def test_visual_targets_and_unsupported_zoom_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_agent_command("visual.capture", {"target": "editor_ui"}, "capture-ui")
        with self.assertRaises(ValueError):
            validate_agent_command(
                "visual.zoom_to",
                {
                    "target": "editor_2d",
                    "focus": {"coordinate_space": "world_2d", "position": [1, 2], "zoom": 2},
                    "restore_view": True,
                },
                "zoom-1",
            )

    def test_idempotency_key_and_payload_limits_are_enforced(self):
        with self.assertRaises(ValueError):
            validate_agent_command("ping", {}, " ")
        with self.assertRaises(ValueError):
            validate_agent_command("ping", {}, "x" * 129)
        with self.assertRaises(ValueError):
            validate_agent_command("ping", {"blob": "x" * (256 * 1024 + 100)}, "large-args")


if __name__ == "__main__":
    unittest.main()
