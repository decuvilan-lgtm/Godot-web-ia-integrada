from __future__ import annotations

import asyncio
import io
import json
import time
import unittest
import zipfile
from unittest.mock import patch

import persistent_sessions as sessions
from app import app


class FakeS3:
    def __init__(self):
        self.objects = {}
    def put_object(self, **kwargs):
        key = (kwargs["Bucket"], kwargs["Key"])
        self.objects[key] = kwargs["Body"]
        self.metadata = getattr(self, "metadata", {})
        self.metadata[key] = kwargs.get("Metadata", {})
    def get_object(self, **kwargs):
        import io
        data = self.objects[(kwargs["Bucket"], kwargs["Key"])]
        return {
            "Body": io.BytesIO(data),
            "ContentLength": len(data),
            "Metadata": self.metadata[(kwargs["Bucket"], kwargs["Key"])],
        }


class FakePage:
    def __init__(self):
        self.closed = False
        self.url = "https://godot-web-ia-integrada-rt2l.onrender.com/"
    def is_closed(self):
        return self.closed
    async def goto(self, url, **kwargs):
        self.url = url
        return None
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
            self.assertEqual(len(result["artifact_sha256"]), 64)
            self.assertEqual(sessions._sessions["test-session"].artifacts, {})
            payload = fake_s3.objects[(sessions.BUCKET, result["object_key"])]
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

    async def test_open_session_reuses_the_existing_browser_for_the_same_revision(self):
        body = sessions.OpenSessionRequest(
            repository="owner/project",
            branch="main",
            project_path="game",
        )
        expected_sha = "a" * 40
        self.session.commit_sha = expected_sha
        with patch.object(sessions, "SESSION_TOKEN", "test-secret"), patch.object(sessions, "resolve_repository_commit_sha", return_value=expected_sha), patch.object(sessions, "_get_browser") as get_browser:
            result = await sessions.open_persistent_session(body, "Bearer test-secret")
        self.assertTrue(result["reused"])
        self.assertEqual(result["session_id"], "test-session")
        get_browser.assert_not_called()

    async def test_open_session_can_reimport_a_new_revision_in_the_same_browser(self):
        body = sessions.OpenSessionRequest(
            repository="owner/project",
            branch="main",
            project_path="game",
            commit_sha="a" * 40,
            reimport_existing=True,
        )
        with patch.object(sessions, "SESSION_TOKEN", "test-secret"):
            result = await sessions.open_persistent_session(body, "Bearer test-secret")
        self.assertTrue(result["reused"])
        self.assertTrue(result["reimported"])
        self.assertEqual(result["session_id"], "test-session")
        self.assertEqual(self.session.commit_sha, "a" * 40)
        self.assertIn("sha=" + "a" * 40, self.page.url)

    async def test_open_session_rejects_switching_projects_without_closing_the_current_session(self):
        body = sessions.OpenSessionRequest(
            repository="owner/project",
            branch="main",
            project_path="another-game",
        )
        with patch.object(sessions, "SESSION_TOKEN", "test-secret"), patch.object(sessions, "resolve_repository_commit_sha", return_value="a" * 40):
            with self.assertRaises(Exception) as raised:
                await sessions.open_persistent_session(body, "Bearer test-secret")
        self.assertEqual(getattr(raised.exception, "status_code", None), 409)
        self.assertIn("test-session", sessions._sessions)

    async def test_session_list_returns_existing_session_metadata(self):
        with patch.object(sessions, "SESSION_TOKEN", "test-secret"):
            result = await sessions.list_persistent_sessions("Bearer test-secret")
        self.assertEqual(result["sessions"][0]["session_id"], "test-session")
        self.assertEqual(result["sessions"][0]["commit_sha"], None)

    async def test_project_profile_route_returns_not_found_without_global_fallback(self):
        with patch.object(sessions, "SESSION_TOKEN", "test-secret"), patch.object(sessions, "load_project_profile", return_value=None):
            result = await sessions.get_project_lab_profile("test-session", "Bearer test-secret")
        self.assertFalse(result["available"])
        self.assertEqual(result["profile_status"], "not_found")
        self.assertEqual(result["manifest_path"], "godot-lab/lab-manifest.json")

    async def test_project_profile_rejects_a_manifest_for_another_project_path(self):
        profile = {
            "manifest": {"project": {"project_path": "other"}, "commands": []},
            "control_profile": {"controls": {}},
            "commands": {},
        }
        with patch.object(sessions, "SESSION_TOKEN", "test-secret"), patch.object(sessions, "load_project_profile", return_value=profile):
            with self.assertRaises(Exception) as raised:
                await sessions.get_project_lab_profile("test-session", "Bearer test-secret")
        self.assertEqual(getattr(raised.exception, "status_code", None), 409)

    async def test_project_profile_command_executes_repo_owned_steps(self):
        profile = {
            "manifest": {"project": {"name": "Test", "project_path": "game"}, "commands": [{"name": "smoke-test", "file": "godot-lab/commands/smoke-test.json"}]},
            "control_profile": {"controls": {}},
            "commands": {"smoke-test": {"name": "smoke-test", "steps": [{"op": "inspect"}]}},
        }
        async def fake_execute(page, loaded_profile, command_name, artifacts):
            return [{"step": 0, "op": "inspect", "result": {"canvas_count": 1}}]
        with patch.object(sessions, "SESSION_TOKEN", "test-secret"), patch.object(sessions, "load_project_profile", return_value=profile), patch.object(sessions, "execute_profile_command", side_effect=fake_execute):
            result = await sessions.run_project_lab_command("test-session", "smoke-test", "Bearer test-secret")
        self.assertTrue(result["ok"])
        self.assertEqual(result["command"], "smoke-test")
        self.assertTrue(result["session_kept_open"])

    def test_project_profile_routes_are_registered(self):
        paths = {getattr(route, "path", None) for route in app.routes}
        self.assertIn("/v1/persistent-sessions/{session_id}/profile", paths)
        self.assertIn("/v1/persistent-sessions/{session_id}/profiles/{command_name}/run", paths)

    def test_session_list_route_is_registered(self):
        self.assertTrue(any(
            getattr(route, "path", None) == "/v1/persistent-sessions"
            and "GET" in getattr(route, "methods", set())
            for route in app.routes
        ))

    def test_artifact_download_route_is_registered(self):
        self.assertTrue(any(
            getattr(route, "path", None) == "/v1/persistent-sessions/{session_id}/artifacts/{artifact_id}"
            and getattr(route, "endpoint", None) is sessions.download_persistent_artifact
            for route in app.routes
        ))

    async def test_idle_expiry_is_at_least_fifteen_minutes(self):
        self.assertGreaterEqual(sessions.IDLE_TTL, 900)
        self.session.last_activity = time.time() - 901
        with self.assertRaises(Exception):
            sessions._get_session("test-session")


if __name__ == "__main__":
    unittest.main()
