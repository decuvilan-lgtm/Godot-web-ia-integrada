from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

import native_remote as remote


class NativeRemoteRelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        remote.sessions.clear()
        self.control = "control-secret"
        self.headers = "Bearer " + self.control
        self.config = patch.object(remote, "CONTROL_TOKEN", self.control)
        self.config.start()
        self.addCleanup(self.config.stop)

    async def test_enroll_issues_distinct_agent_credential(self):
        body = remote.EnrollRequest(project_id="a" * 64, project_path="/workspace/game")
        result = await remote.enroll(body, self.headers)
        self.assertTrue(result["session_id"])
        self.assertGreaterEqual(len(result["agent_token"]), 32)
        self.assertNotEqual(result["agent_token"], self.control)

    async def test_controller_command_waits_for_outbound_agent_result(self):
        enrolled = await remote.enroll(
            remote.EnrollRequest(project_id="b" * 64, project_path="/workspace/game"),
            self.headers,
        )
        session_id = enrolled["session_id"]
        agent = "Bearer " + enrolled["agent_token"]
        import asyncio
        task = asyncio.create_task(remote.enqueue_command(
            session_id,
            remote.CommandRequest(command="editor.get_state", args={}),
            self.headers,
        ))
        for _ in range(20):
            if remote.sessions[session_id].commands:
                break
            await asyncio.sleep(0)
        packet = await remote.next_command(session_id, agent)
        command = packet["command"]
        self.assertEqual(command["command"], "editor.get_state")
        submitted = await remote.submit_result(
            session_id,
            remote.ResultRequest(
                command_id=command["command_id"], ok=True,
                result={"adapter": "godot_native_editor"},
            ),
            agent,
        )
        result = await task
        self.assertTrue(submitted["accepted"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["adapter"], "godot_native_editor")

    async def test_agent_token_cannot_control_or_cross_project(self):
        enrolled = await remote.enroll(
            remote.EnrollRequest(project_id="c" * 64, project_path="/workspace/other"),
            self.headers,
        )
        session_id = enrolled["session_id"]
        with self.assertRaises(HTTPException) as denied:
            await remote.next_command(session_id, "Bearer wrong-token")
        self.assertEqual(denied.exception.status_code, 401)
        with self.assertRaises(HTTPException) as denied_controller:
            await remote.list_sessions("Bearer wrong-token")
        self.assertEqual(denied_controller.exception.status_code, 401)

    async def test_arbitrary_commands_are_rejected(self):
        enrolled = await remote.enroll(
            remote.EnrollRequest(project_id="d" * 64, project_path="/workspace/game"),
            self.headers,
        )
        with self.assertRaises(HTTPException) as denied:
            await remote.enqueue_command(
                enrolled["session_id"],
                remote.CommandRequest(command="shell.exec", args={"cmd": "anything"}),
                self.headers,
            )
        self.assertEqual(denied.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
