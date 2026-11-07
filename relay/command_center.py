"""Neon-backed device pairing and durable command queue for the Godot relay.

The API is deliberately separate from the legacy ephemeral WebSocket sessions.
It fails closed when COMMAND_CENTER_DATABASE_URL is not configured.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import hmac
import json
import math
import os
import secrets
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/command-center", tags=["command-center"])

DEVICE_KINDS = {"android_editor", "web_editor", "agent_controller"}
EDITOR_KINDS = {"android_editor", "web_editor"}
READ_ONLY_ACTIONS = {
    "ping",
    "project.get_state",
    "project.list_files",
    "scene.inspect",
    "script.read",
}
VISUAL_ACTIONS = {
    "visual.capture",
    "visual.capture_sequence",
    "visual.zoom_to",
}
ALLOWED_ACTIONS = READ_ONLY_ACTIONS | VISUAL_ACTIONS
# Keep visual commands rejected until signed storage transfer and real capture
# backends are implemented and verified end-to-end.
VISUAL_COMMANDS_ENABLED = False
VISUAL_TARGETS = {"editor_ui", "editor_2d", "editor_3d", "game_preview"}
VISUAL_SEQUENCE_TARGETS = VISUAL_TARGETS
VISUAL_COORDINATE_SPACES = {
    "world_2d", "world_3d", "viewport_pixels", "viewport_normalized"
}
MAX_IDEMPOTENCY_KEY = 128
MAX_ARGS_BYTES = 256 * 1024
MAX_RESULT_BYTES = 1024 * 1024
MAX_LABEL = 80
logger = logging.getLogger("godot_web_ia_relay.command_center")
MAX_INSTALLATION_ID = 128
CLAIM_SECONDS = 45


class PairingCodeRequest(BaseModel):
    device_kind: Literal["android_editor", "web_editor", "agent_controller"]
    workspace: str = Field(default="default", min_length=1, max_length=80)


class PairDeviceRequest(BaseModel):
    pairing_code: str = Field(min_length=24, max_length=128)
    label: str = Field(min_length=1, max_length=MAX_LABEL)
    installation_id: str = Field(min_length=8, max_length=MAX_INSTALLATION_ID)


class CreateCommandRequest(BaseModel):
    target: Literal["android_editor", "web_editor"]
    action: str = Field(min_length=1, max_length=80)
    args: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=MAX_IDEMPOTENCY_KEY)


class CommandResultRequest(BaseModel):
    ok: bool
    result: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)


def digest_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def decode_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
    return value


def json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return MAX_ARGS_BYTES + 1


def _visual_error(code: str, message: str) -> None:
    raise HTTPException(status_code=422, detail={"code": code, "message": message})


def _strict_keys(value: dict[str, Any], allowed: set[str], required: set[str], code: str) -> None:
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        _visual_error(code, f"Unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        _visual_error(code, f"Missing required fields: {', '.join(sorted(missing))}")


def _bounded_int(value: Any, minimum: int, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_visual_output(output: Any) -> None:
    if not isinstance(output, dict):
        _visual_error("VISUAL_OUTPUT_INVALID", "output must be an object")
    _strict_keys(
        output,
        {"format", "max_width", "max_height", "quality"},
        set(),
        "VISUAL_OUTPUT_INVALID",
    )
    if "format" in output and output["format"] not in {"jpeg", "webp", "png"}:
        _visual_error("VISUAL_OUTPUT_INVALID", "format must be jpeg, webp or png")
    for key in ("max_width", "max_height"):
        if key in output and not _bounded_int(output[key], 320, 8192):
            _visual_error("VISUAL_OUTPUT_INVALID", f"{key} must be an integer from 320 to 8192")
    if "quality" in output:
        if not _bounded_int(output["quality"], 40, 100):
            _visual_error("VISUAL_OUTPUT_INVALID", "quality must be an integer from 40 to 100")
        if output.get("format") == "png":
            _visual_error("VISUAL_OUTPUT_INVALID", "quality is not valid for PNG output")


def _validate_visual_viewport(args: dict[str, Any], target: str) -> None:
    if "viewport_index" in args:
        if target != "editor_3d":
            _visual_error("VISUAL_TARGET_MISMATCH", "viewport_index is only valid for editor_3d")
        if not _bounded_int(args["viewport_index"], 0, 7):
            _visual_error("VISUAL_ARGUMENT_INVALID", "viewport_index must be an integer from 0 to 7")


def validate_visual_command(action: str, args: dict[str, Any]) -> None:
    """Validate the canonical visual command contract before it can enter Neon."""
    if not isinstance(args, dict):
        _visual_error("VISUAL_ARGUMENT_INVALID", "Visual command args must be an object")

    if action == "visual.capture":
        _strict_keys(
            args,
            {"target", "viewport_index", "output", "include_metadata"},
            {"target"},
            "VISUAL_ARGUMENT_INVALID",
        )
        target = args["target"]
        if target not in VISUAL_TARGETS:
            _visual_error("VISUAL_TARGET_REQUIRED", "target must identify one supported visual source")
        _validate_visual_viewport(args, target)
        if "output" in args:
            _validate_visual_output(args["output"])
        if "include_metadata" in args and not isinstance(args["include_metadata"], bool):
            _visual_error("VISUAL_ARGUMENT_INVALID", "include_metadata must be boolean")
        return

    if action == "visual.capture_sequence":
        _strict_keys(
            args,
            {
                "target", "viewport_index", "frames", "interval_ms", "timing_mode",
                "output", "include_metadata", "include_contact_sheet",
            },
            {"target", "frames", "interval_ms"},
            "VISUAL_ARGUMENT_INVALID",
        )
        target = args["target"]
        if target not in VISUAL_SEQUENCE_TARGETS:
            _visual_error("VISUAL_TARGET_REQUIRED", "target must identify one supported visual source")
        _validate_visual_viewport(args, target)
        if not _bounded_int(args["frames"], 2, 24):
            _visual_error("VISUAL_SEQUENCE_LIMIT", "frames must be an integer from 2 to 24")
        if not _bounded_int(args["interval_ms"], 50, 5000):
            _visual_error("VISUAL_SEQUENCE_LIMIT", "interval_ms must be an integer from 50 to 5000")
        if args.get("timing_mode", "realtime") != "realtime":
            _visual_error("VISUAL_TIMING_UNAVAILABLE", "Only realtime timing is currently supported")
        if "output" in args:
            _validate_visual_output(args["output"])
        for key in ("include_metadata", "include_contact_sheet"):
            if key in args and not isinstance(args[key], bool):
                _visual_error("VISUAL_ARGUMENT_INVALID", f"{key} must be boolean")
        return

    if action == "visual.zoom_to":
        _strict_keys(
            args,
            {"target", "viewport_index", "focus", "restore_view", "output"},
            {"target", "focus", "restore_view"},
            "VISUAL_ARGUMENT_INVALID",
        )
        target = args["target"]
        if target not in {"editor_2d", "editor_3d"}:
            _visual_error("VISUAL_TARGET_MISMATCH", "zoom_to supports only editor_2d or editor_3d")
        _validate_visual_viewport(args, target)
        if args["restore_view"] is not True:
            _visual_error("VISUAL_RESTORE_REQUIRED", "restore_view must be true")
        focus = args["focus"]
        if not isinstance(focus, dict):
            _visual_error("VISUAL_COORDINATE_SPACE_REQUIRED", "focus must be an object")
        _strict_keys(
            focus,
            {"coordinate_space", "position", "zoom", "distance"},
            {"coordinate_space", "position"},
            "VISUAL_ARGUMENT_INVALID",
        )
        space = focus["coordinate_space"]
        if space not in VISUAL_COORDINATE_SPACES:
            _visual_error("VISUAL_COORDINATE_SPACE_REQUIRED", "coordinate_space is missing or unsupported")
        if space == "world_2d" and target != "editor_2d":
            _visual_error("VISUAL_COORDINATE_MISMATCH", "world_2d coordinates require editor_2d")
        if space == "world_3d" and target != "editor_3d":
            _visual_error("VISUAL_COORDINATE_MISMATCH", "world_3d coordinates require editor_3d")
        position = focus["position"]
        expected_length = 3 if space == "world_3d" else 2
        if (
            not isinstance(position, list)
            or len(position) != expected_length
            or not all(_finite_number(value) for value in position)
        ):
            _visual_error("VISUAL_COORDINATE_MISMATCH", f"{space} position must contain {expected_length} finite numbers")
        if space == "viewport_normalized" and any(value < 0 or value > 1 for value in position):
            _visual_error("VISUAL_COORDINATE_MISMATCH", "normalized viewport coordinates must be between 0 and 1")
        if space == "viewport_pixels" and any(value < 0 for value in position):
            _visual_error("VISUAL_COORDINATE_MISMATCH", "viewport pixel coordinates cannot be negative")
        if space == "world_2d":
            if "zoom" not in focus or not _finite_number(focus["zoom"]) or not 0.25 <= focus["zoom"] <= 16:
                _visual_error("VISUAL_ARGUMENT_INVALID", "world_2d focus requires zoom between 0.25 and 16")
            if "distance" in focus:
                _visual_error("VISUAL_ARGUMENT_INVALID", "distance is not valid for world_2d")
        elif space == "world_3d":
            if "distance" not in focus or not _finite_number(focus["distance"]) or not 0.1 <= focus["distance"] <= 1000:
                _visual_error("VISUAL_ARGUMENT_INVALID", "world_3d focus requires distance between 0.1 and 1000")
            if "zoom" in focus:
                _visual_error("VISUAL_ARGUMENT_INVALID", "zoom is not valid for world_3d")
        elif "zoom" in focus or "distance" in focus:
            _visual_error("VISUAL_ARGUMENT_INVALID", "zoom/distance are not valid for viewport coordinate focus")
        if "output" in args:
            _validate_visual_output(args["output"])
        return

    _visual_error("VISUAL_ACTION_UNKNOWN", "Unknown visual command")


async def get_pool(request: Request):
    """Return the Neon pool, reconnecting lazily after startup or transient outages."""
    pool = getattr(request.app.state, "command_center_db", None)
    if pool is not None:
        return pool

    database_url = os.environ.get("COMMAND_CENTER_DATABASE_URL", "").strip()
    if not database_url:
        raise HTTPException(status_code=503, detail="Neon Command Center database is not configured")
    if time.monotonic() < getattr(request.app.state, "command_center_db_retry_after", 0.0):
        raise HTTPException(status_code=503, detail="Neon Command Center database is temporarily unavailable")

    lock = getattr(request.app.state, "command_center_db_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.command_center_db_lock = lock

    async with lock:
        pool = getattr(request.app.state, "command_center_db", None)
        if pool is not None:
            return pool
        if time.monotonic() < getattr(request.app.state, "command_center_db_retry_after", 0.0):
            raise HTTPException(status_code=503, detail="Neon Command Center database is temporarily unavailable")
        try:
            import asyncpg
            pool = await asyncpg.create_pool(
                dsn=database_url, min_size=1, max_size=5, timeout=5, command_timeout=10
            )
            request.app.state.command_center_db = pool
            request.app.state.command_center_db_retry_after = 0.0
            logger.info("Neon Command Center database pool connected")
            return pool
        except Exception as exc:
            request.app.state.command_center_db_retry_after = time.monotonic() + 5.0
            logger.warning("Neon Command Center lazy connection failed: %s", type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail="Neon Command Center database is temporarily unavailable",
            ) from exc


def require_admin(supplied: str | None) -> None:
    expected = os.environ.get("COMMAND_CENTER_ADMIN_TOKEN", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="Command Center administrator credential required")


async def authenticate_device(request: Request, authorization: str | None):
    if not authorization:
        raise HTTPException(status_code=401, detail="Bearer device credential required")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token or len(token) > 512:
        raise HTTPException(status_code=401, detail="Bearer device credential required")
    pool = await get_pool(request)
    row = await pool.fetchrow(
        """SELECT id, workspace_id, device_kind, label
           FROM command_center.devices
           WHERE token_hash=$1 AND revoked_at IS NULL""",
        digest_secret(token),
    )
    if row is None:
        raise HTTPException(status_code=401, detail="Device credential is invalid or revoked")
    await pool.execute(
        """UPDATE command_center.devices SET last_seen_at=now()
           WHERE id=$1 AND (last_seen_at IS NULL OR last_seen_at < now() - interval '30 seconds')""",
        row["id"],
    )
    return row


@router.post("/pairing-codes", status_code=201)
async def create_pairing_code(
    body: PairingCodeRequest,
    request: Request,
    x_command_center_admin: str | None = Header(default=None, alias="X-Command-Center-Admin"),
):
    require_admin(x_command_center_admin)
    pool = await get_pool(request)
    workspace_id = await pool.fetchval(
        "SELECT id FROM command_center.workspaces WHERE slug=$1",
        body.workspace,
    )
    if workspace_id is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    code = secrets.token_urlsafe(24)
    await pool.execute(
        """INSERT INTO command_center.pairing_codes
           (workspace_id, code_hash, device_kind, expires_at)
           VALUES ($1,$2,$3,now() + interval '2 minutes')""",
        workspace_id,
        digest_secret(code),
        body.device_kind,
    )
    return {
        "pairing_code": code,
        "device_kind": body.device_kind,
        "workspace": body.workspace,
        "expires_in_seconds": 120,
    }


@router.post("/pair", status_code=201)
async def pair_device(body: PairDeviceRequest, request: Request):
    if not body.label.strip():
        raise HTTPException(status_code=422, detail="Device label cannot be blank")
    pool = await get_pool(request)
    credential = secrets.token_urlsafe(48)
    async with pool.acquire() as connection:
        async with connection.transaction():
            pairing = await connection.fetchrow(
                """SELECT id, workspace_id, device_kind
                   FROM command_center.pairing_codes
                   WHERE code_hash=$1 AND consumed_at IS NULL AND expires_at > now()
                   FOR UPDATE""",
                digest_secret(body.pairing_code),
            )
            if pairing is None:
                raise HTTPException(status_code=401, detail="Pairing code expired, used or invalid")
            device_id = await connection.fetchval(
                """INSERT INTO command_center.devices
                   (workspace_id, device_kind, label, installation_id, token_hash, last_seen_at, revoked_at)
                   VALUES ($1,$2,$3,$4,$5,now(),NULL)
                   ON CONFLICT (workspace_id, installation_id)
                   DO UPDATE SET device_kind=EXCLUDED.device_kind,
                                 label=EXCLUDED.label,
                                 token_hash=EXCLUDED.token_hash,
                                 last_seen_at=now(),
                                 revoked_at=NULL
                   RETURNING id""",
                pairing["workspace_id"],
                pairing["device_kind"],
                body.label.strip(),
                body.installation_id,
                digest_secret(credential),
            )
            await connection.execute(
                """UPDATE command_center.pairing_codes
                   SET consumed_at=now(), consumed_by_device=$2 WHERE id=$1""",
                pairing["id"],
                device_id,
            )
            await connection.execute(
                """INSERT INTO command_center.events
                   (workspace_id, actor_device_id, event_type, payload)
                   VALUES ($1,$2,'device.paired',$3::jsonb)""",
                pairing["workspace_id"],
                device_id,
                json.dumps({"device_kind": pairing["device_kind"], "label": body.label.strip()}),
            )
    return {
        "device_id": str(device_id),
        "device_kind": pairing["device_kind"],
        "device_credential": credential,
        "token_type": "Bearer",
    }


@router.post("/commands", status_code=202)
async def create_command(
    body: CreateCommandRequest,
    request: Request,
    authorization: str | None = Header(default=None),
):
    identity = await authenticate_device(request, authorization)
    if identity["device_kind"] != "agent_controller":
        raise HTTPException(status_code=403, detail="Only an agent controller can enqueue commands")
    if body.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail="Action is not enabled in the command policy")
    if body.action in VISUAL_ACTIONS:
        if body.target != "web_editor":
            raise HTTPException(status_code=403, detail="Visual commands are restricted to the AI web_editor workspace")
        validate_visual_command(body.action, body.args)
        if not VISUAL_COMMANDS_ENABLED:
            raise HTTPException(
                status_code=503,
                detail={"code": "VISUAL_PIPELINE_NOT_READY", "message": "Visual capture is not enabled until storage transfer and capture backends pass end-to-end tests"},
            )
    if json_size(body.args) > MAX_ARGS_BYTES:
        raise HTTPException(status_code=413, detail="Command arguments exceed the size limit")
    pool = await get_pool(request)
    async with pool.acquire() as connection:
        async with connection.transaction():
            command_id = await connection.fetchval(
                """INSERT INTO command_center.commands
                   (workspace_id, origin_device_id, target, action, args, idempotency_key, expires_at)
                   VALUES ($1,$2,$3,$4,$5::jsonb,$6,now() + interval '2 minutes')
                   ON CONFLICT (workspace_id,idempotency_key) DO NOTHING
                   RETURNING id""",
                identity["workspace_id"],
                identity["id"],
                body.target,
                body.action,
                json.dumps(body.args),
                body.idempotency_key,
            )
            if command_id is None:
                existing = await connection.fetchrow(
                    """SELECT id,target,action,args,status FROM command_center.commands
                       WHERE workspace_id=$1 AND idempotency_key=$2""",
                    identity["workspace_id"],
                    body.idempotency_key,
                )
                if existing is None:
                    raise HTTPException(status_code=409, detail="Idempotency key collision; retry with a new key")
                if (
                    existing["target"] != body.target
                    or existing["action"] != body.action
                    or decode_json(existing["args"]) != body.args
                ):
                    raise HTTPException(status_code=409, detail="Idempotency key was already used for a different command")
                return {
                    "command_id": str(existing["id"]),
                    "target": existing["target"],
                    "action": existing["action"],
                    "status": existing["status"],
                    "reused": True,
                }
            await connection.execute(
                """INSERT INTO command_center.events
                   (workspace_id, actor_device_id, event_type, payload)
                   VALUES ($1,$2,'command.queued',$3::jsonb)""",
                identity["workspace_id"],
                identity["id"],
                json.dumps({"command_id": str(command_id), "target": body.target, "action": body.action}),
            )
    return {"command_id": str(command_id), "status": "queued"}


@router.get("/commands/next")
async def claim_next_command(
    request: Request,
    target: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    identity = await authenticate_device(request, authorization)
    target = target or identity["device_kind"]
    if target not in EDITOR_KINDS or target != identity["device_kind"]:
        raise HTTPException(status_code=403, detail="A device can only claim commands for its own editor role")
    pool = await get_pool(request)
    async with pool.acquire() as connection:
        async with connection.transaction():
            expired_rows = await connection.fetch(
                """UPDATE command_center.commands
                   SET status='expired', finished_at=now(), claim_expires_at=NULL
                   WHERE workspace_id=$1 AND target=$2
                     AND status IN ('queued','claimed')
                     AND (
                       (expires_at IS NOT NULL AND expires_at <= now())
                       OR (status='claimed' AND claim_expires_at IS NOT NULL
                           AND claim_expires_at <= now() AND attempt_count >= 5)
                     )
                   RETURNING id""",
                identity["workspace_id"],
                target,
            )
            for expired in expired_rows:
                await connection.execute(
                    """INSERT INTO command_center.events
                       (workspace_id, actor_device_id, event_type, payload)
                       VALUES ($1,$2,'command.expired',$3::jsonb)""",
                    identity["workspace_id"],
                    identity["id"],
                    json.dumps({"command_id": str(expired["id"])}),
                )
            row = await connection.fetchrow(
                """WITH candidate AS (
                     SELECT id FROM command_center.commands
                     WHERE workspace_id=$1 AND target=$2
                       AND expires_at > now()
                       AND (status='queued' OR
                            (status='claimed' AND claim_expires_at IS NOT NULL AND claim_expires_at < now()))
                       AND attempt_count < 5
                     ORDER BY priority DESC, created_at ASC
                     FOR UPDATE SKIP LOCKED LIMIT 1
                   )
                   UPDATE command_center.commands c
                   SET status='claimed', claimed_at=now(), claimed_by_device=$3,
                       claim_expires_at=now() + ($4::text || ' seconds')::interval,
                       attempt_count=attempt_count+1
                   FROM candidate WHERE c.id=candidate.id
                   RETURNING c.id,c.action,c.args,c.priority,c.expires_at,c.attempt_count""",
                identity["workspace_id"],
                target,
                identity["id"],
                CLAIM_SECONDS,
            )
            if row is None:
                return {"command": None}
            await connection.execute(
                """INSERT INTO command_center.events
                   (workspace_id, actor_device_id, event_type, payload)
                   VALUES ($1,$2,'command.claimed',$3::jsonb)""",
                identity["workspace_id"],
                identity["id"],
                json.dumps({"command_id": str(row["id"]), "attempt": row["attempt_count"]}),
            )
    return {
        "command": {
            "id": str(row["id"]),
            "action": row["action"],
            "args": decode_json(row["args"]),
            "priority": row["priority"],
            "expires_at": row["expires_at"].isoformat(),
            "attempt": row["attempt_count"],
        }
    }


@router.post("/commands/{command_id}/result")
async def submit_command_result(
    command_id: str,
    body: CommandResultRequest,
    request: Request,
    authorization: str | None = Header(default=None),
):
    identity = await authenticate_device(request, authorization)
    if identity["device_kind"] not in EDITOR_KINDS:
        raise HTTPException(status_code=403, detail="Only an editor device can submit command results")
    try:
        parsed_id = uuid.UUID(command_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid command ID")
    if json_size(body.result) > MAX_RESULT_BYTES:
        raise HTTPException(status_code=413, detail="Command result exceeds the size limit")
    pool = await get_pool(request)
    async with pool.acquire() as connection:
        async with connection.transaction():
            command = await connection.fetchrow(
                """SELECT id,workspace_id,status,target,claimed_by_device,
                          (claim_expires_at > now()) AS lease_valid
                   FROM command_center.commands
                   WHERE id=$1 AND workspace_id=$2 FOR UPDATE""",
                parsed_id,
                identity["workspace_id"],
            )
            if command is None:
                raise HTTPException(status_code=404, detail="Command not found")
            if command["target"] != identity["device_kind"] or command["claimed_by_device"] != identity["id"]:
                raise HTTPException(status_code=409, detail="Command is not leased to this device")
            existing = await connection.fetchrow(
                "SELECT ok,result FROM command_center.command_results WHERE command_id=$1",
                parsed_id,
            )
            if existing is not None:
                return {
                    "command_id": str(parsed_id),
                    "ok": existing["ok"],
                    "result": decode_json(existing["result"]),
                    "reused": True,
                }
            if command["status"] != "claimed" or not command["lease_valid"]:
                raise HTTPException(status_code=409, detail="Command lease expired; claim it again")
            status = "succeeded" if body.ok else "failed"
            await connection.execute(
                """INSERT INTO command_center.command_results
                   (command_id,ok,result,duration_ms) VALUES ($1,$2,$3::jsonb,$4)""",
                parsed_id,
                body.ok,
                json.dumps(body.result),
                body.duration_ms,
            )
            await connection.execute(
                """UPDATE command_center.commands
                   SET status=$2, finished_at=now(), claim_expires_at=NULL
                   WHERE id=$1""",
                parsed_id,
                status,
            )
            await connection.execute(
                """INSERT INTO command_center.events
                   (workspace_id, actor_device_id, event_type, payload)
                   VALUES ($1,$2,'command.completed',$3::jsonb)""",
                identity["workspace_id"],
                identity["id"],
                json.dumps({"command_id": str(parsed_id), "status": status}),
            )
    return {"command_id": str(parsed_id), "status": status, "ok": body.ok}


@router.get("/commands/{command_id}")
async def get_command(
    command_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    identity = await authenticate_device(request, authorization)
    try:
        parsed_id = uuid.UUID(command_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid command ID")
    pool = await get_pool(request)
    row = await pool.fetchrow(
        """SELECT c.id,c.target,c.action,c.status,c.created_at,c.finished_at,
                  r.ok,r.result,r.error_code,r.error_message,r.duration_ms
           FROM command_center.commands c
           LEFT JOIN command_center.command_results r ON r.command_id=c.id
           WHERE c.id=$1 AND c.workspace_id=$2
             AND ($3='agent_controller' OR c.target=$3 OR c.origin_device_id=$4)""",
        parsed_id,
        identity["workspace_id"],
        identity["device_kind"],
        identity["id"],
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Command not found")
    return {
        "command_id": str(row["id"]),
        "target": row["target"],
        "action": row["action"],
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "ok": row["ok"],
        "result": decode_json(row["result"]),
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "duration_ms": row["duration_ms"],
    }
