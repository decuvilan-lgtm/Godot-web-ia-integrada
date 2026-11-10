import asyncio
import json
import unittest

import httpx

from task_dispatch import (
    TaskDispatchError,
    dispatch_task,
    task_status,
    provider_status,
    validate_request_id,
    validate_task_profile,
)


class TaskDispatchTests(unittest.TestCase):
    def test_profiles_and_request_ids_are_allowlisted(self):
        self.assertEqual(validate_task_profile("scene_audit_3d"), "scene_audit_3d")
        with self.assertRaises(ValueError):
            validate_task_profile("shell")
        self.assertEqual(validate_request_id("task_123456"), "task_123456")
        with self.assertRaises(ValueError):
            validate_request_id("../../etc/passwd")

    def test_circleci_is_primary(self):
        calls = []

        async def handler(request):
            calls.append(request)
            return httpx.Response(201, json={
                "id": "12345678-1234-1234-1234-123456789abc",
                "number": 42,
                "state": "created",
            })

        transport = httpx.MockTransport(handler)
        result = asyncio.run(dispatch_task(
            "engine_smoke", "task_123456",
            env={
                "CIRCLECI_TOKEN": "circle-secret",
                "CIRCLECI_PROJECT_SLUG": "gh/example/project",
                "GITHUB_ACTIONS_TOKEN": "github-secret",
            },
            transport=transport,
        ))
        self.assertEqual(result["provider"], "circleci")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].headers["Circle-Token"], "circle-secret")
        body = json.loads(calls[0].content)
        self.assertEqual(body["parameters"]["task_profile"], "engine_smoke")

    def test_github_actions_is_used_when_circleci_is_not_configured(self):
        calls = []

        async def handler(request):
            calls.append(request)
            return httpx.Response(204)

        result = asyncio.run(dispatch_task(
            "scene_audit_3d", "task_123456",
            env={"GITHUB_ACTIONS_TOKEN": "github-secret"},
            transport=httpx.MockTransport(handler),
        ))
        self.assertEqual(result["provider"], "github_actions")
        self.assertTrue(result["fallback_used"])
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].url.path.endswith("/actions/workflows/remote-godot-task.yml/dispatches"))

    def test_github_actions_is_fallback_when_circleci_fails(self):
        calls = []

        async def handler(request):
            calls.append(request)
            if "circleci.com" in str(request.url):
                return httpx.Response(503)
            return httpx.Response(204)

        result = asyncio.run(dispatch_task(
            "engine_smoke", "task_123456",
            env={
                "CIRCLECI_TOKEN": "circle-secret",
                "CIRCLECI_PROJECT_SLUG": "gh/example/project",
                "GITHUB_ACTIONS_TOKEN": "github-secret",
            },
            transport=httpx.MockTransport(handler),
        ))
        self.assertEqual(result["provider"], "github_actions")
        self.assertTrue(result["fallback_used"])
        self.assertEqual(len(calls), 2)

    def test_dispatch_fails_closed_when_no_provider_is_configured(self):
        with self.assertRaises(TaskDispatchError):
            asyncio.run(dispatch_task("engine_smoke", "task_123456", env={}))

    def test_circleci_status_returns_pipeline_and_workflow_state(self):
        async def handler(request):
            if request.url.path.endswith("/workflow"):
                return httpx.Response(200, json={"items": [{
                    "id": "workflow-123",
                    "name": "remote-godot-task",
                    "status": "success",
                }]})
            return httpx.Response(200, json={"id": "12345678-1234-1234-1234-123456789abc", "state": "created", "number": 7})

        result = asyncio.run(task_status(
            "circleci", "12345678-1234-1234-1234-123456789abc", "task_123456",
            env={"CIRCLECI_TOKEN": "circle-secret", "CIRCLECI_PROJECT_SLUG": "gh/example/project"},
            transport=httpx.MockTransport(handler),
        ))
        self.assertEqual(result["state"], "created")
        self.assertEqual(result["workflows"][0]["status"], "success")

    def test_provider_status_never_exposes_secret_values(self):
        result = provider_status(env={
            "CIRCLECI_TOKEN": "do-not-return-this",
            "CIRCLECI_PROJECT_SLUG": "gh/example/project",
            "GITHUB_ACTIONS_TOKEN": "also-secret",
        })
        serialized = json.dumps(result)
        self.assertTrue(result["primary"]["configured"])
        self.assertTrue(result["fallback"]["configured"])
        self.assertNotIn("do-not-return-this", serialized)
        self.assertNotIn("also-secret", serialized)

    def test_github_status_includes_artifact_metadata(self):
        async def handler(request):
            if request.url.path.endswith("/runs"):
                return httpx.Response(200, json={"workflow_runs": [{
                    "id": 77, "display_title": "Godot task task_123456",
                    "status": "completed", "conclusion": "success",
                    "html_url": "https://github.com/example/project/actions/runs/77",
                }]})
            return httpx.Response(200, json={"artifacts": [{
                "id": 88, "name": "godot-task-task_123456",
                "size_in_bytes": 1234, "expired": False,
                "archive_download_url": "https://api.github.com/artifacts/88",
            }]})

        result = asyncio.run(task_status(
            "github_actions", None, "task_123456",
            env={"GITHUB_ACTIONS_TOKEN": "github-secret"},
            transport=httpx.MockTransport(handler),
        ))
        self.assertEqual(result["artifacts"][0]["id"], 88)

    def test_status_rejects_unknown_provider(self):
        with self.assertRaises(ValueError):
            asyncio.run(task_status("unknown", None, "task_123456", env={}))


if __name__ == "__main__":
    unittest.main()
