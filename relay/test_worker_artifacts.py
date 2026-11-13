from __future__ import annotations
import hashlib
import io
import json
import zipfile
import unittest
from unittest.mock import patch
from starlette.requests import Request
import worker_artifacts
from app import app

class FakeS3:
    def __init__(self): self.objects={}
    def put_object(self,**kwargs): self.objects[(kwargs["Bucket"],kwargs["Key"])]=kwargs["Body"]

def make_request(payload:bytes)->Request:
    async def receive():
        return {"type":"http.request","body":payload,"more_body":False}
    scope={"type":"http","method":"POST","path":"/v1/persistent-sessions/worker-artifacts/test-run","headers":[(b"content-length",str(len(payload)).encode())]}
    return Request(scope,receive)

def make_bundle():
    manifest={"worker_backend":"github-actions-hosted-runner","repository":"owner/game","commit_sha":"a"*40,"task_id":"test-task"}
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("task-result.json",json.dumps(manifest))
        archive.writestr("artifacts/editor.png",b"image")
    return out.getvalue()

class WorkerArtifactTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_artifact_is_validated_and_persisted(self):
        payload=make_bundle(); store=FakeS3()
        async def authorize(_): return None
        with patch.object(worker_artifacts,"_authorize",side_effect=authorize),patch.object(worker_artifacts,"storage_client",return_value=store):
            result=await worker_artifacts.upload_worker_artifact("test-run",make_request(payload),"Bearer test",hashlib.sha256(payload).hexdigest())
        self.assertEqual(result["storage"],"neon-object-storage")
        self.assertEqual(result["commit_sha"],"a"*40)
        self.assertFalse(result["browser_process_persisted"])
        self.assertEqual(len(store.objects),1)

    async def test_worker_artifact_rejects_digest_mismatch(self):
        payload=make_bundle()
        async def authorize(_): return None
        with patch.object(worker_artifacts,"_authorize",side_effect=authorize):
            with self.assertRaises(Exception) as raised:
                await worker_artifacts.upload_worker_artifact("test-run",make_request(payload),"Bearer test","0"*64)
        self.assertEqual(getattr(raised.exception,"status_code",None),400)

    def test_worker_upload_route_is_registered(self):
        paths={getattr(route,"path",None) for route in app.routes}
        self.assertIn("/v1/persistent-sessions/worker-artifacts/{session_id}",paths)
