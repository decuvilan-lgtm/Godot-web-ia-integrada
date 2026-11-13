from __future__ import annotations
import hashlib, hmac, io, json, re, secrets, zipfile
from fastapi import APIRouter, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from persistent_sessions import MAX_ARTIFACT_BYTES, BUCKET, _authorize, _persistent_artifact_key, storage_client

router=APIRouter(prefix="/v1/persistent-sessions",tags=["persistent-session-worker"])

@router.post("/worker-artifacts/{session_id}")
async def upload_worker_artifact(session_id:str,request:Request,authorization:str|None=Header(default=None),x_artifact_sha256:str|None=Header(default=None)):
    """Accept a ZIP produced by Chromium running on a GitHub-hosted worker."""
    await _authorize(authorization)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",session_id):
        raise HTTPException(status_code=400,detail="Invalid worker session ID")
    length=int(request.headers.get("content-length","0") or 0)
    if length<1 or length>MAX_ARTIFACT_BYTES:
        raise HTTPException(status_code=413,detail="Worker evidence must be between 1 byte and 32 MiB")
    payload=await request.body()
    if len(payload)!=length or len(payload)>MAX_ARTIFACT_BYTES:
        raise HTTPException(status_code=413,detail="Worker evidence size is invalid")
    digest=hashlib.sha256(payload).hexdigest()
    if not x_artifact_sha256 or not re.fullmatch(r"[0-9a-f]{64}",x_artifact_sha256) or not hmac.compare_digest(digest,x_artifact_sha256):
        raise HTTPException(status_code=400,detail="Worker evidence SHA-256 is invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if archive.testzip() is not None or "task-result.json" not in archive.namelist(): raise ValueError("Invalid ZIP")
            if archive.getinfo("task-result.json").file_size>1024*1024: raise ValueError("Manifest too large")
            manifest=json.loads(archive.read("task-result.json").decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400,detail="Evidence must be a valid ZIP containing task-result.json") from exc
    if not isinstance(manifest,dict) or manifest.get("worker_backend")!="github-actions-hosted-runner":
        raise HTTPException(status_code=400,detail="Evidence is not from the authorized browser worker")
    repository=manifest.get("repository"); sha=manifest.get("commit_sha")
    if not isinstance(repository,str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",repository):
        raise HTTPException(status_code=400,detail="Evidence repository metadata is invalid")
    if not isinstance(sha,str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})",sha):
        raise HTTPException(status_code=400,detail="Evidence commit SHA is invalid")
    artifact_id=secrets.token_urlsafe(18); key=_persistent_artifact_key(session_id,artifact_id)
    try:
        await run_in_threadpool(storage_client().put_object,Bucket=BUCKET,Key=key,Body=payload,ContentType="application/zip",Metadata={"sha256":digest,"repository":repository[:200],"commit-sha":sha,"worker":"github-actions"})
    except Exception as exc:
        raise HTTPException(status_code=503,detail="Worker evidence could not be persisted in Neon Object Storage") from exc
    return {"state":"completed","session_id":session_id,"artifact_id":artifact_id,"artifact_url":f"/v1/persistent-sessions/{session_id}/artifacts/{artifact_id}","artifact_bytes":len(payload),"artifact_sha256":digest,"storage":"neon-object-storage","repository":repository,"commit_sha":sha,"browser_backend":"github-actions-hosted-runner","browser_process_persisted":False}

