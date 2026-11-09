"""Authenticated, revisioned project-file sync for paired Godot editors.

All project bytes pass through Render; Neon S3 credentials never reach clients.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import re
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response
from pydantic import BaseModel, Field

from command_center import authenticate_device, get_pool
from visual_storage import BUCKET, storage_client

router = APIRouter(prefix="/v1/command-center/projects", tags=["shared-projects"])
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_FILES = 10000
MAX_PATH_BYTES = 1024
MAX_CHANGES = 2000
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
FORBIDDEN_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = (".pem", ".p12", ".pfx", ".keystore", ".jks", ".mobileprovision")


class CreateProjectRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=64)
    display_name: str = Field(min_length=1, max_length=100)


async def _editor_identity(request: Request, authorization: str | None) -> tuple[dict[str, Any], Any]:
    identity = await authenticate_device(request, authorization)
    if identity["device_kind"] not in {"web_editor", "android_editor"}:
        raise HTTPException(status_code=403, detail="Only paired Godot editors can sync project files")
    return identity, await get_pool(request)


async def _project(pool, project_id: str, workspace_id: str):
    try:
        parsed_id = uuid.UUID(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid project ID") from exc
    row = await pool.fetchrow(
        """SELECT id, workspace_id, slug, display_name, head_revision
           FROM command_center.projects WHERE id=$1 AND workspace_id=$2""",
        parsed_id, workspace_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Shared project not found")
    return row


def validate_project_path(raw: str) -> str:
    if not raw or len(raw.encode("utf-8")) > MAX_PATH_BYTES:
        raise HTTPException(status_code=422, detail="Project path is empty or too long")
    if raw.startswith("/") or "\\\\" in raw or "\x00" in raw or ":" in raw:
        raise HTTPException(status_code=422, detail="Project path must be a relative POSIX path")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise HTTPException(status_code=422, detail="Project path contains an invalid segment")
    lowered = [part.lower() for part in parts]
    if any(part in {".git", ".godot"} for part in lowered):
        raise HTTPException(status_code=422, detail="Git metadata and Godot cache files are not synchronized")
    name = lowered[-1]
    if name in FORBIDDEN_NAMES or name.endswith(FORBIDDEN_SUFFIXES):
        raise HTTPException(status_code=422, detail="Credential and signing files cannot be synchronized")
    if name.endswith(".env") or name.startswith(".env."):
        raise HTTPException(status_code=422, detail="Environment files cannot be synchronized")
    return "/".join(parts)


async def _store_bytes(key: str, data: bytes, content_type: str) -> None:
    client = storage_client()
    try:
        await run_in_threadpool(
            client.put_object, Bucket=BUCKET, Key=key, Body=data, ContentType=content_type
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Relay could not store the project file") from exc


async def _load_bytes(key: str, expected_size: int) -> bytes:
    client = storage_client()
    try:
        obj = await run_in_threadpool(client.get_object, Bucket=BUCKET, Key=key)
        stream = obj["Body"]
        try:
            data = await run_in_threadpool(stream.read, MAX_FILE_BYTES + 1)
        finally:
            await run_in_threadpool(stream.close)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Relay could not retrieve the project file") from exc
    if len(data) != expected_size or len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=502, detail="Stored project file failed its size check")
    return data


@router.get("")
async def list_projects(request: Request, authorization: str | None = Header(default=None)):
    identity, pool = await _editor_identity(request, authorization)
    rows = await pool.fetch(
        """SELECT id, slug, display_name, head_revision, updated_at
           FROM command_center.projects WHERE workspace_id=$1
           ORDER BY updated_at DESC, slug ASC""",
        identity["workspace_id"],
    )
    return {"projects": [
        {"id": str(r["id"]), "slug": r["slug"], "display_name": r["display_name"],
         "head_revision": int(r["head_revision"]), "updated_at": r["updated_at"].isoformat()}
        for r in rows
    ]}


@router.post("", status_code=201)
async def create_project(body: CreateProjectRequest, request: Request,
                         authorization: str | None = Header(default=None)):
    identity, pool = await _editor_identity(request, authorization)
    slug = body.slug.strip().lower()
    name = body.display_name.strip()
    if not SLUG_RE.fullmatch(slug) or not name:
        raise HTTPException(status_code=422, detail="Project slug or display name is invalid")
    try:
        row = await pool.fetchrow(
            """INSERT INTO command_center.projects
               (workspace_id, slug, display_name, created_by_device)
               VALUES ($1,$2,$3,$4)
               ON CONFLICT (workspace_id,slug) DO NOTHING
               RETURNING id, slug, display_name, head_revision""",
            identity["workspace_id"], slug, name, identity["id"],
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not create shared project") from exc
    if row is None:
        raise HTTPException(status_code=409, detail="A project with this slug already exists")
    return {"id": str(row["id"]), "slug": row["slug"],
            "display_name": row["display_name"], "head_revision": int(row["head_revision"])}


@router.get("/{project_id}/manifest")
async def get_manifest(project_id: str, request: Request,
                       authorization: str | None = Header(default=None)):
    identity, pool = await _editor_identity(request, authorization)
    project = await _project(pool, project_id, identity["workspace_id"])
    rows = await pool.fetch(
        """SELECT path, sha256, byte_size, mime_type, revision
           FROM command_center.project_files
           WHERE project_id=$1 AND deleted_at IS NULL
           ORDER BY path ASC LIMIT $2""",
        project["id"], MAX_FILES + 1,
    )
    if len(rows) > MAX_FILES:
        raise HTTPException(status_code=413, detail="Project has too many tracked files")
    return {
        "project": {"id": str(project["id"]), "slug": project["slug"],
                    "display_name": project["display_name"]},
        "head_revision": int(project["head_revision"]),
        "files": [{"path": r["path"], "sha256": r["sha256"], "byte_size": int(r["byte_size"]),
                   "mime_type": r["mime_type"], "revision": int(r["revision"])} for r in rows],
    }


@router.get("/{project_id}/changes")
async def get_changes(project_id: str, request: Request,
                      since_revision: int = Query(default=0, ge=0),
                      authorization: str | None = Header(default=None)):
    identity, pool = await _editor_identity(request, authorization)
    project = await _project(pool, project_id, identity["workspace_id"])
    rows = await pool.fetch(
        """SELECT revision, path, operation, old_sha256, new_sha256, byte_size, mime_type
           FROM command_center.project_changes
           WHERE project_id=$1 AND revision>$2
           ORDER BY revision ASC LIMIT $3""",
        project["id"], since_revision, MAX_CHANGES + 1,
    )
    if len(rows) > MAX_CHANGES:
        raise HTTPException(status_code=413, detail="Change window is too large; fetch a fresh manifest")
    return {
        "head_revision": int(project["head_revision"]),
        "changes": [{"revision": int(r["revision"]), "path": r["path"], "operation": r["operation"],
                     "old_sha256": r["old_sha256"], "new_sha256": r["new_sha256"],
                     "byte_size": int(r["byte_size"]) if r["byte_size"] is not None else None,
                     "mime_type": r["mime_type"]} for r in rows],
    }


@router.post("/{project_id}/files", status_code=201)
async def upload_file(project_id: str, request: Request,
                      path: str = Query(..., min_length=1, max_length=MAX_PATH_BYTES),
                      base_sha256: str | None = Header(default=None, alias="X-Base-SHA256"),
                      file_sha256: str | None = Header(default=None, alias="X-File-SHA256"),
                      authorization: str | None = Header(default=None)):
    identity, pool = await _editor_identity(request, authorization)
    project = await _project(pool, project_id, identity["workspace_id"])
    path = validate_project_path(path)
    if base_sha256 is not None and not SHA_RE.fullmatch(base_sha256):
        raise HTTPException(status_code=422, detail="X-Base-SHA256 must be a lowercase SHA-256 digest")
    if file_sha256 is not None and not SHA_RE.fullmatch(file_sha256):
        raise HTTPException(status_code=422, detail="X-File-SHA256 must be a lowercase SHA-256 digest")
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > MAX_FILE_BYTES:
                raise HTTPException(status_code=413, detail="Project file exceeds the 32 MiB limit")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="Project file exceeds the 32 MiB limit")
    data = bytes(chunks)
    digest = hashlib.sha256(data).hexdigest()
    if file_sha256 and not hmac.compare_digest(digest, file_sha256):
        raise HTTPException(status_code=422, detail="Uploaded file SHA-256 does not match")
    current = await pool.fetchrow(
        """SELECT sha256 FROM command_center.project_files
           WHERE project_id=$1 AND path=$2 AND deleted_at IS NULL""",
        project["id"], path,
    )
    current_sha = current["sha256"] if current else None
    if current_sha != base_sha256:
        raise HTTPException(status_code=409, detail={
            "code": "PROJECT_FILE_CONFLICT", "path": path,
            "expected_base": base_sha256, "remote_sha256": current_sha,
        })
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not content_type or content_type == "application/octet-stream":
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    key = f"projects/{project['workspace_id']}/{project['id']}/{digest}"
    await _store_bytes(key, data, content_type)
    async with pool.acquire() as connection:
        async with connection.transaction():
            locked = await connection.fetchrow(
                "SELECT head_revision FROM command_center.projects WHERE id=$1 AND workspace_id=$2 FOR UPDATE",
                project["id"], identity["workspace_id"],
            )
            if locked is None:
                raise HTTPException(status_code=404, detail="Shared project no longer exists")
            latest = await connection.fetchrow(
                """SELECT sha256 FROM command_center.project_files
                   WHERE project_id=$1 AND path=$2 AND deleted_at IS NULL""",
                project["id"], path,
            )
            latest_sha = latest["sha256"] if latest else None
            if latest_sha != base_sha256:
                raise HTTPException(status_code=409, detail={"code": "PROJECT_FILE_CONFLICT",
                    "path": path, "expected_base": base_sha256, "remote_sha256": latest_sha})
            revision = int(locked["head_revision"]) + 1
            await connection.execute(
                """INSERT INTO command_center.project_files
                   (project_id, path, sha256, byte_size, mime_type, object_key, revision,
                    updated_by_device, deleted_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NULL)
                   ON CONFLICT (project_id,path) DO UPDATE SET sha256=EXCLUDED.sha256,
                    byte_size=EXCLUDED.byte_size, mime_type=EXCLUDED.mime_type,
                    object_key=EXCLUDED.object_key, revision=EXCLUDED.revision,
                    updated_by_device=EXCLUDED.updated_by_device, updated_at=now(), deleted_at=NULL""",
                project["id"], path, digest, len(data), content_type, key, revision, identity["id"],
            )
            await connection.execute(
                """INSERT INTO command_center.project_changes
                   (project_id, revision, path, operation, old_sha256, new_sha256, byte_size, mime_type, actor_device_id)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                project["id"], revision, path, "modify" if current_sha else "add",
                current_sha, digest, len(data), content_type, identity["id"],
            )
            await connection.execute(
                "UPDATE command_center.projects SET head_revision=$2, updated_at=now() WHERE id=$1",
                project["id"], revision,
            )
    return {"project_id": str(project["id"]), "path": path, "sha256": digest,
            "byte_size": len(data), "revision": revision}


