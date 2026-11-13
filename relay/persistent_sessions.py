from __future__ import annotations

import asyncio
import hmac
import io
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("godot_web_ia_persistent_sessions")
router = APIRouter(prefix="/v1/persistent-sessions", tags=["persistent-sessions"])

EDITOR_URL = os.environ.get(
    "GODOT_WEB_EDITOR_URL",
    "https://godot-web-ia-integrada-rt2l.onrender.com/",
).rstrip("/") + "/"
SESSION_TOKEN = os.environ.get("PERSISTENT_SESSION_TOKEN", "")
IDLE_TTL = max(900, int(os.environ.get("PERSISTENT_SESSION_IDLE_TTL_SECONDS", "900")))
MAX_SESSIONS = max(1, int(os.environ.get("PERSISTENT_SESSION_MAX_COUNT", "2")))
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,128}$")

@dataclass
class PersistentSession:
    session_id: str
    repository: str
    branch: str
    project_path: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    context: Any = None
    page: Any = None
    events: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, bytes] = field(default_factory=dict)
    completed_tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

_sessions: dict[str, PersistentSession] = {}
_browser: Any = None
_browser_lock = asyncio.Lock()
_reaper_task: asyncio.Task | None = None

class OpenSessionRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=140)
    branch: str = Field(default="main", min_length=1, max_length=128)
    project_path: str = Field(default="", max_length=240)

class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=32)
    text: str | None = Field(default=None, max_length=160)
    key: str | None = Field(default=None, max_length=32)
    timeout_ms: int = Field(default=10000, ge=100, le=30000)

class CompleteTaskRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=100)
    summary: str = Field(default="", max_length=4000)
    result: dict[str, Any] = Field(default_factory=dict)

def _authorize(value: str | None) -> None:
    if not SESSION_TOKEN or not value:
        raise HTTPException(status_code=503, detail="Persistent session API is not configured")
    supplied = value.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, SESSION_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid persistent-session token")

def _touch(session: PersistentSession) -> None:
    session.last_activity = time.time()

def _get_session(session_id: str) -> PersistentSession:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Persistent session not found")
    if time.time() - session.last_activity > IDLE_TTL:
        raise HTTPException(status_code=410, detail="Persistent session expired after inactivity")
    return session

