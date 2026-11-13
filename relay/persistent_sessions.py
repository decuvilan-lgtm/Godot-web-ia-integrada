from __future__ import annotations

import asyncio
import hmac
import hashlib
import io
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import time
import threading
import zipfile
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from visual_storage import BUCKET, storage_client
from project_profiles import MANIFEST_PATH, execute_profile_command, load_project_profile, resolve_repository_commit_sha

logger = logging.getLogger("godot_web_ia_persistent_sessions")
router = APIRouter(prefix="/v1/persistent-sessions", tags=["persistent-sessions"])

EDITOR_URL = os.environ.get(
    "GODOT_WEB_EDITOR_URL",
    "https://godot-web-ia-integrada-rt2l.onrender.com/",
).rstrip("/") + "/"
SESSION_TOKEN = os.environ.get("PERSISTENT_SESSION_TOKEN", "")
OIDC_AUDIENCE = os.environ.get("PERSISTENT_SESSION_OIDC_AUDIENCE", "godot-web-ia-relay")
OIDC_REPOSITORY = os.environ.get("PERSISTENT_SESSION_OIDC_REPOSITORY", "decuvilan-lgtm/Godot-web-ia-integrada")
OIDC_WORKFLOW = os.environ.get("PERSISTENT_SESSION_OIDC_WORKFLOW", ".github/workflows/persistent-session-smoke.yml")
OIDC_REF = os.environ.get("PERSISTENT_SESSION_OIDC_REF", "refs/heads/main")
_oidc_jwks_client = None
_oidc_jwks_lock = threading.Lock()
IDLE_TTL = max(900, int(os.environ.get("PERSISTENT_SESSION_IDLE_TTL_SECONDS", "900")))
MAX_SESSIONS = max(1, int(os.environ.get("PERSISTENT_SESSION_MAX_COUNT", "2")))
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_SESSION_ARTIFACT_BYTES = 24 * 1024 * 1024
REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,128}$")

@dataclass
class PersistentSession:
    session_id: str
    repository: str
    branch: str
    project_path: str
    commit_sha: str | None = None
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
    commit_sha: str | None = Field(default=None, min_length=40, max_length=64)
    reuse_existing: bool = True
    reimport_existing: bool = False

class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=32)
    text: str | None = Field(default=None, max_length=160)
    key: str | None = Field(default=None, max_length=32)
    timeout_ms: int = Field(default=10000, ge=100, le=30000)

class CompleteTaskRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=100)
    summary: str = Field(default="", max_length=4000)
    result: dict[str, Any] = Field(default_factory=dict)

def _validate_github_oidc_claims(claims: dict[str, Any]) -> None:
    expected_workflow_ref = f"{OIDC_REPOSITORY}/{OIDC_WORKFLOW}@{OIDC_REF}"
    if (
        claims.get("repository") != OIDC_REPOSITORY
        or claims.get("ref") != OIDC_REF
        or claims.get("workflow_ref") != expected_workflow_ref
    ):
        raise ValueError("GitHub Actions identity is not allowed for persistent sessions")


def _verify_github_oidc_token(token: str) -> None:
    try:
        import jwt
    except ImportError:
        raise
    global _oidc_jwks_client
    if _oidc_jwks_client is None:
        with _oidc_jwks_lock:
            if _oidc_jwks_client is None:
                _oidc_jwks_client = jwt.PyJWKClient(
                    "https://token.actions.githubusercontent.com/.well-known/jwks",
                    cache_keys=True,
                )
    signing_key = _oidc_jwks_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=OIDC_AUDIENCE,
        issuer="https://token.actions.githubusercontent.com",
        options={"require": ["exp", "iat", "nbf", "sub"]},
    )
    _validate_github_oidc_claims(claims)


