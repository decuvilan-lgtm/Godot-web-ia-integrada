from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import app
from agent_github_bridge import (
    OIDC_ISSUER,
    TRUSTED_REPOSITORY,
    TRUSTED_REPOSITORY_ID,
    TRUSTED_OWNER_ID,
    TRUSTED_ACTOR_ID,
    TRUSTED_WORKFLOW,
    validate_github_claims,
)


def valid_claims() -> dict:
    return {
        "iss": OIDC_ISSUER,
        "aud": "godot-relay-agent-bridge",
        "repository": TRUSTED_REPOSITORY,
        "repository_id": TRUSTED_REPOSITORY_ID,
        "repository_owner_id": TRUSTED_OWNER_ID,
        "actor_id": TRUSTED_ACTOR_ID,
        "event_name": "push",
        "ref": "refs/heads/agent-transfer/test-task",
        "sub": f"repo:{TRUSTED_REPOSITORY}:ref:refs/heads/agent-transfer/test-task",
        "workflow_ref": f"{TRUSTED_REPOSITORY}/{TRUSTED_WORKFLOW}@refs/heads/agent-transfer/test-task",
        "run_id": "123456",
        "run_attempt": "1",
    }


class FakePool:
    def __init__(self):
        self.calls = []
        self.execute_calls = []

    async def fetchval(self, query, *args):
        self.calls.append((query, args))
        if "FROM command_center.workspaces" in query:
            return "workspace-id"
        if "INSERT INTO command_center.devices" in query:
            return "device-id"
        raise AssertionError("Unexpected fetchval query")

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "UPDATE 1"


class AgentGithubBridgeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_valid_github_claims_are_accepted(self):
        validate_github_claims(valid_claims())

    def test_claim_validation_rejects_untrusted_repository_actor_event_and_ref(self):
        cases = [
            ("repository", "attacker/repo"),
            ("repository_id", "1"),
            ("repository_owner_id", "2"),
            ("actor_id", "3"),
            ("event_name", "pull_request"),
            ("ref", "refs/heads/main"),
            ("sub", "repo:attacker/repo:ref:refs/heads/agent-transfer/test-task"),
            ("workflow_ref", "attacker/repo/.github/workflows/evil.yml@refs/heads/agent-transfer/x"),
            ("run_id", "not-a-run"),
            ("run_attempt", "not-an-attempt"),
        ]
        for key, value in cases:
            with self.subTest(key=key):
                claims = valid_claims()
                claims[key] = value
                with self.assertRaises(HTTPException) as raised:
                    validate_github_claims(claims)
                self.assertIn(raised.exception.status_code, {403})

    def test_exchange_requires_a_bearer_oidc_token(self):
        response = self.client.post("/v1/agent-bridge/github/exchange")
        self.assertEqual(response.status_code, 401)

    def test_exchange_rotates_a_scoped_agent_controller_device_token(self):
        pool = FakePool()
        with patch("agent_github_bridge.decode_github_oidc", new=AsyncMock(return_value=valid_claims())), \
             patch("agent_github_bridge.get_pool", new=AsyncMock(return_value=pool)):
            response = self.client.post(
                "/v1/agent-bridge/github/exchange",
                headers={"Authorization": "Bearer signed-github-oidc-token"},
            )

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.assertEqual(payload["device_kind"], "agent_controller")
        self.assertEqual(payload["token_type"], "Bearer")
        self.assertGreaterEqual(len(payload["access_token"]), 48)
        self.assertEqual(len(pool.calls), 2)
        insert_sql = pool.calls[1][0].lower()
        self.assertIn("on conflict (workspace_id, installation_id)", insert_sql)
        self.assertIn("token_hash", insert_sql)
        self.assertEqual(len(pool.execute_calls), 1)

    def test_revoke_requires_bridge_device_identity(self):
        response = self.client.post("/v1/agent-bridge/github/revoke")
        self.assertEqual(response.status_code, 401)

    def test_revoke_marks_only_the_authenticated_bridge_device(self):
        pool = FakePool()
        identity = {"id": "device-id", "device_kind": "agent_controller",
                    "label": "GitHub Actions binary bridge"}
        with patch("agent_github_bridge.authenticate_device", new=AsyncMock(return_value=identity)), \
             patch("agent_github_bridge.get_pool", new=AsyncMock(return_value=pool)):
            response = self.client.post(
                "/v1/agent-bridge/github/revoke",
                headers={"Authorization": "Bearer bridge-device-token"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["revoked"])
        self.assertIn("revoked_at=now()", pool.execute_calls[0][0])


if __name__ == "__main__":
    unittest.main()