async def _get_browser():
    global _browser
    async with _browser_lock:
        if _browser is None or not _browser.is_connected():
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise HTTPException(status_code=503, detail="Playwright is not installed on this relay") from exc
            if not hasattr(_get_browser, "_playwright"):
                _get_browser._playwright = await async_playwright().start()
            launch_args = {
                "headless": True,
                "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            }
            try:
                _browser = await _get_browser._playwright.chromium.launch(**launch_args)
            except Exception as first_error:
                # Render's existing service build command may not yet include the
                # browser-install step from render-relay.yaml. Install the pinned
                # Playwright Chromium on first use, then retry once.
                logger.warning("Chromium binary missing; installing Playwright Chromium on first use")
                try:
                    process = await asyncio.create_subprocess_exec(
                        sys.executable, "-m", "playwright", "install", "chromium",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                    )
                    output, _ = await asyncio.wait_for(process.communicate(), timeout=180)
                    if process.returncode != 0:
                        raise RuntimeError(output.decode("utf-8", "replace")[-3000:])
                    _browser = await _get_browser._playwright.chromium.launch(**launch_args)
                except Exception as exc:
                    logger.exception("Could not install or start persistent Chromium")
                    raise HTTPException(
                        status_code=503,
                        detail=f"Persistent browser unavailable: {type(exc).__name__}; check Render memory and system libraries",
                    ) from first_error
        return _browser

async def _close_session(session: PersistentSession) -> None:
    try:
        if session.context is not None:
            await session.context.close()
    except Exception:
        logger.exception("Could not close expired browser context")
    _sessions.pop(session.session_id, None)

async def _expire_loop() -> None:
    while True:
        now = time.time()
        for session in list(_sessions.values()):
            if now - session.last_activity > IDLE_TTL:
                await _close_session(session)
        await asyncio.sleep(30)

@router.on_event("startup")
async def start_session_reaper():
    global _reaper_task
    _reaper_task = asyncio.create_task(_expire_loop())

@router.on_event("shutdown")
async def stop_session_reaper():
    global _reaper_task
    task = _reaper_task
    _reaper_task = None
    if task:
        task.cancel()
    for session in list(_sessions.values()):
        await _close_session(session)
    global _browser
    if _browser is not None:
        await _browser.close()
        _browser = None
    playwright = getattr(_get_browser, "_playwright", None)
    if playwright is not None:
        await playwright.stop()

@router.post("")
async def open_persistent_session(body: OpenSessionRequest, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    if not REPO_RE.fullmatch(body.repository):
        raise HTTPException(status_code=400, detail="repository must be OWNER/REPOSITORY")
    if not BRANCH_RE.fullmatch(body.branch) or body.branch.startswith("/") or body.branch.endswith("/") or ".." in body.branch:
        raise HTTPException(status_code=400, detail="Invalid branch")
    if body.project_path and (
        body.project_path.startswith("/") or body.project_path.endswith("/")
        or "\\" in body.project_path
        or any(part in {"", ".", ".."} for part in body.project_path.split("/"))
    ):
        raise HTTPException(status_code=400, detail="Invalid project_path")
    if len(_sessions) >= MAX_SESSIONS:
        raise HTTPException(status_code=429, detail="Persistent session capacity reached")
    browser = await _get_browser()
    session_id = secrets.token_urlsafe(18)
    session = PersistentSession(
        session_id=session_id,
        repository=body.repository,
        branch=body.branch,
        project_path=body.project_path,
    )
    try:
        session.context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )
        session.page = await session.context.new_page()
        query = f"?repo={quote(body.repository, safe='/')}&branch={quote(body.branch, safe='')}"
        if body.project_path:
            query += f"&path={quote(body.project_path, safe='/')}"
        await session.page.goto(EDITOR_URL + query, wait_until="domcontentloaded", timeout=90000)
        session.events.append({
            "type": "session.opened",
            "at": time.time(),
            "editor_url": EDITOR_URL,
            "repository": body.repository,
            "branch": body.branch,
            "project_path": body.project_path,
        })
        _sessions[session_id] = session
    except Exception as exc:
        await _close_session(session)
        logger.exception("Persistent editor session could not be opened")
        raise HTTPException(status_code=502, detail=f"Could not open deployed Godot Web editor: {type(exc).__name__}") from exc
    return {
        "session_id": session_id,
        "state": "open",
        "editor_url": EDITOR_URL,
        "repository": body.repository,
        "branch": body.branch,
        "project_path": body.project_path,
        "idle_ttl_seconds": IDLE_TTL,
        "reused_for_follow_up_tasks": True,
        "note": "Completing a task does not close this browser session.",
    }

@router.get("/{session_id}")
async def persistent_session_status(session_id: str, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    session = _get_session(session_id)
    _touch(session)
    return {
        "session_id": session_id,
        "state": "open" if session.page and not session.page.is_closed() else "disconnected",
        "repository": session.repository,
        "branch": session.branch,
        "project_path": session.project_path,
        "last_activity_at": session.last_activity,
        "idle_ttl_seconds": IDLE_TTL,
        "completed_tasks": list(session.completed_tasks.values()),
        "artifact_count": len(session.artifacts),
    }

@router.post("/{session_id}/heartbeat")
async def persistent_session_heartbeat(session_id: str, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    session = _get_session(session_id)
    _touch(session)
    return {"ok": True, "session_id": session_id, "idle_ttl_seconds": IDLE_TTL}

@router.post("/{session_id}/commands")
async def persistent_session_command(session_id: str, body: CommandRequest, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    session = _get_session(session_id)
    if session.page is None or session.page.is_closed():
        raise HTTPException(status_code=409, detail="Editor page is disconnected")
    async with session.lock:
        try:
            if body.command == "screenshot":
                image = await session.page.screenshot(full_page=False, timeout=body.timeout_ms)
                name = f"screenshot-{int(time.time() * 1000)}.png"
                session.artifacts[name] = image
                output: dict[str, Any] = {"artifact": name, "bytes": len(image)}
            elif body.command == "click_text":
                if not body.text:
                    raise HTTPException(status_code=400, detail="text is required")
                locator = session.page.get_by_text(body.text, exact=True).first
                await locator.click(timeout=body.timeout_ms)
                output = {"clicked_text": body.text}
            elif body.command == "press_key":
                if body.key not in {"F5", "F6", "F7", "Escape", "Enter", "Tab", "Space", "Control+s", "Control+Shift+s"}:
                    raise HTTPException(status_code=400, detail="Key is not in the safe allowlist")
                await session.page.keyboard.press(body.key)
                output = {"pressed_key": body.key}
            elif body.command == "inspect":
                output = {
                    "url": session.page.url,
                    "title": await session.page.title(),
                    "visible_text": (await session.page.locator("body").inner_text(timeout=body.timeout_ms))[:12000],
                }
            else:
                raise HTTPException(status_code=400, detail="Unsupported command")
        except HTTPException:
            raise
        except Exception as exc:
            session.events.append({"type": "command.failed", "command": body.command, "error": type(exc).__name__, "at": time.time()})
            raise HTTPException(status_code=502, detail=f"Browser command failed: {type(exc).__name__}") from exc
        session.events.append({"type": "command.completed", "command": body.command, "at": time.time(), "result": output})
        _touch(session)
        return {"ok": True, "session_id": session_id, "result": output, "session_kept_open": True}

@router.post("/{session_id}/tasks/complete")
async def complete_persistent_task(session_id: str, body: CompleteTaskRequest, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    session = _get_session(session_id)
    async with session.lock:
        if body.task_id in session.completed_tasks:
            return {**session.completed_tasks[body.task_id], "session_kept_open": True}
        if session.page is None or session.page.is_closed():
            raise HTTPException(status_code=409, detail="Editor page is disconnected")
        try:
            screenshot = await session.page.screenshot(full_page=False, timeout=20000)
            screenshot_name = f"task-{body.task_id[:40]}-final.png"
            session.artifacts[screenshot_name] = screenshot
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not capture final editor state: {type(exc).__name__}") from exc
        manifest = {
            "task_id": body.task_id,
            "completed_at": time.time(),
            "repository": session.repository,
            "branch": session.branch,
            "project_path": session.project_path,
            "summary": body.summary,
            "result": body.result,
            "editor_url": EDITOR_URL,
            "session_id": session.session_id,
            "session_remains_open": True,
            "artifacts": sorted(session.artifacts),
            "events": session.events[-500:],
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("task-result.json", manifest_bytes)
            for name, data in session.artifacts.items():
                archive.writestr(f"artifacts/{name}", data)
        payload = bundle.getvalue()
        if len(payload) > MAX_ARTIFACT_BYTES:
            raise HTTPException(status_code=413, detail="Task artifact bundle exceeds 32 MiB")
        artifact_id = secrets.token_urlsafe(18)
        session.artifacts[f"bundle-{artifact_id}.zip"] = payload
        result = {
            "task_id": body.task_id,
            "state": "completed",
            "artifact_id": artifact_id,
            "artifact_url": f"/v1/persistent-sessions/{session_id}/artifacts/{artifact_id}",
            "artifact_bytes": len(payload),
            "session_kept_open": True,
            "session_id": session.session_id,
        }
        session.completed_tasks[body.task_id] = result
        session.events.append({"type": "task.completed", "task_id": body.task_id, "artifact_id": artifact_id, "at": time.time()})
        _touch(session)
        return result

@router.get("/{session_id}/artifacts/{artifact_id}")
async def download_persistent_artifact(session_id: str, artifact_id: str, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    session = _get_session(session_id)
    name = f"bundle-{artifact_id}.zip"
    payload = session.artifacts.get(name)
    if payload is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    _touch(session)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="godot-task-{artifact_id}.zip"'},
    )

@router.delete("/{session_id}")
async def close_persistent_session(session_id: str, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    session = _get_session(session_id)
    await _close_session(session)
    return {"ok": True, "closed": True, "session_id": session_id}
