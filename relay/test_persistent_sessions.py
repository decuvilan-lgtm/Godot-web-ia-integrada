from __future__ import annotations

import asyncio
import io
import json
import time
import unittest
import zipfile
from unittest.mock import patch

import persistent_sessions as sessions


class FakeS3:
    def __init__(self):
        self.objects = {}
    def put_object(self, **kwargs):
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]
    def get_object(self, **kwargs):
        import io
        return {"Body": io.BytesIO(self.objects[(kwargs["Bucket"], kwargs["Key"])])}


class FakePage:
    def __init__(self):
        self.closed = False
    def is_closed(self):
        return self.closed
    async def screenshot(self, **kwargs):
        return b"fake-png-bytes"
    async def evaluate(self, script):
        return {"phase": "started", "commitSha": None}
    def locator(self, selector):
        class FakeLocator:
            async def inner_text(self, **kwargs):
                return "Godot Web test editor"
            async def count(self):
                return 1
        return FakeLocator()


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
        fake_s3 = FakeS3()
        with patch.object(sessions, "SESSION_TOKEN", "test-secret"), patch.object(sessions, "storage_client", return_value=fake_s3):
            result = await sessions.complete_persistent_task(
                "test-session", body, "Bearer test-secret"
            )
            self.assertTrue(result["session_kept_open"])
            self.assertEqual(result["state"], "completed")
            self.assertFalse(self.page.closed)
            self.assertEqual(result["storage"], "neon-object-storage")
            self.assertEqual(len(fake_s3.objects), 1)
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
        fake_s3 = FakeS3()
        with patch.object(sessions, "SESSION_TOKEN", "test-secret"), patch.object(sessions, "storage_client", return_value=fake_s3):
            first = await sessions.complete_persistent_task(
                "test-session", body, "Bearer test-secret"
            )
            second = await sessions.complete_persistent_task(
                "test-session", body, "Bearer test-secret"
            )
        self.assertEqual(first["artifact_id"], second["artifact_id"])
        self.assertTrue(second["session_kept_open"])
        self.assertFalse(self.page.closed)

    async def test_artifact_can_be_downloaded_after_session_memory_is_lost(self):
        fake_s3 = FakeS3()
        body = sessions.CompleteTaskRequest(task_id="restart-safe-task")
        with patch.object(sessions, "SESSION_TOKEN", "test-secret"), patch.object(sessions, "storage_client", return_value=fake_s3):
            result = await sessions.complete_persistent_task("test-session", body, "Bearer test-secret")
            sessions._sessions.clear()
            response = await sessions.download_persistent_artifact("test-session", result["artifact_id"], "Bearer test-secret")
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        self.assertTrue(b"".join(chunks).startswith(b"PK"))

    async def test_github_oidc_claims_are_restricted_to_the_expected_workflow(self):
        claims = {
            "repository": sessions.OIDC_REPOSITORY,
            "ref": sessions.OIDC_REF,
            "workflow_ref": f"{sessions.OIDC_REPOSITORY}/{sessions.OIDC_WORKFLOW}@{sessions.OIDC_REF}",
        }
        sessions._validate_github_oidc_claims(claims)
        claims["repository"] = "someone-else/other-repo"
        with self.assertRaises(ValueError):
            sessions._validate_github_oidc_claims(claims)

    async def test_commit_sha_is_validated_and_saved(self):
        request = sessions.OpenSessionRequest(repository="owner/project", commit_sha="a" * 40)
        self.assertEqual(request.commit_sha, "a" * 40)
        with self.assertRaises(Exception):
            sessions.OpenSessionRequest(repository="owner/project", commit_sha="not-a-sha")

    async def test_idle_expiry_is_at_least_fifteen_minutes(self):
        self.assertGreaterEqual(sessions.IDLE_TTL, 900)
        self.session.last_activity = time.time() - 901
        with self.assertRaises(Exception):
            sessions._get_session("test-session")


if __name__ == "__main__":
    unittest.main()
