import asyncio
import os
import sys
import types
import unittest
from unittest.mock import patch
from starlette.requests import Request
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ["RELAY_ADMIN_TOKEN"] = "test-admin-secret"
from app import app, sessions

class RelayApiTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.client = TestClient(app)

    def test_health_is_public_and_identifies_service(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["service"], "godot-web-ia-relay")

    def test_session_creation_requires_admin_token(self):
        denied = self.client.post("/v1/sessions", json={"label": "test"})
        self.assertEqual(denied.status_code, 401)

        created = self.client.post(
            "/v1/sessions",
            headers={"X-Admin-Token": "test-admin-secret"},
            json={"label": "Android Godot project"},
        )
        self.assertEqual(created.status_code, 200)
        payload = created.json()
        self.assertTrue(payload["session_id"])
        self.assertTrue(payload["editor_token"])
        self.assertTrue(payload["controller_token"])
        self.assertNotEqual(payload["editor_token"], payload["controller_token"])

    def test_session_status_requires_controller_token(self):
        created = self.client.post(
            "/v1/sessions",
            headers={"X-Admin-Token": "test-admin-secret"},
            json={"label": "test"},
        ).json()
        denied = self.client.get(f"/v1/sessions/{created['session_id']}")
        self.assertEqual(denied.status_code, 401)

        allowed = self.client.get(
            f"/v1/sessions/{created['session_id']}",
            headers={"Authorization": f"Bearer {created['controller_token']}"},
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertFalse(allowed.json()["editor_connected"])

    def test_controller_cannot_send_actions_outside_read_only_allowlist(self):
        created = self.client.post(
            "/v1/sessions",
            headers={"X-Admin-Token": "test-admin-secret"},
            json={"label": "test"},
        ).json()
        response = self.client.post(
            f"/v1/sessions/{created['session_id']}/request",
            headers={"Authorization": f"Bearer {created['controller_token']}"},
            json={"action": "filesystem.delete", "args": {}},
        )
        self.assertEqual(response.status_code, 400)

    def test_command_center_routes_fail_closed_without_neon(self):
        denied = self.client.post(
            "/v1/command-center/pairing-codes",
            json={"device_kind": "android_editor"},
        )
        self.assertEqual(denied.status_code, 401)
        self.assertIn("no-store", denied.headers.get("cache-control", ""))

        no_database = self.client.post(
            "/v1/command-center/pair",
            json={
                "pairing_code": "p" * 32,
                "label": "Android editor",
                "installation_id": "install-identifier-123",
            },
        )
        self.assertEqual(no_database.status_code, 503)
        self.assertIn("no-store", no_database.headers.get("cache-control", ""))

    def test_command_center_requires_bearer_device_credential(self):
        response = self.client.get("/v1/command-center/commands/next")
        self.assertEqual(response.status_code, 401)

    def test_command_center_policy_keeps_visual_commands_separate_and_disabled(self):
        from command_center import READ_ONLY_ACTIONS, VISUAL_ACTIONS, VISUAL_COMMANDS_ENABLED
        self.assertEqual(
            READ_ONLY_ACTIONS,
            {"ping", "project.get_state", "project.list_files", "scene.inspect", "script.read"},
        )
        self.assertEqual(
            VISUAL_ACTIONS,
            {"visual.capture", "visual.capture_sequence", "visual.zoom_to"},
        )
        self.assertFalse(VISUAL_COMMANDS_ENABLED)
        self.assertNotIn("script.write", READ_ONLY_ACTIONS)
        self.assertNotIn("shell.execute", READ_ONLY_ACTIONS)

    def test_visual_capture_requires_an_exact_target(self):
        from command_center import validate_visual_command
        with self.assertRaises(HTTPException) as raised:
            validate_visual_command("visual.capture", {})
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(raised.exception.detail["code"], "VISUAL_ARGUMENT_INVALID")

        with self.assertRaises(HTTPException) as raised:
            validate_visual_command("visual.capture", {"target": "editor"})
        self.assertEqual(raised.exception.detail["code"], "VISUAL_TARGET_REQUIRED")

    def test_visual_capture_sequence_validates_target_count_and_interval(self):
        from command_center import validate_visual_command
        validate_visual_command("visual.capture_sequence", {
            "target": "editor_ui",
            "frames": 12,
            "interval_ms": 250,
            "timing_mode": "realtime",
        })
        with self.assertRaises(HTTPException) as raised:
            validate_visual_command("visual.capture_sequence", {
                "target": "editor_3d",
                "frames": 25,
                "interval_ms": 250,
            })
        self.assertEqual(raised.exception.detail["code"], "VISUAL_SEQUENCE_LIMIT")

        with self.assertRaises(HTTPException) as raised:
            validate_visual_command("visual.capture_sequence", {
                "target": "editor_3d",
                "frames": 12,
                "interval_ms": 10,
            })
        self.assertEqual(raised.exception.detail["code"], "VISUAL_SEQUENCE_LIMIT")

    def test_visual_zoom_requires_matching_coordinate_space_and_restoration(self):
        from command_center import validate_visual_command
        validate_visual_command("visual.zoom_to", {
            "target": "editor_2d",
            "focus": {
                "coordinate_space": "world_2d",
                "position": [640.0, 360.0],
                "zoom": 3.0,
            },
            "restore_view": True,
        })
        with self.assertRaises(HTTPException) as raised:
            validate_visual_command("visual.zoom_to", {
                "target": "editor_3d",
                "focus": {
                    "coordinate_space": "world_2d",
                    "position": [640.0, 360.0],
                    "zoom": 3.0,
                },
                "restore_view": True,
            })
        self.assertEqual(raised.exception.detail["code"], "VISUAL_COORDINATE_MISMATCH")

        with self.assertRaises(HTTPException) as raised:
            validate_visual_command("visual.zoom_to", {
                "target": "editor_2d",
                "focus": {
                    "coordinate_space": "world_2d",
                    "position": [640.0, 360.0],
                    "zoom": 3.0,
                },
                "restore_view": False,
            })
        self.assertEqual(raised.exception.detail["code"], "VISUAL_RESTORE_REQUIRED")

    def test_visual_commands_reject_unknown_fields_and_frame_step_until_supported(self):
        from command_center import validate_visual_command
        with self.assertRaises(HTTPException) as raised:
            validate_visual_command("visual.capture", {
                "target": "editor_ui",
                "screen": "android_phone",
            })
        self.assertEqual(raised.exception.detail["code"], "VISUAL_ARGUMENT_INVALID")

        with self.assertRaises(HTTPException) as raised:
            validate_visual_command("visual.capture_sequence", {
                "target": "game_preview",
                "frames": 4,
                "interval_ms": 100,
                "timing_mode": "frame_step",
            })
        self.assertEqual(raised.exception.detail["code"], "VISUAL_TIMING_UNAVAILABLE")

    def test_pairing_admin_page_is_ephemeral_and_hardened(self):
        page = self.client.get("/command-center/admin")
        self.assertEqual(page.status_code, 200)
        self.assertIn("no-store", page.headers.get("cache-control", ""))
        self.assertEqual(page.headers.get("referrer-policy"), "no-referrer")
        self.assertIn("script-src 'self'", page.headers.get("content-security-policy", ""))
        self.assertIn("/command-center/admin.js", page.text)

        script = self.client.get("/command-center/admin.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("X-Command-Center-Admin", script.text)
        self.assertIn("/v1/command-center/pairing-codes", script.text)
        self.assertNotIn("localStorage", script.text)
        self.assertNotIn("sessionStorage", script.text)
        self.assertIn("token.value = ''", script.text)

    def test_browser_cors_allows_editor_origin_and_required_headers_only(self):
        allowed = self.client.options(
            "/v1/command-center/pair",
            headers={
                "Origin": "https://godot-web-ia-integrada-rt2l.onrender.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"),
            "https://godot-web-ia-integrada-rt2l.onrender.com",
        )

        authenticated = self.client.options(
            "/v1/command-center/commands/next",
            headers={
                "Origin": "https://godot-web-ia-integrada-rt2l.onrender.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        self.assertEqual(authenticated.status_code, 200)
        self.assertIn("authorization", authenticated.headers.get("access-control-allow-headers", "").lower())

        denied = self.client.options(
            "/v1/command-center/pair",
            headers={
                "Origin": "https://untrusted.invalid",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(denied.status_code, 400)

    def test_command_center_lazily_reconnects_after_startup_failure(self):
        from command_center import get_pool
        attempts = {"count": 0}
        sentinel_pool = object()

        async def create_pool(**kwargs):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise OSError("temporary database outage")
            return sentinel_pool

        async def exercise(request):
            with self.assertRaises(HTTPException) as first:
                await get_pool(request)
            self.assertEqual(first.exception.status_code, 503)
            self.assertGreater(app.state.command_center_db_retry_after, 0)
            with self.assertRaises(HTTPException) as cooling_down:
                await get_pool(request)
            self.assertEqual(cooling_down.exception.status_code, 503)
            app.state.command_center_db_retry_after = 0.0
            return await get_pool(request)

        fake_asyncpg = types.SimpleNamespace(create_pool=create_pool)
        request = Request({
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "app": app,
        })
        app.state.command_center_db = None
        app.state.command_center_db_lock = None
        with patch.dict(os.environ, {"COMMAND_CENTER_DATABASE_URL": "postgresql://test.invalid/db"}):
            with patch.dict(sys.modules, {"asyncpg": fake_asyncpg}):
                pool = asyncio.run(exercise(request))
        self.assertIs(pool, sentinel_pool)
        self.assertEqual(attempts["count"], 2)
        app.state.command_center_db = None
        app.state.command_center_db_lock = None
        app.state.command_center_db_retry_after = 0.0

    def test_expired_or_unknown_session_is_not_found(self):
        response = self.client.get("/v1/sessions/not-a-real-session")
        self.assertEqual(response.status_code, 404)

if __name__ == "__main__":
    unittest.main()
