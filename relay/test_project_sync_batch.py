from __future__ import annotations

import hashlib
import io
import json
import sys
import unittest
import uuid
import zipfile
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

REPOSITORY_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from app import app
import project_sync

PROJECT_ID = "11111111-2222-4333-8444-555555555555"
WORKSPACE_ID = "workspace-test"
DEVICE_ID = "device-test"


class FakeTransaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.connection.rolled_back = exc_type is not None
        return False


class FakeConnection:
    def __init__(self, head_revision, existing_rows):
        self.head_revision = head_revision
        self.existing_rows = existing_rows
        self.executions = []
        self.rolled_back = False

    def transaction(self):
        return FakeTransaction(self)

    async def fetchrow(self, query, *args):
        if "FOR UPDATE" in query:
            return {"head_revision": self.head_revision}
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def fetch(self, query, *args):
        return self.existing_rows

    async def execute(self, query, *args):
        self.executions.append((query, args))
        return "OK"


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    async def fetchrow(self, query, *args):
        return {
            "id": uuid.UUID(PROJECT_ID),
            "workspace_id": WORKSPACE_ID,
            "slug": "fixture",
            "display_name": "Fixture",
            "head_revision": self.connection.head_revision,
        }

    def acquire(self):
        return FakeAcquire(self.connection)