async def _authorize(value: str | None) -> None:
    if not value:
        raise HTTPException(status_code=401, detail="Authorization is required")
    supplied = value.removeprefix("Bearer ").strip()
    if len(supplied) > 16000:
        raise HTTPException(status_code=401, detail="Invalid authorization token")
    if SESSION_TOKEN and hmac.compare_digest(supplied, SESSION_TOKEN):
        return
    try:
        await run_in_threadpool(_verify_github_oidc_token, supplied)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Persistent-session authentication is not configured") from exc
    except Exception as exc:
        logger.info("Rejected persistent-session identity: %s", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid persistent-session identity") from exc

def _store_session_artifact(session: PersistentSession, name: str, data: bytes) -> None:
    current_size = sum(len(item) for item in session.artifacts.values())
    if len(data) > MAX_SESSION_ARTIFACT_BYTES or current_size + len(data) > MAX_SESSION_ARTIFACT_BYTES:
        raise HTTPException(status_code=413, detail="Session screenshot artifacts exceed the 24 MiB limit")
    session.artifacts[name] = data


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

@router.get("")
async def list_persistent_sessions(authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    return {
        "sessions": [
            {
                "session_id": session.session_id,
                "repository": session.repository,
                "branch": session.branch,
                "project_path": session.project_path,
                "commit_sha": session.commit_sha,
                "created_at": session.created_at,
                "last_activity_at": session.last_activity,
                "state": "open" if session.page is not None and not session.page.is_closed() else "disconnected",
            }
            for session in _sessions.values()
        ]
    }


@router.post("")
def _editor_url_for(repository: str, branch: str, project_path: str, commit_sha: str | None) -> str:
    query = f"?repo={quote(repository, safe='/')}&branch={quote(branch, safe='')}"
    if project_path:
        query += f"&path={quote(project_path, safe='/')}"
    if commit_sha:
        query += f"&sha={quote(commit_sha, safe='')}"
    return EDITOR_URL + query


async def open_persistent_session(body: OpenSessionRequest, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
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
    if body.commit_sha and not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", body.commit_sha):
        raise HTTPException(status_code=400, detail="commit_sha must be a full 40- or 64-character hexadecimal Git object ID")
    effective_sha = body.commit_sha or await resolve_repository_commit_sha(body.repository, body.branch)
    for existing in list(_sessions.values()):
        if existing.page is None or existing.page.is_closed():
            await _close_session(existing)
            continue
        same_project = (
            existing.repository == body.repository
            and existing.branch == body.branch
            and existing.project_path == body.project_path
            and existing.commit_sha == effective_sha
        )
        if body.reuse_existing and same_project:
            _touch(existing)
            existing.events.append({"type": "session.reused", "at": time.time(), "task_repository": body.repository})
            return {
                "session_id": existing.session_id,
                "state": "open",
                "editor_url": EDITOR_URL,
                "repository": existing.repository,
                "branch": existing.branch,
                "project_path": existing.project_path,
                "commit_sha": existing.commit_sha,
                "idle_ttl_seconds": IDLE_TTL,
                "reused": True,
                "reimported": False,
                "reused_for_follow_up_tasks": True,
                "note": "The existing browser and editor page were reused; the session remains open.",
            }
        if body.reuse_existing and body.reimport_existing and existing.repository == body.repository:
            previous = {
                "branch": existing.branch,
                "project_path": existing.project_path,
                "commit_sha": existing.commit_sha,
            }
            try:
                await existing.page.goto(
                    _editor_url_for(body.repository, body.branch, body.project_path, effective_sha),
                    wait_until="domcontentloaded",
                    timeout=90000,
                )
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Could not re-import project into the existing browser: {type(exc).__name__}") from exc
            existing.branch = body.branch
            existing.project_path = body.project_path
            existing.commit_sha = effective_sha
            existing.artifacts.clear()
            existing.events.append({
                "type": "session.reimported",
                "at": time.time(),
                "previous": previous,
                "repository": body.repository,
                "branch": body.branch,
                "project_path": body.project_path,
                "commit_sha": effective_sha,
            })
            _touch(existing)
            return {
                "session_id": existing.session_id,
                "state": "open",
                "editor_url": EDITOR_URL,
                "repository": existing.repository,
                "branch": existing.branch,
                "project_path": existing.project_path,
                "commit_sha": existing.commit_sha,
                "idle_ttl_seconds": IDLE_TTL,
                "reused": True,
                "reimported": True,
                "reused_for_follow_up_tasks": True,
                "note": "The same browser context was kept open and the selected project revision was re-imported.",
            }
        raise HTTPException(
            status_code=409,
            detail="An active persistent session already exists for a different project or revision. Reuse that project or close the session first.",
        )
    if len(_sessions) >= MAX_SESSIONS:
        raise HTTPException(status_code=429, detail="Persistent session capacity reached")
    browser = await _get_browser()
    session_id = secrets.token_urlsafe(18)
    session = PersistentSession(
        session_id=session_id,
        repository=body.repository,
        branch=body.branch,
        project_path=body.project_path,
        commit_sha=effective_sha,
    )
    try:
        session.context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )
        session.page = await session.context.new_page()
        await session.page.goto(_editor_url_for(body.repository, body.branch, body.project_path, effective_sha), wait_until="domcontentloaded", timeout=90000)
        session.events.append({
            "type": "session.opened",
            "at": time.time(),
            "editor_url": EDITOR_URL,
            "repository": body.repository,
            "branch": body.branch,
            "project_path": body.project_path,
            "commit_sha": effective_sha,
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
        "commit_sha": effective_sha,
        "idle_ttl_seconds": IDLE_TTL,
        "reused": False,
        "reused_for_follow_up_tasks": True,
        "note": "Completing a task does not close this browser session.",
    }

@router.get("/{session_id}")
async def persistent_session_status(session_id: str, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    session = _get_session(session_id)
    _touch(session)
    return {
        "session_id": session_id,
        "state": "open" if session.page and not session.page.is_closed() else "disconnected",
        "repository": session.repository,
        "branch": session.branch,
        "project_path": session.project_path,
        "commit_sha": session.commit_sha,
        "last_activity_at": session.last_activity,
        "idle_ttl_seconds": IDLE_TTL,
        "completed_tasks": list(session.completed_tasks.values()),
        "artifact_count": len(session.artifacts),
    }

@router.post("/{session_id}/heartbeat")
async def persistent_session_heartbeat(session_id: str, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    session = _get_session(session_id)
    _touch(session)
    return {"ok": True, "session_id": session_id, "idle_ttl_seconds": IDLE_TTL}

def _assert_profile_matches_session(profile: dict[str, Any], session: PersistentSession) -> None:
    declared_path = profile["manifest"].get("project", {}).get("project_path")
    if declared_path is not None and declared_path != session.project_path:
        raise HTTPException(
            status_code=409,
            detail="Project-owned lab manifest targets a different project_path than the imported project",
        )


@router.get("/{session_id}/profile")
async def get_project_lab_profile(session_id: str, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    session = _get_session(session_id)
    profile = await load_project_profile(session.repository, session.commit_sha or session.branch)
    if profile is None:
        return {
            "available": False,
            "profile_status": "not_found",
            "manifest_path": MANIFEST_PATH,
            "repository": session.repository,
            "ref": session.commit_sha or session.branch,
            "note": "This repository revision has no project-owned Godot lab manifest. No global game-specific commands were substituted.",
        }
    _assert_profile_matches_session(profile, session)
    return {
        "available": True,
        "profile_status": profile["control_profile"]["verification"]["status"],
        "manifest_path": MANIFEST_PATH,
        "repository": session.repository,
        "ref": session.commit_sha or session.branch,
        "project": profile["manifest"]["project"],
        "control_profile": profile["manifest"]["control_profile"],
        "commands": profile["manifest"]["commands"],
        "controls": profile["control_profile"]["controls"],
    }


@router.post("/{session_id}/profiles/{command_name}/run")
async def run_project_lab_command(
    session_id: str,
    command_name: str,
    authorization: str | None = Header(default=None),
):
    await _authorize(authorization)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", command_name):
        raise HTTPException(status_code=400, detail="Invalid project-owned command name")
    session = _get_session(session_id)
    if session.page is None or session.page.is_closed():
        raise HTTPException(status_code=409, detail="Editor page is disconnected")
    profile = await load_project_profile(session.repository, session.commit_sha or session.branch, command_name=command_name)
    if profile is None:
        raise HTTPException(status_code=404, detail="This repository revision has no project-owned lab manifest")
    _assert_profile_matches_session(profile, session)
    if profile["control_profile"]["verification"]["status"] != "verified":
        raise HTTPException(status_code=409, detail="Project control profile has not been verified against this exact commit SHA")
    command_profile = profile["commands"].get(command_name)
    if command_profile is None or command_profile["verification"]["status"] != "verified":
        raise HTTPException(status_code=409, detail="Project command has not been verified against this exact commit SHA")
    async with session.lock:
        try:
            results = await asyncio.wait_for(
                execute_profile_command(session.page, profile, command_name, session.artifacts),
                timeout=120,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=504, detail="Project-owned command exceeded the 120-second execution limit") from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Project-owned lab command failed")
            raise HTTPException(status_code=502, detail=f"Project-owned command failed: {type(exc).__name__}") from exc
        session.events.append({
            "type": "project-profile.command.completed",
            "command": command_name,
            "at": time.time(),
            "step_count": len(results),
        })
        session.events = session.events[-1000:]
        _touch(session)
    return {
        "ok": True,
        "session_id": session_id,
        "repository": session.repository,
        "commit_sha": session.commit_sha,
        "command": command_name,
        "results": results,
        "session_kept_open": True,
    }


@router.post("/{session_id}/commands")
async def persistent_session_command(session_id: str, body: CommandRequest, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    session = _get_session(session_id)
    if session.page is None or session.page.is_closed():
        raise HTTPException(status_code=409, detail="Editor page is disconnected")
    async with session.lock:
        try:
            if body.command == "screenshot":
                image = await session.page.screenshot(full_page=False, timeout=body.timeout_ms)
                name = f"screenshot-{int(time.time() * 1000)}.png"
                _store_session_artifact(session, name, image)
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
                    "canvas_count": await session.page.locator("canvas").count(),
                    "connector_status": await session.page.evaluate("() => window.__godotGithubConnectorStatus || null"),
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
    await _authorize(authorization)
    session = _get_session(session_id)
    async with session.lock:
        if body.task_id in session.completed_tasks:
            return {**session.completed_tasks[body.task_id], "session_kept_open": True}
        if session.page is None or session.page.is_closed():
            raise HTTPException(status_code=409, detail="Editor page is disconnected")
        try:
            screenshot = await session.page.screenshot(full_page=False, timeout=20000)
            screenshot_name = f"task-{body.task_id[:40]}-final.png"
            _store_session_artifact(session, screenshot_name, screenshot)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Could not capture final editor state: {type(exc).__name__}") from exc
        manifest = {
            "task_id": body.task_id,
            "completed_at": time.time(),
            "repository": session.repository,
            "branch": session.branch,
            "project_path": session.project_path,
            "commit_sha": session.commit_sha,
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
        object_key = _persistent_artifact_key(session.session_id, artifact_id)
        try:
            client = storage_client()
            await run_in_threadpool(
                client.put_object,
                Bucket=BUCKET,
                Key=object_key,
                Body=payload,
                ContentType="application/zip",
                Metadata={
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "task-id-sha256": hashlib.sha256(body.task_id.encode("utf-8")).hexdigest(),
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Could not persist completed task bundle in Neon Object Storage")
            raise HTTPException(status_code=503, detail="Task bundle could not be persisted in Neon Object Storage") from exc
        artifact_sha256 = hashlib.sha256(payload).hexdigest()
        result = {
            "task_id": body.task_id,
            "state": "completed",
            "artifact_id": artifact_id,
            "artifact_url": f"/v1/persistent-sessions/{session_id}/artifacts/{artifact_id}",
            "artifact_bytes": len(payload),
            "artifact_sha256": artifact_sha256,
            "session_kept_open": True,
            "session_id": session.session_id,
            "storage": "neon-object-storage",
            "object_key": object_key,
        }
        session.completed_tasks[body.task_id] = result
        session.artifacts.clear()
        session.events.append({"type": "task.completed", "task_id": body.task_id, "artifact_id": artifact_id, "at": time.time()})
        _touch(session)
        return result

def _persistent_artifact_key(session_id: str, artifact_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", artifact_id):
        raise HTTPException(status_code=400, detail="Invalid artifact ID")
    return f"persistent-sessions/{session_id}/{artifact_id}.zip"


@router.get("/{session_id}/artifacts/{artifact_id}")
async def download_persistent_artifact(session_id: str, artifact_id: str, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    key = _persistent_artifact_key(session_id, artifact_id)
    session = _sessions.get(session_id)
    try:
        client = storage_client()
        response = await run_in_threadpool(client.get_object, Bucket=BUCKET, Key=key)
        content_length = int(response.get("ContentLength", 0))
        if content_length < 1 or content_length > MAX_ARTIFACT_BYTES:
            raise HTTPException(status_code=404, detail="Artifact not found")
        body = response["Body"]
        try:
            payload = await run_in_threadpool(body.read, MAX_ARTIFACT_BYTES + 1)
        finally:
            await run_in_threadpool(body.close)
        if not payload or len(payload) > MAX_ARTIFACT_BYTES or len(payload) != content_length:
            raise HTTPException(status_code=404, detail="Artifact not found")
        expected_digest = str((response.get("Metadata") or {}).get("sha256", ""))
        if expected_digest and not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), expected_digest):
            raise HTTPException(status_code=502, detail="Persistent artifact integrity check failed")
    except HTTPException:
        raise
    except Exception as exc:
        logger.info("Persistent artifact unavailable for %s/%s: %s", session_id, artifact_id, type(exc).__name__)
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    if session is not None:
        _touch(session)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="godot-task-{artifact_id}.zip"'},
    )

@router.delete("/{session_id}")
async def close_persistent_session(session_id: str, authorization: str | None = Header(default=None)):
    await _authorize(authorization)
    session = _get_session(session_id)
    await _close_session(session)
    return {"ok": True, "closed": True, "session_id": session_id}
