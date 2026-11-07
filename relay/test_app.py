import os
import unittest
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

    def test_expired_or_unknown_session_is_not_found(self):
        response = self.client.get("/v1/sessions/not-a-real-session")
        self.assertEqual(response.status_code, 404)

if __name__ == "__main__":
    unittest.main()