def make_archive(base_revision: int) -> bytes:
    original = b"old project data"
    updated = b"new project data"
    added = b"\x00Godot\xfffixture"
    manifest = {
        "base_revision": base_revision,
        "files": [
            {
                "path": "data/existing.bin",
                "byte_size": len(updated),
                "sha256": hashlib.sha256(updated).hexdigest(),
                "mime_type": "application/octet-stream",
                "base_sha256": hashlib.sha256(original).hexdigest(),
            },
            {
                "path": "assets/new.bin",
                "byte_size": len(added),
                "sha256": hashlib.sha256(added).hexdigest(),
                "mime_type": "application/octet-stream",
                "base_sha256": None,
            },
        ],
        "deletes": [],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("files/data/existing.bin", updated)
        archive.writestr("files/assets/new.bin", added)
    return buffer.getvalue()


class ProjectBatchAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.identity = {
            "id": DEVICE_ID,
            "workspace_id": WORKSPACE_ID,
            "device_kind": "agent_controller",
        }
        self.original_sha = hashlib.sha256(b"old project data").hexdigest()

    def test_batch_commits_all_files_and_one_revision_transaction(self):
        connection = FakeConnection(
            5, [{"path": "data/existing.bin", "sha256": self.original_sha}]
        )
        pool = FakePool(connection)
        with patch("project_sync.authenticate_device", new=AsyncMock(return_value=self.identity)), \
             patch("project_sync.get_pool", new=AsyncMock(return_value=pool)), \
             patch("project_sync._store_bytes", new=AsyncMock()) as store:
            response = self.client.post(
                f"/v1/command-center/projects/{PROJECT_ID}/batch",
                content=make_archive(5),
                headers={
                    "Authorization": "Bearer test-token",
                    "Content-Type": "application/zip",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["atomic"])
        self.assertEqual(payload["base_revision"], 5)
        self.assertEqual(payload["head_revision"], 7)
        self.assertEqual(len(payload["operations"]), 2)
        self.assertEqual(store.await_count, 2)
        self.assertEqual(len(connection.executions), 5)
        self.assertFalse(connection.rolled_back)

    def test_revision_conflict_rolls_back_without_manifest_writes(self):
        connection = FakeConnection(
            6, [{"path": "data/existing.bin", "sha256": self.original_sha}]
        )
        pool = FakePool(connection)
        with patch("project_sync.authenticate_device", new=AsyncMock(return_value=self.identity)), \
             patch("project_sync.get_pool", new=AsyncMock(return_value=pool)), \
             patch("project_sync._store_bytes", new=AsyncMock()):
            response = self.client.post(
                f"/v1/command-center/projects/{PROJECT_ID}/batch",
                content=make_archive(5),
                headers={
                    "Authorization": "Bearer test-token",
                    "Content-Type": "application/zip",
                },
            )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(connection.executions, [])
        self.assertTrue(connection.rolled_back)

    def test_invalid_payload_hash_is_rejected_before_storage_or_transaction(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr("manifest.json", json.dumps({
                "base_revision": 5,
                "files": [{
                    "path": "assets/bad.bin",
                    "byte_size": 3,
                    "sha256": "0" * 64,
                    "mime_type": "application/octet-stream",
                    "base_sha256": None,
                }],
                "deletes": [],
            }))
            zf.writestr("files/assets/bad.bin", b"bad")
        connection = FakeConnection(5, [])
        pool = FakePool(connection)
        with patch("project_sync.authenticate_device", new=AsyncMock(return_value=self.identity)), \
             patch("project_sync.get_pool", new=AsyncMock(return_value=pool)), \
             patch("project_sync._store_bytes", new=AsyncMock()) as store:
            response = self.client.post(
                f"/v1/command-center/projects/{PROJECT_ID}/batch",
                content=archive.getvalue(),
                headers={
                    "Authorization": "Bearer test-token",
                    "Content-Type": "application/zip",
                },
            )

        self.assertEqual(response.status_code, 422, response.text)
        store.assert_not_awaited()
        self.assertEqual(connection.executions, [])


    def test_file_base_hash_conflict_rolls_back_the_entire_batch(self):
        remote_sha = hashlib.sha256(b"remote edit").hexdigest()
        connection = FakeConnection(5, [{"path": "data/existing.bin", "sha256": remote_sha}])
        pool = FakePool(connection)
        with patch("project_sync.authenticate_device", new=AsyncMock(return_value=self.identity)), \
             patch("project_sync.get_pool", new=AsyncMock(return_value=pool)), \
             patch("project_sync._store_bytes", new=AsyncMock()) as store:
            response = self.client.post(
                f"/v1/command-center/projects/{PROJECT_ID}/batch",
                content=make_archive(5),
                headers={"Authorization": "Bearer test-token", "Content-Type": "application/zip"},
            )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(connection.executions, [])
        self.assertTrue(connection.rolled_back)
        self.assertEqual(store.await_count, 2)

    def test_delete_operation_commits_as_one_revision(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr("manifest.json", json.dumps({
                "base_revision": 5, "files": [],
                "deletes": [{"path": "data/existing.bin", "base_sha256": self.original_sha}],
            }))
        connection = FakeConnection(5, [{"path": "data/existing.bin", "sha256": self.original_sha}])
        pool = FakePool(connection)
        with patch("project_sync.authenticate_device", new=AsyncMock(return_value=self.identity)), \
             patch("project_sync.get_pool", new=AsyncMock(return_value=pool)), \
             patch("project_sync._store_bytes", new=AsyncMock()) as store:
            response = self.client.post(
                f"/v1/command-center/projects/{PROJECT_ID}/batch",
                content=archive.getvalue(),
                headers={"Authorization": "Bearer test-token", "Content-Type": "application/zip"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["atomic"])
        self.assertEqual(payload["head_revision"], 6)
        self.assertEqual(payload["operations"], [
            {"path": "data/existing.bin", "deleted": True, "revision": 6},
        ])
        self.assertEqual(len(connection.executions), 3)
        self.assertFalse(connection.rolled_back)
        store.assert_not_awaited()

    def test_zip_symlink_entries_are_rejected_before_storage(self):
        archive = io.BytesIO()
        payload = b"link-target"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr("manifest.json", json.dumps({
                "base_revision": 5,
                "files": [{
                    "path": "assets/link.bin", "byte_size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "mime_type": "application/octet-stream", "base_sha256": None,
                }],
                "deletes": [],
            }))
            info = zipfile.ZipInfo("files/assets/link.bin")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            zf.writestr(info, payload)
        connection = FakeConnection(5, [])
        pool = FakePool(connection)
        with patch("project_sync.authenticate_device", new=AsyncMock(return_value=self.identity)), \
             patch("project_sync.get_pool", new=AsyncMock(return_value=pool)), \
             patch("project_sync._store_bytes", new=AsyncMock()) as store:
            response = self.client.post(
                f"/v1/command-center/projects/{PROJECT_ID}/batch",
                content=archive.getvalue(),
                headers={"Authorization": "Bearer test-token", "Content-Type": "application/zip"},
            )
        self.assertEqual(response.status_code, 422, response.text)
        store.assert_not_awaited()
        self.assertEqual(connection.executions, [])


if __name__ == "__main__":
    unittest.main()
