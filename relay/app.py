from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from command_center import router as command_center_router
from admin import router as command_center_admin_router
from visual_storage import router as visual_storage_router
from visual_proxy import router as visual_proxy_router
from project_sync import router as project_sync_router

APP_VERSION = "0.2.1"
logger = logging.getLogger("godot_web_ia_relay")
ADMIN_TOKEN = os.environ.get("RELAY_ADMIN_TOKEN", "")
SESSION_TTL = int(os.environ.get("SESSION_TTL_SECONDS", "1800"))
MAX_PENDING = 64
MAX_MESSAGE_BYTES = 256 * 1024
ALLOWED_ACTIONS = {"ping", "project.get_state", "project.list_files", "scene.inspect", "script.read"}

app = FastAPI(title="Godot Web IA Relay", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "https://godot-web-ia-integrada-rt2l.onrender.com").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Token", "X-Command-Center-Admin", "X-Command-Id", "X-Frame-Index", "X-Project-Path", "X-Base-SHA256", "X-File-SHA256"],
    expose_headers=["X-File-SHA256"],
)

@dataclass
class Session:
    session_id: str
    editor_token: str
    controller_token: str
    created_at: float = field(default_factory=time.time)
    editor: WebSocket | None = None
    pending: dict[str, asyncio.Future] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

sessions: dict[str, Session] = {}
app.state.command_center_db = None
app.state.session_cleanup_task = None

app.include_router(command_center_router)
app.include_router(command_center_admin_router)
app.include_router(visual_storage_router)
app.include_router(visual_proxy_router)
app.include_router(project_sync_router)

@app.middleware("http")
async def prevent_command_center_response_caching(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/v1/command-center/", "/command-center/admin")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response

class CreateSession(BaseModel):
    label: str = Field(default="Godot project", max_length=80)

class RelayRequest(BaseModel):
    action: str = Field(min_length=1, max_length=80)
    args: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=20, ge=1, le=60)

