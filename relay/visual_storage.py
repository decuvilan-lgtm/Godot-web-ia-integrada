"""Private, lease-scoped visual capture transfers to Neon Object Storage."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from command_center import authenticate_device, get_pool

router = APIRouter(prefix="/v1/command-center/visual", tags=["command-center-visual"])
BUCKET = "godot-visual-captures"
MAX_BYTES = 12 * 1024 * 1024
URL_TTL = 180
MIME_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
CAPTURE_KINDS = {"editor_ui", "editor_2d", "editor_3d", "game_preview"}
KEY_RE = re.compile(r"^([0-9a-f-]{36})/([0-9a-f-]{36})/(single|(?:[0-9]|1[0-9]|2[0-3]))/([0-9a-f-]{36})\.(jpg|png|webp)$")


class UploadRequest(BaseModel):
    command_id: str = Field(min_length=36, max_length=36)
    content_type: str
    frame_index: int | None = Field(default=None, ge=0, le=23)


class CompleteRequest(BaseModel):
    object_key: str = Field(min_length=1, max_length=1024)
    width: int = Field(ge=1, le=8192)
    height: int = Field(ge=1, le=8192)
    captured_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AbandonRequest(BaseModel):
    object_key: str = Field(min_length=1, max_length=1024)



def verify_uploaded_object(client, key: str, extension: str, width: int, height: int):
    head = client.head_object(Bucket=BUCKET, Key=key)
    size = int(head.get("ContentLength", 0))
    mime = head.get("ContentType", "")
    if size < 1 or size > MAX_BYTES or mime not in MIME_EXTENSIONS or MIME_EXTENSIONS[mime] != extension:
        raise ValueError("Uploaded object size or MIME type is invalid")
    obj = client.get_object(Bucket=BUCKET, Key=key)
    stream = obj["Body"]
    try:
        data = stream.read(MAX_BYTES + 1)
    finally:
        stream.close()
    if len(data) != size or len(data) > MAX_BYTES:
        raise ValueError("Uploaded object length could not be verified")
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            expected_format = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[mime]
            if image.format != expected_format:
                raise ValueError("Uploaded image format is invalid")
            if image.size != (width, height):
                raise ValueError("Reported dimensions do not match the image")
            if image.width > 8192 or image.height > 8192:
                raise ValueError("Image dimensions exceed the allowed limit")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Uploaded object is not a valid supported image") from exc
    return mime, size, hashlib.sha256(data).hexdigest()


async def _insert_asset_idempotently(
    pool, client, *, workspace_id, command_id, sequence_id, frame_index,
    capture_kind, object_key, mime, width, height, size, digest, captured_at, metadata,
):
    asset_id = await pool.fetchval(
        """INSERT INTO command_center.visual_assets
           (workspace_id, command_id, sequence_id, frame_index, capture_kind,
            object_key, mime_type, width, height, byte_size, sha256, captured_at, metadata)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb)
           ON CONFLICT DO NOTHING
           RETURNING id""",
        workspace_id, command_id, sequence_id, frame_index, capture_kind,
        object_key, mime, width, height, size, digest, captured_at, json.dumps(metadata),
    )
    if asset_id is not None:
        return str(asset_id), False

    existing = await pool.fetchrow(
        """SELECT id, object_key FROM command_center.visual_assets
           WHERE command_id=$1 AND sequence_id IS NOT DISTINCT FROM $2
             AND frame_index IS NOT DISTINCT FROM $3""",
        command_id, sequence_id, frame_index,
    )
    if existing is None:
        raise HTTPException(status_code=409, detail="Capture metadata conflicts with an existing asset")

    # A retried completion can upload a fresh nonce for a frame that is already
    # registered. Keep the original object and remove the unreferenced duplicate.
    if existing["object_key"] != object_key:
        try:
            await run_in_threadpool(client.delete_object, Bucket=BUCKET, Key=object_key)
        except Exception:
            logging.getLogger(__name__).warning(
                "Could not remove duplicate unreferenced visual object for command %s", command_id
            )
    return str(existing["id"]), True


def storage_client():
    required = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ENDPOINT_URL_S3", "AWS_REGION")
    if any(not os.environ.get(key, "").strip() for key in required):
        raise HTTPException(status_code=503, detail={
            "code": "VISUAL_STORAGE_NOT_CONFIGURED",
            "message": "Neon Object Storage credentials are not configured on the relay",
        })
    try:
        import boto3
        from botocore.config import Config
        return boto3.client(
            "s3",
            endpoint_url=os.environ["AWS_ENDPOINT_URL_S3"],
            region_name=os.environ["AWS_REGION"],
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 2}),
        )
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="S3 client dependency is unavailable") from exc


async def leased_visual_command(request: Request, authorization: str | None, command_id: str):
    identity = await authenticate_device(request, authorization)
    if identity["device_kind"] != "web_editor":
        raise HTTPException(status_code=403, detail="Visual uploads are restricted to the AI web editor")
    try:
        parsed_id = uuid.UUID(command_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid command ID") from exc
    pool = await get_pool(request)
    row = await pool.fetchrow(
        """SELECT id, workspace_id, action, args, target, status, claimed_by_device,
                  (claim_expires_at > now()) AS lease_valid
           FROM command_center.commands
           WHERE id=$1 AND workspace_id=$2""",
        parsed_id, identity["workspace_id"],
    )
    if row is None or row["target"] != "web_editor" or row["claimed_by_device"] != identity["id"]:
        raise HTTPException(status_code=404, detail="Visual command not found for this editor")
    if row["status"] != "claimed" or not row["lease_valid"]:
        raise HTTPException(status_code=409, detail="Visual command lease is not active")
    if row["action"] not in {"visual.capture", "visual.capture_sequence", "visual.zoom_to"}:
        raise HTTPException(status_code=403, detail="Command is not a visual capture operation")
    args = row["args"]
    if isinstance(args, str):
        args = json.loads(args)
    return identity, row, args, pool


@router.post("/uploads/abandon", status_code=200)
async def abandon_upload(
    body: AbandonRequest, request: Request,
    authorization: str | None = Header(default=None),
):
    """Delete an unregistered upload owned by the same paired web editor."""
    match = KEY_RE.fullmatch(body.object_key)
    if match is None:
        raise HTTPException(status_code=422, detail="Object key is not a valid relay-issued key")
    workspace_in_key, command_in_key, _frame_in_key, _nonce, _extension = match.groups()

    identity = await authenticate_device(request, authorization)
    if identity["device_kind"] != "web_editor":
        raise HTTPException(status_code=403, detail="Only the paired AI web editor can abandon visual uploads")
    if workspace_in_key != str(identity["workspace_id"]):
        raise HTTPException(status_code=403, detail="Object key belongs to another workspace")

    try:
        command_uuid = uuid.UUID(command_in_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Object key contains an invalid command ID") from exc

    pool = await get_pool(request)
    command = await pool.fetchrow(
        """SELECT id FROM command_center.commands
           WHERE id=$1 AND workspace_id=$2 AND target='web_editor'
             AND claimed_by_device=$3
             AND action IN ('visual.capture', 'visual.capture_sequence', 'visual.zoom_to')""",
        command_uuid, identity["workspace_id"], identity["id"],
    )
    if command is None:
        raise HTTPException(status_code=404, detail="Visual upload does not belong to this editor command")

    referenced = await pool.fetchval(
        "SELECT EXISTS(SELECT 1 FROM command_center.visual_assets WHERE object_key=$1)",
        body.object_key,
    )
    if referenced:
        raise HTTPException(status_code=409, detail="Registered visual assets cannot be abandoned")

    client = storage_client()
    try:
        await run_in_threadpool(client.delete_object, Bucket=BUCKET, Key=body.object_key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Relay could not remove the unregistered visual upload") from exc
    return {"abandoned": True}


@router.post("/uploads/presign", status_code=201)
async def presign_upload(
    body: UploadRequest, request: Request,
    authorization: str | None = Header(default=None),
):
    if body.content_type not in MIME_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Unsupported image MIME type")
    # Authenticate and validate ownership/lease, but never return a direct Neon S3 URL
    # to the browser-based editor. Binary transfers must pass through the relay proxy.
    await leased_visual_command(request, authorization, body.command_id)
    raise HTTPException(
        status_code=410,
        detail="Direct presigned uploads are disabled; use the authenticated relay proxy",
    )


@router.get("/assets/{asset_id}/download")
async def presign_download(
    asset_id: str, request: Request,
    authorization: str | None = Header(default=None),
):
    identity = await authenticate_device(request, authorization)
    if identity["device_kind"] not in {"agent_controller", "web_editor"}:
        raise HTTPException(status_code=403, detail="This device role cannot retrieve visual assets")
    # Keep the legacy route recognizable, but never expose a presigned S3 URL.
    # Authorized downloads must use /content so the relay enforces workspace scope.
    raise HTTPException(
        status_code=410,
        detail="Direct presigned downloads are disabled; use the authenticated relay content endpoint",
    )
