"""Authenticated proxy transfers for private Neon visual assets.

The browser/editor talks only to this relay. Neon credentials never leave Render.
"""
from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from command_center import authenticate_device, get_pool
from starlette.responses import Response

from visual_storage import (
    BUCKET, CAPTURE_KINDS, MAX_BYTES, MIME_EXTENSIONS,
    leased_visual_command, storage_client,
)

router = APIRouter(prefix="/v1/command-center/visual", tags=["command-center-visual"])


@router.post("/uploads/proxy", status_code=201)
async def proxy_upload(
    request: Request,
    command_id: str = Header(..., alias="X-Command-Id"),
    frame_index: int | None = Header(default=None, alias="X-Frame-Index"),
    authorization: str | None = Header(default=None),
):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in MIME_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported image MIME type")
    if frame_index is not None and not 0 <= frame_index <= 23:
        raise HTTPException(status_code=422, detail="Frame index is outside the allowed range")

    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > MAX_BYTES:
                raise HTTPException(status_code=413, detail="Image exceeds the 12 MiB limit")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="Image exceeds the 12 MiB limit")
    body = bytes(chunks)
    if not body:
        raise HTTPException(status_code=400, detail="Image body is empty")

    identity, command, args, pool = await leased_visual_command(request, authorization, command_id)
    action = command["action"]
    target = args.get("target")
    capture_kind = "zoom_detail" if action == "visual.zoom_to" else target
    if capture_kind not in CAPTURE_KINDS and capture_kind != "zoom_detail":
        raise HTTPException(status_code=422, detail="Visual command target is invalid")

    if action == "visual.capture_sequence":
        frames = args.get("frames")
        if not isinstance(frames, int) or frames < 2 or frames > 24:
            raise HTTPException(status_code=422, detail="Sequence frame count is invalid")
        if frame_index is None or frame_index >= frames:
            raise HTTPException(status_code=422, detail="A valid X-Frame-Index is required")
        sequence_id = await pool.fetchval(
            """INSERT INTO command_center.visual_sequences
               (workspace_id, command_id, source, requested_frames, interval_ms, status, started_at)
               VALUES ($1,$2,$3,$4,$5,'capturing',now())
               ON CONFLICT (command_id) DO UPDATE SET status='capturing'
               RETURNING id""",
            identity["workspace_id"], command["id"], target, frames, args["interval_ms"],
        )
    else:
        if frame_index is not None:
            raise HTTPException(status_code=422, detail="X-Frame-Index is only valid for capture_sequence")
        sequence_id = None

    slot = str(frame_index) if frame_index is not None else "single"
    key = f'{identity["workspace_id"]}/{command["id"]}/{slot}/{uuid.uuid4()}.{MIME_EXTENSIONS[content_type]}'
    client = storage_client()
    try:
        await run_in_threadpool(
            client.put_object,
            Bucket=BUCKET,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Relay could not store the image in private Neon storage") from exc

    return {
        "object_key": key,
        "sequence_id": str(sequence_id) if sequence_id else None,
        "byte_size": len(body),
        "transfer": "relay",
    }


@router.get("/assets/{asset_id}/content")
async def proxy_download(
    asset_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    identity = await authenticate_device(request, authorization)
    if identity["device_kind"] not in {"agent_controller", "web_editor"}:
        raise HTTPException(status_code=403, detail="This device role cannot retrieve visual assets")
    try:
        parsed_id = uuid.UUID(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset ID") from exc

    pool = await get_pool(request)
    row = await pool.fetchrow(
        """SELECT object_key, mime_type, byte_size FROM command_center.visual_assets
           WHERE id=$1 AND workspace_id=$2""",
        parsed_id, identity["workspace_id"],
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Visual asset not found")
    if int(row["byte_size"]) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Stored visual asset exceeds the relay download limit")

    client = storage_client()
    try:
        obj = await run_in_threadpool(client.get_object, Bucket=BUCKET, Key=row["object_key"])
        stream = obj["Body"]
        try:
            data = await run_in_threadpool(stream.read, MAX_BYTES + 1)
        finally:
            await run_in_threadpool(stream.close)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Relay could not retrieve the private Neon asset") from exc
    if len(data) != int(row["byte_size"]) or len(data) > MAX_BYTES:
        raise HTTPException(status_code=502, detail="Stored visual asset failed its size check")

    return Response(
        content=data,
        media_type=row["mime_type"],
        headers={
            "Cache-Control": "no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )
