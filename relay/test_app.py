import asyncio
import io
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch
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

    def test_multiple_queries_reuse_one_workspace_without_creating_projects_or_sessions(self):
        from command_center import create_command

        class AsyncContext:
            def __init__(self, value=None):
                self.value = value
            async def __aenter__(self):
                return self.value
            async def __aexit__(self, exc_type, exc, traceback):
                return False

        class FakeConnection:
            def __init__(self):
                self.command_inserts = []
                self.other_inserts = []
                self.counter = 0
            def transaction(self):
                return AsyncContext()
            async def fetchval(self, query, *args):
                self.command_inserts.append((query, args))
                self.counter += 1
                return f"command-{self.counter}"
            async def execute(self, query, *args):
                self.other_inserts.append((query, args))

        class FakePool:
            def __init__(self, connection):
                self.connection = connection
            def acquire(self):
                return AsyncContext(self.connection)

        connection = FakeConnection()
        identity = {
            "id": "device-web-1",
            "device_kind": "agent_controller",
            "workspace_id": "persistent-workspace-1",
        }
        with patch("command_center.authenticate_device", new=AsyncMock(return_value=identity)), \
             patch("command_center.get_pool", new=AsyncMock(return_value=FakePool(connection))):
            first = self.client.post(
                "/v1/command-center/commands",
                headers={"Authorization": "Bearer test"},
                json={"target": "web_editor", "action": "ping", "args": {}, "idempotency_key": "query-1"},
            )
            second = self.client.post(
                "/v1/command-center/commands",
                headers={"Authorization": "Bearer test"},
                json={"target": "web_editor", "action": "project.get_state", "args": {}, "idempotency_key": "query-2"},
            )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.json()["command_id"], "command-1")
        self.assertEqual(second.json()["command_id"], "command-2")
        self.assertEqual(len(connection.command_inserts), 2)
        self.assertEqual(
            [entry[1][0] for entry in connection.command_inserts],
            ["persistent-workspace-1", "persistent-workspace-1"],
        )
        sql = " ".join(entry[0].lower() for entry in connection.command_inserts)
        self.assertIn("insert into command_center.commands", sql)
        self.assertNotIn("insert into command_center.workspaces", sql)
        self.assertNotIn("insert into command_center.sessions", sql)
        self.assertNotIn("insert into command_center.projects", sql)

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
        self.assertEqual(raised.exception.detail["code"], "VISUAL_TARGET_REQUIRED")

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

    def test_visual_storage_routes_require_authenticated_web_editor(self):
        upload = self.client.post(
            "/v1/command-center/visual/uploads/presign",
            json={
                "command_id": "00000000-0000-0000-0000-000000000001",
                "content_type": "image/png",
            },
        )
        self.assertEqual(upload.status_code, 401)
        download = self.client.get(
            "/v1/command-center/visual/assets/00000000-0000-0000-0000-000000000001/download"
        )
        self.assertEqual(download.status_code, 401)

    def test_visual_storage_fails_closed_without_neon_storage_credentials(self):
        from visual_storage import storage_client
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                storage_client()
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["code"], "VISUAL_STORAGE_NOT_CONFIGURED")

    def test_visual_upload_completion_rejects_unissued_object_key_shape(self):
        response = self.client.post(
            "/v1/command-center/visual/uploads/complete",
            json={"object_key": "../public/image.png", "width": 10, "height": 10},
        )
        self.assertEqual(response.status_code, 422)

    def test_command_heartbeat_requires_authenticated_editor(self):
        response = self.client.post(
            "/v1/command-center/commands/00000000-0000-0000-0000-000000000001/heartbeat"
        )
        self.assertEqual(response.status_code, 401)

    def test_visual_object_keys_bind_workspace_command_and_sequence_frame(self):
        from visual_storage import KEY_RE
        workspace = "11111111-1111-4111-8111-111111111111"
        command = "22222222-2222-4222-8222-222222222222"
        nonce = "33333333-3333-4333-8333-333333333333"
        self.assertIsNotNone(KEY_RE.fullmatch(f"{workspace}/{command}/single/{nonce}.png"))
        self.assertIsNotNone(KEY_RE.fullmatch(f"{workspace}/{command}/23/{nonce}.webp"))
        self.assertIsNone(KEY_RE.fullmatch(f"{workspace}/{command}/24/{nonce}.webp"))
        self.assertIsNone(KEY_RE.fullmatch(f"{workspace}/{command}/../{nonce}.png"))

    def test_expired_or_unknown_session_is_not_found(self):
        response = self.client.get("/v1/sessions/not-a-real-session")
        self.assertEqual(response.status_code, 404)


