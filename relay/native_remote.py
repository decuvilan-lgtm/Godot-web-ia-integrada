from __future__ import annotations

import asyncio
import hmac
import os
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/native-remote", tags=["native-remote"])
CONTROL_TOKEN = os.environ.get("NATIVE_REMOTE_CONTROL_TOKEN", "")
SESSION_TTL_SECONDS = max(60, min(86400, int(os.environ.get("NATIVE_REMOTE_SESSION_TTL_SECONDS", "1800"))))
MAX_QUEUE = 32
MAX_RESULT_BYTES = 256 * 1024
ALLOWED_COMMANDS = frozenset({
    "editor.list_capabilities", "editor.get_state", "scene.get_tree",
    "scene.inspect_selection", "scene.add_node", "scene.set_node_properties",
    "scene.configure_collision_shape", "scene.assign_visual_resource",
    "scene.create_sprite_frames", "editor.open_scene", "editor.focus_inspector",
    "editor.inspect_undo_history", "editor.undo", "editor.redo",
    "editor.inspect_project_settings", "editor.inspect_editor_settings",
    "project.list_resources", "project.inspect_resource", "preview.get_status",
    "preview.start", "preview.stop", "capture.editor_screenshot",
    "capture.desktop_screenshot", "capture.start_editor_video",
    "capture.stop_editor_video", "capture.get_video_status", "capture.read_chunk",
})


@dataclass
class NativeSession:
    session_id: str
    agent_token: str
    project_id: str
    project_path: str
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    commands: deque = field(default_factory=deque)
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


sessions: dict[str, NativeSession] = {}


class EnrollRequest(BaseModel):
    project_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    project_path: str = Field(min_length=1, max_length=1024)


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=80)
    args: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=20, ge=1, le=60)


class ResultRequest(BaseModel):
    command_id: str = Field(min_length=16, max_length=64)
    ok: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error: str = Field(default="", max_length=1000)


def _require_control(value: str | None) -> None:
    if not CONTROL_TOKEN or not value:
        raise HTTPException(status_code=503, detail="Native remote control is not configured")
    supplied = value.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, CONTROL_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid native remote control token")


def _session(session_id: str) -> NativeSession:
    item = sessions.get(session_id)
    if item is None or time.time() - item.created_at > SESSION_TTL_SECONDS:
        sessions.pop(session_id, None)
        raise HTTPException(status_code=404, detail="Native editor session not found or expired")
    return item


def _require_agent(item: NativeSession, value: str | None) -> None:
    supplied = value.removeprefix("Bearer ").strip() if value else ""
    if not supplied or not hmac.compare_digest(supplied, item.agent_token):
        raise HTTPException(status_code=401, detail="Invalid native agent token")


@router.post("/sessions")
async def enroll(body: EnrollRequest, authorization: str | None = Header(default=None)):
    _require_control(authorization)
    if len(sessions) >= 8:
        raise HTTPException(status_code=429, detail="Native editor session capacity reached")
    session_id = secrets.token_urlsafe(18)
    agent_token = secrets.token_urlsafe(36)
    item = NativeSession(session_id, agent_token, body.project_id, body.project_path)
    sessions[session_id] = item
    return {"session_id": session_id, "agent_token": agent_token, "expires_in": SESSION_TTL_SECONDS}


@router.get("/sessions")
async def list_sessions(authorization: str | None = Header(default=None)):
    _require_control(authorization)
    now = time.time()
    return {"sessions": [
        {"session_id": s.session_id, "project_id": s.project_id, "project_path": s.project_path,
         "agent_connected": now - s.last_seen < 15, "queued": len(s.commands),
         "expires_in": max(0, int(SESSION_TTL_SECONDS - (now - s.created_at)))}
        for s in sessions.values() if now - s.created_at <= SESSION_TTL_SECONDS
    ]}


@router.post("/sessions/{session_id}/commands")
async def enqueue_command(session_id: str, body: CommandRequest, authorization: str | None = Header(default=None)):
    _require_control(authorization)
    item = _session(session_id)
    if body.command not in ALLOWED_COMMANDS:
        raise HTTPException(status_code=400, detail="Native editor command is not allowlisted")
    if len(str(body.args).encode("utf-8")) > 60 * 1024:
        raise HTTPException(status_code=413, detail="Command arguments exceed 60 KiB")
    async with item.lock:
        if len(item.commands) >= MAX_QUEUE:
            raise HTTPException(status_code=429, detail="Native command queue is full")
        command_id = secrets.token_urlsafe(18)
        future = asyncio.get_running_loop().create_future()
        item.results[command_id] = {"future": future, "created_at": time.time()}
        item.commands.append({"command_id": command_id, "command": body.command, "args": body.args})
    try:
        return await asyncio.wait_for(future, timeout=body.timeout_seconds)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Native editor agent did not return a result in time")
    finally:
        item.results.pop(command_id, None)


@router.get("/sessions/{session_id}/next")
async def next_command(session_id: str, authorization: str | None = Header(default=None)):
    item = _session(session_id)
    _require_agent(item, authorization)
    item.last_seen = time.time()
    if not item.commands:
        await asyncio.sleep(1)
    if not item.commands:
        return {"command": None}
    return {"command": item.commands.popleft()}


@router.post("/sessions/{session_id}/results")
async def submit_result(session_id: str, body: ResultRequest, authorization: str | None = Header(default=None)):
    item = _session(session_id)
    _require_agent(item, authorization)
    item.last_seen = time.time()
    if len(str(body.result).encode("utf-8")) > MAX_RESULT_BYTES:
        raise HTTPException(status_code=413, detail="Native command result exceeds 256 KiB")
    record = item.results.get(body.command_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Command expired or unknown")
    future = record["future"]
    if not future.done():
        future.set_result({"ok": body.ok, "command_id": body.command_id, "result": body.result, "error": body.error})
    return {"accepted": True}


@router.delete("/sessions/{session_id}")
async def close_session(session_id: str, authorization: str | None = Header(default=None)):
    _require_control(authorization)
    item = _session(session_id)
    sessions.pop(session_id, None)
    for record in item.results.values():
        future = record["future"]
        if not future.done():
            future.set_exception(RuntimeError("Native editor session was closed"))
    return {"closed": True}
