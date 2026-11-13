from __future__ import annotations

import asyncio
import io
import json
import time
import unittest
import zipfile
from unittest.mock import patch

import persistent_sessions as sessions


class FakePage:
    def __init__(self):
        self.closed = False
    def is_closed(self):
        return self.closed
    async def screenshot(self, **kwargs):
        return b"fake-png-bytes"


class PersistentSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        sessions._sessions.clear()
        self.page = FakePage()
        self.session = sessions.PersistentSession(
            session_id="test-session",
            repository="owner/project",
            branch="main",
            project_path="game",
            page=self.page,
        )
        sessions._sessions[self.session.session_id] = self.session

    async def test_task_completion_returns_bundle_without_closing_session(self):
        body = sessions.CompleteTaskRequest(
            task_id="task-001",
            summary="Finished inspection",
            result={"checks": ["editor-open", "screenshot"]},
        )
        with patch.object(sessions, "SESSION_TOKEN", "test-secret"):
            result = await sessions.complete_persistent_task(
                "test-session", body, "Bearer test-secret"
            )
            self.assertTrue(result["session_kept_open"])
            self.assertEqual(result["state"], "completed")
            self.assertFalse(self.page.closed)
            payload = sessions._sessions["test-session"].artifacts[
                f"bundle-{result['artifact_id']}.zip"
            ]
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                manifest = json.loads(archive.read("task-result.json"))
                self.assertTrue(manifest["session_remains_open"])
                self.assertEqual(manifest["task_id"], "task-001")
                self.assertIn("artifacts/task-task-001-final.png", archive.namelist())

    async def test_completed_task_is_idempotent_and_keeps_session(self):
        body = sessions.CompleteTaskRequest(task_id="same-task")
        with patch.object(sessions, "SESSION_TOKEN", "test-secret"):
            first = await sessions.complete_persistent_task(
                "test-session", body, "Bearer test-secret"
            )
            second = await sessions.complete_persistent_task(
                "test-session", body, "Bearer test-secret"
            )
        self.assertEqual(first["artifact_id"], second["artifact_id"])
        self.assertTrue(second["session_kept_open"])
        self.assertFalse(self.page.closed)

    async def test_idle_expiry_is_at_least_fifteen_minutes(self):
        self.assertGreaterEqual(sessions.IDLE_TTL, 900)
        self.session.last_activity = time.time() - 901
        with self.assertRaises(Exception):
            sessions._get_session("test-session")


if __name__ == "__main__":
    unittest.main()