@router.post("/{project_id}/files/delete", status_code=200)
async def delete_file(project_id: str, request: Request,
                      path: str = Query(..., min_length=1, max_length=MAX_PATH_BYTES),
                      base_sha256: str = Header(..., alias="X-Base-SHA256"),
                      authorization: str | None = Header(default=None)):
    identity, pool = await _editor_identity(request, authorization)
    project = await _project(pool, project_id, identity["workspace_id"])
    path = validate_project_path(path)
    if not SHA_RE.fullmatch(base_sha256):
        raise HTTPException(status_code=422, detail="X-Base-SHA256 must be a lowercase SHA-256 digest")
    async with pool.acquire() as connection:
        async with connection.transaction():
            locked = await connection.fetchrow(
                "SELECT head_revision FROM command_center.projects WHERE id=$1 AND workspace_id=$2 FOR UPDATE",
                project["id"], identity["workspace_id"],
            )
            current = await connection.fetchrow(
                """SELECT sha256, byte_size, mime_type FROM command_center.project_files
                   WHERE project_id=$1 AND path=$2 AND deleted_at IS NULL FOR UPDATE""",
                project["id"], path,
            )
            if current is None or current["sha256"] != base_sha256:
                raise HTTPException(status_code=409, detail={"code": "PROJECT_FILE_CONFLICT",
                    "path": path, "expected_base": base_sha256,
                    "remote_sha256": current["sha256"] if current else None})
            revision = int(locked["head_revision"]) + 1
            await connection.execute(
                """UPDATE command_center.project_files SET deleted_at=now(), revision=$3,
                   updated_by_device=$4 WHERE project_id=$1 AND path=$2""",
                project["id"], path, revision, identity["id"],
            )
            await connection.execute(
                """INSERT INTO command_center.project_changes
                   (project_id, revision, path, operation, old_sha256, new_sha256, byte_size, mime_type, actor_device_id)
                   VALUES ($1,$2,$3,'delete',$4,NULL,$5,$6,$7)""",
                project["id"], revision, path, current["sha256"], current["byte_size"],
                current["mime_type"], identity["id"],
            )
            await connection.execute(
                "UPDATE command_center.projects SET head_revision=$2, updated_at=now() WHERE id=$1",
                project["id"], revision,
            )
    return {"project_id": str(project["id"]), "path": path, "revision": revision, "deleted": True}


@router.get("/{project_id}/files/content")
async def download_file(project_id: str, request: Request, path: str = Query(..., min_length=1, max_length=MAX_PATH_BYTES),
                        authorization: str | None = Header(default=None)):
    identity, pool = await _editor_identity(request, authorization)
    project = await _project(pool, project_id, identity["workspace_id"])
    path = validate_project_path(path)
    row = await pool.fetchrow(
        """SELECT object_key, sha256, byte_size, mime_type FROM command_center.project_files
           WHERE project_id=$1 AND path=$2 AND deleted_at IS NULL""",
        project["id"], path,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Project file not found")
    data = await _load_bytes(row["object_key"], int(row["byte_size"]))
    if hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise HTTPException(status_code=502, detail="Stored project file failed its SHA-256 check")
    return Response(content=data, media_type=row["mime_type"], headers={
        "Cache-Control": "no-store, max-age=0",
        "X-Content-Type-Options": "nosniff",
        "X-File-SHA256": row["sha256"],
        "Content-Disposition": "attachment",
    })