class VisualObjectVerificationTests(unittest.TestCase):
    def _png(self, size=(3, 2)):
        from PIL import Image
        buffer = io.BytesIO()
        Image.new("RGB", size, (12, 34, 56)).save(buffer, format="PNG")
        return buffer.getvalue()

    def _client(self, data, mime="image/png", declared_size=None):
        class FakeClient:
            def head_object(self, **kwargs):
                return {
                    "ContentLength": len(data) if declared_size is None else declared_size,
                    "ContentType": mime,
                }
            def get_object(self, **kwargs):
                return {"Body": io.BytesIO(data)}
        return FakeClient()

    def test_valid_png_is_verified_and_hashed(self):
        import hashlib
        from visual_storage import verify_uploaded_object
        payload = self._png()
        mime, size, digest = verify_uploaded_object(
            self._client(payload), "capture.png", "png", 3, 2
        )
        self.assertEqual(mime, "image/png")
        self.assertEqual(size, len(payload))
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())

    def test_image_dimensions_must_match_reported_metadata(self):
        from visual_storage import verify_uploaded_object
        payload = self._png(size=(3, 2))
        with self.assertRaisesRegex(ValueError, "valid supported image"):
            verify_uploaded_object(
                self._client(payload), "capture.png", "png", 2, 3
            )

    def test_declared_mime_and_extension_must_match(self):
        from visual_storage import verify_uploaded_object
        payload = self._png()
        with self.assertRaisesRegex(ValueError, "size or MIME"):
            verify_uploaded_object(
                self._client(payload, mime="image/jpeg"), "capture.png", "png", 3, 2
            )

    def test_invalid_image_bytes_are_rejected(self):
        from visual_storage import verify_uploaded_object
        with self.assertRaisesRegex(ValueError, "valid supported image"):
            verify_uploaded_object(
                self._client(b"not an image"), "capture.png", "png", 3, 2
            )

    def test_uploaded_length_must_match_head_metadata(self):
        from visual_storage import verify_uploaded_object
        payload = self._png()
        with self.assertRaisesRegex(ValueError, "length could not be verified"):
            verify_uploaded_object(
                self._client(payload, declared_size=len(payload) + 1),
                "capture.png", "png", 3, 2,
            )


    def test_visual_viewport_index_is_limited_to_godot_supported_range(self):
        from command_center import validate_visual_command
        for index in range(4):
            validate_visual_command("visual.capture", {
                "target": "editor_3d",
                "viewport_index": index,
            })
        with self.assertRaises(HTTPException) as raised:
            validate_visual_command("visual.capture", {
                "target": "editor_3d",
                "viewport_index": 4,
            })
        self.assertEqual(raised.exception.detail["code"], "VISUAL_ARGUMENT_INVALID")


class VisualAssetIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_with_same_object_key_reuses_asset_without_deleting_it(self):
        from visual_storage import _insert_asset_idempotently
        pool = types.SimpleNamespace(
            fetchval=AsyncMock(return_value=None),
            fetchrow=AsyncMock(return_value={"id": "asset-1", "object_key": "workspace/command/single/nonce.png"}),
        )
        client = types.SimpleNamespace(delete_object=unittest.mock.Mock())
        with patch("visual_storage.run_in_threadpool", new=AsyncMock()) as threaded:
            asset_id, reused = await _insert_asset_idempotently(
                pool, client, workspace_id="workspace", command_id="command",
                sequence_id=None, frame_index=None, capture_kind="editor_2d",
                object_key="workspace/command/single/nonce.png", mime="image/png",
                width=3, height=2, size=78, digest="a" * 64,
                captured_at=None, metadata={},
            )
        self.assertEqual(asset_id, "asset-1")
        self.assertTrue(reused)
        threaded.assert_not_awaited()

    async def test_retry_with_new_nonce_deletes_unreferenced_duplicate_object(self):
        from visual_storage import _insert_asset_idempotently
        pool = types.SimpleNamespace(
            fetchval=AsyncMock(return_value=None),
            fetchrow=AsyncMock(return_value={"id": "asset-1", "object_key": "workspace/command/0/old.png"}),
        )
        client = types.SimpleNamespace(delete_object=unittest.mock.Mock(return_value={}))
        with patch("visual_storage.run_in_threadpool", new=AsyncMock(return_value={})) as threaded:
            asset_id, reused = await _insert_asset_idempotently(
                pool, client, workspace_id="workspace", command_id="command",
                sequence_id="sequence", frame_index=0, capture_kind="editor_2d",
                object_key="workspace/command/0/new.png", mime="image/png",
                width=3, height=2, size=78, digest="a" * 64,
                captured_at=None, metadata={},
            )
        self.assertEqual(asset_id, "asset-1")
        self.assertTrue(reused)
        threaded.assert_awaited_once_with(client.delete_object, Bucket="godot-visual-captures", Key="workspace/command/0/new.png")


if __name__ == "__main__":
    unittest.main()
