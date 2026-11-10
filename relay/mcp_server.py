"""Authenticated Streamable HTTP MCP interface for the Godot Command Center.

The MCP endpoint accepts only paired agent_controller credentials. It shares the
same Neon queue and policy as the HTTP Command Center API; it is not a second queue.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from command_center import (
    ALLOWED_ACTIONS,
    COMMAND_TTL_SECONDS,
    MAX_ARGS_BYTES,
    MAX_IDEMPOTENCY_KEY,
    VISUAL_ACTIONS,
    VISUAL_COMMANDS_ENABLED,
    decode_json,
    digest_secret,
    json_size,
    validate_visual_command,
)

logger = logging.getLogger("godot_web_ia_relay.mcp")
_database_pool = None


def set_database_pool(pool) -> None:
    """Share the existing Command Center pool; MCP never creates a second DB pool."""
    global _database_pool
    _database_pool = pool


def validate_agent_command(action: str, args: dict[str, Any], idempotency_key: str) -> str:
    """Apply the same allowlist and visual contract before an MCP command is queued."""
    if action not in ALLOWED_ACTIONS:
        raise ValueError("Action is not enabled by the Godot Command Center policy")
    if not isinstance(args, dict):
        raise ValueError("Command args must be an object")
    key = idempotency_key.strip() if isinstance(idempotency_key, str) else ""
    if not key or len(key) > MAX_IDEMPOTENCY_KEY:
        raise ValueError(f"idempotency_key must contain 1 to {MAX_IDEMPOTENCY_KEY} characters")
    if json_size(args) > MAX_ARGS_BYTES:
        raise ValueError("Command arguments exceed the size limit")
    if action in VISUAL_ACTIONS:
        if action == "visual.zoom_to":
            raise ValueError("Coordinate zoom is disabled until exact view restoration is implemented")
        if not VISUAL_COMMANDS_ENABLED:
            raise ValueError("Visual capture is not enabled")
        try:
            validate_visual_command(action, args)
        except Exception as exc:
            detail = getattr(exc, "detail", str(exc))
            if isinstance(detail, dict):
                detail = detail.get("message", str(detail))
            raise ValueError(str(detail)) from exc
    return key


def _request_identity(ctx: Context) -> tuple[dict[str, Any], Any]:
    request = getattr(ctx.request_context, "request", None)
    scope = getattr(request, "scope", {})
    state = scope.get("state", {}) if isinstance(scope, dict) else {}
    identity = state.get("godot_mcp_identity")
    pool = state.get("godot_mcp_pool")
    if not isinstance(identity, dict) or pool is None:
        raise PermissionError("Authenticated Godot agent_controller identity is required")
    if identity.get("device_kind") != "agent_controller":
        raise PermissionError("Only an agent_controller may use Godot MCP tools")
    return identity, pool


class PairedAgentAuthMiddleware:
    """Validate the existing paired-device Bearer credential on every MCP HTTP request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        authorization = headers.get("authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token or len(token) > 512:
            await JSONResponse(
                {"error": "unauthorized", "message": "Paired agent_controller Bearer credential required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
            )(scope, receive, send)
            return

        pool = _database_pool
        if pool is None:
            await JSONResponse(
                {"error": "unavailable", "message": "Neon Command Center database is not ready"},
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )(scope, receive, send)
            return

        try:
            row = await pool.fetchrow(
                """SELECT id, workspace_id, device_kind, label
                   FROM command_center.devices
                   WHERE token_hash=$1 AND revoked_at IS NULL""",
                digest_secret(token),
            )
        except Exception as exc:
            logger.warning("MCP device authentication lookup failed: %s", type(exc).__name__)
            await JSONResponse(
                {"error": "unavailable", "message": "Device authentication is temporarily unavailable"},
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )(scope, receive, send)
            return

        if row is None:
            await JSONResponse(
                {"error": "unauthorized", "message": "Device credential is invalid or revoked"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
            )(scope, receive, send)
            return
        if row["device_kind"] != "agent_controller":
            await JSONResponse(
                {"error": "forbidden", "message": "MCP access is restricted to agent_controller devices"},
                status_code=403,
                headers={"Cache-Control": "no-store"},
            )(scope, receive, send)
            return

        try:
            await pool.execute(
                """UPDATE command_center.devices SET last_seen_at=now()
                   WHERE id=$1 AND (last_seen_at IS NULL OR last_seen_at < now() - interval '30 seconds')""",
                row["id"],
            )
        except Exception as exc:
            logger.warning("MCP last-seen update failed: %s", type(exc).__name__)

        state = dict(scope.get("state") or {})
        state["godot_mcp_identity"] = {
            "id": str(row["id"]),
            "workspace_id": str(row["workspace_id"]),
            "device_kind": row["device_kind"],
            "label": row["label"],
        }
        state["godot_mcp_pool"] = pool
        scope = dict(scope)
        scope["state"] = state
        await self.app(scope, receive, send)


mcp_server = MCPServer("Godot Command Center")


@mcp_server.tool()
async def godot_workspace_status(ctx: Context) -> dict[str, Any]:
    """Show paired Godot devices and recent connectivity in the agent workspace."""
    identity, pool = _request_identity(ctx)
    rows = await pool.fetch(
        """SELECT device_kind, label, last_seen_at
           FROM command_center.devices
           WHERE workspace_id=$1 AND revoked_at IS NULL
           ORDER BY device_kind, label""",
        identity["workspace_id"],
    )
    devices = []
    for row in rows:
        last_seen = row["last_seen_at"]
        devices.append({
            "device_kind": row["device_kind"],
            "label": row["label"],
            "last_seen_at": last_seen.isoformat() if last_seen else None,
        })
    return {"workspace_id": identity["workspace_id"], "devices": devices}


@mcp_server.tool()
async def godot_enqueue_command(
    action: str,
    args: dict[str, Any],
    idempotency_key: str,
    ctx: Context,
) -> dict[str, Any]:
    """Queue one allowlisted read-only or supported viewport-capture command for the isolated Godot Web editor.

    Supported actions: ping, project.get_state, project.list_files, scene.inspect,
    script.read, visual.capture, visual.capture_sequence. The editor executes commands
    sequentially from the durable Neon queue. This tool never writes project files.
    """
    identity, pool = _request_identity(ctx)
    key = validate_agent_command(action, args, idempotency_key)
    target = "web_editor"

    async with pool.acquire() as connection:
        async with connection.transaction():
            command_id = await connection.fetchval(
                """INSERT INTO command_center.commands
                   (workspace_id, origin_device_id, target, action, args, idempotency_key, expires_at)
                   VALUES ($1,$2,$3,$4,$5::jsonb,$6,now() + ($7::text || ' seconds')::interval)
                   ON CONFLICT (workspace_id,idempotency_key) DO NOTHING
                   RETURNING id""",
                identity["workspace_id"],
                identity["id"],
                target,
                action,
                json.dumps(args),
                key,
                COMMAND_TTL_SECONDS,
            )
            if command_id is None:
                existing = await connection.fetchrow(
                    """SELECT id,target,action,args,status FROM command_center.commands
                       WHERE workspace_id=$1 AND idempotency_key=$2""",
                    identity["workspace_id"],
                    key,
                )
                if existing is None:
                    raise ValueError("Idempotency key collision; retry with a new key")
                if (
                    existing["target"] != target
                    or existing["action"] != action
                    or decode_json(existing["args"]) != args
                ):
                    raise ValueError("Idempotency key was already used for a different command")
                return {
                    "command_id": str(existing["id"]),
                    "target": existing["target"],
                    "action": existing["action"],
                    "status": existing["status"],
                    "reused": True,
                }

            if action == "visual.capture_sequence":
                await connection.execute(
                    """INSERT INTO command_center.visual_sequences
                       (workspace_id, command_id, source, requested_frames, interval_ms, status)
                       VALUES ($1,$2,$3,$4,$5,'pending')
                       ON CONFLICT (command_id) DO NOTHING""",
                    identity["workspace_id"],
                    command_id,
                    args["target"],
                    args["frames"],
                    args["interval_ms"],
                )
            await connection.execute(
                """INSERT INTO command_center.events
                   (workspace_id, actor_device_id, event_type, payload)
                   VALUES ($1,$2,'command.queued',$3::jsonb)""",
                identity["workspace_id"],
                identity["id"],
                json.dumps({"command_id": str(command_id), "target": target, "action": action}),
            )

    return {
        "command_id": str(command_id),
        "target": target,
        "action": action,
        "status": "queued",
        "reused": False,
        "expires_in_seconds": COMMAND_TTL_SECONDS,
    }


@mcp_server.tool()
async def godot_command_status(command_id: str, ctx: Context) -> dict[str, Any]:
    """Read the status and result of one command belonging to the authenticated workspace."""
    identity, pool = _request_identity(ctx)
    try:
        parsed_id = uuid.UUID(command_id)
    except (ValueError, TypeError) as exc:
        raise ValueError("command_id must be a UUID") from exc
    row = await pool.fetchrow(
        """SELECT c.id, c.target, c.action, c.status, c.created_at, c.claimed_at,
                  c.finished_at, c.expires_at, c.attempt_count, c.error_code, c.error_message,
                  r.ok, r.result, r.duration_ms
           FROM command_center.commands c
           LEFT JOIN command_center.command_results r ON r.command_id=c.id
           WHERE c.id=$1 AND c.workspace_id=$2""",
        parsed_id,
        identity["workspace_id"],
    )
    if row is None:
        raise ValueError("Command not found in the authenticated workspace")
    return {
        "command_id": str(row["id"]),
        "target": row["target"],
        "action": row["action"],
        "status": row["status"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "claimed_at": row["claimed_at"].isoformat() if row["claimed_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        "attempt_count": row["attempt_count"],
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "ok": row["ok"],
        "result": decode_json(row["result"]) if row["result"] is not None else None,
        "duration_ms": row["duration_ms"],
    }


@mcp_server.tool()
async def godot_list_recent_commands(limit: int, ctx: Context) -> dict[str, Any]:
    """List recent command summaries from the authenticated workspace (limit 1–50)."""
    identity, pool = _request_identity(ctx)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("limit must be an integer from 1 to 50")
    rows = await pool.fetch(
        """SELECT c.id, c.target, c.action, c.status, c.created_at, c.finished_at,
                  c.error_code, r.ok
           FROM command_center.commands c
           LEFT JOIN command_center.command_results r ON r.command_id=c.id
           WHERE c.workspace_id=$1
           ORDER BY c.created_at DESC LIMIT $2""",
        identity["workspace_id"],
        limit,
    )
    return {
        "commands": [
            {
                "command_id": str(row["id"]),
                "target": row["target"],
                "action": row["action"],
                "status": row["status"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
                "error_code": row["error_code"],
                "ok": row["ok"],
            }
            for row in rows
        ]
    }


_mcp_transport = mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    max_request_body_size=1024 * 1024,
    transport_security=TransportSecuritySettings(
        allowed_hosts=["godot-web-ia-relay.onrender.com", "godot-web-ia-relay.onrender.com:*"]
    ),
)
mcp_asgi_app = PairedAgentAuthMiddleware(_mcp_transport)