def require_admin(value: str | None) -> None:
    if not ADMIN_TOKEN or not value or not hmac.compare_digest(value, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid admin token")

def get_session(session_id: str) -> Session:
    session = sessions.get(session_id)
    if session is None or time.time() - session.created_at > SESSION_TTL:
        sessions.pop(session_id, None)
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session

@app.get("/health")
async def health():
    return {"ok": True, "service": "godot-web-ia-relay", "version": APP_VERSION, "command_center_ready": app.state.command_center_db is not None}

@app.post("/v1/sessions")
async def create_session(body: CreateSession, x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    session_id = secrets.token_urlsafe(18)
    session = Session(
        session_id=session_id,
        editor_token=secrets.token_urlsafe(32),
        controller_token=secrets.token_urlsafe(32),
    )
    sessions[session_id] = session
    return {
        "session_id": session_id,
        "editor_token": session.editor_token,
        "controller_token": session.controller_token,
        "websocket_url": f"/v1/editor/{session_id}",
        "expires_in": SESSION_TTL,
        "label": body.label,
    }

@app.get("/v1/sessions/{session_id}")
async def session_status(session_id: str, authorization: str | None = Header(default=None)):
    session = get_session(session_id)
    if not authorization or not hmac.compare_digest(authorization.removeprefix("Bearer "), session.controller_token):
        raise HTTPException(status_code=401, detail="Invalid controller token")
    return {
        "session_id": session_id,
        "editor_connected": session.editor is not None,
        "pending_requests": len(session.pending),
        "expires_in": max(0, int(SESSION_TTL - (time.time() - session.created_at))),
    }

@app.post("/v1/sessions/{session_id}/request")
async def controller_request(session_id: str, body: RelayRequest, authorization: str | None = Header(default=None)):
    session = get_session(session_id)
    if not authorization or not hmac.compare_digest(authorization.removeprefix("Bearer "), session.controller_token):
        raise HTTPException(status_code=401, detail="Invalid controller token")
    if body.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail="Action is not allowed by bridge protocol v1")
    if len(json.dumps(body.args, ensure_ascii=False).encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise HTTPException(status_code=413, detail="Request arguments exceed the message limit")
    if session.editor is None:
        raise HTTPException(status_code=409, detail="Godot editor is not connected")
    if len(session.pending) >= MAX_PENDING:
        raise HTTPException(status_code=429, detail="Too many pending requests")

    request_id = secrets.token_urlsafe(12)
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    session.pending[request_id] = future
    packet = {"type": "request", "id": request_id, "action": body.action, "args": body.args}
    try:
        await session.editor.send_json(packet)
        return await asyncio.wait_for(future, timeout=body.timeout_seconds)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Editor request timed out")
    except WebSocketDisconnect:
        raise HTTPException(status_code=503, detail="Editor disconnected")
    finally:
        session.pending.pop(request_id, None)

@app.websocket("/v1/editor/{session_id}")
async def editor_socket(websocket: WebSocket, session_id: str):
    session = sessions.get(session_id)
    if session is None or time.time() - session.created_at > SESSION_TTL:
        await websocket.close(code=4404, reason="Session expired")
        return
    await websocket.accept()
    if session.editor is not None:
        await websocket.close(code=4409, reason="Editor already connected")
        return
    session.editor = websocket
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        supplied = str(auth.get("token", "")) if isinstance(auth, dict) else ""
        valid = (
            isinstance(auth, dict)
            and auth.get("type") == "auth"
            and auth.get("protocol") == 1
            and hmac.compare_digest(supplied, session.editor_token)
        )
        if not valid:
            await websocket.send_json({"type": "auth_error"})
            await websocket.close(code=4401, reason="Authentication failed")
            return
        await websocket.send_json({"type": "auth_ok"})
        while True:
            raw_message = await websocket.receive_text()
            if len(raw_message.encode("utf-8")) > MAX_MESSAGE_BYTES:
                await websocket.close(code=1009, reason="Message too large")
                break
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict) or message.get("type") != "response":
                continue
            request_id = str(message.get("id", ""))
            future = session.pending.get(request_id)
            if future is not None and not future.done():
                future.set_result({
                    "ok": bool(message.get("ok", False)),
                    "data": message.get("data", {}),
                    "error": str(message.get("error", ""))[:1000],
                })
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        if session.editor is websocket:
            session.editor = None

@app.on_event("startup")
async def cleanup_expired_sessions():
    database_url = os.environ.get("COMMAND_CENTER_DATABASE_URL", "").strip()
    app.state.command_center_db = None
    app.state.command_center_db_lock = asyncio.Lock()
    app.state.command_center_db_retry_after = 0.0
    if database_url:
        try:
            import asyncpg
            app.state.command_center_db = await asyncpg.create_pool(
                dsn=database_url, min_size=1, max_size=5, timeout=5, command_timeout=10
            )
        except Exception:
            # A Neon outage or missing driver must not take down the existing
            # WebSocket relay. Command Center routes remain fail-closed (503).
            app.state.command_center_db_retry_after = time.monotonic() + 5.0
            logger.exception("Command Center database pool could not be initialized")

    async def cleanup_loop():
        while True:
            now = time.time()
            for key, session in list(sessions.items()):
                if now - session.created_at > SESSION_TTL:
                    if session.editor is not None:
                        try:
                            await session.editor.close(code=4408, reason="Session expired")
                        except Exception:
                            pass
                    for future in session.pending.values():
                        if not future.done():
                            future.set_exception(RuntimeError("Session expired"))
                    sessions.pop(key, None)
            await asyncio.sleep(30)
    app.state.session_cleanup_task = asyncio.create_task(cleanup_loop())


@app.on_event("shutdown")
async def shutdown_services():
    task = app.state.session_cleanup_task
    if task is not None:
        task.cancel()
    pool = app.state.command_center_db
    if pool is not None:
        await pool.close()
